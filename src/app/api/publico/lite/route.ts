import { NextResponse } from "next/server";

import type { LanzarPublicoResponse, N8nWebhookPayload } from "@/lib/shared/dto";
import { validarLanzarRun } from "@/lib/shared/validate";
import { clientIp, conCors, corsHeaders, errorResponse, preflight } from "@/server/http";
import {
  construirPayload,
  countActiveRuns,
  countPublicToday,
  createPublicRun,
  failRun,
} from "@/server/runs/repo";
import { dispararAnalisis } from "@/server/runs/trigger";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST /api/publico/lite — lanzamiento del análisis LITE desde la web pública.
 *
 * Es el MISMO patrón asíncrono que /api/runs (crear fila → disparar n8n → acuse
 * inmediato → la web sondea), pero SIN sesión y con las defensas del canal
 * abierto: rate-limit por IP, tope de gasto global, token opaco en vez de id, y
 * LITE forzado (el completo cuesta y no se ofrece gratis).
 *
 * SEGURIDAD (docs/08 — LITE público): esta ruta es la superficie pública. NO
 * debe estar viva en producción hasta cerrar el Paso 1 (auth del webhook n8n),
 * el Paso 4 (tope de gasto) y el Paso 5 (WAF/captcha) de docs/08. El rate-limit
 * de aquí es una defensa, no la única.
 */

function limiteDiario(): number {
  const n = parseInt(process.env.PUBLIC_DAILY_LIMIT ?? "3", 10);
  return Number.isFinite(n) && n > 0 ? n : 3;
}

function maxConcurrentes(): number {
  const n = parseInt(process.env.MAX_CONCURRENT_RUNS ?? "2", 10);
  return Number.isFinite(n) && n > 0 ? n : 2;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

export function OPTIONS(req: Request) {
  return preflight(req);
}

export async function POST(req: Request) {
  const cors = corsHeaders(req);
  const json = (body: unknown, status = 200) =>
    NextResponse.json(body, { status, headers: cors });

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return json({ error: "json_invalido" }, 400);
  }
  const raw = body && typeof body === "object" ? (body as Record<string, unknown>) : {};

  // El canal público SOLO lanza LITE. Se ignora cualquier `tipo` del cliente.
  const val = validarLanzarRun({ ...raw, tipo: "lite" });
  if (!val.ok) {
    return json({ error: "validacion", errores: val.errores }, 400);
  }

  // Email: obligatorio en el canal público (es a donde va el informe). Se valida
  // aquí además de en la web, porque la ruta es alcanzable sin pasar por ella.
  const email = typeof raw.email === "string" ? raw.email.trim() : "";
  if (!email || !EMAIL_RE.test(email) || email.length > 254) {
    return json({ error: "validacion", errores: { email: "Revisa el email" } }, 400);
  }

  try {
    const ip = clientIp(req);

    // Rate-limit por IP: N análisis públicos cada 24 h. Sin IP (no debería pasar
    // detrás de Vercel) no se puede limitar por IP, así que solo queda el tope
    // global de más abajo.
    if (ip) {
      const hoy = await countPublicToday(ip);
      if (hoy >= limiteDiario()) return json({ error: "rate" }, 429);
    }

    // Tope de gasto global: no más de M análisis vivos a la vez (compartido con
    // el panel interno). Para el canal público es "cupo agotado".
    if ((await countActiveRuns()) >= maxConcurrentes()) {
      return json({ error: "cupo" }, 429);
    }

    const payload: N8nWebhookPayload = { ...construirPayload(val.value), email };
    const creado = await createPublicRun(payload, ip);

    // La fila ya existe: si el disparo falla, hay que dejarla en 'error' para que
    // no ocupe hueco en el tope de concurrencia colgada en 'pendiente'.
    try {
      await dispararAnalisis(creado.id, "lite", payload);
    } catch (err) {
      const detalle = err instanceof Error ? err.message : String(err);
      await failRun(creado.id, `No se pudo lanzar el análisis: ${detalle}`).catch(
        () => {},
      );
      return json({ error: "servicio", detalle }, 502);
    }

    const res: LanzarPublicoResponse = { token: creado.token, estado: creado.estado };
    return json(res, 201);
  } catch (err) {
    return conCors(errorResponse(err), req);
  }
}

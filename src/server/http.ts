import { NextResponse } from "next/server";

import { PanelDbError } from "@/server/n8n/client";

/**
 * Traduce un error a una respuesta HTTP honesta. Si el fallo viene de que n8n no
 * responde (la BD vive dentro de n8n), es un 503, no un 500: el panel está bien,
 * su dependencia no.
 */
export function errorResponse(err: unknown): NextResponse {
  if (err instanceof PanelDbError) {
    const status = err.n8nRespondio ? 502 : 503;
    return NextResponse.json(
      {
        error: err.n8nRespondio ? "db_error" : "n8n_unreachable",
        detalle: err.message,
      },
      { status },
    );
  }
  const detalle = err instanceof Error ? err.message : String(err);
  return NextResponse.json({ error: "internal", detalle }, { status: 500 });
}

// ============================================================
// CORS del canal público (landing)
// ============================================================
// Las rutas /api/publico/* las llama la web pública desde OTRO dominio, así que
// necesitan CORS. NO se refleja cualquier Origin: solo los de la allowlist
// (PUBLIC_CORS_ORIGIN, coma-separados). Sin la variable no se emite
// Allow-Origin y el navegador bloquea la llamada cross-site: es el fallo seguro.

function origenesPermitidos(): string[] {
  return (process.env.PUBLIC_CORS_ORIGIN ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/** Cabeceras CORS para una respuesta pública. Refleja el Origin solo si está permitido. */
export function corsHeaders(req: Request): Record<string, string> {
  const permitidos = origenesPermitidos();
  const origin = req.headers.get("origin") ?? "";
  const h: Record<string, string> = {
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
  // Solo se autoriza un Origin que esté en la allowlist. Si no hay allowlist o el
  // Origin no encaja, no se emite la cabecera y el navegador corta la respuesta.
  if (origin && permitidos.includes(origin)) {
    h["Access-Control-Allow-Origin"] = origin;
  }
  return h;
}

/** Respuesta a un preflight OPTIONS de una ruta pública. */
export function preflight(req: Request): NextResponse {
  return new NextResponse(null, { status: 204, headers: corsHeaders(req) });
}

/** Copia las cabeceras CORS sobre una respuesta ya construida (p. ej. errorResponse). */
export function conCors(res: NextResponse, req: Request): NextResponse {
  for (const [k, v] of Object.entries(corsHeaders(req))) res.headers.set(k, v);
  return res;
}

/**
 * IP del cliente detrás del proxy de Vercel. Se usa solo para el rate-limit del
 * canal público; nunca se guarda en el informe ni se muestra.
 */
export function clientIp(req: Request): string | null {
  const xff = req.headers.get("x-forwarded-for");
  if (xff) return xff.split(",")[0]!.trim() || null;
  return req.headers.get("x-real-ip");
}

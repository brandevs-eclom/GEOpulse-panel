import { NextResponse } from "next/server";

import type { LanzarRunResponse, RunsAtCapacity } from "@/lib/shared/dto";
import { validarLanzarRun } from "@/lib/shared/validate";
import { exigirSesion, filtroPropiedad } from "@/server/auth/guard";
import { errorResponse } from "@/server/http";
import {
  construirPayload,
  countActiveRuns,
  createRun,
  failRun,
  listRuns,
} from "@/server/runs/repo";
import { dispararAnalisis } from "@/server/runs/trigger";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function maxConcurrentes(): number {
  const n = parseInt(process.env.MAX_CONCURRENT_RUNS ?? "2", 10);
  return Number.isFinite(n) && n > 0 ? n : 2;
}

/**
 * GET /api/runs — listado paginado. ?page=1&pageSize=50
 *
 * Un miembro ve solo las suyas; un admin, todas (incluidas las históricas sin
 * dueño). El filtro se aplica en el SQL, no en el panel: así una ejecución de
 * otra persona no llega ni a salir de la base de datos.
 */
export async function GET(req: Request) {
  const g = await exigirSesion();
  if (!g.ok) return g.res;
  try {
    const url = new URL(req.url);
    const page = parseInt(url.searchParams.get("page") ?? "1", 10) || 1;
    const pageSize = parseInt(url.searchParams.get("pageSize") ?? "50", 10) || 50;
    const pagina = await listRuns(page, pageSize, filtroPropiedad(g.sesion));
    return NextResponse.json(pagina);
  } catch (err) {
    return errorResponse(err);
  }
}

/** POST /api/runs — crea la ejecución y dispara n8n. */
export async function POST(req: Request) {
  const g = await exigirSesion();
  if (!g.ok) return g.res;

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "json_invalido" }, { status: 400 });
  }

  const val = validarLanzarRun(body);
  if (!val.ok) {
    return NextResponse.json(
      { error: "validacion", errores: val.errores },
      { status: 400 },
    );
  }

  try {
    // Tope de gasto: no dejamos más de N análisis vivos a la vez. Un completo son
    // ~64 llamadas LLM de pago. Se comprueba antes de crear.
    const max = maxConcurrentes();
    const activos = await countActiveRuns();
    if (activos >= max) {
      return NextResponse.json<RunsAtCapacity>(
        { error: "at_capacity", activos, max },
        { status: 429 },
      );
    }

    const payload = construirPayload(val.value);
    // Queda registrado quién la lanzó: es lo que luego decide quién la ve.
    const creado = await createRun(val.value, payload, g.sesion.id);

    // La fila ya existe: a partir de aquí, cualquier fallo debe dejarla en 'error'
    // y no colgada en 'pendiente' (ocuparía hueco en el tope de concurrencia).
    try {
      await dispararAnalisis(creado.id, val.value.tipo, payload);
    } catch (err) {
      const detalle = err instanceof Error ? err.message : String(err);
      // Si esto también falla, no hay mucho más que hacer: el watchdog de
      // ejecuciones estancadas (STALE_MINUTES) es la última red.
      await failRun(creado.id, `No se pudo lanzar el análisis: ${detalle}`).catch(
        () => {},
      );
      return NextResponse.json(
        { error: "trigger_fallido", detalle, id: creado.id },
        { status: 502 },
      );
    }

    return NextResponse.json<LanzarRunResponse>(
      { id: creado.id, estado: creado.estado },
      { status: 201 },
    );
  } catch (err) {
    return errorResponse(err);
  }
}

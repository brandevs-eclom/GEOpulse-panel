/**
 * Repositorio de ejecuciones. Traduce las operaciones del workflow `panel-db`
 * (filas con columnas snake_case) a los DTOs del panel (camelCase), y al revés.
 * Toda la E/S de datos del panel pasa por aquí.
 */

import type {
  LanzarRunInput,
  N8nWebhookPayload,
  RunDetail,
  RunListItem,
  RunsPage,
} from "@/lib/shared/dto";
import type { RunEstado, RunTipo } from "@/lib/shared/status";
import { callPanelDb } from "@/server/n8n/client";

// --- Helpers de coerción (n8n serializa a JSON; los tipos llegan flojos) ---

function num(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function str(v: unknown): string | null {
  return v === null || v === undefined ? null : String(v);
}

function bool(v: unknown): boolean {
  return v === true || v === "true" || v === "t" || v === 1;
}

/** jsonb puede llegar como objeto ya parseado o como string; toleramos ambos. */
function obj(v: unknown): Record<string, unknown> | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "object") return v as Record<string, unknown>;
  if (typeof v === "string") {
    try {
      return JSON.parse(v) as Record<string, unknown>;
    } catch {
      return null;
    }
  }
  return null;
}

type DbRow = Record<string, unknown>;

function aListItem(r: DbRow): RunListItem {
  return {
    id: String(r.id),
    createdAt: String(r.created_at),
    tipo: String(r.tipo) as RunTipo,
    brand: String(r.brand),
    domain: String(r.domain),
    keyword: String(r.keyword),
    pais: String(r.pais),
    region: str(r.region),
    estado: String(r.estado) as RunEstado,
    nota: num(r.nota),
    veredicto: str(r.veredicto),
    sov: num(r.sov),
    sondeos: num(r.sondeos),
    tieneAvisos: bool(r.tiene_avisos),
    duracionMs: num(r.duracion_ms),
    errorMensaje: str(r.error_mensaje),
    lanzadoPor: str(r.lanzado_por),
    lanzadoPorEmail: str(r.lanzado_por_email),
  };
}

/**
 * Filtro de propiedad que viaja a `panel-db`.
 *
 * null = sin filtro (admin). Un uuid = solo las ejecuciones de esa persona. Las
 * históricas tienen `lanzado_por` NULL, así que quedan fuera del filtro y solo
 * las ve un admin: es deliberado, no aparecen en el listado de un compañero
 * nuevo como si fueran suyas.
 */
export type FiltroDueno = string | null;

// --- Operaciones ---

/** Análisis vivos ahora mismo (para el tope de concurrencia). */
export async function countActiveRuns(): Promise<number> {
  const rows = await callPanelDb<{ activos: number }>("count_active");
  return num(rows[0]?.activos) ?? 0;
}

/**
 * Construye el body exacto para n8n a partir del input del formulario.
 * Normaliza país (mayúsculas, por defecto ES) y omite region si viene vacía.
 */
export function construirPayload(input: LanzarRunInput): N8nWebhookPayload {
  const region = input.region?.trim();
  return {
    brand: input.brand.trim(),
    domain: input.domain.trim(),
    keyword: input.keyword.trim(),
    pais: (input.pais?.trim().toUpperCase() || "ES") as string,
    ...(region ? { region } : {}),
  };
}

export interface RunCreado {
  id: string;
  estado: RunEstado;
  createdAt: string;
}

/**
 * Crea la ejecución en 'pendiente' y devuelve su id. Aún no dispara n8n.
 *
 * `lanzadoPor` es opcional para que un reintento manual por curl (sin sesión)
 * siga funcionando; en ese caso la ejecución se guarda sin dueño.
 */
export async function createRun(
  input: LanzarRunInput,
  payload: N8nWebhookPayload,
  lanzadoPor?: string | null,
): Promise<RunCreado> {
  const rows = await callPanelDb<DbRow>("create_run", {
    tipo: input.tipo,
    brand: payload.brand,
    domain: payload.domain,
    keyword: payload.keyword,
    pais: payload.pais,
    region: payload.region ?? null,
    payload,
    lanzado_por: lanzadoPor ?? null,
  });
  const r = rows[0];
  if (!r) throw new Error("create_run no devolvió la fila creada");
  return {
    id: String(r.id),
    estado: String(r.estado) as RunEstado,
    createdAt: String(r.created_at),
  };
}

/** Listado paginado. page es 1-indexado. `soloDe` filtra por dueño. */
export async function listRuns(
  page = 1,
  pageSize = 50,
  soloDe: FiltroDueno = null,
): Promise<RunsPage> {
  const p = Math.max(1, page);
  const size = Math.min(200, Math.max(1, pageSize));
  const rows = await callPanelDb<DbRow>("list_runs", {
    limit: size,
    offset: (p - 1) * size,
    solo_de: soloDe,
  });
  const total = num(rows[0]?._total) ?? 0;
  return { items: rows.map(aListItem), total, page: p, pageSize: size };
}

/**
 * Marca una ejecución como fallida. Solo actúa sobre ejecuciones vivas, así que
 * no pisa un resultado ya guardado por n8n.
 */
export async function failRun(id: string, mensaje: string): Promise<void> {
  await callPanelDb("fail_run", { id, mensaje });
}

/**
 * Borra una ejecución (y su informe por cascade). true si existía Y el filtro de
 * dueño la alcanza: para un miembro, la de otra persona se comporta como si no
 * existiera.
 */
export async function deleteRun(
  id: string,
  soloDe: FiltroDueno = null,
): Promise<boolean> {
  const rows = await callPanelDb<DbRow>("delete_run", { id, solo_de: soloDe });
  return rows.length > 0;
}

/**
 * Detalle de una ejecución con su informe (o null si aún no hay).
 * Devuelve null también cuando existe pero pertenece a otra persona: así el
 * panel responde 404 y no confirma que ese id exista.
 */
export async function getRun(
  id: string,
  soloDe: FiltroDueno = null,
): Promise<RunDetail | null> {
  const rows = await callPanelDb<DbRow>("get_run", { id, solo_de: soloDe });
  const r = rows[0];
  if (!r) return null;
  return {
    ...aListItem(r),
    updatedAt: String(r.updated_at),
    startedAt: str(r.started_at),
    finishedAt: str(r.finished_at),
    httpStatus: num(r.http_status),
    payload: obj(r.payload) ?? {},
    informe: obj(r.informe),
    rawBody: str(r.raw_body),
  };
}

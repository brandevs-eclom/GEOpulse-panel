/**
 * Contratos de la API del panel (cliente ↔ servidor).
 * Nada de esto se envía a n8n tal cual salvo `N8nWebhookPayload`.
 */

import type { RunEstado, RunTipo } from "./status";

/**
 * Respuesta de GET /api/health.
 *
 * Son tres hechos distintos y se informan por separado a propósito: el Postgres
 * está dentro del servidor de n8n, así que "el panel vive" no implica "n8n
 * responde", y "n8n responde" no implica "n8n puede consultar la BD".
 */
export interface HealthResponse {
  /** true solo si toda la cadena funciona. */
  ok: boolean;
  /** El panel alcanza el webhook de n8n. */
  n8n: boolean;
  /** n8n ha podido ejecutar una consulta contra Postgres. */
  db: boolean;
  /** Motivo real del fallo cuando ok=false. Nunca incluye secretos. */
  error?: string;
}

/**
 * Países que el workflow mapea a nombre + mercado (docs/02).
 * Otros códigos se aceptan, pero se usan tal cual (sin traducir el mercado).
 */
export const PAISES_SOPORTADOS = [
  "ES",
  "MX",
  "AR",
  "CO",
  "CL",
  "PE",
  "US",
  "GB",
  "FR",
  "DE",
  "IT",
  "PT",
] as const;
export type PaisSoportado = (typeof PAISES_SOPORTADOS)[number];

/** Body de POST /api/runs (lo que rellena el formulario del panel). */
export interface LanzarRunInput {
  tipo: RunTipo;
  /** Obligatorio. */
  brand: string;
  /** Obligatorio. Con o sin protocolo; el workflow lo normaliza. */
  domain: string;
  /** Obligatorio. El sector/término. */
  keyword: string;
  /** ISO-3166 alpha-2. Por defecto "ES". */
  pais?: string;
  /** Ciudad o región; afina la geolocalización de los sondeos. */
  region?: string;
}

/** Respuesta de POST /api/runs: se responde YA, sin esperar a n8n. */
export interface LanzarRunResponse {
  id: string;
  estado: RunEstado;
}

/**
 * Body exacto que se envía al webhook de n8n (docs/02).
 * Se guarda tal cual en runs.payload para poder reproducir/reintentar.
 */
export interface N8nWebhookPayload {
  brand: string;
  domain: string;
  keyword: string;
  pais: string;
  region?: string;
}

/** Fila del listado: solo lo que se necesita para la tabla, sin el informe. */
export interface RunListItem {
  id: string;
  createdAt: string;
  tipo: RunTipo;
  brand: string;
  domain: string;
  keyword: string;
  pais: string;
  region: string | null;
  estado: RunEstado;
  /** GEO Score. null es legítimo: el informe puede no tener datos suficientes. */
  nota: number | null;
  veredicto: string | null;
  sov: number | null;
  sondeos: number | null;
  tieneAvisos: boolean;
  duracionMs: number | null;
  errorMensaje: string | null;
  /**
   * Quién la lanzó. null en las ejecuciones anteriores a la autenticación (y en
   * las disparadas a mano por curl): no tienen dueño y solo las ven los admins.
   */
  lanzadoPor: string | null;
  lanzadoPorEmail: string | null;
}

export interface RunsPage {
  items: RunListItem[];
  total: number;
  page: number;
  pageSize: number;
}

/** Detalle completo de una ejecución: la fila + payload + informe (si existe). */
export interface RunDetail extends RunListItem {
  updatedAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  httpStatus: number | null;
  /** Body exacto que se envió (o se enviará) al webhook de n8n. */
  payload: Record<string, unknown>;
  /** El informe completo tal cual lo devolvió n8n. null si aún no hay resultado. */
  informe: unknown | null;
  /** Cuerpo crudo, por si el JSON vino raro. */
  rawBody: string | null;
}

/** Respuesta de POST /api/runs cuando se rechaza por tope de concurrencia. */
export interface RunsAtCapacity {
  error: "at_capacity";
  activos: number;
  max: number;
}

/**
 * Disparo del análisis en n8n.
 *
 * El webhook del panel (`geopulse-lite2-panel`) responde con un ack INMEDIATO y
 * sigue analizando por su cuenta durante 1-2 min (LITE) o 3-5 min (completo).
 * Al terminar escribe el informe en Postgres, que tiene al lado. Por eso aquí
 * basta con esperar el ack: no sostenemos la conexión durante todo el análisis,
 * que es justo lo que serverless no permite.
 */

import type { N8nWebhookPayload } from "@/lib/shared/dto";
import type { RunTipo } from "@/lib/shared/status";

/** El ack debería llegar en ~1 s; si tarda esto, algo va mal. */
const TIMEOUT_ACK_MS = 15_000;

export class TriggerError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TriggerError";
  }
}

function rutaDe(tipo: RunTipo): string {
  const path =
    tipo === "lite"
      ? process.env.N8N_PATH_LITE
      : process.env.N8N_PATH_COMPLETO;
  if (!path) {
    throw new TriggerError(
      `Falta la variable ${tipo === "lite" ? "N8N_PATH_LITE" : "N8N_PATH_COMPLETO"}`,
    );
  }
  const base = process.env.N8N_BASE_URL;
  if (!base) throw new TriggerError("Falta la variable N8N_BASE_URL");
  return `${base.replace(/\/+$/, "")}/webhook/${path}`;
}

/**
 * Dispara el análisis. Devuelve cuando n8n confirma que lo ha aceptado.
 * Lanza TriggerError si no se pudo encolar: quien llame debe marcar la
 * ejecución como error para no dejarla colgada en 'pendiente'.
 */
export async function dispararAnalisis(
  runId: string,
  tipo: RunTipo,
  payload: N8nWebhookPayload,
): Promise<void> {
  const url = rutaDe(tipo);
  const token = process.env.N8N_WEBHOOK_TOKEN;

  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), TIMEOUT_ACK_MS);

  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { "x-panel-secret": token } : {}),
      },
      // run_id es lo que permite al workflow escribir el resultado en su fila.
      body: JSON.stringify({ run_id: runId, ...payload }),
      signal: ctrl.signal,
      cache: "no-store",
    });
  } catch (err) {
    const abortado = err instanceof Error && err.name === "AbortError";
    throw new TriggerError(
      abortado
        ? `n8n no confirmó el análisis en ${TIMEOUT_ACK_MS} ms`
        : `No se pudo contactar con n8n: ${err instanceof Error ? err.message : String(err)}`,
    );
  } finally {
    clearTimeout(t);
  }

  const texto = await res.text();
  if (!res.ok) {
    throw new TriggerError(
      `n8n devolvió HTTP ${res.status}: ${texto.slice(0, 300)}`,
    );
  }

  // El ack dice si el workflow aceptó el run_id. Si no lo aceptó, el análisis
  // correría igual pero sin poder guardar el resultado: eso es un fallo.
  try {
    const data = JSON.parse(texto) as unknown;
    const cuerpo = (Array.isArray(data) ? data[0] : data) as {
      aceptado?: boolean;
    } | null;
    if (cuerpo && cuerpo.aceptado === false) {
      throw new TriggerError("n8n aceptó la llamada pero sin run_id válido");
    }
  } catch (err) {
    if (err instanceof TriggerError) throw err;
    // Un ack no-JSON no es motivo para fallar: el análisis ya está en marcha.
  }
}

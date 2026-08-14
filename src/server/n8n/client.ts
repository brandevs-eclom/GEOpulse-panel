/**
 * Cliente de la capa de datos del panel.
 *
 * El Postgres de GEOpulse vive DENTRO del servidor de n8n y no tiene salida al
 * exterior: no se puede abrir una conexión directa desde Vercel. Por eso toda
 * lectura y escritura pasa por el workflow `panel-db`, que ejecuta la consulta
 * con el nodo Postgres local y devuelve las filas por HTTP.
 *
 * Consecuencias que conviene tener presentes al usar esto:
 *  - No hay transacciones entre llamadas: cada operación es un HTTP independiente.
 *  - Si n8n está caído, el panel no puede mostrar ni siquiera el histórico.
 *  - El SQL NUNCA viaja desde aquí. El panel envía un nombre de operación y unos
 *    parámetros; el SQL está en una lista blanca dentro del workflow. Mandar SQL
 *    desde el cliente convertiría este webhook en un "ejecuta lo que quieras"
 *    expuesto a internet.
 */

/** Operaciones permitidas. Deben coincidir con la lista blanca de build_panel_db.py. */
export type PanelDbOp =
  // Diagnóstico y esquema
  | "ping"
  | "migrate"
  | "check"
  | "whoami"
  // Ejecuciones
  | "count_active"
  | "create_run"
  | "list_runs"
  | "get_run"
  | "delete_run"
  | "fail_run"
  // Usuarios
  | "count_users"
  | "count_admins"
  | "get_user_by_email"
  | "get_user"
  | "list_users"
  | "create_user"
  | "update_user_rol"
  | "update_user_password"
  | "delete_user";

export type EtapaFallo = "config" | "red" | "http" | "formato" | "n8n";

export class PanelDbError extends Error {
  constructor(
    message: string,
    readonly etapa: EtapaFallo,
    readonly status?: number,
  ) {
    super(message);
    this.name = "PanelDbError";
  }

  /** true si n8n llegó a responder (aunque fuese con error). */
  get n8nRespondio(): boolean {
    return this.etapa === "http" || this.etapa === "formato" || this.etapa === "n8n";
  }
}

const HEADER_SECRETO = "x-panel-secret";

function resolverConfig() {
  const base = process.env.N8N_BASE_URL;
  const path = process.env.N8N_PANEL_DB_PATH || "panel-db";
  const secreto = process.env.N8N_PANEL_DB_SECRET;

  if (!base) {
    throw new PanelDbError("Falta la variable N8N_BASE_URL", "config");
  }
  if (!secreto) {
    throw new PanelDbError("Falta la variable N8N_PANEL_DB_SECRET", "config");
  }
  return {
    url: `${base.replace(/\/+$/, "")}/webhook/${path}`,
    secreto,
  };
}

interface OpcionesLlamada {
  /** Por defecto 20 s. `migrate` necesita más. */
  timeoutMs?: number;
}

/**
 * Ejecuta una operación contra la BD a través de n8n y devuelve las filas.
 * Lanza PanelDbError con la etapa en la que falló, para que quien llame pueda
 * distinguir "n8n no responde" de "n8n responde pero la consulta falló".
 */
export async function callPanelDb<T = Record<string, unknown>>(
  op: PanelDbOp,
  params: Record<string, unknown> = {},
  { timeoutMs = 20_000 }: OpcionesLlamada = {},
): Promise<T[]> {
  const { url, secreto } = resolverConfig();

  const ctrl = new AbortController();
  const temporizador = setTimeout(() => ctrl.abort(), timeoutMs);

  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        [HEADER_SECRETO]: secreto,
      },
      body: JSON.stringify({ op, params }),
      signal: ctrl.signal,
      cache: "no-store",
    });
  } catch (err) {
    const abortado = err instanceof Error && err.name === "AbortError";
    throw new PanelDbError(
      abortado
        ? `n8n no respondió en ${timeoutMs} ms (op=${op})`
        : `No se pudo contactar con n8n: ${describir(err)}`,
      "red",
    );
  } finally {
    clearTimeout(temporizador);
  }

  const texto = await res.text();

  if (!res.ok) {
    // n8n está vivo pero rechazó la petición (secreto incorrecto, operación
    // desconocida, fallo del nodo Postgres…). Se conserva el cuerpo recortado
    // porque es lo único que explica qué pasó.
    throw new PanelDbError(
      `n8n devolvió HTTP ${res.status}: ${recortar(texto)}`,
      "http",
      res.status,
    );
  }

  // Cuerpo vacío con 2xx: es lo que devuelve n8n cuando el workflow aborta antes
  // de llegar al nodo 'Responder'. La causa más habitual con diferencia es que el
  // workflow importado no conoce la operación (se tocó el builder y falta
  // reimportar el JSON), así que se dice en vez de dejar un "no es JSON" pelado.
  if (!texto.trim()) {
    throw new PanelDbError(
      `n8n respondió sin cuerpo a la operación "${op}". Suele significar que el ` +
        `workflow panel-db abortó: comprueba que tienes importada la última ` +
        `versión de workflows/panel-db-workflow.json (¿conoce esa operación?) y ` +
        `mira su última ejecución en n8n.`,
      "formato",
    );
  }

  let datos: unknown;
  try {
    datos = JSON.parse(texto);
  } catch {
    throw new PanelDbError(
      `Respuesta de n8n no es JSON: ${recortar(texto)}`,
      "formato",
    );
  }

  // n8n puede devolver el objeto directamente o envuelto en un array.
  const cuerpo = (Array.isArray(datos) ? datos[0] : datos) as {
    ok?: boolean;
    error?: string;
    rows?: T[];
  } | null;

  if (!cuerpo || cuerpo.ok !== true) {
    throw new PanelDbError(
      cuerpo?.error ?? `Respuesta inesperada de n8n: ${recortar(texto)}`,
      "n8n",
    );
  }

  return cuerpo.rows ?? [];
}

/** Comprueba que n8n responde y que puede consultar Postgres. */
export async function pingPanelDb(): Promise<void> {
  await callPanelDb("ping", {}, { timeoutMs: 10_000 });
}

function describir(err: unknown): string {
  if (!(err instanceof Error)) return String(err);
  const e = err as Error & { code?: string; cause?: unknown };
  const partes: string[] = [];
  if (e.message) partes.push(e.message);
  if (e.code) partes.push(`code=${e.code}`);
  // fetch envuelve el fallo real en `cause`; sin esto el mensaje queda en
  // "fetch failed", que no dice nada.
  const causa = e.cause as { code?: string; message?: string } | undefined;
  if (causa?.code) partes.push(`causa=${causa.code}`);
  else if (causa?.message) partes.push(`causa=${causa.message}`);
  return partes.length ? partes.join(" · ") : err.name;
}

function recortar(texto: string, max = 300): string {
  const limpio = texto.trim().replace(/\s+/g, " ");
  return limpio.length > max ? `${limpio.slice(0, max)}…` : limpio;
}

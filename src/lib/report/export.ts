/**
 * Exports del informe (G12). Helpers PUROS, sin React: aplanan un `RunDetail` a
 * JSON y a una fila CSV, tolerantes a LITE y COMPLETO (formas distintas), y se
 * pueden ejercer desde un script de verificación (scripts/verificar_export.mjs).
 *
 * Honestidad del dato (docs/00): un valor null o ausente cae a CELDA VACÍA, nunca
 * a 0. La CSV/JSON son INFORMATIVAS: solo exponen valores ya calculados; no
 * recomputan la nota ni nada que alimente el score (pesos congelados).
 *
 * Este módulo NO importa nada en runtime a propósito (solo tipos, que Node borra):
 * así el verificador puede importarlo con Node sin el resolutor de alias `@/` de
 * Next. Por eso el discriminador LITE/COMPLETO va inline (espejo de
 * `esInformeCompleto` en report-completo.ts): es un check trivial y estable.
 */
import type { RunDetail } from "@/lib/shared/dto";

/**
 * ¿El informe es COMPLETO? Espejo de `esInformeCompleto` (report-completo.ts):
 * mira la FORMA (tiene `score`, no tiene `nota`), no el `tipo` de la fila. Se
 * duplica aquí, mínimo y a propósito, para que el módulo sea autocontenido.
 */
function esCompleto(informe: unknown): boolean {
  if (!informe || typeof informe !== "object") return false;
  const r = informe as Record<string, unknown>;
  return typeof r.score === "object" && r.score !== null && !("nota" in r);
}

/** El informe crudo, tal cual lo devolvió n8n, sin transformar. */
export function informeAJson(run: RunDetail): string {
  return JSON.stringify(run.informe ?? null, null, 2);
}

/** Lee un path anidado de forma tolerante (undefined si algo falta). */
function leer(obj: unknown, path: string): unknown {
  return path
    .split(".")
    .reduce<unknown>(
      (o, k) =>
        o && typeof o === "object"
          ? (o as Record<string, unknown>)[k]
          : undefined,
      obj,
    );
}

function numOrNull(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/**
 * Escalares del run como pares [columna, valor]. Un valor vacío ("") significa
 * "no medido / ausente": NUNCA se sustituye por 0.
 */
export function filasCsv(run: RunDetail): Array<[string, string]> {
  const inf = (run.informe ?? null) as Record<string, unknown> | null;
  const completo = inf ? esCompleto(inf) : false;

  const s = (v: unknown): string => (v === null || v === undefined ? "" : String(v));
  const n = (v: unknown): string => {
    const x = numOrNull(v);
    return x === null ? "" : String(x);
  };

  // por_area: LITE en `por_area.*`, COMPLETO en `score.por_area.*`.
  const area = (k: string): string =>
    completo ? n(leer(inf, `score.por_area.${k}`)) : n(leer(inf, `por_area.${k}`));

  // tasa de aparición por modelo: LITE array `aparicion.por_modelo[]`,
  // COMPLETO objeto `sondeo_llm.descubrimiento.por_modelo{}`.
  const tasa = (clave: string): string => {
    if (!inf) return "";
    if (completo) return n(leer(inf, `sondeo_llm.descubrimiento.por_modelo.${clave}.tasa_aparicion`));
    const arr = leer(inf, "aparicion.por_modelo");
    if (Array.isArray(arr)) {
      const m = arr.find(
        (x) => x && (x as Record<string, unknown>).clave === clave,
      );
      return m ? n((m as Record<string, unknown>).tasa) : "";
    }
    return "";
  };

  const meta = ((inf?.meta as Record<string, unknown>) ?? {}) as Record<string, unknown>;
  const avisos = inf ? (inf as { avisos?: unknown[] }).avisos : undefined;

  return [
    ["id", run.id],
    ["tipo", run.tipo],
    ["estado", run.estado],
    ["created_at", run.createdAt],
    ["finished_at", s(run.finishedAt)],
    ["duracion_s", run.duracionMs != null ? String(Math.round(run.duracionMs / 1000)) : ""],
    ["brand", run.brand],
    ["domain", run.domain],
    ["keyword", run.keyword],
    ["pais", run.pais],
    ["region", s(run.region)],
    // Escalares de fila ya extraídos por la API (canónicos): se usan tal cual.
    ["nota", n(run.nota)],
    ["veredicto", s(run.veredicto)],
    ["sov_global", n(run.sov)],
    ["area_seo_tecnico", area("seo_tecnico")],
    ["area_contenido", area("contenido")],
    ["area_sov", area("sov")],
    ["area_huella", area("huella")],
    ["eeatc_global", n(leer(inf, "huella_digital.eeatc.puntuacion_global"))],
    ["tasa_chatgpt", tasa("chatgpt")],
    ["tasa_claude", tasa("claude")],
    ["tasa_gemini", tasa("gemini")],
    ["tasa_perplexity", tasa("perplexity")],
    ["num_avisos", Array.isArray(avisos) ? String(avisos.length) : ""],
    // Coste (E1): estimación; coste_completo=false ⇒ es un suelo.
    ["coste_usd", n(meta.estimated_cost_usd)],
    ["coste_completo", meta.coste_completo === undefined ? "" : String(meta.coste_completo)],
    ["tokens_total", n(meta.tokens_total)],
    // Versionado (E2): para no comparar peras con manzanas.
    ["analysis_version", s(meta.analysis_version)],
    ["scoring_version", s(meta.scoring_version)],
    ["prompt_version", s(meta.prompt_version)],
  ];
}

function escaparCsv(v: string): string {
  return `"${v.replace(/"/g, '""')}"`;
}

/** Una fila CSV (cabecera + valores). BOM + CRLF para que Excel abra bien el UTF-8. */
export function informeAFilaCsv(run: RunDetail): string {
  const f = filasCsv(run);
  const cabecera = f.map(([k]) => escaparCsv(k)).join(",");
  const valores = f.map(([, v]) => escaparCsv(v)).join(",");
  return "\uFEFF" + cabecera + "\r\n" + valores + "\r\n";
}

/** Nombre de fichero de descarga, seguro y estable: geopulse-<marca>-<id>.<ext>. */
export function nombreFichero(run: RunDetail, ext: string): string {
  const slug =
    (run.brand || "informe")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 40) || "informe";
  return `geopulse-${slug}-${run.id}.${ext}`;
}

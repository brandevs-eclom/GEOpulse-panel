/**
 * Esquema del informe que devuelve n8n (docs/02 + docs/ejemplo-informe-lite.json).
 *
 * Este fichero tipa el informe **LITE**. El COMPLETO es más rico y, según el
 * frontend de referencia (workflows/geopulse-frontend-brandevs.html), anida la
 * cabecera de otra forma (`score.global` en vez de `nota`). Por eso:
 *
 *  - NO se asume que el completo encaje aquí. Se tipará aparte en la fase 2,
 *    cuando tengamos un payload real capturado.
 *  - La extracción de columnas para la tabla debe ser tolerante a ambas formas.
 *
 * Todo lo que el workflow puede no saber medir viene como `null` o con estado
 * `no_verificable`. No lo conviertas a 0 en ninguna capa: la honestidad del dato
 * es un principio de producto (docs/00).
 */

/** Estado de un punto de comprobación. `no_verificable` ≠ error: es "no se pudo medir". */
export type EstadoPunto = "ok" | "warning" | "error" | "no_verificable";

/** Veredicto de posicionamiento. `sin_datos` cuando no hubo sondeos válidos. */
export type Veredicto = "visible" | "parcial" | "invisible" | "sin_datos";

/** Clave estable de cada modelo (en minúscula), útil para columnas y agregados. */
export type ClaveModelo = "chatgpt" | "claude" | "gemini" | "perplexity";

export const CLAVES_MODELO: readonly ClaveModelo[] = [
  "chatgpt",
  "claude",
  "gemini",
  "perplexity",
];

export const ETIQUETA_MODELO: Record<ClaveModelo, string> = {
  chatgpt: "ChatGPT",
  claude: "Claude",
  gemini: "Gemini",
  perplexity: "Perplexity",
};

export interface InformeMeta {
  brand: string;
  domain: string;
  host: string;
  keyword: string;
  mercado: string;
  /** "lite2" | "completo" */
  version: string;
  fecha: string;
  /**
   * OJO: no es de fiar como fuente de verdad de qué modelos se sondearon.
   * En docs/ejemplo-informe-lite.json lista 3 modelos pero Gemini aparece en
   * `preguntas`, `aparicion` y `mapa_competitivo`. Para pintar columnas de
   * modelo usa `aparicion.por_modelo`, no esto.
   */
  modelos: string[];
  preguntas_lanzadas: number;
  /** Sondeos que devolvieron respuesta (puede ser < máximo). */
  sondeos: number;
}

export interface PorArea {
  seo_tecnico: number | null;
  contenido: number | null;
  /** "share of voice": visibilidad en IA. */
  sov: number | null;
  huella: number | null;
}

export interface PuntoSeoTecnico {
  clave: string;
  titulo: string;
  estado: EstadoPunto;
  valor: string | null;
  detalle: string | null;
  // Campos opcionales según la clave del punto:
  bloqueados_por_categoria?: {
    retrieval: string[];
    user_fetch: string[];
    training: string[];
  };
  waf?: { bloquea: boolean; status: number; challenge: boolean };
  tipos_detectados?: string[];
  campos_ausentes?: string[];
  validador?: { disponible: boolean; errores: number; warnings: number };
  entidades?: string[];
}

export interface Eeatc {
  experiencia: number | null;
  expertise: number | null;
  autoridad: number | null;
  confianza: number | null;
  citabilidad: number | null;
  puntuacion_global: number | null;
}

export interface HuellaDigital {
  enlaces: Array<{ dominio: string; url: string }>;
  dominio_propio_citado: boolean;
  eeatc: Eeatc;
  /** Comprobaciones extra que solo trae el informe completo. */
  bloqueados: number;
}

export interface RespuestaModelo {
  modelo: string;
  clave: ClaveModelo;
  /** false si el modelo no contestó (timeout, error de API…). */
  respondio: boolean;
  /** Si la marca aparece en la respuesta. */
  aparece: boolean;
  /** Texto literal devuelto por el modelo. */
  respuesta: string;
}

export interface PreguntaInforme {
  pregunta: string;
  respuestas: RespuestaModelo[];
}

export interface AparicionPorModelo {
  modelo: string;
  clave: ClaveModelo;
  apariciones: number;
  preguntas_validas: number;
  /** Porcentaje 0-100. */
  tasa: number;
  celdas: Array<{ respondio: boolean; aparece: boolean }>;
}

export interface Aparicion {
  por_modelo: AparicionPorModelo[];
  tasa_global: number;
  total_hits: number;
  total_validas: number;
}

/** La marca SIEMPRE está presente en el mapa, aunque sea con 0 menciones. */
export interface CompetidorMapa {
  empresa: string;
  es_marca: boolean;
  menciones: number;
  por_modelo: Partial<Record<ClaveModelo, number>>;
}

/** Diagnóstico técnico, útil en el detalle para depurar. */
export interface Diag {
  home_status?: number;
  robots_status?: number;
  sitemap_status?: number;
  html_bytes?: number;
  palabras?: number;
  home_legible?: boolean;
  csr?: boolean;
  spa?: string[];
  encabezados?: number;
  jsonld_bloques?: number;
  robots_grupos?: number;
  sitemap_urls?: number;
  validador_schema?: string;
  [k: string]: unknown;
}

export interface InformeLite {
  meta: InformeMeta;
  /** GEO Score 0-100. `null` es legítimo si no hubo datos suficientes. */
  nota: number | null;
  por_area: PorArea;
  resumen_hallazgos: string;
  posicionamiento: { veredicto: Veredicto };
  /** Avisos de fiabilidad. Se muestran SIEMPRE tal cual. Vacío = todo medible. */
  avisos: string[];
  seo_tecnico: { puntos: PuntoSeoTecnico[]; bloqueados: number };
  huella_digital: HuellaDigital;
  preguntas: PreguntaInforme[];
  aparicion: Aparicion;
  mapa_competitivo: CompetidorMapa[];
  _diag?: Diag;
}

/**
 * n8n puede devolver el objeto directamente o envuelto en un array (docs/02).
 * Usa esto siempre antes de tocar un informe recién recibido.
 */
export function desenvolverInforme(data: unknown): unknown {
  return Array.isArray(data) ? data[0] : data;
}

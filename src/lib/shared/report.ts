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

/**
 * Estado de un módulo del análisis (E3). Mismo union que el COMPLETO
 * (report-completo.ts) para que ambos informes sean comparables. Se define aquí
 * aparte porque LITE y COMPLETO viven en ficheros separados por regla del proyecto.
 */
export type EstadoModulo = "completed" | "partial" | "failed";

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

/**
 * Variantes de marca (C2). `deteccion` = medido (determinista); `observadas` =
 * inferido por los modelos. Se muestran por separado y marcando cuál es cuál.
 */
export interface VariantesMarca {
  deteccion: string[];
  observadas: string[];
}

/**
 * Ficha de Google Business (Places API New). `encontrada:false` es un resultado
 * legítimo (empresa sin ficha, o ninguna casó con seguridad). `confianza`: 'alta'
 * = casó por dominio; 'media' = solo por nombre (menos seguro, se avisa).
 */
export interface FichaGoogle {
  encontrada: boolean;
  confianza?: "alta" | "media";
  candidatos?: number;
  motivo?: string;
  nombre?: string | null;
  direccion?: string | null;
  rating?: number | null;
  resenas?: number | null;
  categoria?: string | null;
  web?: string | null;
  telefono?: string | null;
  /** OPERATIONAL | CLOSED_TEMPORARILY | CLOSED_PERMANENTLY */
  estado?: string | null;
  horario_publicado?: boolean;
  maps_url?: string | null;
}

/**
 * Enlaces rotos (404). Honestidad: `rotos` son 404/410 (seguro); `no_verificables`
 * son 403/429/5xx/timeout (un WAF o un lento no es un enlace roto). `cap_aplicado`
 * avisa si se revisó solo una muestra (los `encontrados` superan el tope).
 */
export interface EnlacesRotos {
  revisados: number;
  encontrados: number;
  /** Nº de páginas del sitio crawleadas (no solo la home). */
  paginas_revisadas: number;
  cap_aplicado: boolean;
  total_rotos: number;
  internos_rotos: number;
  externos_rotos: number;
  no_verificables: number;
  rotos: Array<{ url: string; tipo: "interno" | "externo"; status: number }>;
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
  /**
   * Estado por módulo (E3): completed | partial | failed. Un módulo caído (ningún
   * modelo respondió, el agente devolvió JSON no parseable) se marca y el render
   * lo dice, en vez de fingir un 0. Claves LITE: seo_tecnico, huella_digital,
   * visibilidad, informe.
   */
  estados_modulos?: Record<string, EstadoModulo>;
  /**
   * Variantes/erratas de marca (C2). `deteccion` es MEDIDO (tokens deterministas
   * con los que el sistema identifica la marca); `observadas` es INFERIDO (las
   * grafías que los modelos dicen haber usado, ya filtradas para que no se cuele
   * un competidor). El render las etiqueta como medido vs inferido; nunca
   * alimentan menciones ni share-of-voice.
   */
  variantes_marca?: VariantesMarca;
  /** Ficha de Google Business (Places API). null/ausente si no se analizó. */
  ficha_google?: FichaGoogle | null;
  /** Enlaces rotos (404) encontrados en la home. null/ausente si no se analizó. */
  enlaces_rotos?: EnlacesRotos | null;
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

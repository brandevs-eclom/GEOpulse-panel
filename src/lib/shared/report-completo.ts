/**
 * Esquema del informe COMPLETO (`geopulse-audit`).
 *
 * IMPORTANTE: no es un superconjunto plano del LITE. La cabecera está anidada de
 * otra forma —`score.global` en vez de `nota`, `score.por_area` en vez de
 * `por_area`— y añade sus propias secciones. Por eso vive en su propio fichero.
 *
 * Derivado de la FUENTE DE VERDAD, no de documentación: los esquemas JSON que
 * los agentes tienen obligación de devolver (prompts de `Agente Informe LLM`,
 * `Evaluador D1..D4`, `Agente 6 - Director`) y los `return` de los nodos Code
 * `Calcular Score`, `Consolidar Sondeos` y `Fusionar Recomendaciones`.
 *
 * Todo es opcional a propósito: los agentes pueden dejar secciones vacías si no
 * hay datos, y el informe lo dice en vez de rellenar. El render debe mostrar esa
 * ausencia, nunca convertirla en un 0.
 */

import type { ClaveModelo, EstadoPunto } from "./report";

/** Bloque estándar de comprobación técnica: estado + detalle. */
export interface PuntoTecnico {
  estado?: EstadoPunto;
  detalle?: string | null;
  calidad?: string;
  [k: string]: unknown;
}

/**
 * Claves que aparecen dentro de los bloques técnicos pero NO son comprobaciones
 * (son listas de acciones sugeridas). El render debe saltarlas.
 */
export const CLAVES_NO_PUNTO = new Set(["acciones"]);

/** Etiquetas legibles de las comprobaciones técnicas, tomadas del frontend original. */
export const ETIQUETA_PUNTO: Record<string, string> = {
  acceso_edge: "¿Pueden llegar los bots de IA?",
  rastreo_bots_ia: "Rastreo de los bots de IA",
  llms_txt: "Guía para modelos (llms.txt)",
  indexabilidad: "Indexación",
  sitemap: "Sitemap",
  renderizado: "Lectura y renderizado",
  rendimiento: "Rendimiento",
  schema: "Datos estructurados (Schema.org)",
  validador_oficial: "Validación oficial del schema",
  jerarquia_contenido: "Jerarquía de encabezados",
  estructura_extraccion: "Facilidad de extracción",
  intent_match: "Ajuste a la intención de búsqueda",
  answer_first: "Answer-first (inferido por IA)",
  intent_mismatch: "Coincidencia de intención (inferido por IA)",
  indice_autoridad: "Índice de autoridad",
  claridad_nucleo: "Claridad del núcleo",
  entidades: "Entidades detectadas",
  tono: "Tono",
  directorios: "Directorios",
  medios: "Medios y prensa",
  listas_sector: "Listas del sector",
  presencia_foros: "Foros y comunidades",
};

export interface MetaCompleto {
  brand: string;
  domain: string;
  keyword: string;
  competitors?: string[];
  fecha?: string;
  /** En el completo la geo es un objeto, no la cadena `mercado` del LITE. */
  geo?: { texto?: string; pais?: string; idioma?: string } | string;
  email?: string | null;
  email_valido?: boolean;
  modelos_sondeados?: string[];
  preguntas_lanzadas?: number;
  /** El completo usa `sondeos_totales`, no `sondeos`. */
  sondeos_totales?: number;
  landings_analizadas?: string[];
  /**
   * Versionado del análisis (E2). Sella cada informe para poder comparar
   * ejecuciones: si el pipeline, el scoring o los prompts cambian, dos informes
   * dejan de ser comparables aunque el dominio sea el mismo.
   */
  analysis_version?: string;
  scoring_version?: string;
  prompt_version?: string;
  /**
   * Resumen de coste (E1). Observabilidad interna, no se muestra al cliente.
   * `tokens_total` es MEDIDO; `estimated_cost_usd` es una estimación y es un
   * suelo cuando `coste_completo` es false (falta la tarifa de algún modelo).
   */
  estimated_cost_usd?: number;
  coste_completo?: boolean;
  tokens_total?: number;
}

/**
 * Coste por ejecución (E1). Tokens medidos del `usage` real de cada API + coste
 * estimado desde una tabla de tarifas editable. Es observabilidad interna del
 * panel: nunca se enseña en el informe del cliente.
 */
export interface CosteRun {
  token_usage: { input: number; output: number; total: number };
  /** Estimación en USD. Cota inferior si `completo` es false. */
  estimated_cost_usd: number;
  /** false ⇒ falta la tarifa de algún modelo y el coste es un suelo. */
  completo: boolean;
  request_count: number;
  fallos: number;
  reintentos: number;
  por_modelo: Array<{
    modelo: string;
    requests: number;
    input: number;
    output: number;
    coste_usd: number;
    sin_precio: boolean;
  }>;
  sin_precio: string[];
  precios: { estimado: boolean; fecha: string; fuente: string };
  /** Nodos cuyo coste no se puede medir (los agentes langchain no exponen usage). */
  no_medido?: { agentes: string[]; motivo: string };
}

export interface ScoreCompleto {
  global: number | null;
  por_area: {
    seo_tecnico: number | null;
    contenido: number | null;
    sov: number | null;
    huella: number | null;
  };
  desglose_sov?: {
    descubrimiento?: number | null;
    competitivo?: number | null;
    conocimiento?: number | null;
    reputacion?: number | null;
  };
  pesos?: Record<string, number>;
}

// --- Las 4 dimensiones del sondeo (sondeo_llm) ---

export interface BloqueDescubrimiento {
  detalle_preguntas?: Array<{
    pregunta: string;
    resultados?: Partial<
      Record<
        ClaveModelo,
        {
          mencionada: boolean;
          posicion: number | null;
          total_listadas: number;
          evidencia: string;
        }
      >
    >;
  }>;
  por_modelo?: Partial<
    Record<
      ClaveModelo,
      {
        apariciones: number;
        total_preguntas: number;
        tasa_aparicion: number;
        posicion_media: number | null;
      }
    >
  >;
  empresas_recomendadas?: Array<Record<string, unknown>>;
  /** Cuota de voz de la marca en descubrimiento, en %. */
  share_of_voice_global?: number | null;
  confusion_entidad?: ConfusionEntidad;
  veredicto?: string;
  hallazgos?: string[];
}

export interface BloqueCompetitivo {
  conjunto_competitivo?: Array<{
    empresa: string;
    menciones: number;
    menciones_por_modelo?: Partial<Record<ClaveModelo, number>>;
    modelos?: string[];
    posicion_media?: number | null;
    atributos?: string[];
  }>;
  posicion_marca?: {
    mencionada_en?: string[];
    posicion_media?: number | null;
    detalle?: string;
  };
  atributos_marca?: string[];
  gaps_atributos?: string[];
  ventajas_percibidas?: string[];
  competidores_inesperados?: string[];
  veredicto?: string;
  hallazgos?: string[];
}

/** Veredicto de una afirmación que la IA hace sobre la marca. */
export type VeredictoFactual = "verificada" | "contradicha" | "no_contrastable";

export interface BloqueConocimiento {
  nivel_conocimiento?: Partial<
    Record<ClaveModelo, "alto" | "medio" | "bajo" | "nulo">
  >;
  descripcion_percibida?: Partial<Record<ClaveModelo, string>>;
  /** Lo que la IA afirma, contrastado con la web real. */
  verificacion_factual?: Array<{
    afirmacion: string;
    modelo: string;
    veredicto: VeredictoFactual;
    fuente_real?: string;
    evidencia?: string;
  }>;
  alucinaciones?: Array<{
    modelo: string;
    afirmacion: string;
    gravedad: "alta" | "media" | "baja";
  }>;
  contradicciones_entre_modelos?: string[];
  servicios_correctos?: string[];
  servicios_erroneos?: string[];
  servicios_ausentes?: string[];
  riesgo_alucinacion?: RiesgoAlucinacion;
  confusion_entidad?: ConfusionEntidad;
  veredicto?: string;
  hallazgos?: string[];
}

export interface BloqueReputacion {
  sentimiento_por_modelo?: Partial<
    Record<ClaveModelo, { polaridad: number; tono: string }>
  >;
  polaridad_global?: number;
  objeciones_detectadas?: Array<{
    objecion: string;
    modelo: string;
    evidencia?: string;
    fuente?: string | null;
    respaldada_por_fuente?: boolean;
  }>;
  defensa_de_marca?: {
    estado?: "ok" | "warning" | "error";
    deriva_a_competidor?: string | null;
    detalle?: string;
  };
  riesgos_reputacionales?: string[];
  atributos_negativos?: string[];
  fuentes_negativas?: string[];
  veredicto?: string;
  hallazgos?: string[];
}

export interface SondeoLlm {
  descubrimiento?: BloqueDescubrimiento;
  competitivo?: BloqueCompetitivo;
  conocimiento?: BloqueConocimiento;
  reputacion?: BloqueReputacion;
}

/**
 * Confusión de entidad: el modelo habla de OTRA empresa homónima. Según el
 * prompt del agente es más grave que la ausencia, así que se muestra arriba.
 */
export interface ConfusionEntidad {
  detectada?: boolean;
  detalle?: string;
}

export interface RiesgoAlucinacion {
  nivel?: "alto" | "medio" | "bajo";
  detalle?: string;
}

// --- El informe redactado por el agente (informe_llm) ---

export type NivelVisibilidad =
  | "invisible"
  | "emergente"
  | "competitiva"
  | "dominante";

export interface InformeLlm {
  resumen_ejecutivo?: string;
  veredicto_visibilidad?: { nivel?: NivelVisibilidad; justificacion?: string };
  tabla_visibilidad?: Array<{
    modelo: string;
    aparece_descubrimiento?: string;
    conoce_marca?: string;
    sentimiento?: string;
    observacion?: string;
  }>;
  analisis_por_dimension?: Partial<
    Record<
      "descubrimiento" | "competitivo" | "conocimiento" | "reputacion",
      { resumen?: string; implicacion_negocio?: string }
    >
  >;
  divergencia_parametrico_grounded?: string;
  conjunto_competitivo_consolidado?: Array<{
    empresa: string;
    es_marca?: boolean;
    menciones?: number;
    menciones_por_modelo?: Partial<Record<ClaveModelo, number>>;
    modelos?: string[];
    amenaza?: "alta" | "media" | "baja";
  }>;
  gaps_criticos?: Array<{ gap: string; evidencia?: string; impacto?: string }>;
  oportunidades?: string[];
  plan_accion_llm?: Array<{
    prioridad?: "alta" | "media" | "baja";
    accion: string;
    por_que?: string;
    evidencia?: string;
    esfuerzo?: "bajo" | "medio" | "alto";
    impacto_esperado?: string;
  }>;
  kpis_seguimiento?: Array<{
    kpi: string;
    valor_actual?: string;
    objetivo?: string;
  }>;
  citas_destacadas?: Array<{ modelo: string; pregunta?: string; cita: string }>;
}

// --- Huella y recomendaciones ---

/**
 * Sitio donde ganar presencia. OJO: el campo real es `sitio` (no `dominio` ni
 * `url`); `fuente` distingue si el motor ya lo cita o si se descubrió aparte.
 */
export interface SitioRecomendado {
  sitio?: string;
  fuente?: "citado" | "descubierto" | string;
  motivo?: string;
  prioridad?: "alta" | "media" | "baja";
  veces_citado?: number;
  /** Tolerado por si alguna ejecución antigua trae otra forma. */
  dominio?: string;
  url?: string;
  [k: string]: unknown;
}

/** Una dimensión E-E-A-T-C: puntuación + explicación. */
export interface DimensionEeatc {
  puntuacion?: number | null;
  detalle?: string;
  citado_por_motores?: boolean;
}

export interface HuellaDigital {
  resumen?: string;
  eeatc?: Record<string, DimensionEeatc | number | string[] | undefined> & {
    puntuacion_global?: number | null;
    carencias?: string[];
  };
  directorios?: PuntoTecnico;
  medios?: PuntoTecnico;
  listas_sector?: PuntoTecnico;
  presencia_foros?: PuntoTecnico;
  [k: string]: unknown;
}

export interface RecomendacionesHuella {
  disponible?: boolean;
  total?: number;
  citadas?: number;
  descubiertas?: number;
  resumen?: string;
  directorios?: SitioRecomendado[];
  medios?: SitioRecomendado[];
  listas_sector?: SitioRecomendado[];
  foros?: SitioRecomendado[];
  otros?: SitioRecomendado[];
  ya_presente_en?: string[];
}

export interface FuentesSector {
  disponible?: boolean;
  total_citas?: number;
  /** En el completo son objetos {dominio, veces}; se tolera la forma plana. */
  dominios_citados?: Array<{ dominio: string; veces?: number } | string>;
  cliente_citado?: boolean;
  urls_cliente?: string[];
}

export interface Sintesis {
  diagnostico_ejecutivo?: string;
  plan_accion?: Array<{
    prioridad?: "alta" | "media" | "baja";
    area?: string;
    accion: string;
    impacto_esperado?: string;
  }>;
  quick_wins?: string[];
}

/**
 * Una empresa del mapa competitivo.
 *
 * OJO con el nombre del campo: el desglose por modelo se llama
 * `menciones_por_modelo`, NO `por_modelo`. Se mantiene `por_modelo` como
 * tolerancia por si alguna ejecución antigua trae la otra forma, pero el dato
 * real de `Ensamblar Reporte` usa el primero.
 */
export interface EmpresaMapa {
  empresa: string;
  es_marca?: boolean;
  menciones?: number;
  menciones_por_modelo?: Partial<Record<ClaveModelo, number>>;
  modelos?: string[];
  amenaza?: "alta" | "media" | "baja" | string;
  /** Forma antigua, tolerada. */
  por_modelo?: Partial<Record<ClaveModelo, number>>;
}

/** Estado de un módulo del análisis (E3). */
export type EstadoModulo = "completed" | "partial" | "failed";

/** El informe completo tal cual lo devuelve `Ensamblar Reporte`. */
export interface InformeCompleto {
  meta: MetaCompleto;
  score: ScoreCompleto;
  /**
   * Estado por módulo (E3): completed | partial | failed. Un módulo caído (un
   * modelo que no respondió, un bloque sin datos) no invalida el resto: se marca
   * y el render lo dice, en vez de fingir un 0.
   */
  estados_modulos?: Record<string, EstadoModulo>;
  /** Coste por ejecución (E1). Observabilidad interna, no se muestra al cliente. */
  coste?: CosteRun;
  infraestructura_geo?: Record<string, PuntoTecnico>;
  seo_tecnico?: Record<string, PuntoTecnico>;
  contenido_geo?: Record<string, PuntoTecnico>;
  sondeo_llm?: SondeoLlm;
  /** Las preguntas lanzadas, agrupadas por dimensión (no es un array plano). */
  preguntas?: Partial<
    Record<
      "descubrimiento" | "competitivo" | "conocimiento" | "reputacion",
      string[]
    >
  >;
  mapa_competitivo?: EmpresaMapa[];
  fuentes_sector?: FuentesSector;
  informe_llm?: InformeLlm;
  huella_digital?: HuellaDigital;
  recomendaciones_huella?: RecomendacionesHuella;
  sintesis?: Sintesis;
}

/**
 * Distingue un informe COMPLETO de uno LITE mirando el dato, no el `tipo` de la
 * fila: si una ejecución se guardó con el tipo equivocado, mandar la forma real.
 */
export function esInformeCompleto(informe: unknown): informe is InformeCompleto {
  if (!informe || typeof informe !== "object") return false;
  const r = informe as Record<string, unknown>;
  return typeof r.score === "object" && r.score !== null && !("nota" in r);
}

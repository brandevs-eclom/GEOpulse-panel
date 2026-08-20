"use client";

import { useState } from "react";

import type {
  BloqueCompetitivo,
  BloqueConocimiento,
  BloqueDescubrimiento,
  BloqueReputacion,
  ConfusionEntidad,
  DimensionEeatc,
  EmpresaMapa,
  HuellaDigital,
  InformeCompleto,
  RecomendacionesHuella,
  SitioRecomendado,
} from "@/lib/shared/report-completo";
import type { ClaveModelo } from "@/lib/shared/report";
import { AreaTiles, Avisos, Barra, ScoreRing } from "./primitivas";
import {
  Accion,
  Desplegable,
  Donut,
  Ficha,
  IndiceInforme,
  Metrica,
  PALETA_DONUT,
  SeccionInforme,
  Tabla,
  peor,
  type FilaTabla,
  type PorcionDonut,
} from "./completo-primitivas";
import "./report.css";
import "./report-completo.css";

/**
 * Render del informe COMPLETO.
 *
 * DISPOSICIÓN
 * El sistema visual (color, tipografía, formas, ritmo) está portado del mockup
 * informe-brandevs-completo(2).html: los tokens viven en
 * scripts/portar_css_informe.py y se aplican ACOTADOS a `.informe.informe-completo`
 * para no repintar el chrome del panel. Los titulares van en Space Grotesk (por
 * petición; el mockup usaba Manrope), el cuerpo en Inter.
 *
 * El informe son OCHO secciones de primer nivel, cada una un `<section>` con su
 * `id`, que es lo que hace navegable el índice (`INDICE`):
 *
 *   1. diagnostico-global   nota + titular + verdict-tag + áreas + avisos
 *   2. metodologia          las preguntas lanzadas (va justo tras el diagnóstico)
 *   3. visibilidad-en-ia    veredicto, resumen, modelo por modelo, memoria vs. web
 *   4. cuota-de-voz         donuts y mapa competitivo completo
 *   5. dimensiones          las 4 dimensiones del sondeo, en pestañas
 *   6. cimientos-tecnicos   SEO técnico (5 tarjetas)
 *   7. huella-externa       presencia, E-E-A-T-C, fuentes y dónde ganar presencia
 *   8. plan-de-accion       gaps, oportunidades, citas, planes y KPIs
 *
 * `metodologia` y `cuota-de-voz` son las dos secciones exceptuadas del rediseño:
 * conservan su estructura, solo heredan la paleta y la tipografía nuevas.
 *
 * El índice es un sidebar fijo a la IZQUIERDA (260px, numerado, con el GEO Score
 * al pie); el contenido, una columna de lectura de 840px. Dentro sigue habiendo
 * rejillas de tarjetas: no son columnas del documento, son piezas homogéneas que
 * se comparan entre sí. La prosa se ajusta a su contenedor.
 *
 * ACCESIBILIDAD
 * El estado nunca viaja solo en el color: cada punto y cada métrica llevan glifo
 * (decorativo) más el estado en texto para lectores de pantalla. La jerarquía es
 * h1 (la página) → h2 (sección) → h3 (bloque). Hay foco visible, respeto a
 * prefers-reduced-motion y hoja de impresión.
 *
 * Honestidad (docs/00): lo que el agente no pudo rellenar se dice ("sin datos"),
 * no se oculta ni se convierte en un 0. `no_verificable` se pinta en gris.
 */

// --- Lectores tolerantes: el informe trae bloques heterogéneos ---
type Bloque = Record<string, unknown>;

const bloque = (v: unknown): Bloque =>
  v && typeof v === "object" && !Array.isArray(v) ? (v as Bloque) : {};

/** Lee `a.b.c` sin reventar si falta un tramo. */
const g = (o: unknown, ruta: string): unknown =>
  ruta.split(".").reduce<unknown>((x, k) => bloque(x)[k], o);

const txt = (v: unknown): string | undefined =>
  typeof v === "string" && v.trim() ? v : undefined;

const est = (v: unknown): string | undefined =>
  typeof v === "string" ? v : undefined;

const arr = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];

const num = (v: unknown): number | null => (typeof v === "number" ? v : null);

/**
 * Quita las comillas que el modelo ya haya puesto alrededor de la cita, para no
 * acabar con `“"texto"”`. Los agentes devuelven unas veces la frase pelada y
 * otras entrecomillada; el render pone SIEMPRE las tipográficas.
 */
function entrecomillar(cita: string | undefined): string {
  const s = String(cita ?? "").trim();
  return s.replace(/^["'“”«»]+/, "").replace(/["'“”«»]+$/, "");
}

const MODELOS: Array<[ClaveModelo, string]> = [
  ["chatgpt", "ChatGPT"],
  ["claude", "Claude"],
  ["gemini", "Gemini"],
  ["perplexity", "Perplexity"],
];

export function InformeCompletoView({ informe }: { informe: InformeCompleto }) {
  const meta = informe.meta ?? ({} as InformeCompleto["meta"]);
  const sondeo = informe.sondeo_llm ?? {};
  const sintesis = informe.sintesis ?? {};
  const score = informe.score ?? { global: null, por_area: {} as never };

  const mercado =
    typeof meta.geo === "string" ? meta.geo : txt(meta.geo?.texto);
  const cabecera = [
    meta.brand,
    meta.domain,
    mercado ? `Mercado: ${mercado}` : null,
    meta.fecha ? new Date(meta.fecha).toLocaleString("es-ES") : null,
    meta.sondeos_totales ? `${meta.sondeos_totales} sondeos` : null,
  ]
    .filter(Boolean)
    .join("  ·  ");

  const confusiones = [
    sondeo.descubrimiento?.confusion_entidad,
    sondeo.conocimiento?.confusion_entidad,
  ].filter((x): x is ConfusionEntidad => !!x?.detectada);

  const inf = informe.informe_llm ?? {};
  const nivel = inf.veredicto_visibilidad?.nivel;

  return (
    <article className="informe informe-completo">
      <div className="con-indice">
        <IndiceInforme entradas={INDICE} nota={num(score.global)} />

        <div>
          {/* La cabecera y el aviso van DENTRO de la columna de contenido, no
              como hijos sueltos del informe: si no, se estiran a todo el ancho
              (sidebar incluido) y la línea de meta, alineada a la derecha,
              sobresalía por encima del diagnóstico. */}
          <p className="meta">{cabecera}</p>

          {/* Confusión de entidad: según el prompt del agente es MÁS grave que la
              ausencia, así que va antes que la nota. */}
          {confusiones.length > 0 && (
            <aside className="errbox" role="note" aria-labelledby="confusion-t">
              <h2 id="confusion-t">Confusión de entidad detectada</h2>
              <p>
                {confusiones
                  .map((x) => x.detalle)
                  .filter(Boolean)
                  .join(" ") ||
                  "Al menos un modelo describe una empresa homónima distinta de la auditada."}
              </p>
            </aside>
          )}

          {/* ===== 1. Diagnóstico ===== */}
          {/* El hero lleva el título dentro (como el mockup), así que esta
              sección no usa la cabecera de SeccionInforme: sería duplicarlo. */}
          <section id="diagnostico-global" aria-labelledby="diagnostico-t" tabIndex={-1}>
            <div className="dark">
              <div className="score-row">
                <ScoreRing nota={num(score.global)} />
                <div>
                  <span className="eyebrow">Diagnóstico global</span>
                  {/* h2: es la cabecera de la primera sección; mantiene la
                      jerarquía h1(página) → h2(sección) → h3(bloque). */}
                  <h2 id="diagnostico-t" className="hero-verdict">
                    Así te ve hoy la inteligencia artificial
                    {nivel && (
                      <span className={`verdict-tag n-${nivel}`}>{nivel}</span>
                    )}
                  </h2>
                  {/* El titular del informe: dos o tres frases. El detalle de
                      mercado y competidores vive en el resumen ejecutivo, más
                      abajo; aquí solo va el resultado global. */}
                  <p className="diagnostico">
                    {sintesis.diagnostico_ejecutivo || "Auditoría completada."}
                  </p>
                </div>
              </div>
            </div>

            <AreaTiles por_area={score.por_area ?? {}} enlaces={ANCLA_AREA} />

            {/* El informe puede traer avisos de honestidad (docs/00): se
                muestran tal cual, nunca se filtran. */}
            <Avisos avisos={(informe as { avisos?: string[] }).avisos} />

            {/* Módulos que no se completaron (E3): se dicen, no se esconden. */}
            <ModulosIncompletos estados={informe.estados_modulos} />
          </section>

          {/* ===== 2. Metodología (las 16 preguntas): va justo tras el
              diagnóstico, no al final. Sigue siendo la sección exceptuada del
              rediseño; solo cambia de sitio. ===== */}
          <SeccionInforme
            id="metodologia"
            eyebrow="Metodología"
            titulo="Cómo se ha medido"
            sub="Las preguntas exactas que se lanzaron a los modelos. Son las mismas para todos, formuladas como las haría un cliente real."
          >
            <PreguntasLanzadas
              preguntas={informe.preguntas}
              descubrimiento={sondeo.descubrimiento}
            />
          </SeccionInforme>

          {/* ===== 3. Visibilidad en IA ===== */}
          <SeccionInforme
            id="visibilidad-en-ia"
            eyebrow="Motores generativos"
            titulo="Tu visibilidad en las respuestas de la IA"
            sub={`${informe.meta?.preguntas_lanzadas ?? ""} preguntas de usuario real lanzadas a ChatGPT, Claude, Gemini y Perplexity, evaluadas por cuatro agentes especializados.`.trim()}
          >
            {/* Una columna: primero el veredicto, que es el dato con peso, y
                debajo el resumen. La prosa se acota con --measure, no
                partiendo la página en dos. */}
            {nivel && (
              <div className="verdict">
                <div className={`v-chip v-${nivel}`}>{nivel}</div>
                <p>{inf.veredicto_visibilidad?.justificacion || ""}</p>
              </div>
            )}
            {inf.resumen_ejecutivo && (
              <div className="exec">{inf.resumen_ejecutivo}</div>
            )}

            {(inf.tabla_visibilidad?.length ?? 0) > 0 && (
              <div className="panel">
                <h3>Modelo por modelo</h3>
                <Tabla
                  id="tabla-modelos"
                  titulo="Qué sabe cada modelo de la marca"
                  cabeceras={[
                    "Modelo",
                    "Descubrimiento",
                    "Conoce la marca",
                    "Sentimiento",
                    "Observación",
                  ]}
                  filas={inf.tabla_visibilidad!.map((t) => ({
                    celdas: [
                      t.modelo || "",
                      t.aparece_descubrimiento || "–",
                      t.conoce_marca || "–",
                      t.sentimiento || "–",
                      t.observacion || "",
                    ],
                  }))}
                />
              </div>
            )}

            {inf.divergencia_parametrico_grounded && (
              <div className="panel">
                <span className="eyebrow">Memoria vs. web actual</span>
                <h3>Lo que el modelo recuerda no es lo que la web dice hoy</h3>
                <p className="card-text">
                  {inf.divergencia_parametrico_grounded}
                </p>
              </div>
            )}
          </SeccionInforme>

          {/* ===== 4. Cuota de voz ===== */}
          <SeccionInforme
            id="cuota-de-voz"
            eyebrow="Cuota de voz"
            titulo="Quién ocupa tu espacio en las respuestas de la IA"
            sub="Reparto de menciones entre tu marca y sus competidores, motor por motor. Tu marca aparece siempre, aunque su cuota sea cero."
          >
            {/* Ancho completo: los 5 donuts y una tabla de 7 columnas no caben
                en media pantalla sin scroll horizontal. */}
            <CuotaDeVoz informe={informe} />
          </SeccionInforme>

          {/* ===== 5. Las 4 dimensiones ===== */}
          <SeccionInforme
            id="dimensiones"
            eyebrow="Las 4 dimensiones"
            titulo="De qué se compone tu visibilidad"
            sub="Cada dimensión se sondea por separado con su propio agente: qué te descubre, con quién te compara, qué sabe de ti y en qué tono habla."
          >
            <Dimensiones informe={informe} />
          </SeccionInforme>

          {/* ===== 6. Cimientos técnicos ===== */}
          <SeccionInforme
            id="cimientos-tecnicos"
            eyebrow="Cimientos"
            titulo="SEO técnico"
            sub="La base que decide si la IA puede encontrarte, leerte y entenderte. Verificado contra fuentes reales: tu servidor y el validador oficial de schema.org."
          >
            {/* Rejilla: cinco tarjetas del mismo tipo que se comparan por su
                punto de estado. */}
            <div className="rejilla">
              <TarjetaRastreo informe={informe} />
              <TarjetaIndexacion informe={informe} />
              <TarjetaDatosEstructurados informe={informe} />
              <TarjetaContenido informe={informe} />
              <TarjetaSemantica informe={informe} />
            </div>
          </SeccionInforme>

          {/* ===== 7. Huella externa ===== */}
          <SeccionInforme
            id="huella-externa"
            eyebrow="Off-page"
            titulo="Tu huella fuera de tu web"
            sub="Dónde te mencionan, con cuánta fuerza y si la IA te reconoce como autoridad. Investigación orgánica y global, sin filtro de país."
          >
            <div className="rejilla">
              <TarjetaPresenciaExterna huella={informe.huella_digital} />
              <TarjetaEeatc huella={informe.huella_digital} />
            </div>
            <FuentesDelSector informe={informe} />
            <DondeGanarPresencia
              recomendaciones={informe.recomendaciones_huella}
              competidores={informe.mapa_competitivo}
            />
          </SeccionInforme>

          {/* ===== 8. Qué hacer ===== */}
          <SeccionInforme
            id="plan-de-accion"
            eyebrow="Qué hacer"
            titulo="Por dónde empezar"
            sub="Ordenado por impacto. Cada acción sale de un hallazgo concreto de este informe."
          >
            <GapsYOportunidades informe={informe} />
            <Citas informe={informe} />
            <PlanesYKpis informe={informe} />
            <PlanGlobal sintesis={sintesis} />
          </SeccionInforme>

          {/* Versionado del análisis (E2): sella con qué pipeline, scoring y
              prompts se generó, para poder comparar ejecuciones. */}
          <VersionFoot meta={meta} />
        </div>
      </div>
    </article>
  );
}

/** Etiqueta legible de cada módulo del análisis. */
const ETIQUETA_MODULO: Record<string, string> = {
  seo_tecnico: "SEO técnico",
  infraestructura_geo: "Infraestructura GEO",
  contenido_geo: "Contenido",
  huella_digital: "Huella externa",
  fuentes_sector: "Fuentes del sector",
  descubrimiento: "Descubrimiento",
  competitivo: "Competitivo",
  conocimiento: "Conocimiento",
  reputacion: "Reputación",
  informe_llm: "Informe de visibilidad",
  sintesis: "Síntesis",
};

/**
 * Aviso de módulos incompletos (E3). Solo se pinta si algún módulo quedó
 * `partial` o `failed`; cuando todo corrió bien no aparece nada. Distingue "se
 * pudo medir a medias" de "no se pudo": no es lo mismo y el cliente debe saberlo.
 */
function ModulosIncompletos({
  estados,
}: {
  estados?: Record<string, string>;
}) {
  if (!estados) return null;
  const parciales = Object.entries(estados)
    .filter(([, v]) => v === "partial")
    .map(([k]) => ETIQUETA_MODULO[k] ?? k);
  const fallidos = Object.entries(estados)
    .filter(([, v]) => v === "failed")
    .map(([k]) => ETIQUETA_MODULO[k] ?? k);
  if (parciales.length === 0 && fallidos.length === 0) return null;

  return (
    <aside className="avisos" role="note" aria-label="Módulos incompletos">
      {fallidos.length > 0 && (
        <div className="aviso">
          <span className="aviso-ico">!</span>
          <span>
            <b>No se pudo completar:</b> {fallidos.join(", ")}. El resto del
            informe es válido; estos bloques no se han podido medir en esta
            ejecución.
          </span>
        </div>
      )}
      {parciales.length > 0 && (
        <div className="aviso">
          <span className="aviso-ico">!</span>
          <span>
            <b>Medido a medias:</b> {parciales.join(", ")}. Corrieron pero sin
            datos suficientes; tómalos como orientativos.
          </span>
        </div>
      )}
    </aside>
  );
}

/** Pie discreto con las versiones del análisis (E2). */
function VersionFoot({ meta }: { meta: InformeCompleto["meta"] }) {
  const partes = [
    meta.analysis_version && `análisis ${meta.analysis_version}`,
    meta.scoring_version && `scoring ${meta.scoring_version}`,
    meta.prompt_version && `prompts ${meta.prompt_version}`,
  ].filter(Boolean);
  if (partes.length === 0) return null;
  return <p className="version-foot">{partes.join(" · ")}</p>;
}

/**
 * A qué sección lleva cada nota de área. Convierte las cuatro cifras de
 * cabecera en enlaces al bloque que las explica.
 */
const ANCLA_AREA: Record<string, string> = {
  seo_tecnico: "cimientos-tecnicos",
  contenido: "cimientos-tecnicos",
  sov: "visibilidad-en-ia",
  huella: "huella-externa",
};

/**
 * A qué sección lleva cada KPI.
 *
 * Los KPI los redacta un agente en texto libre ("Cuota de voz en
 * descubrimiento", "Dominios del sector que te citan"...), así que no hay clave
 * por la que mapear: se resuelve por palabras. Si ninguna casa, el KPI se queda
 * como texto plano — mejor eso que un enlace que lleva al sitio equivocado.
 */
const PALABRAS_ANCLA: Array<[RegExp, string]> = [
  [/cuota|share|sov|menciones|competid|rival|comparativa/i, "cuota-de-voz"],
  [/schema|json-?ld|robots|bot|rastreo|index|render|encabezado|sitemap|llms\.txt|t[eé]cnic/i, "cimientos-tecnicos"],
  [
    /huella|directorio|medio|foro|rese[ñn]a|autoridad|e-?e-?a-?t|backlink|credibilidad|extern|cita.*dominio|dominio.*cita/i,
    "huella-externa",
  ],
  [
    /visibilidad|aparic|aparec|descubrimiento|discovery|posici|modelo|chatgpt|claude|gemini|perplexity|respuesta/i,
    "visibilidad-en-ia",
  ],
  [
    /conocimiento|reputaci|sentimiento|alucinaci|objeci|consistencia|descripci|coheren/i,
    "dimensiones",
  ],
];

function anclaDeKpi(texto: string): string | null {
  for (const [re, ancla] of PALABRAS_ANCLA) if (re.test(texto)) return ancla;
  return null;
}

/** Índice navegable. El orden es el del informe; las anclas, las de cada sección. */
const INDICE: Array<{ texto: string; ancla: string }> = [
  { texto: "Diagnóstico", ancla: "diagnostico-global" },
  { texto: "Metodología", ancla: "metodologia" },
  { texto: "Visibilidad en IA", ancla: "visibilidad-en-ia" },
  { texto: "Cuota de voz", ancla: "cuota-de-voz" },
  { texto: "Las 4 dimensiones", ancla: "dimensiones" },
  { texto: "Cimientos técnicos", ancla: "cimientos-tecnicos" },
  { texto: "Huella externa", ancla: "huella-externa" },
  { texto: "Qué hacer", ancla: "plan-de-accion" },
];

// ============================================================
// Metodología
// ============================================================

const BLOQUES_PREGUNTAS: Array<[string, string, string]> = [
  ["descubrimiento", "Descubrimiento", "¿Emerges cuando nadie te nombra?"],
  ["competitivo", "Competitivo", "¿Con quién te compara la IA?"],
  ["conocimiento", "Conocimiento", "¿Qué sabe de ti y es cierto?"],
  ["reputacion", "Reputación", "¿Qué dice cuando el cliente duda?"],
];

/** Acordeón con las preguntas exactas que se lanzaron a los modelos. */
function PreguntasLanzadas({
  preguntas,
  descubrimiento,
}: {
  preguntas?: InformeCompleto["preguntas"];
  descubrimiento?: BloqueDescubrimiento;
}) {
  const [abierto, setAbierto] = useState<string | null>(null);

  const mapa: Record<string, string[]> = { ...(preguntas ?? {}) } as Record<
    string,
    string[]
  >;
  // Fallback del original: si no viene el bloque de preguntas, al menos se
  // reconstruyen las de descubrimiento desde el detalle del sondeo.
  if (!BLOQUES_PREGUNTAS.some(([k]) => (mapa[k] ?? []).length)) {
    const dp = descubrimiento?.detalle_preguntas;
    if (Array.isArray(dp)) {
      mapa.descubrimiento = dp.map((x) => x.pregunta).filter(Boolean);
    }
  }

  const total = BLOQUES_PREGUNTAS.reduce(
    (a, [k]) => a + (mapa[k] ?? []).length,
    0,
  );
  if (!total) return null;

  return (
    <div className="panel">
      <span className="eyebrow">Metodología</span>
      <h3>{`Las ${total} preguntas que hemos lanzado`}</h3>
      <p className="card-text">
        Las mismas para todos los modelos, formuladas como las haría un cliente
        real y ancladas a tu mercado. En descubrimiento y competitivo no se
        fuerza la mención de tu marca: si apareces, apareces sola.
      </p>
      <div className="qs">
        {BLOQUES_PREGUNTAS.map(([clave, titulo, sub]) => {
          const qs = mapa[clave] ?? [];
          if (!qs.length) return null;
          const open = abierto === clave;
          return (
            <div className="q-item" key={clave}>
              <button
                type="button"
                className="q-head"
                aria-expanded={open}
                onClick={() => setAbierto(open ? null : clave)}
              >
                <div>
                  <span className="q-title">{titulo}</span>
                  <span className="q-sub">{`${sub}  ·  ${qs.length} preguntas`}</span>
                </div>
                <span className="q-pm">{open ? "–" : "+"}</span>
              </button>
              <div className={`q-body${open ? " open" : ""}`}>
                <ol>
                  {qs.map((q, i) => (
                    <li key={i}>{q}</li>
                  ))}
                </ol>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================
// Cimientos: SEO técnico (5 tarjetas, como el original)
// ============================================================

/** Bloque 1 — ¿pueden los bots de IA llegar a la web? */
function TarjetaRastreo({ informe }: { informe: InformeCompleto }) {
  const seo = bloque(informe.seo_tecnico);
  const infra = bloque(informe.infraestructura_geo);
  const bpc = bloque(g(seo, "rastreo_bots_ia.bloqueados_por_categoria"));

  const partes: string[] = [];
  if (arr(bpc.retrieval).length)
    partes.push(`Retrieval: ${arr(bpc.retrieval).join(", ")}`);
  if (arr(bpc.user_fetch).length)
    partes.push(`User-fetch: ${arr(bpc.user_fetch).join(", ")}`);
  if (arr(bpc.training).length)
    partes.push(
      `Training (sin coste de citación): ${arr(bpc.training).join(", ")}`,
    );
  const bots = Object.keys(bpc).length
    ? partes.length
      ? partes.join(" · ")
      : "Sin bloqueos"
    : undefined;

  const edge = bloque(seo.acceso_edge);
  const bloqueadosEdge = arr(edge.bots_bloqueados_edge).join(", ");
  const obsoletas = arr(g(seo, "rastreo_bots_ia.reglas_obsoletas"));

  return (
    <Ficha
      eyebrow="Rastreo"
      titulo="¿Pueden llegar los bots de IA?"
      estado={peor([
        est(g(seo, "rastreo_bots_ia.estado")),
        est(g(seo, "acceso_edge.estado")),
        est(g(infra, "sitemap.estado")),
      ])}
    >
      <Metrica
        etiqueta="Bots de IA (robots.txt)"
        estado={est(g(seo, "rastreo_bots_ia.estado"))}
        detalle={[bots, txt(g(seo, "rastreo_bots_ia.detalle"))]
          .filter(Boolean)
          .join(" — ")}
      />
      {Object.keys(edge).length > 0 && (
        <Metrica
          etiqueta="Acceso real (CDN/WAF)"
          estado={est(edge.estado)}
          valor={bloqueadosEdge ? `Bloqueados: ${bloqueadosEdge}` : null}
          detalle={txt(edge.detalle)}
        />
      )}
      <Metrica
        etiqueta="Sitemap XML"
        estado={est(g(infra, "sitemap.estado"))}
        detalle={txt(g(infra, "sitemap.detalle"))}
      />
      {obsoletas.length > 0 && (
        <Metrica
          etiqueta="Reglas obsoletas en robots.txt"
          estado="warning"
          valor={String(obsoletas.length)}
          detalle={obsoletas.join(" · ")}
        />
      )}
    </Ficha>
  );
}

/** Bloque 2 — ¿pueden leer e indexar el contenido? */
function TarjetaIndexacion({ informe }: { informe: InformeCompleto }) {
  const seo = bloque(informe.seo_tecnico);
  const porPagina = g(seo, "jerarquia_contenido.por_pagina");
  const paginas = Array.isArray(porPagina) ? porPagina.map(bloque) : [];

  return (
    <Ficha
      eyebrow="Indexación"
      titulo="Lectura y renderizado"
      estado={peor([
        est(g(seo, "indexabilidad.estado")),
        est(g(seo, "renderizado.estado")),
        est(g(seo, "jerarquia_contenido.estado")),
      ])}
    >
      <Metrica
        etiqueta="Indexabilidad"
        estado={est(g(seo, "indexabilidad.estado"))}
        detalle={txt(g(seo, "indexabilidad.detalle"))}
      />
      {seo.renderizado != null && (
        <Metrica
          etiqueta="Renderizado sin JS"
          estado={est(g(seo, "renderizado.estado"))}
          detalle={txt(g(seo, "renderizado.detalle"))}
        />
      )}
      <Metrica
        etiqueta="Jerarquía de encabezados"
        estado={est(g(seo, "jerarquia_contenido.estado"))}
        detalle={txt(g(seo, "jerarquia_contenido.detalle"))}
      />
      {/* Detalle página por página: bloque denso, plegado por defecto. */}
      {paginas.length > 0 && (
        <Desplegable
          titulo="Análisis página por página"
          cuenta={`${paginas.length} ${paginas.length === 1 ? "página" : "páginas"}`}
        >
          {paginas.slice(0, 15).map((pg, i) => (
            <Metrica
              key={i}
              etiqueta={
                String(pg.url ?? "")
                  .replace(/^https?:\/\//, "")
                  .replace(/\/$/, "") || "Página"
              }
              estado={
                ["ok", "warning", "error"].includes(String(pg.estado))
                  ? String(pg.estado)
                  : "warning"
              }
              detalle={txt(pg.detalle)}
            />
          ))}
        </Desplegable>
      )}
    </Ficha>
  );
}

/** Bloque 3 — ¿entiende la IA qué eres? */
function TarjetaDatosEstructurados({ informe }: { informe: InformeCompleto }) {
  const infra = bloque(informe.infraestructura_geo);
  const tipos = arr(g(infra, "schema.tipos_detectados")).join(", ");
  const ausentes = arr(g(infra, "schema.campos_ausentes")).join(", ");
  const invalidas = arr(g(infra, "schema.propiedades_invalidas")).join(", ");
  const vo = bloque(infra.validador_oficial);
  const hayValidador = Object.keys(vo).length > 0;
  const nErr = num(vo.num_errores) ?? 0;
  const nWarn = num(vo.num_warnings) ?? 0;
  const cobertura = txt(g(infra, "schema.cobertura_landings"));

  return (
    <Ficha
      eyebrow="Datos estructurados"
      titulo="Señales que la IA interpreta"
      estado={peor([
        est(g(infra, "schema.estado")),
        est(g(infra, "llms_txt.estado")),
      ])}
    >
      <Metrica
        etiqueta="Marcado Schema (JSON-LD)"
        estado={est(g(infra, "schema.estado"))}
        valor={tipos || null}
        detalle={[
          txt(g(infra, "schema.detalle")),
          ausentes ? `Campos ausentes: ${ausentes}` : null,
          invalidas ? `Propiedades inválidas: ${invalidas}` : null,
        ]
          .filter(Boolean)
          .join(" ")}
      />
      {hayValidador &&
        (vo.disponible ? (
          <Metrica
            etiqueta="Validador schema.org"
            estado={nErr > 0 ? "error" : nWarn > 0 ? "warning" : "ok"}
            valor={`${nErr} errores · ${nWarn} avisos`}
          />
        ) : (
          // El validador no respondió: se dice, no se da por bueno.
          <Metrica
            etiqueta="Validador schema.org"
            estado="no_verificable"
            valor="no disponible"
            detalle="El validador no respondió; la evaluación se basa en el análisis propio."
          />
        ))}
      <Metrica
        etiqueta="Archivo llms.txt"
        estado={est(g(infra, "llms_txt.estado"))}
        detalle={txt(g(infra, "llms_txt.detalle"))}
      />
      {cobertura && (
        <p className="m-detail">{`Cobertura en páginas internas: ${cobertura}`}</p>
      )}
    </Ficha>
  );
}

/** Bloque 4 — contenido optimizado para IA. */
function TarjetaContenido({ informe }: { informe: InformeCompleto }) {
  const cont = bloque(informe.contenido_geo);
  return (
    <Ficha
      eyebrow="Contenido"
      titulo="Contenido optimizado para IA"
      estado={peor([
        est(g(cont, "indice_autoridad.estado")),
        est(g(cont, "intent_match.estado")),
        est(g(cont, "estructura_extraccion.estado")),
      ])}
    >
      <Metrica
        etiqueta="Índice de autoridad (datos/citas)"
        estado={est(g(cont, "indice_autoridad.estado"))}
        detalle={txt(g(cont, "indice_autoridad.detalle"))}
      />
      <Metrica
        etiqueta="Alineación con la intención"
        estado={est(g(cont, "intent_match.estado"))}
        detalle={txt(g(cont, "intent_match.detalle"))}
      />
      {/* [B2] answer-first e intent-mismatch: informativos e INFERIDOS por el
          LLM. Fuera del estado de la Ficha (no pesan en la nota). Solo se pintan
          si el informe los trae (prompt-v2+): un informe viejo no los inventa. */}
      {g(cont, "answer_first.estado") ? (
        <Metrica
          etiqueta="Answer-first (inferido por IA)"
          estado={est(g(cont, "answer_first.estado"))}
          detalle={txt(g(cont, "answer_first.detalle"))}
        />
      ) : null}
      {g(cont, "intent_mismatch.estado") ? (
        <Metrica
          etiqueta="Coincidencia de intención (inferido por IA)"
          estado={est(g(cont, "intent_mismatch.estado"))}
          detalle={txt(g(cont, "intent_mismatch.detalle"))}
        />
      ) : null}
      <Metrica
        etiqueta="Chunks autocontenidos"
        estado={est(g(cont, "estructura_extraccion.estado"))}
        detalle={txt(g(cont, "estructura_extraccion.detalle"))}
      />
      {txt(cont.tono) && (
        <Metrica etiqueta="Tono percibido" estado="ok" valor={txt(cont.tono)} />
      )}
    </Ficha>
  );
}

/** Bloque 5 — semántica: qué conceptos extrae la IA del contenido real. */
function TarjetaSemantica({ informe }: { informe: InformeCompleto }) {
  const cont = bloque(informe.contenido_geo);
  const cl = num(cont.claridad_nucleo);
  const entidades = arr(cont.entidades);

  return (
    <Ficha
      eyebrow="Semántica"
      titulo="Cómo lee la IA tu web"
      estado={
        cl === null ? "muted" : cl >= 75 ? "ok" : cl >= 50 ? "warning" : "error"
      }
    >
      <p className="m-detail">Conceptos núcleo extraídos del contenido real:</p>
      <div className="tags">
        {entidades.length > 0 ? (
          entidades
            .slice(0, 10)
            .map((e, i) => (
              <span className={`tag${i < 2 ? " tag-accent" : ""}`} key={i}>
                {e}
              </span>
            ))
        ) : (
          <span className="tag">Sin entidades extraídas</span>
        )}
      </div>
      <Metrica
        etiqueta="Claridad del núcleo del negocio"
        estado={
          cl === null
            ? "no_verificable"
            : cl >= 75
              ? "ok"
              : cl >= 50
                ? "warning"
                : "error"
        }
        valor={cl === null ? null : `${cl} / 100`}
      />
    </Ficha>
  );
}

// ============================================================
// Off-page
// ============================================================

const CANALES_HUELLA: Array<[string, string]> = [
  ["presencia_foros", "Foros y comunidades"],
  ["medios", "Medios y prensa"],
  ["directorios", "Directorios y reseñas"],
  ["listas_sector", "Listas y rankings del sector"],
];

function TarjetaPresenciaExterna({ huella }: { huella?: HuellaDigital }) {
  const h = bloque(huella);
  const conError = !!h._error;

  return (
    <Ficha
      eyebrow="Off-page"
      titulo="Presencia externa"
      estado={
        conError ? "muted" : peor(CANALES_HUELLA.map(([k]) => est(g(h, `${k}.estado`))))
      }
    >
      {conError ? (
        <p className="m-detail">
          La investigación de huella no devolvió un resultado estructurado en
          esta ejecución.
        </p>
      ) : (
        CANALES_HUELLA.map(([k, lab]) => {
          const o = bloque(h[k]);
          if (!Object.keys(o).length) return null;
          const listas = arr(o.listas_encontradas);
          const extra =
            k === "listas_sector" && listas.length
              ? `Listas: ${listas.slice(0, 3).join(" · ")}`
              : null;
          return (
            <Metrica
              key={k}
              etiqueta={lab}
              estado={est(o.estado)}
              valor={txt(o.calidad) ?? null}
              detalle={[txt(o.detalle), extra].filter(Boolean).join(" — ")}
              fuentes={o.fuentes}
            />
          );
        })
      )}
    </Ficha>
  );
}

const EEATC_DIMS: Array<[string, string]> = [
  ["experiencia", "Experiencia"],
  ["expertise", "Expertise"],
  ["autoridad", "Autoridad"],
  ["confianza", "Confianza"],
  ["citabilidad", "Citabilidad"],
];

function TarjetaEeatc({ huella }: { huella?: HuellaDigital }) {
  const h = bloque(huella);
  const ee = bloque(h.eeatc);
  const global = num(ee.puntuacion_global);
  if (global === null && !ee.experiencia) return null;
  const carencias = arr(ee.carencias).slice(0, 4);

  return (
    <Ficha
      eyebrow="Autoridad"
      titulo="E-E-A-T-C"
      estado={
        global === null ? "muted" : global >= 70 ? "ok" : global >= 40 ? "warning" : "error"
      }
    >
      {EEATC_DIMS.map(([k, lab]) => {
        const o = ee[k] as DimensionEeatc | undefined;
        if (!o) return null;
        const v = num(o.puntuacion);
        return (
          <div className="eeatc" key={k}>
            <div className="m-row">
              <span className="m-lbl">{lab}</span>
              <span
                className={`m-val ${
                  v === null
                    ? "v-muted"
                    : v >= 70
                      ? "v-ok"
                      : v >= 40
                        ? "v-warning"
                        : "v-error"
                }`}
              >
                {v === null ? "–" : `${v} / 100`}
              </span>
            </div>
            <Barra v={v} />
            {o.detalle && <p className="m-detail">{o.detalle}</p>}
          </div>
        );
      })}
      {global !== null && (
        <Metrica
          etiqueta="Puntuación global"
          estado={global >= 70 ? "ok" : global >= 40 ? "warning" : "error"}
          valor={`${global} / 100`}
          detalle={txt(h.resumen)}
        />
      )}
      {carencias.length > 0 && (
        <Metrica
          etiqueta="Carencias"
          estado="warning"
          valor={String(carencias.length)}
          detalle={carencias.join(" · ")}
        />
      )}
    </Ficha>
  );
}

// ============================================================
// Motores generativos
// ============================================================

/**
 * Gaps y oportunidades.
 *
 * En rejilla porque son fichas homogéneas que se comparan entre sí; a ancho
 * completo cada una quedaba en dos líneas de 130 caracteres.
 *
 * Y en DOS paneles, no en uno: antes las oportunidades vivían anidadas dentro
 * del panel de gaps y solo se pintaban si había gaps, así que un informe sin
 * gaps se comía también las oportunidades.
 */
function GapsYOportunidades({ informe }: { informe: InformeCompleto }) {
  const inf = informe.informe_llm ?? {};
  const gaps = inf.gaps_criticos ?? [];
  const oportunidades = inf.oportunidades ?? [];
  if (gaps.length === 0 && oportunidades.length === 0) return null;

  return (
    <>
      {gaps.length > 0 && (
        <div className="panel">
          <span className="eyebrow">Los agujeros</span>
          <h3>Gaps críticos</h3>
          <div className="rejilla">
            {gaps.map((x, i) => (
              <div className="card gap" key={i}>
                <div className="g-t">{x.gap || ""}</div>
                {x.evidencia && (
                  <div className="g-b">{`Evidencia: ${x.evidencia}`}</div>
                )}
                {x.impacto && <div className="g-b">{`Impacto: ${x.impacto}`}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {oportunidades.length > 0 && (
        <div className="panel">
          <span className="eyebrow">Lo que juega a favor</span>
          <h3>Oportunidades</h3>
          <div className="wins">
            <ul>
              {oportunidades.map((o, i) => (
                <li key={i}>{o}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}

/**
 * Lo que la IA dice, literalmente.
 *
 * Rejilla de tarjetas: las citas son muy desiguales (de 10 a 65 caracteres) y
 * una cita corta estirada a todo el ancho rompe el ritmo una y otra vez.
 */
function Citas({ informe }: { informe: InformeCompleto }) {
  const citas = informe.informe_llm?.citas_destacadas ?? [];
  if (citas.length === 0) return null;

  return (
    <div className="panel">
      <span className="eyebrow">Textual</span>
      <h3>Lo que la IA dice de ti, literalmente</h3>
      {/* Orden: la pregunta arriba (contexto), la respuesta debajo y el modelo
          como fuente al pie. La respuesta conserva el tamaño grande: es lo que
          hay que leer, la pregunta solo la sitúa. */}
      <div className="rejilla">
        {citas.map((x, i) => (
          <blockquote className="quote" key={i}>
            {x.pregunta && <p className="q-p">{x.pregunta}</p>}
            <p className="q-t">{`“${entrecomillar(x.cita)}”`}</p>
            {x.modelo && <p className="q-m">{x.modelo}</p>}
          </blockquote>
        ))}
      </div>
    </div>
  );
}

/**
 * Plan del agente de informe y KPIs.
 *
 * A UNA columna a propósito: es una lista priorizada y numerada, y el orden es
 * el mensaje. En dos columnas el lector no sabe si leer en Z o en columna y la
 * secuencia se pierde. La tabla de KPIs también va a ancho completo: dos de sus
 * tres columnas son frases, no cifras.
 */
function PlanesYKpis({ informe }: { informe: InformeCompleto }) {
  const inf = informe.informe_llm ?? {};
  const plan = inf.plan_accion_llm ?? [];
  const kpis = inf.kpis_seguimiento ?? [];
  if (plan.length === 0 && kpis.length === 0) return null;

  return (
    <>
      {plan.length > 0 && (
        <div className="panel">
          <span className="eyebrow">Visibilidad en IA</span>
          <h3>Plan para ganar visibilidad</h3>
          {plan.map((a, i) => (
            <Accion a={a} i={i} key={i} />
          ))}
        </div>
      )}

      {kpis.length > 0 && (
        <div className="panel">
          <span className="eyebrow">Medición</span>
          <h3>KPIs para la próxima auditoría</h3>
          <Tabla
            id="tabla-kpis"
            titulo="Indicadores a vigilar, con su valor de hoy y el objetivo"
            cabeceras={["KPI", "Hoy", "Objetivo"]}
            filas={kpis.map((k) => {
              const ancla = anclaDeKpi(k.kpi || "");
              return {
                celdas: [
                  ancla ? (
                    <a href={`#${ancla}`} key="k">
                      {k.kpi}
                    </a>
                  ) : (
                    k.kpi || ""
                  ),
                  k.valor_actual || "–",
                  k.objetivo || "–",
                ],
              };
            })}
          />
        </div>
      )}
    </>
  );
}

/**
 * Cuota de voz: un donut total + uno por modelo, leyenda y la tabla COMPLETA de
 * empresas detectadas (las de una sola mención también informan: en un sector
 * fragmentado la cola larga dice quién más está en la conversación).
 */
function CuotaDeVoz({ informe }: { informe: InformeCompleto }) {
  const mapa = (informe.mapa_competitivo ?? []).filter((x) => x?.empresa);
  const consolidado = (informe.informe_llm?.conjunto_competitivo_consolidado ??
    []) as EmpresaMapa[];
  const cc = mapa.length ? mapa : consolidado;
  if (cc.length === 0) return null;

  const brand = (informe.meta?.brand || "").trim();
  const empresas = cc.map((x) => ({
    empresa: x.empresa || "",
    es_marca:
      !!x.es_marca ||
      (!!brand && String(x.empresa || "").toLowerCase() === brand.toLowerCase()),
    menciones: num(x.menciones) ?? 0,
    // El campo real es `menciones_por_modelo`; `por_modelo` es forma antigua.
    pm: x.menciones_por_modelo ?? x.por_modelo ?? null,
    modelos: x.modelos ?? [],
    amenaza: x.amenaza || "–",
  }));
  // La marca aparece siempre, aunque tenga cero menciones: es el dato.
  if (brand && !empresas.some((e) => e.es_marca)) {
    empresas.unshift({
      empresa: brand,
      es_marca: true,
      menciones: 0,
      pm: null,
      modelos: [],
      amenaza: "–",
    });
  }

  const valorEn = (e: (typeof empresas)[number], mk: ClaveModelo): number => {
    const v = e.pm?.[mk];
    if (typeof v === "number") return v;
    return e.modelos.includes(mk) ? 1 : 0;
  };

  const orden = [...empresas].sort(
    (a, b) =>
      (b.es_marca ? 1 : 0) - (a.es_marca ? 1 : 0) || b.menciones - a.menciones,
  );
  const TOP = 8;
  const color: Record<string, string> = {};
  let ci = 0;
  orden.slice(0, TOP).forEach((e) => {
    color[e.empresa] = e.es_marca
      ? "var(--accent)"
      : PALETA_DONUT[ci++ % PALETA_DONUT.length];
  });
  const resto = orden.slice(TOP);

  const porciones = (valor: (e: (typeof empresas)[number]) => number): PorcionDonut[] => {
    const sl: PorcionDonut[] = orden.slice(0, TOP).map((e) => ({
      nombre: e.empresa,
      marca: e.es_marca,
      valor: valor(e),
      color: color[e.empresa],
    }));
    const vr = resto.reduce((a, e) => a + valor(e), 0);
    if (vr > 0)
      sl.push({ nombre: "Otros", marca: false, valor: vr, color: "#5C5952" });
    return sl;
  };

  const VISIBLES = 5;
  const filas: FilaTabla[] = orden.map((e) => ({
    marca: e.es_marca,
    celdas: [
      e.empresa + (e.es_marca ? " · tu marca" : ""),
      String(e.menciones),
      ...MODELOS.map(([mk]) => String(valorEn(e, mk))),
      e.amenaza,
    ],
  }));

  return (
    // El titulo y la entradilla los pone ya la seccion que lo envuelve: aqui
    // repetirlos era decir dos veces lo mismo con dos jerarquias distintas.
    <div className="panel panel-dark">
      <div className="donuts">
        <Donut titulo="Total" porciones={porciones((e) => e.menciones)} />
        {MODELOS.map(([mk, ml]) => (
          <Donut
            key={mk}
            titulo={ml}
            porciones={porciones((e) => valorEn(e, mk))}
          />
        ))}
      </div>

      <div className="legend">
        {orden.slice(0, TOP).map((e, i) => (
          <span className={`leg${e.es_marca ? " leg-brand" : ""}`} key={i}>
            <i style={{ background: color[e.empresa] }} />
            <span>{e.empresa + (e.es_marca ? " (tu marca)" : "")}</span>
          </span>
        ))}
        {resto.length > 0 && (
          <span className="leg">
            <i style={{ background: "#5C5952" }} />
            <span>{`Otros (${resto.length})`}</span>
          </span>
        )}
      </div>

      {/* Cabeceras con los CUATRO modelos: el frontend original solo rotulaba
          tres y desplazaba la columna de amenaza. */}
      <Tabla
        cabeceras={[
          "Empresa",
          "Menciones",
          ...MODELOS.map(([, ml]) => ml),
          "Amenaza",
        ]}
        filas={filas}
        visibles={VISIBLES}
        etiquetaResto={(n) => `Ver las ${n} empresas restantes`}
      />
    </div>
  );
}

// ============================================================
// Las 4 dimensiones (con todo el detalle del sondeo dentro)
// ============================================================

const DIMENSIONES: Array<[
  "descubrimiento" | "competitivo" | "conocimiento" | "reputacion",
  string,
  string,
]> = [
  ["descubrimiento", "Descubrimiento", "Visibilidad espontánea"],
  ["competitivo", "Competitivo", "Posición frente a rivales"],
  ["conocimiento", "Conocimiento", "Qué saben y si es cierto"],
  ["reputacion", "Reputación", "Qué dicen ante una objeción"],
];

/** Estado de una dimensión a partir de su nota, para el punto de color. */
function estadoDim(v: number | null): "ok" | "warning" | "error" | "" {
  if (v === null) return "";
  return v >= 75 ? "ok" : v >= 50 ? "warning" : "error";
}

/**
 * Las 4 dimensiones en PESTAÑAS (como el mockup): una tab por dimensión con su
 * punto de estado, y el detalle debajo. Es un patrón tab/tabpanel accesible:
 * flechas del teclado mueven entre pestañas, cada panel se asocia a su tab.
 */
function Dimensiones({ informe }: { informe: InformeCompleto }) {
  const inf = informe.informe_llm ?? {};
  const bl = informe.sondeo_llm ?? {};
  const desglose = informe.score?.desglose_sov;

  const disponibles = DIMENSIONES.filter(([k]) => inf.analisis_por_dimension?.[k]);
  const [activa, setActiva] = useState(0);
  if (disponibles.length === 0) return null;
  const idx = Math.min(activa, disponibles.length - 1);

  const detalle = (k: string) => {
    if (k === "descubrimiento") return <DetalleDescubrimiento b={bl.descubrimiento} />;
    if (k === "competitivo") return <DetalleCompetitivo b={bl.competitivo} />;
    if (k === "conocimiento") return <DetalleConocimiento b={bl.conocimiento} />;
    if (k === "reputacion") return <DetalleReputacion b={bl.reputacion} />;
    return null;
  };

  return (
    <div className="panel">
      <div className="tabs" role="tablist" aria-label="Las 4 dimensiones">
        {disponibles.map(([k, eyebrow], i) => {
          const st = estadoDim(num(desglose?.[k]));
          return (
            <button
              key={k}
              type="button"
              role="tab"
              id={`tab-${k}`}
              aria-selected={i === idx}
              aria-controls={`panel-${k}`}
              tabIndex={i === idx ? 0 : -1}
              className={`tab${st ? ` st-${st}` : ""}`}
              onClick={() => setActiva(i)}
              onKeyDown={(e) => {
                if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                  e.preventDefault();
                  const d = e.key === "ArrowRight" ? 1 : -1;
                  setActiva((i + d + disponibles.length) % disponibles.length);
                }
              }}
            >
              <span className="d" aria-hidden="true" />
              {eyebrow}
            </button>
          );
        })}
      </div>

      {disponibles.map(([k, , titulo], i) => {
        const dd = inf.analisis_por_dimension?.[k];
        return (
          <div
            key={k}
            id={`panel-${k}`}
            role="tabpanel"
            aria-labelledby={`tab-${k}`}
            hidden={i !== idx}
            className="tab-panel"
          >
            <div className="card">
              <h3 className="sr-only">{titulo}</h3>
              {dd?.resumen && <p className="card-text">{dd.resumen}</p>}
              {dd?.implicacion_negocio && (
                <div className="dim-impl">
                  <b>Qué significa: </b>
                  {dd.implicacion_negocio}
                </div>
              )}
              {detalle(k)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function DetalleDescubrimiento({ b }: { b?: BloqueDescubrimiento }) {
  if (!b?.por_modelo) return null;
  return (
    <>
      {MODELOS.map(([mk, ml]) => {
        const pm = b.por_modelo?.[mk];
        if (!pm) return null;
        const t = num(pm.tasa_aparicion);
        return (
          <Metrica
            key={mk}
            etiqueta={ml}
            estado={
              t === null ? "no_verificable" : t >= 50 ? "ok" : t > 0 ? "warning" : "error"
            }
            valor={
              (t === null ? "–" : `${t}% de aparición`) +
              (pm.posicion_media ? ` · pos. ${pm.posicion_media}` : "")
            }
          />
        );
      })}
    </>
  );
}

function DetalleCompetitivo({ b }: { b?: BloqueCompetitivo }) {
  if (!b) return null;
  const ventajas = (b.ventajas_percibidas ?? []).slice(0, 5);
  const gaps = (b.gaps_atributos ?? []).slice(0, 5);
  const inesperados = b.competidores_inesperados ?? [];
  return (
    <>
      {(ventajas.length > 0 || gaps.length > 0) && (
        <>
          <div className="tags">
            {ventajas.map((a, i) => (
              <span className="tag tag-ok" key={`v${i}`}>
                {a}
              </span>
            ))}
            {gaps.map((a, i) => (
              <span className="tag tag-neg" key={`g${i}`}>
                {a}
              </span>
            ))}
          </div>
          <p className="m-detail">
            Verde: atributos que la IA te asigna. Rojo: los que asigna a rivales
            y a ti no.
          </p>
        </>
      )}
      {inesperados.length > 0 && (
        <Metrica
          etiqueta="Rivales que no esperabas"
          estado="warning"
          valor={String(inesperados.length)}
          detalle={inesperados.join(" · ")}
        />
      )}
    </>
  );
}

function DetalleConocimiento({ b }: { b?: BloqueConocimiento }) {
  if (!b) return null;
  const vf = b.verificacion_factual ?? [];
  const contradichas = vf.filter((x) => x.veredicto === "contradicha");
  const verificadas = vf.filter((x) => x.veredicto === "verificada");
  const alucinaciones = b.alucinaciones ?? [];
  const contradicciones = b.contradicciones_entre_modelos ?? [];
  const correctos = b.servicios_correctos ?? [];
  const erroneos = b.servicios_erroneos ?? [];
  const ausentes = b.servicios_ausentes ?? [];
  const ra = b.riesgo_alucinacion;

  return (
    <>
      {MODELOS.map(([mk, ml]) => {
        const n = b.nivel_conocimiento?.[mk];
        if (!n) return null;
        return (
          <Metrica
            key={mk}
            etiqueta={ml}
            estado={
              n === "alto" ? "ok" : n === "medio" ? "warning" : n === "nulo" ? "error" : "warning"
            }
            valor={n}
          />
        );
      })}

      {/* Cómo describe cada modelo a la marca, literal. */}
      {MODELOS.map(([mk, ml]) => {
        const d = b.descripcion_percibida?.[mk];
        return d ? (
          <p className="m-detail" key={`d${mk}`}>{`${ml}: “${d}”`}</p>
        ) : null;
      })}

      {vf.length > 0 && (
        <>
          <Metrica
            etiqueta="Contraste con tu web real"
            estado={contradichas.length ? "error" : "ok"}
            valor={`${verificadas.length} verificadas · ${contradichas.length} contradichas`}
          />
          {contradichas.slice(0, 3).map((x, i) => (
            <p className="m-detail" key={i}>
              {`✕ ${x.modelo ? `${x.modelo}: ` : ""}“${x.afirmacion}” — ${
                x.evidencia || x.fuente_real || "contradicho por la fuente real"
              }`}
            </p>
          ))}
        </>
      )}

      {ra?.nivel && (
        <Metrica
          etiqueta="Riesgo de alucinación"
          estado={ra.nivel === "bajo" ? "ok" : ra.nivel === "medio" ? "warning" : "error"}
          valor={ra.nivel}
          detalle={ra.detalle}
        />
      )}

      {alucinaciones.length > 0 && (
        <>
          <Metrica
            etiqueta="Datos inventados por la IA"
            estado="error"
            valor={String(alucinaciones.length)}
          />
          {alucinaciones.slice(0, 4).map((x, i) => (
            <p className="m-detail" key={i}>
              {`✕ ${x.modelo ? `${x.modelo}: ` : ""}“${x.afirmacion}”${
                x.gravedad ? ` · gravedad ${x.gravedad}` : ""
              }`}
            </p>
          ))}
        </>
      )}

      {contradicciones.length > 0 && (
        <>
          <p className="m-detail">Contradicciones entre modelos:</p>
          {contradicciones.slice(0, 3).map((x, i) => (
            <p className="m-detail" key={i}>{`· ${x}`}</p>
          ))}
        </>
      )}

      {(correctos.length > 0 || erroneos.length > 0) && (
        <>
          <div className="tags">
            {correctos.slice(0, 6).map((a, i) => (
              <span className="tag tag-ok" key={`c${i}`}>
                {a}
              </span>
            ))}
            {erroneos.slice(0, 6).map((a, i) => (
              <span className="tag tag-neg" key={`e${i}`}>
                {a}
              </span>
            ))}
          </div>
          <p className="m-detail">
            Verde: servicios que la IA te atribuye bien. Rojo: los que te
            atribuye por error.
          </p>
        </>
      )}

      {ausentes.length > 0 && (
        <Metrica
          etiqueta="Servicios que la IA no capta"
          estado="warning"
          valor={String(ausentes.length)}
          detalle={ausentes.join(" · ")}
        />
      )}
    </>
  );
}

function DetalleReputacion({ b }: { b?: BloqueReputacion }) {
  if (!b) return null;
  const pol = num(b.polaridad_global);
  const objeciones = b.objeciones_detectadas ?? [];
  const riesgos = b.riesgos_reputacionales ?? [];
  const negativos = b.atributos_negativos ?? [];
  const fuentesNeg = b.fuentes_negativas ?? [];
  const df = b.defensa_de_marca;

  return (
    <>
      {pol !== null && (
        <Metrica
          etiqueta="Polaridad global"
          estado={pol >= 0.3 ? "ok" : pol >= -0.2 ? "warning" : "error"}
          valor={`${pol > 0 ? "+" : ""}${pol.toFixed(2)}`}
        />
      )}
      {MODELOS.map(([mk, ml]) => {
        const s = b.sentimiento_por_modelo?.[mk];
        if (!s || typeof s.polaridad !== "number") return null;
        return (
          <Metrica
            key={mk}
            etiqueta={ml}
            estado={
              s.polaridad >= 0.3 ? "ok" : s.polaridad >= -0.2 ? "warning" : "error"
            }
            valor={`${s.polaridad > 0 ? "+" : ""}${s.polaridad.toFixed(2)}`}
            detalle={s.tono}
          />
        );
      })}
      {df && (
        <Metrica
          etiqueta="Defensa ante objeción"
          estado={df.estado}
          valor={df.deriva_a_competidor ? `Deriva a ${df.deriva_a_competidor}` : null}
          detalle={df.detalle}
        />
      )}
      {objeciones.length > 0 && (
        <>
          <Metrica
            etiqueta="Objeciones detectadas"
            estado="warning"
            valor={String(objeciones.length)}
          />
          {objeciones.slice(0, 5).map((x, i) => (
            <p className="m-detail" key={i}>
              {`· ${x.objecion}${x.modelo ? ` — ${x.modelo}` : ""}${
                x.respaldada_por_fuente
                  ? " (con fuente real)"
                  : " (sin fuente: posible alucinación negativa)"
              }`}
            </p>
          ))}
        </>
      )}
      {riesgos.length > 0 && (
        <>
          <p className="m-detail">Riesgos reputacionales:</p>
          {riesgos.slice(0, 5).map((x, i) => (
            <p className="m-detail" key={i}>{`· ${x}`}</p>
          ))}
        </>
      )}
      {negativos.length > 0 && (
        <div className="tags">
          {negativos.slice(0, 6).map((a, i) => (
            <span className="tag tag-neg" key={i}>
              {a}
            </span>
          ))}
        </div>
      )}
      {fuentesNeg.length > 0 && (
        <Metrica
          etiqueta="Fuentes negativas"
          estado="error"
          valor={String(fuentesNeg.length)}
          detalle={[
            ...new Set(
              fuentesNeg.map((u) =>
                String(u)
                  .replace(/^https?:\/\//, "")
                  .replace(/^www\./, "")
                  .split("/")[0],
              ),
            ),
          ]
            .slice(0, 5)
            .join(" · ")}
        />
      )}
    </>
  );
}

// ============================================================
// Fuentes y recomendaciones
// ============================================================

function FuentesDelSector({ informe }: { informe: InformeCompleto }) {
  const fs = informe.fuentes_sector;
  if (!fs?.disponible) return null;
  const dominios = (fs.dominios_citados ?? []).map((d) =>
    typeof d === "string" ? { dominio: d, veces: undefined } : d,
  );

  return (
    <div className="panel">
      <span className="eyebrow">Dónde busca el motor</span>
      <h3>Las fuentes que la IA consulta para tu sector</h3>
      <Metrica
        etiqueta="Tu dominio entre las fuentes citadas"
        estado={fs.cliente_citado ? "ok" : "error"}
        valor={fs.cliente_citado ? "Citado" : "No citado"}
        detalle={
          fs.cliente_citado
            ? undefined
            : "El motor respondió a las preguntas de tu sector sin citar tu web ni una vez. Estos son los dominios donde sí está buscando: ahí es donde hay que estar."
        }
      />
      {dominios.length > 0 && (
        <Desplegable
          titulo="Dominios que la IA cita en tu sector"
          cuenta={`${dominios.length} ${dominios.length === 1 ? "dominio" : "dominios"}`}
        >
          <div className="tags">
            {dominios.slice(0, 15).map((x, i) => (
              <span className="tag" key={i}>
                {`${x.dominio}${x.veces ? ` ×${x.veces}` : ""}`}
              </span>
            ))}
          </div>
        </Desplegable>
      )}
    </div>
  );
}

const CANALES_RECO: Array<[keyof RecomendacionesHuella, string]> = [
  ["directorios", "Directorios y reseñas"],
  ["listas_sector", "Listas y rankings del sector"],
  ["medios", "Medios y prensa"],
  ["foros", "Foros y comunidades"],
  ["otros", "Otros portales del sector"],
];

/**
 * Reduce un dominio a su "núcleo" comparable: sin protocolo, sin www, sin
 * subdominio y SIN TLD. Así `sortlist.es`, `sortlist.com`, `www.sortlist.com` y
 * `es.sortlist.com` colapsan todos a `sortlist`.
 *
 * BUG REAL que esto arregla: el informe listaba `sortlist.com` en
 * `ya_presente_en` y a la vez recomendaba darse de alta en `sortlist.es` como
 * "falta", porque la comparación era de cadena exacta. El propio informe decía
 * en otro bloque "Sortlist la lista repetidamente en rankings".
 */
export function nucleoDominio(d: string): string {
  const limpio = String(d || "")
    .toLowerCase()
    .trim()
    .replace(/^https?:\/\//, "")
    .replace(/\/.*$/, "")
    .replace(/^www\./, "");
  const partes = limpio.split(".").filter(Boolean);
  if (partes.length <= 1) return limpio;
  // Quita el TLD, incluidos los compuestos (.co.uk, .com.es...).
  const compuesto = /^(co|com|org|net|gob|gov|edu|ac)$/;
  let corte = partes.length - 1;
  if (partes.length >= 3 && compuesto.test(partes[partes.length - 2])) corte -= 1;
  // El nucleo es la ultima etiqueta antes del TLD (ignora subdominios).
  return partes[corte - 1] ?? partes[0];
}

function DondeGanarPresencia({
  recomendaciones,
  competidores,
}: {
  recomendaciones?: RecomendacionesHuella;
  competidores?: EmpresaMapa[];
}) {
  if (!recomendaciones?.disponible) return null;

  // Se compara por núcleo de dominio, no por cadena exacta.
  const yaPresente = new Set(
    (recomendaciones.ya_presente_en ?? []).map(nucleoDominio),
  );
  // Cruce que el workflow no hace: si un "sitio donde ganar presencia" es en
  // realidad la web de un competidor detectado, darse de alta ahí no es una
  // acción posible. Se marca en vez de presentarlo como una tarea más.
  const nucleosCompetidores = new Set(
    (competidores ?? [])
      .filter((c) => !c.es_marca && c.empresa)
      .map((c) => nucleoDominio(c.empresa.replace(/\s+/g, ""))),
  );

  const totalSitios = CANALES_RECO.reduce(
    (n, [clave]) =>
      n + ((recomendaciones[clave] as SitioRecomendado[] | undefined)?.length ?? 0),
    0,
  );

  return (
    <div className="panel">
      <span className="eyebrow">Plan de enlaces</span>
      <h3>Dónde ganar presencia para que la IA te cite</h3>
      {recomendaciones.resumen && (
        <p className="card-text">{recomendaciones.resumen}</p>
      )}
      <Desplegable
        titulo="Sitios donde ganar presencia"
        cuenta={`${totalSitios} ${totalSitios === 1 ? "sitio" : "sitios"}`}
      >
        {CANALES_RECO.map(([clave, lab]) => {
          const sitios = (recomendaciones[clave] as SitioRecomendado[]) ?? [];
          if (!sitios.length) return null;
          return (
            <div className="reco-group" key={String(clave)}>
            <div className="reco-cat">{lab}</div>
            {sitios.map((x, i) => {
              const dom = String(x.sitio ?? x.dominio ?? "");
              const nucleo = nucleoDominio(dom);
              const presente = yaPresente.has(nucleo);
              const esCompetidor = nucleosCompetidores.has(nucleo);
              const pr = String(x.prioridad || "media").toLowerCase();
              return (
                <div className="reco-item" key={i}>
                  <div className="reco-left">
                    <div className="reco-head">
                      {x.url ? (
                        <a
                          className="reco-site reco-link"
                          href={x.url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {dom}
                        </a>
                      ) : (
                        <span className="reco-site">{dom}</span>
                      )}
                      {/* Origen: la IA ya lo cita (dato duro) vs descubierto. */}
                      {x.fuente === "citado" && (
                        <span className="reco-src src-cita">La IA ya lo cita</span>
                      )}
                      {x.fuente === "descubierto" && (
                        <span className="reco-src src-desc">Descubierto</span>
                      )}
                      {esCompetidor ? (
                        <span className="marca-sitio m-competidor">
                          es un competidor
                        </span>
                      ) : presente ? (
                        <span className="marca-sitio m-presente">ya presente</span>
                      ) : (
                        <span className="marca-sitio m-falta">falta</span>
                      )}
                    </div>
                    {x.motivo && <span className="reco-why">{x.motivo}</span>}
                    {esCompetidor && (
                      <span className="reco-why sin-datos">
                        Este dominio es de una empresa que aparece en tu mapa
                        competitivo: no es un sitio donde puedas darte de alta.
                      </span>
                    )}
                  </div>
                  <span
                    className={`reco-pri pri-${
                      ["alta", "media", "baja"].includes(pr) ? pr : "media"
                    }`}
                  >
                    {pr}
                  </span>
                </div>
              );
            })}
          </div>
        );
        })}
      </Desplegable>
      {(recomendaciones.ya_presente_en ?? []).length > 0 && (
        <p className="m-detail">
          {`No se repiten los sitios donde ya tienes presencia: ${recomendaciones
            .ya_presente_en!.slice(0, 8)
            .join(" · ")}${
            recomendaciones.ya_presente_en!.length > 8 ? " …" : ""
          }`}
        </p>
      )}
    </div>
  );
}

// ============================================================
// Plan global
// ============================================================

function PlanGlobal({ sintesis }: { sintesis: InformeCompleto["sintesis"] }) {
  const plan = sintesis?.plan_accion ?? [];
  const quickWins = sintesis?.quick_wins ?? [];
  if (plan.length === 0 && quickWins.length === 0) return null;

  return (
    <div className="panel">
      <span className="eyebrow">Prioridades</span>
      <h3>Plan de acción global</h3>
      {plan.map((a, i) => (
        <Accion a={a} i={i} key={i} />
      ))}
      {quickWins.length > 0 && (
        <div className="wins">
          <h4>Quick wins · menos de un día</h4>
          <ul>
            {quickWins.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** Bloque plegable con el JSON crudo, para depurar. */
export function JsonCrudo({ informe }: { informe: unknown }) {
  const [abierto, setAbierto] = useState(false);
  return (
    <details
      className="gp-json"
      open={abierto}
      onToggle={(e) => setAbierto((e.target as HTMLDetailsElement).open)}
    >
      <summary>JSON crudo del informe</summary>
      {abierto && <pre>{JSON.stringify(informe, null, 2)}</pre>}
    </details>
  );
}

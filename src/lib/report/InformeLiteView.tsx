"use client";

import { useState } from "react";

import type {
  CompetidorMapa,
  EstadoPunto,
  InformeLite,
  PuntoSeoTecnico,
} from "@/lib/shared/report";
import { PALETA_COMPETIDORES, tono } from "./tono";
import "./report.css";

/**
 * Render del informe LITE. Portado con fidelidad de workflows/geopulse-lite2.html:
 * mismos colores, misma estructura, misma matemática del anillo y el donut.
 *
 * Principios que se respetan (docs/00):
 *  - Un valor `null` se pinta "–", no 0.
 *  - Estado `no_verificable` se muestra como "n/d" en gris, no como error.
 *  - Los `avisos` se muestran siempre, tal cual.
 *  - Las columnas de modelos salen de `aparicion.por_modelo`, no de `meta.modelos`
 *    (que en algún informe real viene incompleto).
 */
export function InformeLiteView({ informe }: { informe: InformeLite }) {
  const meta = informe.meta ?? ({} as InformeLite["meta"]);
  const nota = typeof informe.nota === "number" ? informe.nota : null;

  const AREAS: Array<[keyof InformeLite["por_area"], string]> = [
    ["seo_tecnico", "SEO técnico"],
    ["contenido", "Contenido"],
    ["sov", "Visibilidad IA"],
    ["huella", "Huella externa"],
  ];
  const pa = informe.por_area ?? ({} as InformeLite["por_area"]);

  const preguntas = informe.preguntas ?? [];
  const seoPuntos = informe.seo_tecnico?.puntos ?? [];
  const huella = informe.huella_digital;
  const aparicion = informe.aparicion;
  const mapa = Array.isArray(informe.mapa_competitivo)
    ? informe.mapa_competitivo
    : [];

  return (
    <div className="informe">
      {/* ===== 1. Diagnóstico global ===== */}
      <div className="dark">
        <div className="score-row">
          <div
            className="ring"
            style={{
              background:
                nota === null
                  ? "var(--dark-soft)"
                  : `conic-gradient(${tono(nota)} ${nota * 3.6}deg, var(--dark-soft) 0deg)`,
            }}
          >
            <div className="ring-in">
              <div className="ring-num">{nota === null ? "–" : nota}</div>
              <div className="ring-lbl">GEO Score</div>
            </div>
          </div>
          <div>
            <span className="eyebrow">Diagnóstico global</span>
            <h3>Así te ve hoy la inteligencia artificial</h3>
            <p>{informe.resumen_hallazgos || "Sin resumen para esta ejecución."}</p>
          </div>
        </div>
      </div>

      <div className="areas">
        {AREAS.map(([k, lab]) => {
          const v = typeof pa[k] === "number" ? (pa[k] as number) : null;
          return (
            <div className="tile" key={k}>
              <div className="t-lbl">{lab}</div>
              <div className="t-val" style={{ color: tono(v) }}>
                {v === null ? "–" : v}
              </div>
              <Barra v={v} />
            </div>
          );
        })}
      </div>

      {/* Avisos: si algo no se pudo medir, se dice */}
      {Array.isArray(informe.avisos) && informe.avisos.length > 0 && (
        <div className="avisos">
          {informe.avisos.map((a, i) => (
            <div className="aviso" key={i}>
              <span className="aviso-ico">!</span>
              <span>{a}</span>
            </div>
          ))}
        </div>
      )}

      {/* ===== 2. Preguntas lanzadas ===== */}
      {preguntas.length > 0 && (
        <>
          <Seccion
            eyebrow="Metodología"
            titulo="Las preguntas que hemos lanzado"
            sub="Cada pregunta se envía por separado a cada modelo. Despliega para leer qué respondió cada uno."
          />
          {preguntas.map((p, i) => (
            <Pregunta key={i} indice={i} pregunta={p} />
          ))}
        </>
      )}

      {/* ===== 3. SEO técnico ===== */}
      {seoPuntos.length > 0 && (
        <>
          <Seccion
            eyebrow="Cimientos"
            titulo="SEO técnico"
            sub="La base que decide si la IA puede llegar a tu web, leerla y entenderla."
          />
          {seoPuntos.map((p, i) => (
            <TarjetaPunto key={i} punto={p} />
          ))}
        </>
      )}

      {/* ===== 4. Huella digital ===== */}
      {huella && (huella.enlaces?.length > 0 || tieneEeatc(huella.eeatc)) && (
        <>
          <Seccion
            eyebrow="Off-page"
            titulo="Huella digital externa"
            sub="Tu presencia fuera de tu propia web: dónde te menciona internet y si la IA te reconoce como autoridad."
          />
          {huella.enlaces?.length > 0 && (
            <div className="card">
              <div className="pt-head">
                <div className="pt-l">
                  <span
                    className={`dot d-${huella.enlaces.length >= 5 ? "ok" : huella.enlaces.length >= 2 ? "warning" : "error"}`}
                  />
                  <span className="pt-title">Dónde te menciona internet</span>
                </div>
                <div className="pt-r">
                  <span className="pt-val">{huella.enlaces.length} fuentes</span>
                </div>
              </div>
              <div className="links">
                {huella.enlaces.slice(0, 10).map((x, i) => (
                  <a key={i} href={x.url} target="_blank" rel="noopener nofollow">
                    {x.dominio}
                  </a>
                ))}
              </div>
            </div>
          )}
          {tieneEeatc(huella.eeatc) && <Eeatc eeatc={huella.eeatc} />}
        </>
      )}

      {/* ===== 5. Visibilidad en la IA ===== */}
      {((aparicion?.por_modelo?.length ?? 0) > 0 || mapa.length > 0) && (
        <>
          <Seccion
            eyebrow="Motores generativos"
            titulo="Tu visibilidad en las respuestas de la IA"
            sub="Dónde apareces cuando los modelos responden sobre tu sector, y quién ocupa tu espacio."
          />
          <div className="diag">
            {aparicion?.por_modelo?.length > 0 && preguntas.length > 0 && (
              <MatrizAparicion aparicion={aparicion} preguntas={preguntas} />
            )}
            {mapa.length > 0 && <Competitivo mapa={mapa} />}
          </div>
        </>
      )}
    </div>
  );
}

function Barra({ v, alto }: { v: number | null; alto?: string }) {
  return (
    <div className="bar" style={alto ? { height: alto } : undefined}>
      <i
        style={{
          width: `${v === null ? 0 : Math.max(0, Math.min(100, v))}%`,
          background: tono(v),
        }}
      />
    </div>
  );
}

function Seccion({
  eyebrow,
  titulo,
  sub,
}: {
  eyebrow: string;
  titulo: string;
  sub?: string;
}) {
  return (
    <div className="sec">
      <span className="eyebrow">{eyebrow}</span>
      <h2>{titulo}</h2>
      {sub && <p>{sub}</p>}
    </div>
  );
}

function etiquetaEstado(estado: EstadoPunto): string {
  return estado === "no_verificable" ? "n/d" : estado;
}

function TarjetaPunto({ punto }: { punto: PuntoSeoTecnico }) {
  return (
    <div className="card">
      <div className="pt-head">
        <div className="pt-l">
          <span className={`dot d-${punto.estado}`} />
          <span className="pt-title">{punto.titulo}</span>
        </div>
        <div className="pt-r">
          {punto.valor && <span className="pt-val">{punto.valor}</span>}
          <span className={`pill p-${punto.estado}`}>
            {etiquetaEstado(punto.estado)}
          </span>
        </div>
      </div>
      {punto.detalle && <div className="pt-detail">{punto.detalle}</div>}
      {Array.isArray(punto.entidades) && punto.entidades.length > 0 && (
        <>
          <div className="pt-detail">
            Conceptos núcleo que la IA extrae de tu contenido:
          </div>
          <div className="tags">
            {punto.entidades.slice(0, 10).map((e, i) => (
              <span className={`tag${i < 2 ? " tag-accent" : ""}`} key={i}>
                {e}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function tieneEeatc(ee: InformeLite["huella_digital"]["eeatc"]): boolean {
  const claves = [
    "experiencia",
    "expertise",
    "autoridad",
    "confianza",
    "citabilidad",
  ] as const;
  return claves.some((k) => typeof ee?.[k] === "number");
}

function Eeatc({ eeatc }: { eeatc: InformeLite["huella_digital"]["eeatc"] }) {
  const EE: Array<[keyof typeof eeatc, string]> = [
    ["experiencia", "Experiencia"],
    ["expertise", "Expertise"],
    ["autoridad", "Autoridad"],
    ["confianza", "Confianza"],
    ["citabilidad", "Citabilidad"],
  ];
  const g = typeof eeatc.puntuacion_global === "number" ? eeatc.puntuacion_global : null;
  const dotClase =
    g === null ? "no_verificable" : g >= 70 ? "ok" : g >= 40 ? "warning" : "error";
  return (
    <div className="card">
      <div className="pt-head">
        <div className="pt-l">
          <span className={`dot d-${dotClase}`} />
          <span className="pt-title">E-E-A-T-C</span>
        </div>
      </div>
      {EE.map(([k, lab]) => {
        const v = typeof eeatc[k] === "number" ? (eeatc[k] as number) : null;
        return (
          <div className="ee-row" key={k}>
            <div className="ee-lbl">{lab}</div>
            <div className="ee-bar">
              <i style={{ width: `${v === null ? 0 : v}%`, background: tono(v) }} />
            </div>
            <div className="ee-val" style={{ color: tono(v) }}>
              {v === null ? "–" : `${v}/100`}
            </div>
          </div>
        );
      })}
      <div className="ee-global">
        <span>Puntuación global</span>
        <b style={{ color: tono(g) }}>{g === null ? "–" : `${g} / 100`}</b>
      </div>
    </div>
  );
}

function Pregunta({
  indice,
  pregunta,
}: {
  indice: number;
  pregunta: InformeLite["preguntas"][number];
}) {
  const [abierto, setAbierto] = useState(false);
  const respuestas = pregunta.respuestas ?? [];
  const hits = respuestas.filter((x) => x.aparece).length;
  const validas = respuestas.filter((x) => x.respondio).length;
  const badge = hits === 0 ? "b-no" : hits === validas ? "b-yes" : "b-part";

  return (
    <div className="q-item">
      <button
        type="button"
        className="q-head"
        onClick={() => setAbierto((o) => !o)}
        aria-expanded={abierto}
      >
        <div>
          <span className="q-num">Pregunta {indice + 1}</span>
          <span className="q-q">{pregunta.pregunta}</span>
        </div>
        <div className="q-meta">
          <span className={`q-badge ${badge}`}>
            {hits}/{validas || respuestas.length}
          </span>
          <span className="q-pm">{abierto ? "–" : "+"}</span>
        </div>
      </button>
      <div className={`q-body${abierto ? " open" : ""}`}>
        <div className="q-inner">
          {respuestas.map((m, i) => (
            <div className="q-model" key={i}>
              <div className="q-model-h">
                <span className="q-model-n">{m.modelo}</span>
                <span className={`q-badge ${m.aparece ? "b-yes" : "b-no"}`}>
                  {m.aparece ? "Te menciona" : "No te menciona"}
                </span>
              </div>
              <div className="q-ans">
                {m.respuesta ||
                  (m.respondio
                    ? "(sin contenido)"
                    : "El modelo no respondió en esta ejecución.")}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function MatrizAparicion({
  aparicion,
  preguntas,
}: {
  aparicion: NonNullable<InformeLite["aparicion"]>;
  preguntas: InformeLite["preguntas"];
}) {
  return (
    <table className="matrix">
      <thead>
        <tr>
          <th>Pregunta</th>
          {aparicion.por_modelo.map((m) => (
            <th key={m.clave}>{m.modelo}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {preguntas.map((p, i) => {
          const q = String(p.pregunta);
          return (
            <tr key={i}>
              <td>
                P{i + 1} · {q.slice(0, 56)}
                {q.length > 56 ? "…" : ""}
              </td>
              {aparicion.por_modelo.map((m) => {
                const celda = m.celdas?.[i] ?? { respondio: false, aparece: false };
                const clase = !celda.respondio
                  ? "mk-na"
                  : celda.aparece
                    ? "mk-yes"
                    : "mk-no";
                const simbolo = !celda.respondio ? "–" : celda.aparece ? "✓" : "✕";
                return (
                  <td key={m.clave}>
                    <span className={`mk ${clase}`}>{simbolo}</span>
                  </td>
                );
              })}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Competitivo({ mapa }: { mapa: CompetidorMapa[] }) {
  const total = mapa.reduce((a, x) => a + (x.menciones || 0), 0);
  return (
    <div className="donut-wrap">
      <Donut mapa={mapa} total={total} />
      <div className="legend">
        {mapa.slice(0, 7).map((x, i) => {
          const pct = total > 0 ? Math.round(((x.menciones || 0) / total) * 100) : 0;
          return (
            <div className="lg" key={i}>
              <i
                style={{
                  background: x.es_marca
                    ? "var(--accent)"
                    : PALETA_COMPETIDORES[i % PALETA_COMPETIDORES.length],
                }}
              />
              <span>
                {x.empresa}
                {x.es_marca ? " (tu marca)" : ""}
              </span>
              <b>{pct}%</b>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Donut({ mapa, total }: { mapa: CompetidorMapa[]; total: number }) {
  const R = 15.9155;
  const CIRC = 2 * Math.PI * R;
  let off = 0;
  const segmentos: React.ReactNode[] = [];
  if (total > 0) {
    mapa.forEach((x, i) => {
      const frac = (x.menciones || 0) / total;
      if (frac <= 0) return;
      segmentos.push(
        <circle
          key={i}
          cx="21"
          cy="21"
          r={R}
          fill="none"
          stroke={
            x.es_marca
              ? "#EF3B2D"
              : PALETA_COMPETIDORES[i % PALETA_COMPETIDORES.length]
          }
          strokeWidth="6"
          strokeDasharray={`${(frac * CIRC).toFixed(3)} ${((1 - frac) * CIRC).toFixed(3)}`}
          strokeDashoffset={(CIRC * 0.25 - off * CIRC).toFixed(3)}
        />,
      );
      off += frac;
    });
  }
  const marca = mapa.find((x) => x.es_marca);
  const pct =
    total > 0 && marca ? Math.round((marca.menciones / total) * 100) : 0;

  return (
    <svg viewBox="0 0 42 42" width="148" height="148">
      <circle
        cx="21"
        cy="21"
        r={R}
        fill="none"
        stroke="#F0EEEA"
        strokeWidth="6"
      />
      {segmentos}
      <text
        x="21"
        y="21.5"
        textAnchor="middle"
        fontSize="7"
        fontWeight="800"
        fontFamily="Manrope,sans-serif"
        fill={pct > 0 ? "#121212" : "#9C9791"}
      >
        {pct}%
      </text>
      <text
        x="21"
        y="26"
        textAnchor="middle"
        fontSize="2.6"
        fontWeight="600"
        fontFamily="Inter,sans-serif"
        fill="#9C9791"
        letterSpacing="0.2"
      >
        {pct > 0 ? "TU CUOTA" : "NO APARECES"}
      </text>
    </svg>
  );
}

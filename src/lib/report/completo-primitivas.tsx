"use client";

/**
 * Primitivas del informe COMPLETO, portadas de las funciones `metric`, `card`,
 * `tabla`, `accion` y `donut` de workflows/geopulse-frontend-brandevs.html.
 *
 * Se replican con el MISMO marcado y las MISMAS clases que el original, porque
 * la hoja portada (report-completo.css) espera esa estructura exacta. Cambiar
 * un nombre de clase aquí rompe el estilo en silencio.
 */

import { useState } from "react";

export type EstadoBruto = string | null | undefined;
export type EstadoNorm = "ok" | "warning" | "error" | "no_verificable";

const ICONO: Record<EstadoNorm, string> = {
  ok: "✓",
  warning: "!",
  error: "✕",
  no_verificable: "–",
};

export function normEstado(e: EstadoBruto): EstadoNorm {
  return e === "ok" || e === "warning" || e === "error" ? e : "no_verificable";
}

function claseValor(e: EstadoBruto): string {
  const n = normEstado(e);
  return n === "no_verificable" ? "v-muted" : `v-${n}`;
}

/**
 * Estado agregado de una tarjeta: manda el peor de sus comprobaciones. Si no hay
 * ninguna medible devuelve 'muted' — gris, no verde: sin datos no es aprobado.
 */
export function peor(estados: EstadoBruto[]): "ok" | "warning" | "error" | "muted" {
  const e = estados.map(normEstado);
  if (e.includes("error")) return "error";
  if (e.includes("warning")) return "warning";
  if (e.includes("ok")) return "ok";
  return "muted";
}

/** Una fila etiqueta ↔ valor, con detalle y fuentes opcionales. */
export function Metrica({
  etiqueta,
  estado,
  valor,
  detalle,
  fuentes,
}: {
  etiqueta: string;
  estado?: EstadoBruto;
  valor?: string | null;
  detalle?: string | null;
  fuentes?: unknown;
}) {
  // Un valor largo (p. ej. la lista de tipos de schema) no cabe en la fila
  // etiqueta↔valor sin aplastar la etiqueta: baja a su propia línea.
  const largo = typeof valor === "string" && valor.length > 32;
  const enlaces = (Array.isArray(fuentes) ? fuentes : [])
    .filter((u): u is string => typeof u === "string" && /^https?:\/\//i.test(u))
    .slice(0, 4);

  return (
    <div className="metric">
      <div className={`m-row${largo ? " m-row-stack" : ""}`}>
        <span className="m-lbl">{etiqueta}</span>
        <span className={`m-val ${claseValor(estado)}`}>
          {ICONO[normEstado(estado)]}{" "}
          {valor || normEstado(estado).replace("_", " ")}
        </span>
      </div>
      {detalle && <p className="m-detail">{detalle}</p>}
      {enlaces.length > 0 && (
        <div className="srcs">
          {enlaces.map((u, i) => (
            <a key={i} href={u} target="_blank" rel="noopener noreferrer">
              {u.replace(/^https?:\/\//, "").slice(0, 52)}
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

/** Tarjeta con antetítulo, punto de estado y título. */
export function Ficha({
  eyebrow,
  titulo,
  estado,
  sinPunto,
  children,
}: {
  eyebrow: string;
  titulo: string;
  estado?: "ok" | "warning" | "error" | "muted";
  /** Las tarjetas de dimensión del original no llevan punto de estado. */
  sinPunto?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className="card">
      <div className="card-top">
        <span className="card-eyebrow">{eyebrow}</span>
        {!sinPunto && <span className={`dot dot-${estado || "muted"}`} />}
      </div>
      <h3>{titulo}</h3>
      {children}
    </div>
  );
}

export interface FilaTabla {
  celdas: Array<string | number>;
  marca?: boolean;
}

/**
 * Tabla del informe. En móvil el CSS convierte cada fila en una ficha apilada
 * usando `data-label`, por eso cada celda lo lleva.
 *
 * Con `visibles` se ocultan las filas sobrantes tras un botón: la tabla de
 * competidores lista TODAS las empresas detectadas (incluidas las de una sola
 * mención, que también informan) sin ocupar tres pantallas de entrada.
 */
export function Tabla({
  cabeceras,
  filas,
  visibles,
  etiquetaResto,
}: {
  cabeceras: string[];
  filas: FilaTabla[];
  visibles?: number;
  etiquetaResto?: (n: number) => string;
}) {
  const [abierta, setAbierta] = useState(false);
  const ocultas = visibles && filas.length > visibles ? filas.length - visibles : 0;

  return (
    <>
      <div className="tw">
        <table>
          <thead>
            <tr>
              {cabeceras.map((h, i) => (
                <th key={i}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filas.map((f, i) => {
              const oculta = !!visibles && i >= visibles;
              return (
                <tr
                  key={i}
                  className={
                    [
                      f.marca ? "brand" : "",
                      oculta ? "hide" : "",
                      oculta && abierta ? "show" : "",
                    ]
                      .filter(Boolean)
                      .join(" ") || undefined
                  }
                >
                  {f.celdas.map((c, j) => (
                    <td
                      key={j}
                      className={j === 0 ? "strong" : undefined}
                      data-label={cabeceras[j] || ""}
                    >
                      {c}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {ocultas > 0 && (
        <button
          type="button"
          className="toggle"
          onClick={() => setAbierta((x) => !x)}
        >
          <span>
            {abierta
              ? "Ver menos"
              : etiquetaResto
                ? etiquetaResto(ocultas)
                : `Ver las ${ocultas} filas restantes`}
          </span>
          <span className="pm">{abierta ? "–" : "+"}</span>
        </button>
      )}
    </>
  );
}

export interface AccionInforme {
  prioridad?: string;
  area?: string;
  esfuerzo?: string;
  accion?: string;
  por_que?: string;
  evidencia?: string;
  impacto_esperado?: string;
}

/** Una acción del plan: número con color de prioridad + cuerpo. */
export function Accion({ a, i }: { a: AccionInforme; i: number }) {
  const pr = String(a.prioridad || "media").toLowerCase();
  const prio = ["alta", "media", "baja"].includes(pr) ? pr : "media";
  const tag = a.area || (a.esfuerzo ? `Esfuerzo ${a.esfuerzo}` : null);
  return (
    <div className="act">
      <span className={`num p-${prio}`}>{i + 1}</span>
      <div className="act-b">
        {tag && <div className="a-tag">{`${tag} · Prioridad ${prio}`}</div>}
        <div className="a-txt">{a.accion || ""}</div>
        {a.por_que && <div className="a-sub">{a.por_que}</div>}
        {a.evidencia && <div className="a-ev">{`“${a.evidencia}”`}</div>}
        {a.impacto_esperado && (
          <div className="a-sub">{`→ ${a.impacto_esperado}`}</div>
        )}
      </div>
    </div>
  );
}

/**
 * Paleta del donut sobre fondo oscuro, tal cual el original. La marca no usa
 * esta paleta: va siempre en el acento de BranDevs.
 */
export const PALETA_DONUT = [
  "#EFEBE3",
  "#C3BCAE",
  "#9A9284",
  "#B8946F",
  "#7A8A90",
  "#D6CFC2",
  "#A19889",
  "#68757B",
];

export interface PorcionDonut {
  nombre: string;
  marca: boolean;
  valor: number;
  color: string;
}

/**
 * Donut de cuota de voz. El porcentaje del centro es SIEMPRE el de la marca:
 * si es 0 se dice "no apareces" en gris, no se deja el hueco en blanco.
 */
export function Donut({
  titulo,
  porciones,
}: {
  titulo: string;
  porciones: PorcionDonut[];
}) {
  const S = 150;
  const R = 56;
  const CX = 75;
  const CY = 75;
  const C = 2 * Math.PI * R;

  const total = porciones.reduce((a, p) => a + p.valor, 0);
  const marca = porciones.find((p) => p.marca);
  const pct = total ? Math.round(((marca ? marca.valor : 0) / total) * 100) : 0;

  let off = 0;
  const arcos = porciones
    .filter((p) => p.valor > 0 && total > 0)
    .map((p, i) => {
      const len = (p.valor / total) * C;
      const dashoffset = -off;
      off += len;
      return (
        <circle
          key={i}
          cx={CX}
          cy={CY}
          r={R}
          fill="none"
          stroke={p.color}
          strokeWidth={p.marca ? 19 : 15}
          strokeDasharray={`${len} ${C - len}`}
          strokeDashoffset={String(dashoffset)}
          transform={`rotate(-90 ${CX} ${CY})`}
        >
          <title>{`${p.nombre}: ${p.valor} (${Math.round((p.valor / total) * 100)}%)`}</title>
        </circle>
      );
    });

  return (
    <div className="donut">
      <div className="donut-t">{titulo}</div>
      <svg viewBox={`0 0 ${S} ${S}`}>
        <circle
          cx={CX}
          cy={CY}
          r={R}
          fill="none"
          stroke="#3D3B37"
          strokeWidth={15}
        />
        {arcos}
        <text
          x={CX}
          y={CY - 1}
          textAnchor="middle"
          dominantBaseline="middle"
          className="d-pct"
          fill={!total ? "#7C776F" : "#FF6152"}
        >
          {total ? `${pct}%` : "–"}
        </text>
        <text x={CX} y={CY + 18} textAnchor="middle" className="d-lbl">
          {!total ? "sin datos" : pct ? "tu marca" : "no apareces"}
        </text>
      </svg>
    </div>
  );
}

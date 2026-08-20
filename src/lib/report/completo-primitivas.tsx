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

/**
 * El estado, en palabras.
 *
 * El glifo y el color no bastan: un lector de pantalla anuncia "✓" como "marca
 * de verificación" y con daltonismo rojo-verde el ok y el error son el mismo
 * tono. Cada estado viaja además como texto para lectores de pantalla.
 */
export const ETIQUETA_ESTADO: Record<EstadoNorm, string> = {
  ok: "Correcto",
  warning: "Aviso",
  error: "Error",
  no_verificable: "No se pudo medir",
};

/** Glifo decorativo + estado en texto solo para lectores de pantalla. */
export function EstadoAccesible({ estado }: { estado?: EstadoBruto }) {
  const n = normEstado(estado);
  return (
    <>
      <span aria-hidden="true">{ICONO[n]}</span>
      <span className="sr-only">{ETIQUETA_ESTADO[n]}. </span>
    </>
  );
}

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
    // El estado va en el contenedor para pintar el carril de color de la
    // izquierda (::before en el CSS): antes solo estaba en el valor.
    <div className={`metric st-${normEstado(estado)}`}>
      <div className={`m-row${largo ? " m-row-stack" : ""}`}>
        <span className="m-lbl">{etiqueta}</span>
        <span className={`m-val ${claseValor(estado)}`}>
          <EstadoAccesible estado={estado} />{" "}
          {valor || ETIQUETA_ESTADO[normEstado(estado)].toLowerCase()}
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
  // El punto de estado llevaba la información SOLO en su color de fondo: para un
  // lector de pantalla no existía y con daltonismo el ok y el error coinciden.
  const glifo: Record<string, string> = {
    ok: "✓",
    warning: "!",
    error: "✕",
    muted: "–",
  };
  const palabra: Record<string, string> = {
    ok: "Correcto",
    warning: "Aviso",
    error: "Error",
    muted: "No se pudo medir",
  };
  const e = estado || "muted";

  return (
    <div className="card">
      <div className="card-top">
        <span className="card-eyebrow">{eyebrow}</span>
        {!sinPunto && (
          <span className={`dot dot-${e}`}>
            <span aria-hidden="true">{glifo[e]}</span>
            <span className="sr-only">{`Estado: ${palabra[e]}`}</span>
          </span>
        )}
      </div>
      <h3>{titulo}</h3>
      {children}
    </div>
  );
}

/**
 * Una sección de primer nivel del informe: destino de ancla del índice.
 *
 * Es lo que hace posible "las secciones hipervinculadas": antes todo el render
 * eran `<div>` sin un solo `id`, así que no había a dónde enlazar. El `h2` lleva
 * el id que lo etiqueta y el `tabIndex={-1}` permite que el foco aterrice aquí
 * al saltar desde el índice (si no, el lector de pantalla sigue donde estaba).
 */
export function SeccionInforme({
  id,
  eyebrow,
  titulo,
  sub,
  children,
}: {
  id: string;
  eyebrow: string;
  titulo: string;
  sub?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-t`} tabIndex={-1}>
      <div className="sec">
        <span className="eyebrow">{eyebrow}</span>
        <h2 id={`${id}-t`}>{titulo}</h2>
        {sub && <p>{sub}</p>}
      </div>
      {children}
    </section>
  );
}

/**
 * Índice navegable. En pantalla ancha es un sidebar fijo a la izquierda
 * (numerado, con el GEO Score al pie), como el mockup. En movil, una tira de
 * píldoras sobre el contenido.
 */
export function IndiceInforme({
  entradas,
  nota,
}: {
  entradas: Array<{ texto: string; ancla: string }>;
  /** GEO Score, para el mini-anillo del pie. null = no se pinta. */
  nota?: number | null;
}) {
  return (
    <nav className="indice" aria-labelledby="indice-t">
      <h2 id="indice-t">En este informe</h2>
      <ol>
        {entradas.map((e) => (
          <li key={e.ancla}>
            <a href={`#${e.ancla}`}>{e.texto}</a>
          </li>
        ))}
      </ol>
      {typeof nota === "number" && <MiniScore nota={nota} />}
    </nav>
  );
}

/** Mini-anillo del GEO Score al pie del sidebar. */
function MiniScore({ nota }: { nota: number }) {
  const R = 20;
  const C = 2 * Math.PI * R;
  const color = nota >= 75 ? "var(--ok)" : nota >= 50 ? "var(--warn)" : "var(--err)";
  return (
    <div className="sb-score">
      <div className="sb-score-ring">
        <svg width="48" height="48" viewBox="0 0 48 48" aria-hidden="true">
          <circle cx="24" cy="24" r={R} fill="none" stroke="var(--line-c)" strokeWidth="4" />
          <circle
            cx="24"
            cy="24"
            r={R}
            fill="none"
            stroke={color}
            strokeWidth="4"
            strokeLinecap="round"
            strokeDasharray={C.toFixed(1)}
            strokeDashoffset={(C * (1 - Math.max(0, Math.min(100, nota)) / 100)).toFixed(1)}
            transform="rotate(-90 24 24)"
          />
        </svg>
        <div className="sb-score-n">{nota}</div>
      </div>
      <div className="sb-score-l">
        GEO Score
        <b>{nota} / 100</b>
      </div>
    </div>
  );
}

/**
 * Bloque desplegable (patrón `<details>` del mockup). Es HTML nativo, así que es
 * accesible por teclado y lector de pantalla sin JavaScript, y en la impresión a
 * PDF se fuerza abierto desde el CSS. Arranca CERRADO por defecto (por petición:
 * el informe abre compacto y el usuario despliega lo que quiera ver).
 */
export function Desplegable({
  titulo,
  cuenta,
  abierto = false,
  children,
}: {
  titulo: string;
  /** Contador que va a la derecha del título ("13 páginas"). */
  cuenta?: string;
  abierto?: boolean;
  children: React.ReactNode;
}) {
  return (
    <details className="disc" open={abierto}>
      <summary>
        <span className="chev" aria-hidden="true">
          ▸
        </span>
        {titulo}
        {cuenta && <span className="count">{cuenta}</span>}
      </summary>
      <div className="disc-body">{children}</div>
    </details>
  );
}

export interface FilaTabla {
  /**
   * El contenido de cada celda. Admite nodos, no solo texto, porque hay tablas
   * cuya primera columna es un enlace a la sección que explica ese dato.
   */
  celdas: React.ReactNode[];
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
  titulo,
  id,
}: {
  cabeceras: string[];
  filas: FilaTabla[];
  visibles?: number;
  etiquetaResto?: (n: number) => string;
  /** Se pinta como <caption> oculto: con 7 columnas hace falta contexto. */
  titulo?: string;
  id?: string;
}) {
  const [abierta, setAbierta] = useState(false);
  const ocultas = visibles && filas.length > visibles ? filas.length - visibles : 0;
  const idTabla = id ?? "tabla";

  return (
    <>
      <div className="tw">
        <table id={idTabla}>
          {titulo && <caption className="sr-only">{titulo}</caption>}
          <thead>
            <tr>
              {cabeceras.map((h, i) => (
                <th key={i} scope="col">
                  {h}
                </th>
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
          aria-expanded={abierta}
          aria-controls={idTabla}
          onClick={() => setAbierta((x) => !x)}
        >
          <span>
            {abierta
              ? "Ver menos"
              : etiquetaResto
                ? etiquetaResto(ocultas)
                : `Ver las ${ocultas} filas restantes`}
          </span>
          <span className="pm" aria-hidden="true">
            {abierta ? "–" : "+"}
          </span>
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

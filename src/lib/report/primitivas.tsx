"use client";

/**
 * Primitivas de render compartidas por el informe LITE y el COMPLETO.
 * Portadas de los frontends de referencia; misma paleta y misma matemática.
 */

import type { EstadoPunto } from "@/lib/shared/report";
import { tono } from "./tono";

/** Anillo del GEO Score. `null` se pinta "–" en gris: no medible ≠ cero. */
export function ScoreRing({ nota }: { nota: number | null }) {
  return (
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
  );
}

export function Barra({ v }: { v: number | null }) {
  return (
    <div className="bar">
      <i
        style={{
          width: `${v === null ? 0 : Math.max(0, Math.min(100, v))}%`,
          background: tono(v),
        }}
      />
    </div>
  );
}

/** Las 4 áreas de cabecera. Mismas claves y etiquetas en LITE y COMPLETO. */
export const AREAS: Array<[string, string]> = [
  ["seo_tecnico", "SEO técnico"],
  ["contenido", "Contenido"],
  ["sov", "Visibilidad IA"],
  ["huella", "Huella externa"],
];

export function AreaTiles({
  por_area,
  enlaces,
}: {
  por_area: Record<string, number | null | undefined>;
  /**
   * Ancla a la que salta cada área, por clave. Convierte cada nota en un enlace
   * al bloque que la explica: ver un 34 y no poder llegar al porqué obliga a
   * buscarlo a mano en un informe de 20 pantallas.
   *
   * Opcional: el informe LITE no tiene secciones con ancla y se queda igual.
   */
  enlaces?: Record<string, string>;
}) {
  return (
    <div className="areas">
      {AREAS.map(([k, lab]) => {
        const v = typeof por_area?.[k] === "number" ? (por_area[k] as number) : null;
        const ancla = enlaces?.[k];
        const dentro = (
          <>
            <div className="t-lbl">{lab}</div>
            <div className="t-val" style={{ color: tono(v) }}>
              {v === null ? "–" : v}
              <span className="sr-only">
                {v === null ? " sin datos" : " sobre 100"}
              </span>
            </div>
            <Barra v={v} />
          </>
        );
        return ancla ? (
          <a className="tile tile-link" href={`#${ancla}`} key={k}>
            {dentro}
          </a>
        ) : (
          <div className="tile" key={k}>
            {dentro}
          </div>
        );
      })}
    </div>
  );
}

export function Seccion({
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

export function Avisos({ avisos }: { avisos?: string[] }) {
  if (!Array.isArray(avisos) || avisos.length === 0) return null;
  return (
    <div className="avisos">
      {avisos.map((a, i) => (
        <div className="aviso" key={i}>
          <span className="aviso-ico">!</span>
          <span>{a}</span>
        </div>
      ))}
    </div>
  );
}

/** `no_verificable` se muestra como "n/d" en gris: no se pudo medir, no es un fallo. */
export function PillEstado({ estado }: { estado?: EstadoPunto | string }) {
  const e = (estado ?? "no_verificable") as string;
  return (
    <span className={`pill p-${e}`}>{e === "no_verificable" ? "n/d" : e}</span>
  );
}

export function DotEstado({ estado }: { estado?: EstadoPunto | string }) {
  return <span className={`dot d-${estado ?? "no_verificable"}`} />;
}

/** Tarjeta genérica con cabecera de estado. */
export function Tarjeta({
  titulo,
  estado,
  valor,
  children,
}: {
  titulo: string;
  estado?: EstadoPunto | string;
  valor?: string | null;
  children?: React.ReactNode;
}) {
  return (
    <div className="card">
      <div className="pt-head">
        <div className="pt-l">
          <DotEstado estado={estado} />
          <span className="pt-title">{titulo}</span>
        </div>
        <div className="pt-r">
          {valor && <span className="pt-val">{valor}</span>}
          {estado && <PillEstado estado={estado} />}
        </div>
      </div>
      {children}
    </div>
  );
}

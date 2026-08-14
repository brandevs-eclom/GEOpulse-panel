import { ESTILO_ESTADO } from "@/lib/client/estado";
import type { RunEstado } from "@/lib/shared/status";

export function EstadoBadge({ estado }: { estado: RunEstado }) {
  const s = ESTILO_ESTADO[estado];
  // pendiente/en_curso siguen vivos: el punto parpadea para indicarlo.
  const vivo = estado === "en_curso" || estado === "pendiente";
  return (
    <span className="gp-badge" style={{ background: s.bg, color: s.color }}>
      <span
        className={`gp-dot${vivo ? " gp-pulse" : ""}`}
        style={{ background: s.color }}
      />
      {s.label}
    </span>
  );
}

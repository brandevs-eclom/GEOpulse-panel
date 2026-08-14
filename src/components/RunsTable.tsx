"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { fetchRuns } from "@/lib/client/api";
import type { RunListItem } from "@/lib/shared/dto";
import { ETIQUETA_TIPO, esEstadoEnVuelo } from "@/lib/shared/status";
import { EstadoBadge } from "./EstadoBadge";

function fecha(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("es-ES", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
}

/**
 * `esAdmin` decide si se pinta la columna "Lanzado por". Un miembro solo recibe
 * sus propias ejecuciones, así que esa columna diría siempre lo mismo y sobra.
 * No es un control de acceso: el filtro de verdad está en el SQL.
 */
export function RunsTable({ esAdmin = false }: { esAdmin?: boolean }) {
  const router = useRouter();
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["runs"],
    queryFn: () => fetchRuns(1, 50),
    // Mientras haya alguna ejecución viva, se refresca cada 3 s. Cuando todo está
    // terminado, se para el polling (no hay nada que actualizar).
    refetchInterval: (q) => {
      const items = q.state.data?.items ?? [];
      return items.some((r) => esEstadoEnVuelo(r.estado)) ? 3000 : false;
    },
  });

  // isError primero: un fallo NUNCA debe verse como "lista vacía". isPending cubre
  // la carga inicial y las pausas entre reintentos (donde isFetching baja a false).
  if (isError) {
    return (
      <div className="gp-error-box">
        No se pudo cargar el listado. ¿Está n8n accesible? ({String(error)})
      </div>
    );
  }
  if (isPending) {
    return <div className="gp-empty">Cargando ejecuciones…</div>;
  }

  const items = data.items;
  if (items.length === 0) {
    return (
      <div className="gp-empty">
        Aún no hay ejecuciones. Lanza la primera con el formulario de arriba.
      </div>
    );
  }

  return (
    <div className="gp-table-wrap">
      <table className="gp-table">
        <thead>
          <tr>
            <th>Fecha</th>
            <th>Marca</th>
            <th>Dominio</th>
            <th>Tipo</th>
            {esAdmin && <th>Lanzado por</th>}
            <th>Estado</th>
            <th style={{ textAlign: "right" }}>Nota</th>
            <th style={{ textAlign: "right" }}>Visibilidad</th>
            <th>Avisos</th>
          </tr>
        </thead>
        <tbody>
          {items.map((r) => (
            <Fila
              key={r.id}
              run={r}
              esAdmin={esAdmin}
              onOpen={() => router.push(`/runs/${r.id}`)}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Fila({
  run,
  esAdmin,
  onOpen,
}: {
  run: RunListItem;
  esAdmin: boolean;
  onOpen: () => void;
}) {
  return (
    <tr onClick={onOpen}>
      <td className="gp-mono">{fecha(run.createdAt)}</td>
      <td>{run.brand}</td>
      <td className="gp-mono" style={{ color: "var(--text-muted)" }}>
        {run.domain}
      </td>
      <td>{ETIQUETA_TIPO[run.tipo]}</td>
      {esAdmin && (
        <td className="gp-mono" style={{ color: "var(--text-muted)" }}>
          {/* Sin dueño = anterior a la autenticación (o lanzada a mano por curl). */}
          {run.lanzadoPorEmail ?? (
            <span style={{ color: "var(--muted)" }} title="Anterior a la autenticación">
              sin dueño
            </span>
          )}
        </td>
      )}
      <td>
        <EstadoBadge estado={run.estado} />
      </td>
      <td className="gp-nota" style={{ textAlign: "right" }}>
        {run.nota ?? "–"}
      </td>
      <td className="gp-mono" style={{ textAlign: "right" }}>
        {run.sov ?? "–"}
      </td>
      <td>
        {run.tieneAvisos ? (
          <span
            className="gp-badge"
            style={{ background: "var(--warn-soft)", color: "var(--warn)" }}
          >
            avisos
          </span>
        ) : (
          <span style={{ color: "var(--muted)" }}>—</span>
        )}
      </td>
    </tr>
  );
}

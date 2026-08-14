"use client";

import { useQuery } from "@tanstack/react-query";

import { ApiError, fetchHealth } from "@/lib/client/api";
import type { HealthResponse } from "@/lib/shared/dto";

/** Indicador de salud en la cabecera: panel → n8n → Postgres. */
export function HealthPill() {
  const { data, error } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
    retry: 0,
  });

  // /api/health responde 503 cuando algo está caído, y el cuerpo trae el detalle.
  const health: HealthResponse | null =
    data ?? (error instanceof ApiError ? (error.body as HealthResponse) : null);

  const ok = !!health?.ok;
  const color = ok ? "var(--ok)" : "var(--err)";
  const label = !health
    ? "Comprobando…"
    : ok
      ? "Sistema OK"
      : !health.n8n
        ? "n8n no responde"
        : "BD no consultable";

  return (
    <span
      className="gp-status-pill"
      title={health?.error ?? "panel → n8n → PostgreSQL"}
    >
      <span
        className="gp-dot"
        style={{ background: color, margin: 0 }}
        aria-hidden
      />
      {label}
    </span>
  );
}

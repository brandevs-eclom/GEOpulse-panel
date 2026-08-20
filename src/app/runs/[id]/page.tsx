"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { EstadoBadge } from "@/components/EstadoBadge";
import { ApiError, eliminarRun, fetchRun } from "@/lib/client/api";
import { informeAFilaCsv, informeAJson, nombreFichero } from "@/lib/report/export";
import { InformeCompletoView, JsonCrudo } from "@/lib/report/InformeCompletoView";
import { InformeLiteView } from "@/lib/report/InformeLiteView";
import type { RunDetail } from "@/lib/shared/dto";
import type { InformeLite } from "@/lib/shared/report";
import type { InformeCompleto } from "@/lib/shared/report-completo";
import { esInformeCompleto } from "@/lib/shared/report-completo";
import { ETIQUETA_TIPO, esEstadoEnVuelo } from "@/lib/shared/status";

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const { data, error, isPending, isError } = useQuery({
    queryKey: ["run", id],
    queryFn: () => fetchRun(id),
    // Mientras la ejecución siga viva, sondeamos cada 2,5 s; al terminar, paramos.
    refetchInterval: (q) =>
      q.state.data && esEstadoEnVuelo(q.state.data.estado) ? 2500 : false,
  });

  return (
    <main className="gp-main">
      <Link
        href="/"
        className="gp-no-print"
        style={{ color: "var(--text-muted)", fontSize: 14, textDecoration: "none" }}
      >
        ← Ejecuciones
      </Link>

      {isError ? (
        <div className="gp-error-box" style={{ marginTop: 16 }}>
          {error instanceof ApiError && error.status === 404
            ? "Esta ejecución no existe."
            : `No se pudo cargar la ejecución (${String(error)}).`}
        </div>
      ) : isPending ? (
        <div className="gp-empty">Cargando…</div>
      ) : (
        <Detalle run={data} />
      )}
    </main>
  );
}

function fechaLarga(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("es-ES");
}

/** Descarga un texto como fichero, 100% en cliente (sin endpoint). */
function descargar(contenido: string, tipo: string, nombre: string): void {
  const url = URL.createObjectURL(new Blob([contenido], { type: tipo }));
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Botones de export (G12). Solo si hay informe que descargar. */
function ExportBotones({ run }: { run: RunDetail }) {
  if (run.informe == null) return null;
  const btn = { padding: "8px 14px", fontSize: "0.72rem" } as const;
  return (
    <div className="gp-no-print" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      <button
        type="button"
        className="gp-btn gp-btn-ghost"
        style={btn}
        onClick={() =>
          descargar(informeAJson(run), "application/json", nombreFichero(run, "json"))
        }
      >
        Descargar JSON
      </button>
      <button
        type="button"
        className="gp-btn gp-btn-ghost"
        style={btn}
        onClick={() =>
          descargar(informeAFilaCsv(run), "text/csv;charset=utf-8", nombreFichero(run, "csv"))
        }
      >
        Descargar CSV
      </button>
      <button
        type="button"
        className="gp-btn gp-btn-ghost"
        style={btn}
        onClick={() => window.print()}
      >
        Imprimir / PDF
      </button>
    </div>
  );
}

function Detalle({ run }: { run: RunDetail }) {
  const router = useRouter();
  const qc = useQueryClient();
  const borrar = useMutation({
    mutationFn: () => eliminarRun(run.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["runs"] });
      router.push("/");
    },
  });

  return (
    <div style={{ marginTop: 16 }}>
      {/* Cabecera (chrome del panel: fuera del PDF; el informe trae su propia cabecera). */}
      <div className="gp-card gp-no-print">
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <h1 className="gp-h2" style={{ fontSize: "1.4rem" }}>
            {run.brand}
          </h1>
          <EstadoBadge estado={run.estado} />
          <span className="gp-header-sp" />
          <span className="gp-badge" style={{ background: "var(--muted-soft)", color: "var(--text-muted)" }}>
            {ETIQUETA_TIPO[run.tipo]}
          </span>
          <button
            type="button"
            className="gp-btn gp-btn-ghost"
            style={{ padding: "8px 14px", fontSize: "0.72rem" }}
            disabled={borrar.isPending}
            onClick={() => {
              if (confirm("¿Eliminar esta ejecución? No se puede deshacer.")) {
                borrar.mutate();
              }
            }}
          >
            {borrar.isPending ? "Eliminando…" : "Eliminar"}
          </button>
          <ExportBotones run={run} />
        </div>
        <p className="gp-sub" style={{ margin: "8px 0 0" }}>
          {run.domain} · {run.keyword}
          {run.region ? ` · ${run.region}` : ""} · {run.pais}
        </p>
        <p style={{ color: "var(--muted)", fontSize: 13, margin: "6px 0 0" }}>
          Lanzada {fechaLarga(run.createdAt)}
          {run.duracionMs != null &&
            ` · duró ${Math.round(run.duracionMs / 1000)} s`}
        </p>
      </div>

      {/* Cuerpo según estado */}
      <div style={{ marginTop: 16 }}>
        {run.estado === "error" ? (
          <div className="gp-error-box">
            <b>La ejecución falló.</b>
            <div style={{ marginTop: 6 }}>
              {run.errorMensaje ?? "Sin mensaje de error."}
            </div>
          </div>
        ) : esEstadoEnVuelo(run.estado) ? (
          <div className="gp-empty">
            Análisis en curso… esta página se actualiza sola cuando termine.
          </div>
        ) : run.informe ? (
          /* Se elige por la FORMA del informe, no por run.tipo: si una ejecución
             se guardó con el tipo equivocado, manda el dato real. */
          esInformeCompleto(run.informe) ? (
            <>
              <InformeCompletoView informe={run.informe as InformeCompleto} />
              <JsonCrudo informe={run.informe} />
            </>
          ) : (
            <InformeLiteView informe={run.informe as unknown as InformeLite} />
          )
        ) : (
          <div className="gp-empty">
            La ejecución está completada pero no hay informe guardado.
          </div>
        )}
      </div>

      {/* Detalle técnico (plegado; chrome, fuera del PDF) */}
      <details className="gp-no-print" style={{ marginTop: 22 }}>
        <summary
          style={{
            cursor: "pointer",
            color: "var(--text-muted)",
            fontSize: 14,
            fontWeight: 600,
          }}
        >
          Detalle técnico
        </summary>
        <div className="gp-card" style={{ marginTop: 10 }}>
          <Meta k="Estado" v={run.estado} />
          <Meta k="Inicio" v={fechaLarga(run.startedAt)} />
          <Meta k="Fin" v={fechaLarga(run.finishedAt)} />
          <Meta k="HTTP status" v={run.httpStatus?.toString() ?? "—"} />
          <div style={{ marginTop: 12 }}>
            <div className="gp-field" style={{ marginBottom: 4 }}>
              <label>Payload enviado a n8n</label>
            </div>
            <pre
              style={{
                background: "var(--muted-soft)",
                border: "1px solid var(--border)",
                borderRadius: "var(--r-sm)",
                padding: 12,
                fontSize: 12,
                overflowX: "auto",
                margin: 0,
              }}
            >
              {JSON.stringify(run.payload, null, 2)}
            </pre>
          </div>
          {/* _diag: diagnóstico técnico de la ejecución (docs/05). El JSON
              completo va aparte, junto al informe, para no duplicarlo aquí. */}
          <Diag informe={run.informe} />
        </div>
      </details>
    </div>
  );
}

/** Muestra el bloque `_diag` del informe si lo trae (el LITE sí; el completo no). */
function Diag({ informe }: { informe: unknown }) {
  const diag = (informe as { _diag?: Record<string, unknown> } | null)?._diag;
  if (!diag || typeof diag !== "object") return null;
  return (
    <div style={{ marginTop: 14 }}>
      <div className="gp-field" style={{ marginBottom: 4 }}>
        <label>Diagnóstico técnico (_diag)</label>
      </div>
      {Object.entries(diag).map(([k, v]) => (
        <Meta
          k={k}
          v={typeof v === "object" ? JSON.stringify(v) : String(v)}
          key={k}
        />
      ))}
    </div>
  );
}

function Meta({ k, v }: { k: string; v: string }) {
  return (
    <div
      style={{
        display: "flex",
        gap: 12,
        padding: "6px 0",
        borderBottom: "1px solid var(--border)",
        fontSize: 14,
      }}
    >
      <span style={{ color: "var(--muted)", minWidth: 120 }}>{k}</span>
      <span className="gp-mono">{v}</span>
    </div>
  );
}

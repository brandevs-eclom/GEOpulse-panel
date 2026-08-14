"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError, lanzarRun } from "@/lib/client/api";
import type { RunsAtCapacity } from "@/lib/shared/dto";
import { PAISES_SOPORTADOS } from "@/lib/shared/dto";
import type { RunTipo } from "@/lib/shared/status";
import { validarLanzarRun } from "@/lib/shared/validate";

const VACIO = { brand: "", domain: "", keyword: "", pais: "ES", region: "" };

export function LaunchForm() {
  const qc = useQueryClient();
  const [tipo, setTipo] = useState<RunTipo>("lite");
  const [form, setForm] = useState({ ...VACIO });
  const [errores, setErrores] = useState<Record<string, string>>({});
  const [aviso, setAviso] = useState<string | null>(null);

  const mut = useMutation({
    mutationFn: lanzarRun,
    onSuccess: () => {
      setForm({ ...VACIO });
      setErrores({});
      setAviso(null);
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 400) {
        const body = err.body as { errores?: Record<string, string> };
        setErrores(body.errores ?? {});
      } else if (err instanceof ApiError && err.status === 429) {
        const body = err.body as RunsAtCapacity;
        setAviso(
          `Hay ${body.activos} análisis en curso (máximo ${body.max}). Espera a que terminen.`,
        );
      } else if (err instanceof ApiError) {
        const body = err.body as { detalle?: string };
        setAviso(body?.detalle ?? `Error ${err.status}`);
      } else {
        setAviso(err instanceof Error ? err.message : "Error desconocido");
      }
    },
  });

  function enviar(e: React.FormEvent) {
    e.preventDefault();
    setAviso(null);
    const input = { tipo, ...form };
    // Validación en cliente antes de gastar la llamada (misma regla que el server).
    const val = validarLanzarRun(input);
    if (!val.ok) {
      setErrores(val.errores);
      return;
    }
    setErrores({});
    mut.mutate(val.value);
  }

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <form className="gp-card" onSubmit={enviar}>
      <span className="gp-eyebrow">Nuevo análisis</span>
      <h2 className="gp-h2">Lanzar una auditoría GEO</h2>
      <p className="gp-sub">
        El análisis corre por detrás en n8n. Verás la ejecución pasar a
        completada sin recargar.
      </p>

      <div style={{ marginBottom: 16 }}>
        <div className="gp-seg" role="group" aria-label="Tipo de informe">
          <button
            type="button"
            aria-pressed={tipo === "lite"}
            onClick={() => setTipo("lite")}
          >
            LITE · 1-2 min
          </button>
          <button
            type="button"
            aria-pressed={tipo === "completo"}
            onClick={() => setTipo("completo")}
          >
            Completo · 3-5 min
          </button>
        </div>
      </div>

      <div className="gp-grid">
        <Campo
          label="Marca *"
          valor={form.brand}
          onChange={set("brand")}
          error={errores.brand}
          placeholder="Nombre de la marca"
          ayuda="Tal y como la citaría alguien al recomendarla."
        />
        <Campo
          label="Dominio *"
          valor={form.domain}
          onChange={set("domain")}
          error={errores.domain}
          placeholder="midominio.com"
          ayuda="Con o sin https://. Se normaliza solo."
        />
        <Campo
          label="Sector / keyword *"
          valor={form.keyword}
          onChange={set("keyword")}
          error={errores.keyword}
          placeholder="servicio o sector"
          ayuda="Lo que buscaría un cliente potencial, no el nombre de la marca."
        />
        <Campo
          label="Región (opcional)"
          valor={form.region}
          onChange={set("region")}
          placeholder="ciudad o región"
          ayuda="Afina dónde se geolocalizan los sondeos."
        />
        <div className="gp-field">
          <label htmlFor="pais">País</label>
          <select id="pais" value={form.pais} onChange={set("pais")}>
            {PAISES_SOPORTADOS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <div className="gp-ayuda">Mercado en el que se pregunta a la IA.</div>
        </div>
      </div>

      {aviso && (
        <div className="gp-error-box" style={{ marginTop: 16 }}>
          {aviso}
        </div>
      )}

      <div style={{ marginTop: 18 }}>
        <button className="gp-btn" type="submit" disabled={mut.isPending}>
          {mut.isPending ? "Lanzando…" : "Lanzar análisis"}
        </button>
      </div>
    </form>
  );
}

function Campo({
  label,
  valor,
  onChange,
  error,
  placeholder,
  ayuda,
}: {
  label: string;
  valor: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  error?: string;
  placeholder?: string;
  /** Explica qué se espera en el campo. Se sustituye por el error si lo hay. */
  ayuda?: string;
}) {
  return (
    <div className="gp-field">
      <label>{label}</label>
      <input
        type="text"
        value={valor}
        onChange={onChange}
        placeholder={placeholder}
        aria-invalid={error ? "true" : undefined}
      />
      {error ? (
        <div className="gp-err">{error}</div>
      ) : (
        ayuda && <div className="gp-ayuda">{ayuda}</div>
      )}
    </div>
  );
}

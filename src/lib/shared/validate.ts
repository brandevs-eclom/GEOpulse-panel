/**
 * Validación del formulario de lanzamiento. Se usa en el servidor (antes de
 * tocar la BD y de gastar una llamada a n8n) y puede reusarse en el cliente.
 *
 * n8n valida brand/domain/keyword otra vez, pero el panel debe validarlos ANTES
 * para no crear una ejecución basura ni gastar una llamada en un 400 (docs/02).
 */

import type { LanzarRunInput } from "./dto";
import { RUN_TIPOS, type RunTipo } from "./status";

export type ValidacionRun =
  | { ok: true; value: LanzarRunInput }
  | { ok: false; errores: Record<string, string> };

export function validarLanzarRun(body: unknown): ValidacionRun {
  const b = (body ?? {}) as Record<string, unknown>;
  const trim = (v: unknown) => (typeof v === "string" ? v.trim() : "");

  const errores: Record<string, string> = {};
  const brand = trim(b.brand);
  const domain = trim(b.domain);
  const keyword = trim(b.keyword);

  if (!brand) errores.brand = "La marca es obligatoria";
  if (!domain) errores.domain = "El dominio es obligatorio";
  if (!keyword) errores.keyword = "El sector (keyword) es obligatorio";

  const tipo = trim(b.tipo) as RunTipo;
  if (!RUN_TIPOS.includes(tipo)) {
    errores.tipo = "Tipo inválido (lite | completo)";
  }

  if (Object.keys(errores).length > 0) return { ok: false, errores };

  const region = trim(b.region);
  return {
    ok: true,
    value: {
      tipo,
      brand,
      domain,
      keyword,
      pais: trim(b.pais) || "ES",
      ...(region ? { region } : {}),
    },
  };
}

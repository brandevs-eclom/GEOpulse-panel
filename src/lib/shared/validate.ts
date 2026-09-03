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

  // Longitudes máximas (seguridad): estos campos entran en el prompt de ~14
  // llamadas de pago; sin tope, 1 MB en `brand` multiplica el coste de un análisis
  // (docs/08 §1.4). El webhook de n8n valida otra vez con .slice(), porque es
  // alcanzable sin pasar por aquí.
  const region = trim(b.region);
  const pais = trim(b.pais);
  if (brand.length > MAX.brand) errores.brand = `La marca no puede superar ${MAX.brand} caracteres`;
  if (domain.length > MAX.domain) errores.domain = `El dominio no puede superar ${MAX.domain} caracteres`;
  if (keyword.length > MAX.keyword) errores.keyword = `El sector no puede superar ${MAX.keyword} caracteres`;
  if (region.length > MAX.region) errores.region = `La región no puede superar ${MAX.region} caracteres`;
  if (pais && !/^[A-Za-z]{2}$/.test(pais)) errores.pais = "El país debe ser un código de 2 letras (p. ej. ES)";

  const tipo = trim(b.tipo) as RunTipo;
  if (!RUN_TIPOS.includes(tipo)) {
    errores.tipo = "Tipo inválido (lite | completo)";
  }

  if (Object.keys(errores).length > 0) return { ok: false, errores };

  return {
    ok: true,
    value: {
      tipo,
      brand,
      domain,
      keyword,
      pais: (pais || "ES").toUpperCase(),
      ...(region ? { region } : {}),
    },
  };
}

/** Topes de longitud (caracteres). También se aplican con .slice() en n8n. */
export const MAX = { brand: 80, domain: 253, keyword: 120, region: 80 } as const;

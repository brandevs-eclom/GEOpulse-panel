/**
 * Color de un valor 0-100 según los umbrales del informe (idénticos al frontend
 * de referencia): >=75 ok, >=50 warning, <50 error. `null` = no medible → gris,
 * nunca rojo: un dato que no se pudo medir no es un suspenso.
 */
export function tono(v: number | null | undefined): string {
  if (v === null || v === undefined) return "var(--muted)";
  return v >= 75 ? "var(--ok)" : v >= 50 ? "var(--warn)" : "var(--err)";
}

/** Paleta de tonos tierra para los competidores del donut (la marca va en acento). */
export const PALETA_COMPETIDORES = [
  "#C3BCAE",
  "#9A9284",
  "#B8946F",
  "#7A8A90",
  "#D6CFC2",
  "#A19889",
  "#68757B",
  "#8C8478",
  "#5C5952",
];

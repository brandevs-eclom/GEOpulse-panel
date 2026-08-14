/**
 * Estados y tipos del ciclo de vida de una ejecución.
 * Vive en shared/ porque lo usan tanto el servidor (worker, callback, cron)
 * como el cliente (badge de estado, condición de parada del polling).
 */

export const RUN_ESTADOS = [
  "pendiente",
  "en_curso",
  "completado",
  "error",
] as const;
export type RunEstado = (typeof RUN_ESTADOS)[number];

export const RUN_TIPOS = ["lite", "completo"] as const;
export type RunTipo = (typeof RUN_TIPOS)[number];

/** Estados en los que la ejecución todavía puede cambiar sola. */
export const ESTADOS_EN_VUELO: readonly RunEstado[] = ["pendiente", "en_curso"];

/** true si el estado ya no va a cambiar: el polling debe pararse aquí. */
export function esEstadoFinal(estado: RunEstado): boolean {
  return estado === "completado" || estado === "error";
}

/** true mientras la ejecución sigue viva (el polling debe continuar). */
export function esEstadoEnVuelo(estado: RunEstado): boolean {
  return !esEstadoFinal(estado);
}

export const ETIQUETA_ESTADO: Record<RunEstado, string> = {
  pendiente: "Pendiente",
  en_curso: "En curso",
  completado: "Completado",
  error: "Error",
};

export const ETIQUETA_TIPO: Record<RunTipo, string> = {
  lite: "LITE",
  completo: "Completo",
};

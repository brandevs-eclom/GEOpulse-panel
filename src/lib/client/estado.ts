import type { RunEstado } from "@/lib/shared/status";

/** Colores del chip de estado. no_verificable/error en rojo; en_curso en ámbar. */
export const ESTILO_ESTADO: Record<
  RunEstado,
  { bg: string; color: string; label: string }
> = {
  pendiente: { bg: "var(--muted-soft)", color: "var(--muted)", label: "Pendiente" },
  en_curso: { bg: "var(--warn-soft)", color: "var(--warn)", label: "En curso" },
  completado: { bg: "var(--ok-soft)", color: "var(--ok)", label: "Completado" },
  error: { bg: "var(--err-soft)", color: "var(--err)", label: "Error" },
};

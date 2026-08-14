/**
 * Lectura de la sesión desde el servidor y guardas para las rutas de API.
 *
 * RUNTIME: Node (usa `next/headers`). El middleware NO importa esto.
 *
 * El middleware ya bloquea lo que no lleve cookie válida, pero las rutas vuelven
 * a comprobarlo. No es redundancia inútil: si algún día se toca el `matcher` del
 * middleware y una ruta se queda fuera por descuido, la guarda de la ruta impide
 * que eso se convierta en una fuga silenciosa. La autorización se comprueba
 * donde está el dato, no solo en la puerta.
 */

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import type { Sesion } from "@/lib/shared/auth";
import { COOKIE_SESION, verificarSesion } from "@/server/auth/session";

/** La sesión actual, o null. Usable desde server components y route handlers. */
export async function leerSesion(): Promise<Sesion | null> {
  const jar = await cookies();
  return verificarSesion(jar.get(COOKIE_SESION)?.value);
}

type Guarda =
  | { ok: true; sesion: Sesion }
  | { ok: false; res: NextResponse };

/** Exige sesión. Devuelve 401 JSON (nunca un redirect: quien llama es un fetch). */
export async function exigirSesion(): Promise<Guarda> {
  const sesion = await leerSesion();
  if (!sesion) {
    return {
      ok: false,
      res: NextResponse.json({ error: "no_autenticado" }, { status: 401 }),
    };
  }
  return { ok: true, sesion };
}

/** Exige sesión Y rol admin. */
export async function exigirAdmin(): Promise<Guarda> {
  const g = await exigirSesion();
  if (!g.ok) return g;
  if (g.sesion.rol !== "admin") {
    return {
      ok: false,
      res: NextResponse.json({ error: "rol_insuficiente" }, { status: 403 }),
    };
  }
  return g;
}

/**
 * Filtro de propiedad para las consultas de ejecuciones.
 *
 * null = sin filtro (admin: lo ve todo, incluidas las ejecuciones históricas que
 * no tienen dueño). Un uuid = solo las de esa persona.
 */
export function filtroPropiedad(sesion: Sesion): string | null {
  return sesion.rol === "admin" ? null : sesion.id;
}

import { NextResponse } from "next/server";

import { COOKIE_SESION, opcionesCookie } from "@/server/auth/session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST /api/auth/logout — borra la cookie.
 *
 * No exige sesión válida a propósito: si la cookie está caducada o corrupta,
 * "salir" tiene que funcionar igual. Devolver 401 aquí dejaría al usuario con
 * una cookie inservible que no puede quitarse desde la interfaz.
 */
export async function POST() {
  const res = NextResponse.json({ ok: true });
  res.cookies.set(COOKIE_SESION, "", opcionesCookie(0));
  return res;
}

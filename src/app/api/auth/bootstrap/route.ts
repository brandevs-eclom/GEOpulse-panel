import { timingSafeEqual } from "node:crypto";

import { NextResponse } from "next/server";

import { validarEmail, validarPassword } from "@/lib/shared/auth";
import { generarPassword } from "@/server/auth/password";
import { errorResponse } from "@/server/http";
import { countUsers, createUser } from "@/server/users/repo";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST /api/auth/bootstrap — crea la PRIMERA cuenta (admin).
 *
 * El problema del huevo y la gallina: la pantalla de usuarios exige ser admin, y
 * al principio no hay ninguno. Esta ruta resuelve solo ese arranque.
 *
 * Dos cerrojos, y ninguno depende del otro:
 *   1. Exige la cabecera `x-panel-secret` con el valor de N8N_PANEL_DB_SECRET.
 *      No es un permiso nuevo: quien tiene ese secreto ya puede escribir en la
 *      base de datos a través del webhook `panel-db`, así que podría crearse un
 *      usuario de todas formas. Esto solo lo hace cómodo, no más permisivo.
 *   2. Solo funciona mientras NO exista ningún usuario. En cuanto hay uno,
 *      devuelve 409 y deja de ser una puerta para siempre.
 *
 * Uso (ver README):
 *   curl -X POST .../api/auth/bootstrap -H "x-panel-secret: $SECRETO" \
 *        -H "Content-Type: application/json" \
 *        -d '{"email":"tu@brandevs.com","nombre":"Tu nombre"}'
 */
export async function POST(req: Request) {
  const secreto = process.env.N8N_PANEL_DB_SECRET;
  if (!secreto) {
    return NextResponse.json(
      { error: "config", detalle: "Falta N8N_PANEL_DB_SECRET en el servidor" },
      { status: 500 },
    );
  }
  if (!igualEnTiempoConstante(req.headers.get("x-panel-secret"), secreto)) {
    return NextResponse.json({ error: "no_autorizado" }, { status: 401 });
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "json_invalido" }, { status: 400 });
  }
  const b = (body ?? {}) as Record<string, unknown>;

  const errEmail = validarEmail(b.email);
  if (errEmail) {
    return NextResponse.json(
      { error: "validacion", errores: { email: errEmail } },
      { status: 400 },
    );
  }

  // La contraseña es opcional: si no la mandas se genera una fuerte y se
  // devuelve UNA sola vez en la respuesta. Es la única vez que el panel enseña
  // una contraseña en claro, y solo a quien ya tiene el secreto del servidor.
  const generada = typeof b.password !== "string" || b.password === "";
  const password = generada ? generarPassword() : String(b.password);
  if (!generada) {
    const errPass = validarPassword(password);
    if (errPass) {
      return NextResponse.json(
        { error: "validacion", errores: { password: errPass } },
        { status: 400 },
      );
    }
  }

  try {
    if ((await countUsers()) > 0) {
      return NextResponse.json(
        {
          error: "ya_hay_usuarios",
          detalle:
            "Ya existe al menos una cuenta. Da de alta a los demás desde /usuarios.",
        },
        { status: 409 },
      );
    }

    const usuario = await createUser({
      email: String(b.email).trim(),
      password,
      nombre: typeof b.nombre === "string" ? b.nombre.trim() || null : null,
      rol: "admin",
    });

    return NextResponse.json(
      { usuario, ...(generada ? { password } : {}) },
      { status: 201 },
    );
  } catch (err) {
    return errorResponse(err);
  }
}

/** Comparación sin fugas de tiempo, tolerante a longitudes distintas. */
function igualEnTiempoConstante(a: string | null, b: string): boolean {
  if (!a) return false;
  const ba = Buffer.from(a);
  const bb = Buffer.from(b);
  // timingSafeEqual exige longitudes iguales; comparar contra una copia del
  // mismo tamaño evita la excepción sin delatar la longitud real.
  if (ba.length !== bb.length) {
    timingSafeEqual(bb, bb);
    return false;
  }
  return timingSafeEqual(ba, bb);
}

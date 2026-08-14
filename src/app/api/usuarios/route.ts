import { NextResponse } from "next/server";

import {
  esRol,
  validarEmail,
  validarPassword,
  type Rol,
} from "@/lib/shared/auth";
import { exigirAdmin } from "@/server/auth/guard";
import { generarPassword } from "@/server/auth/password";
import { errorResponse } from "@/server/http";
import { createUser, listUsers } from "@/server/users/repo";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** GET /api/usuarios — listado. Solo admin. */
export async function GET() {
  const g = await exigirAdmin();
  if (!g.ok) return g.res;
  try {
    return NextResponse.json({ items: await listUsers() });
  } catch (err) {
    return errorResponse(err);
  }
}

/**
 * POST /api/usuarios — da de alta a un compañero. Solo admin.
 *
 * Si no se envía contraseña se genera una y se devuelve UNA sola vez: no se
 * guarda en claro en ningún sitio, así que si se pierde hay que resetearla.
 */
export async function POST(req: Request) {
  const g = await exigirAdmin();
  if (!g.ok) return g.res;

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "json_invalido" }, { status: 400 });
  }
  const b = (body ?? {}) as Record<string, unknown>;

  const errores: Record<string, string> = {};
  const errEmail = validarEmail(b.email);
  if (errEmail) errores.email = errEmail;

  const rol: Rol = esRol(b.rol) ? b.rol : "miembro";
  if (b.rol !== undefined && !esRol(b.rol)) {
    errores.rol = "Rol inválido (admin | miembro)";
  }

  const generada = typeof b.password !== "string" || b.password === "";
  const password = generada ? generarPassword() : String(b.password);
  if (!generada) {
    const errPass = validarPassword(password);
    if (errPass) errores.password = errPass;
  }

  if (Object.keys(errores).length > 0) {
    return NextResponse.json({ error: "validacion", errores }, { status: 400 });
  }

  try {
    const usuario = await createUser({
      email: String(b.email).trim(),
      password,
      nombre: typeof b.nombre === "string" ? b.nombre.trim() || null : null,
      rol,
    });
    return NextResponse.json(
      { usuario, ...(generada ? { password } : {}) },
      { status: 201 },
    );
  } catch (err) {
    // El unique de email salta aquí. Mejor un mensaje claro que un 502 opaco.
    const detalle = err instanceof Error ? err.message : String(err);
    if (/users_email_unique|duplicate key/i.test(detalle)) {
      return NextResponse.json(
        { error: "email_duplicado", detalle: "Ya existe una cuenta con ese email" },
        { status: 409 },
      );
    }
    return errorResponse(err);
  }
}

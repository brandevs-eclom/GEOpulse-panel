import { NextResponse } from "next/server";

import { esRol, validarPassword } from "@/lib/shared/auth";
import { exigirAdmin } from "@/server/auth/guard";
import { generarPassword } from "@/server/auth/password";
import { errorResponse } from "@/server/http";
import {
  countAdmins,
  deleteUser,
  getUser,
  updateUserPassword,
  updateUserRol,
} from "@/server/users/repo";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * PATCH /api/usuarios/:id — cambia el rol o resetea la contraseña. Solo admin.
 *
 * Body: { rol } | { password } | { password: "" } para generar una nueva.
 */
export async function PATCH(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const g = await exigirAdmin();
  if (!g.ok) return g.res;

  const { id } = await params;
  if (!UUID_RE.test(id)) {
    return NextResponse.json({ error: "id_invalido" }, { status: 400 });
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "json_invalido" }, { status: 400 });
  }
  const b = (body ?? {}) as Record<string, unknown>;

  try {
    // --- Cambio de rol ---
    if (b.rol !== undefined) {
      if (!esRol(b.rol)) {
        return NextResponse.json(
          { error: "validacion", errores: { rol: "Rol inválido (admin | miembro)" } },
          { status: 400 },
        );
      }
      // Quedarse sin ningún admin dejaría el panel sin nadie que pueda dar de
      // alta a nadie: habría que repetir el arranque inicial a mano.
      //
      // Esta comprobación es SOLO para dar un mensaje claro. El cerrojo de
      // verdad está dentro del propio UPDATE (ver build_panel_db.py): entre
      // contar y escribir hay dos viajes HTTP a n8n, así que dos degradaciones
      // simultáneas pasarían las dos comprobaciones previas.
      if (b.rol === "miembro" && (await countAdmins()) <= 1) {
        return NextResponse.json(
          {
            error: "ultimo_admin",
            detalle: "Es el único admin. Asciende a otra persona antes de quitarle el rol.",
          },
          { status: 409 },
        );
      }
      const usuario = await updateUserRol(id, b.rol);
      if (!usuario) {
        // 0 filas: o no existe, o el cerrojo del SQL lo frenó por ser el último
        // admin (la carrera que la comprobación de arriba no puede cubrir).
        return (await getUser(id))
          ? NextResponse.json(
              {
                error: "ultimo_admin",
                detalle:
                  "No se ha cambiado: dejaría el panel sin ningún administrador.",
              },
              { status: 409 },
            )
          : NextResponse.json({ error: "no_encontrado" }, { status: 404 });
      }
      return NextResponse.json({ usuario });
    }

    // --- Reseteo de contraseña ---
    if (b.password !== undefined) {
      const generada = typeof b.password !== "string" || b.password === "";
      const password = generada ? generarPassword() : String(b.password);
      if (!generada) {
        const err = validarPassword(password);
        if (err) {
          return NextResponse.json(
            { error: "validacion", errores: { password: err } },
            { status: 400 },
          );
        }
      }
      const ok = await updateUserPassword(id, password);
      if (!ok) {
        return NextResponse.json({ error: "no_encontrado" }, { status: 404 });
      }
      // Aviso honesto: la sesión que ya tuviera esa persona NO se cierra al
      // cambiarle la contraseña. La cookie está firmada, no se consulta la BD en
      // cada petición, así que sigue siendo válida hasta que caduque.
      return NextResponse.json({
        ok: true,
        ...(generada ? { password } : {}),
        aviso: "La sesión que ya tuviera abierta sigue activa hasta que caduque.",
      });
    }

    return NextResponse.json(
      { error: "validacion", errores: { _: "Indica 'rol' o 'password'" } },
      { status: 400 },
    );
  } catch (err) {
    return errorResponse(err);
  }
}

/** DELETE /api/usuarios/:id — quita el acceso. Solo admin. */
export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const g = await exigirAdmin();
  if (!g.ok) return g.res;

  const { id } = await params;
  if (!UUID_RE.test(id)) {
    return NextResponse.json({ error: "id_invalido" }, { status: 400 });
  }
  // Borrarte a ti mismo te dejaría fuera con la sesión aún viva y sin forma de
  // volver a entrar. Se bloquea.
  if (id === g.sesion.id) {
    return NextResponse.json(
      { error: "no_te_puedes_borrar", detalle: "No puedes borrar tu propia cuenta." },
      { status: 409 },
    );
  }

  try {
    const borrado = await deleteUser(id);
    if (!borrado) {
      // 0 filas: o no existe, o es el último admin. Sin el cerrojo del SQL se
      // podía dejar el panel con CERO admins (un admin se degrada a sí mismo —
      // su cookie sigue diciendo admin hasta que caduque — y acto seguido borra
      // al otro), y ya no habría forma de dar de alta a nadie.
      return (await getUser(id))
        ? NextResponse.json(
            {
              error: "ultimo_admin",
              detalle:
                "Es el único administrador. Asciende a otra persona antes de borrar esta cuenta.",
            },
            { status: 409 },
          )
        : NextResponse.json({ error: "no_encontrado" }, { status: 404 });
    }
    return NextResponse.json({
      ok: true,
      aviso:
        "Sus ejecuciones se conservan sin dueño y pasan a verlas solo los admins. " +
        "Su sesión sigue siendo válida hasta que caduque: para cortar en el acto, rota AUTH_SECRET.",
    });
  } catch (err) {
    return errorResponse(err);
  }
}

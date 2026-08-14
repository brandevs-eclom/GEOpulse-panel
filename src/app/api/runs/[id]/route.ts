import { NextResponse } from "next/server";

import { exigirSesion, filtroPropiedad } from "@/server/auth/guard";
import { errorResponse } from "@/server/http";
import { deleteRun, getRun } from "@/server/runs/repo";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * GET /api/runs/:id — detalle de una ejecución con su informe.
 *
 * La de otra persona devuelve 404, no 403: así el panel no confirma que ese id
 * exista.
 */
export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const g = await exigirSesion();
  if (!g.ok) return g.res;

  const { id } = await params;
  if (!UUID_RE.test(id)) {
    return NextResponse.json({ error: "id_invalido" }, { status: 400 });
  }
  try {
    const run = await getRun(id, filtroPropiedad(g.sesion));
    if (!run) {
      return NextResponse.json({ error: "no_encontrado" }, { status: 404 });
    }
    return NextResponse.json(run);
  } catch (err) {
    return errorResponse(err);
  }
}

/** DELETE /api/runs/:id — borra la ejecución. Solo la propia (el admin, cualquiera). */
export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const g = await exigirSesion();
  if (!g.ok) return g.res;

  const { id } = await params;
  if (!UUID_RE.test(id)) {
    return NextResponse.json({ error: "id_invalido" }, { status: 400 });
  }
  try {
    const borrado = await deleteRun(id, filtroPropiedad(g.sesion));
    if (!borrado) {
      return NextResponse.json({ error: "no_encontrado" }, { status: 404 });
    }
    return NextResponse.json({ ok: true });
  } catch (err) {
    return errorResponse(err);
  }
}

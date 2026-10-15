import { NextResponse } from "next/server";

import { exigirSesion, filtroPropiedad } from "@/server/auth/guard";
import { errorResponse } from "@/server/http";
import { getRun } from "@/server/runs/repo";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * GET /api/runs/:id/pdf — descarga el PDF del informe.
 *
 * El PDF lo genera Gotenberg a través del webhook `geopulse-pdf` (misma plantilla
 * que la landing y el correo). Esta ruta es la cara AUTENTICADA: exige sesión y que
 * el run sea del usuario (o que sea admin), y solo entonces llama al webhook con el
 * `run_id` + el secreto compartido. El webhook acepta el camino por `run_id` SOLO
 * con ese secreto, así que los informes de cliente no quedan descargables por
 * cualquiera que conozca un id (a diferencia del camino público por token).
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
    // Comprobación de propiedad: la de otra persona devuelve 404 (igual que GET).
    const run = await getRun(id, filtroPropiedad(g.sesion));
    if (!run) {
      return NextResponse.json({ error: "no_encontrado" }, { status: 404 });
    }
    if (run.estado !== "completado" || run.informe == null) {
      return NextResponse.json({ error: "sin_informe" }, { status: 409 });
    }

    const base = process.env.N8N_BASE_URL;
    const path = process.env.N8N_PDF_PATH || "geopulse-pdf";
    const secreto = process.env.PDF_PANEL_SECRET;
    if (!base || !secreto) {
      // Falta configuración: sin base de n8n o sin el secreto compartido no se
      // puede pedir el PDF. Se dice claro en vez de un 500 opaco.
      return NextResponse.json(
        { error: "config_pdf", detalle: "Falta N8N_BASE_URL o PDF_PANEL_SECRET" },
        { status: 500 },
      );
    }

    const url = `${base.replace(/\/+$/, "")}/webhook/${path}`;
    let res: Response;
    try {
      res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-panel-secret": secreto,
        },
        body: JSON.stringify({ run_id: id }),
        cache: "no-store",
      });
    } catch (err) {
      const detalle = err instanceof Error ? err.message : String(err);
      return NextResponse.json(
        { error: "pdf_inaccesible", detalle },
        { status: 503 },
      );
    }

    if (!res.ok) {
      const cuerpo = await res.text().catch(() => "");
      return NextResponse.json(
        { error: "pdf_fallido", detalle: `geopulse-pdf devolvió ${res.status}: ${cuerpo.slice(0, 200)}` },
        { status: 502 },
      );
    }

    const buf = await res.arrayBuffer();
    const slug =
      String(run.domain || "informe")
        .replace(/[^a-z0-9]+/gi, "-")
        .replace(/^-+|-+$/g, "")
        .toLowerCase() || "informe";

    return new NextResponse(buf, {
      status: 200,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": `attachment; filename="geopulse-${slug}.pdf"`,
        "Cache-Control": "no-store",
      },
    });
  } catch (err) {
    return errorResponse(err);
  }
}

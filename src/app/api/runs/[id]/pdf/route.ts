import { NextResponse } from "next/server";

import { exigirSesion, filtroPropiedad } from "@/server/auth/guard";
import { errorResponse } from "@/server/http";
import { getRun } from "@/server/runs/repo";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function fallo(error: string, detalle: string, status: number) {
  return NextResponse.json({ error, detalle }, { status });
}

/**
 * POST /api/runs/:id/pdf — genera el PDF del informe.  Body: { html }
 *
 * El `html` es el informe TAL COMO SE VE en el panel (LITE o COMPLETO), serializado
 * en el navegador con su CSS (lib/client/pdf-html.ts): así el PDF lleva exactamente
 * todo el contenido del análisis. Gotenberg lo convierte en n8n a través del webhook
 * `geopulse-pdf-panel`. Esta ruta es la cara
 * AUTENTICADA: exige sesión y que el run sea del usuario (o admin), y solo entonces
 * llama al webhook. El webhook está protegido con la MISMA credencial Header Auth
 * que `panel-db`, así que reutiliza `N8N_PANEL_DB_SECRET`: no hace falta ningún
 * secreto nuevo.
 *
 * Se comprueba que lo recibido sea DE VERDAD un PDF: cuando un workflow de n8n
 * falla antes de llegar a su nodo de respuesta, n8n contesta 200 con el cuerpo
 * vacío, y darlo por bueno descargaba un fichero corrupto sin decir por qué.
 */
export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const g = await exigirSesion();
  if (!g.ok) return g.res;

  const { id } = await params;
  if (!UUID_RE.test(id)) return fallo("id_invalido", "Id de ejecución no válido.", 400);

  try {
    // Propiedad: la de otra persona devuelve 404 (igual que GET /api/runs/:id).
    const run = await getRun(id, filtroPropiedad(g.sesion));
    if (!run) return fallo("no_encontrado", "Esta ejecución no existe.", 404);
    if (run.estado !== "completado" || run.informe == null) {
      return fallo("sin_informe", "Esta ejecución no tiene un informe completado.", 409);
    }

    let html = "";
    try {
      const body = (await req.json()) as { html?: unknown };
      html = typeof body.html === "string" ? body.html : "";
    } catch {
      return fallo("json_invalido", "Cuerpo de la petición no válido.", 400);
    }
    if (!html.startsWith("<!doctype html>")) {
      return fallo("html_invalido", "Falta el HTML del informe.", 400);
    }
    if (html.length > 4_400_000) {
      return fallo("html_grande", "El informe es demasiado grande para generar el PDF.", 413);
    }

    const base = process.env.N8N_BASE_URL;
    const path = process.env.N8N_PDF_PANEL_PATH || "geopulse-pdf-panel";
    const secreto = process.env.N8N_PANEL_DB_SECRET;
    if (!base || !secreto) {
      return fallo("config_pdf", "Falta N8N_BASE_URL o N8N_PANEL_DB_SECRET en el panel.", 500);
    }

    let res: Response;
    try {
      res = await fetch(`${base.replace(/\/+$/, "")}/webhook/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-panel-secret": secreto },
        body: JSON.stringify({ run_id: id, html }),
        cache: "no-store",
        signal: AbortSignal.timeout(90_000),
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return fallo("pdf_inaccesible", `No se pudo contactar con n8n: ${msg}`, 503);
    }

    if (res.status === 404) {
      return fallo(
        "pdf_no_activo",
        `El webhook "${path}" no está activo en n8n: importa workflows/geopulse-pdf-panel-workflow.json y actívalo.`,
        502,
      );
    }
    if (res.status === 401 || res.status === 403) {
      return fallo(
        "pdf_no_autorizado",
        `n8n rechazó la llamada (${res.status}): el webhook "${path}" debe usar la credencial "GEOpulse Panel - Header Auth" (la misma que panel-db).`,
        502,
      );
    }

    const buf = await res.arrayBuffer();
    const cabecera = new TextDecoder().decode(buf.slice(0, 5));
    if (!res.ok || !cabecera.startsWith("%PDF")) {
      const texto = new TextDecoder().decode(buf.slice(0, 200)).trim();
      return fallo(
        "pdf_fallido",
        texto
          ? `n8n respondió ${res.status} sin PDF: ${texto}`
          : `n8n respondió ${res.status} con el cuerpo vacío: el workflow "${path}" falló antes de responder. Mira su última ejecución en n8n (suele ser Gotenberg o la credencial de Postgres).`,
        502,
      );
    }

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

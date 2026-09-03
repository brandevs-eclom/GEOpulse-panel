import { NextResponse } from "next/server";

import { conCors, corsHeaders, errorResponse, preflight } from "@/server/http";
import { getPublicRun } from "@/server/runs/repo";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** El token son dos uuid sin guiones concatenados: 64 hex. */
const TOKEN_RE = /^[0-9a-f]{64}$/i;

export function OPTIONS(req: Request) {
  return preflight(req);
}

/**
 * GET /api/publico/runs/:token — sondeo del análisis público.
 *
 * Devuelve estado + fase + (cuando termina) el informe. La web lo llama en bucle
 * hasta un estado final. Solo alcanza runs con origen='publico': un token no
 * puede leer una ejecución interna del panel. Un token inexistente es 404, no un
 * 200 vacío, para que la web distinga "aún no existe" de "no existe".
 */
export async function GET(
  req: Request,
  { params }: { params: Promise<{ token: string }> },
) {
  const cors = corsHeaders(req);
  const { token } = await params;
  if (!TOKEN_RE.test(token)) {
    return NextResponse.json({ error: "token_invalido" }, { status: 400, headers: cors });
  }
  try {
    const estado = await getPublicRun(token);
    if (!estado) {
      return NextResponse.json({ error: "no_encontrado" }, { status: 404, headers: cors });
    }
    return NextResponse.json(estado, { headers: cors });
  } catch (err) {
    return conCors(errorResponse(err), req);
  }
}

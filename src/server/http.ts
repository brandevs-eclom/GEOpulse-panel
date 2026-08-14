import { NextResponse } from "next/server";

import { PanelDbError } from "@/server/n8n/client";

/**
 * Traduce un error a una respuesta HTTP honesta. Si el fallo viene de que n8n no
 * responde (la BD vive dentro de n8n), es un 503, no un 500: el panel está bien,
 * su dependencia no.
 */
export function errorResponse(err: unknown): NextResponse {
  if (err instanceof PanelDbError) {
    const status = err.n8nRespondio ? 502 : 503;
    return NextResponse.json(
      {
        error: err.n8nRespondio ? "db_error" : "n8n_unreachable",
        detalle: err.message,
      },
      { status },
    );
  }
  const detalle = err instanceof Error ? err.message : String(err);
  return NextResponse.json({ error: "internal", detalle }, { status: 500 });
}

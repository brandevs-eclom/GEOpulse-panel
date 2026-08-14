import { NextResponse } from "next/server";

import type { HealthResponse } from "@/lib/shared/dto";
import { leerSesion } from "@/server/auth/guard";
import { PanelDbError, pingPanelDb } from "@/server/n8n/client";

// Usa fetch contra n8n y no debe cachearse nunca.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Quita el secreto compartido si por lo que sea apareciese en un mensaje de
 * error. El panel es interno, pero un healthcheck no debe filtrar credenciales
 * a quien lo llame.
 */
function sanear(mensaje: string): string {
  const secreto = process.env.N8N_PANEL_DB_SECRET;
  let salida = mensaje;
  if (secreto && secreto.length > 3) {
    salida = salida.split(secreto).join("<secreto-oculto>");
  }
  return salida.replace(
    /(postgres(?:ql)?:\/\/)[^@\s]*@/gi,
    "$1<credenciales-ocultas>@",
  );
}

/**
 * GET /api/health — estado de la cadena panel → n8n → Postgres.
 *
 * Es la ÚNICA ruta que sigue siendo pública (para poder monitorizarla desde
 * fuera sin credenciales), así que sin sesión responde solo los tres booleanos.
 * El mensaje de error de n8n puede llevar rutas internas, nombres de nodo o el
 * estado del servidor: eso solo lo ve quien ha iniciado sesión.
 */
export async function GET() {
  try {
    await pingPanelDb();
    return NextResponse.json<HealthResponse>({ ok: true, n8n: true, db: true });
  } catch (err) {
    // Se distingue "no llego a n8n" de "n8n responde pero la consulta falla",
    // porque son dos averías muy distintas de diagnosticar.
    const n8nRespondio = err instanceof PanelDbError && err.n8nRespondio;
    const mensaje =
      err instanceof Error ? err.message : String(err ?? "error desconocido");
    const conSesion = (await leerSesion()) !== null;

    return NextResponse.json<HealthResponse>(
      {
        ok: false,
        n8n: n8nRespondio,
        db: false,
        ...(conSesion ? { error: sanear(mensaje) } : {}),
      },
      { status: 503 },
    );
  }
}

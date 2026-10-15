#!/usr/bin/env python3
# geopulse-estado — webhook de SOLO LECTURA para el sondeo de la landing publica.
#
# QUE ES
# La web publica llama a este webhook por GET con ?token=... cada pocos segundos.
# Devuelve el estado del run, la fase actual y el informe (cuando ya esta). Solo
# lee runs PUBLICOS (origen='publico'): un token no puede leer una ejecucion
# interna del panel. Escribe/lee Postgres LOCAL (co-ubicado), como el resto de la
# fontaneria; la web nunca toca el panel.
#
# POR QUE UN GET
# Un GET con cabeceras normales (Accept) es una peticion "simple" de CORS: no hay
# preflight, asi que el navegador puede sondear sin fricciones. El webhook lleva
# allowedOrigins para emitir Access-Control-Allow-Origin en la respuesta, y
# X-Robots-Tag: noindex, nofollow para que la URL no la indexe nadie.
#
# Uso:  python build_estado.py
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel_common as pc  # noqa: E402  (pg, code, responder_headers, credencial)

AQUI = os.path.dirname(os.path.abspath(__file__))
WEBHOOK_PATH = "geopulse-estado"

# Alias en camelCase para que la landing lea data.progresoIdx / data.errorMensaje
# tal cual (asi no hay que mapear en la web).
SQL_LEER_ESTADO = (
    'select r.estado, r.progreso_idx as "progresoIdx", '
    'r.error_mensaje as "errorMensaje", i.informe '
    "from runs r left join informes i on i.run_id = r.id "
    "where r.token = $1 and r.origen = 'publico'"
)

CODE_TOKEN = r"""// Extrae el token del query (?token=...). GET simple: sin cabeceras raras no hay
// preflight, asi que el navegador puede sondear sin CORS de escritura.
const q = $json.query || {};
const token = String(q.token || '').trim().slice(0, 128);
return [{ json: { token } }];"""

CODE_FORMATEAR = r"""// Forma estable para la landing. Si el token no existe (0 filas), estado=null y la
// web sigue sondeando. Parsea el informe si viniera como string (segun driver).
const r = $json || {};
let informe = r.informe;
if (typeof informe === 'string') { try { informe = JSON.parse(informe); } catch (e) { informe = null; } }
return [{ json: {
  estado: r.estado || null,
  progresoIdx: (r.progresoIdx === undefined || r.progresoIdx === null) ? null : Number(r.progresoIdx),
  informe: informe || null,
  errorMensaje: r.errorMensaje || null
} }];"""

nodes = []
conns = {}


def connect(a, b):
    conns.setdefault(a, {"main": [[]]})
    conns[a]["main"][0].append({"node": b, "type": "main", "index": 0})


nodes.append(
    {
        "parameters": {
            "httpMethod": "GET",
            "path": WEBHOOK_PATH,
            "responseMode": "responseNode",
            "options": {"allowedOrigins": "*"},
        },
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [200, 300],
        "name": "Webhook",
        "webhookId": WEBHOOK_PATH,
    }
)
nodes.append(pc.code("Token", CODE_TOKEN, [380, 300]))
nodes.append(
    pc.pg("Leer Estado", SQL_LEER_ESTADO, "={{ [$json.token] }}", [560, 300], tolerar_fallo=True)
)
nodes.append(pc.code("Formatear Estado", CODE_FORMATEAR, [740, 300]))
nodes.append(
    pc.responder_headers(
        "Responder Estado",
        [920, 300],
        [{"name": "X-Robots-Tag", "value": "noindex, nofollow"}],
    )
)

connect("Webhook", "Token")
connect("Token", "Leer Estado")
connect("Leer Estado", "Formatear Estado")
connect("Formatear Estado", "Responder Estado")

wf = {
    "name": "GEOpulse estado (sondeo publico, solo lectura)",
    "nodes": nodes,
    "connections": conns,
    # La landing sondea cada 3 s: sin esto, cada pestana genera decenas de
    # ejecuciones. No guardar las correctas para no inflar el historial de n8n.
    "settings": {"executionOrder": "v1", "saveDataSuccessExecution": "none"},
}

salida = os.path.join(AQUI, "geopulse-estado-workflow.json")
with open(salida, "w", encoding="utf-8") as fh:
    json.dump(wf, fh, ensure_ascii=False, indent=2)

print("OK - geopulse-estado -", len(nodes), "nodos | ruta:", WEBHOOK_PATH)
print("Escrito en:", salida)

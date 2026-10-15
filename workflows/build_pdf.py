#!/usr/bin/env python3
# geopulse-pdf — genera el PDF del informe (plantilla propia + Gotenberg) y lo
# DEVUELVE para que la web lo descargue. El envio por correo va APARTE: automatico
# al terminar la ejecucion (en el workflow LITE, build_lite2_panel).
#
# FLUJO
# La web hace POST { token }. Se busca el informe en la BD por ese token (solo runs
# publicos y completados), se genera el HTML con la plantilla compartida
# (panel_common.CODE_PLANTILLA_PDF, misma que el correo -> mismo PDF), se convierte
# con Gotenberg y se devuelve el binario. La web lo descarga (Blob + <a download>).
#
# CONSTRUIDO A CIEGAS (no hay n8n aqui). Verifica al importar, sobre todo:
#   · Gotenberg PDF -> URL alcanzable + multipart 'files'/index.html
#   · Responder PDF -> respondWith binary (la web recibe el PDF)
#   · Plantilla PDF -> que reciba el informe como objeto (no string)
#
# Uso:  python build_pdf.py
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel_common as pc  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
WEBHOOK_PATH = "geopulse-pdf"

# Busca el informe COMPLETADO por una de dos vias:
#   $1 token  -> solo runs PUBLICOS (landing). Es la via sin auth: el token (UUID
#               opaco) es la credencial.
#   $2 run_id -> cualquier run (tambien del panel). Lo usa la RUTA AUTENTICADA del
#               panel, que ya ha comprobado sesion+propiedad; 'Datos PDF' solo deja
#               pasar este camino si llega el secreto compartido.
SQL_BUSCAR_INFORME = (
    "select i.informe, (r.payload->>'email') as email "
    "from runs r join informes i on i.run_id = r.id "
    "where r.estado = 'completado' and ("
    "  (nullif($1, '') is not null and r.token = $1 and r.origen = 'publico')"
    "  or (r.id = nullif($2, '')::uuid)"
    ") limit 1"
)

CODE_DATOS = r"""// El informe NO viene del cliente: se lee de la BD. Dos vias:
//  - PUBLICO: token (la landing). Via sin auth; el token es la credencial.
//  - PANEL: run_id, pero SOLO si llega el secreto compartido en 'x-panel-secret'.
//    Asi este webhook publico NO queda abierto a bajar cualquier run por id.
const b = $json.body || $json;
const h = $json.headers || {};
const token = String(b.token || '').trim().slice(0, 128);
let run_id = String(b.run_id || '').trim();
const secreto = String(h['x-panel-secret'] || '');
const porId = !!(run_id && secreto && secreto === String($env.PDF_PANEL_SECRET || ''));
if (!porId) run_id = '';  // sin secreto valido, el run_id se ignora
if (!token && !run_id) throw new Error('No autorizado: falta token (publico) o run_id + x-panel-secret (panel)');
return [{ json: { token, run_id } }];"""

CODE_ERR = r"""return [{ json: { ok: false, error: 'servicio' } }];"""

nodes = []
conns = {}


def connect(a, b, out=0, inp=0):
    conns.setdefault(a, {"main": []})
    while len(conns[a]["main"]) <= out:
        conns[a]["main"].append([])
    conns[a]["main"][out].append({"node": b, "type": "main", "index": inp})


nodes.append(
    {
        "parameters": {
            "httpMethod": "POST",
            "path": WEBHOOK_PATH,
            "responseMode": "responseNode",
            "options": {"allowedOrigins": "*"},
        },
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [180, 300],
        "name": "Webhook",
        "webhookId": WEBHOOK_PATH,
    }
)
nodes.append(pc.code("Datos PDF", CODE_DATOS, [360, 300]))
nodes.append(pc.pg("Buscar Informe", SQL_BUSCAR_INFORME, "={{ [$json.token, $json.run_id] }}", [540, 300]))
nodes.append(pc.code("Plantilla PDF", pc.CODE_PLANTILLA_PDF, [720, 300]))
nodes.append(pc.code("Preparar HTML", pc.CODE_PREP_HTML_PDF, [900, 300]))
nodes.append(pc.nodo_gotenberg("Gotenberg PDF", [1080, 300]))  # onError continueErrorOutput
nodes.append(
    {
        "parameters": {
            "respondWith": "binary",
            "responseBinaryPropertyName": "data",
            "options": {
                "responseHeaders": {
                    "entries": [
                        {"name": "Content-Disposition", "value": 'attachment; filename="informe-geopulse.pdf"'},
                        {"name": "X-Robots-Tag", "value": "noindex, nofollow"},
                    ]
                }
            },
        },
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1,
        "position": [1260, 220],
        "name": "Responder PDF",
    }
)
nodes.append(pc.code("Cuerpo Error", CODE_ERR, [1260, 420]))
nodes.append(
    pc.responder_headers("Responder Error", [1440, 420], [{"name": "X-Robots-Tag", "value": "noindex, nofollow"}])
)

connect("Webhook", "Datos PDF")
connect("Datos PDF", "Buscar Informe")
connect("Buscar Informe", "Plantilla PDF")
connect("Plantilla PDF", "Preparar HTML")
connect("Preparar HTML", "Gotenberg PDF")
connect("Gotenberg PDF", "Responder PDF", out=0)   # ok    -> devuelve el PDF
connect("Gotenberg PDF", "Cuerpo Error", out=1)     # error -> json de error
connect("Cuerpo Error", "Responder Error")

wf = {
    "name": "GEOpulse PDF (plantilla + Gotenberg, descarga)",
    "nodes": nodes,
    "connections": conns,
    # No guardar ejecuciones correctas: el PDF binario no queda retenido en disco.
    "settings": {"executionOrder": "v1", "saveDataSuccessExecution": "none"},
}

salida = os.path.join(AQUI, "geopulse-pdf-workflow.json")
with open(salida, "w", encoding="utf-8") as fh:
    json.dump(wf, fh, ensure_ascii=False, indent=2)

print("OK - geopulse-pdf (descarga) -", len(nodes), "nodos | ruta:", WEBHOOK_PATH)
print("Gotenberg:", pc.GOTENBERG_URL)
print("Escrito en:", salida)

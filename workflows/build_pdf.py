#!/usr/bin/env python3
# geopulse-pdf / geopulse-pdf-panel — generan el PDF del informe (plantilla propia +
# Gotenberg) y lo DEVUELVEN para descargarlo. El envio por correo va APARTE
# (automatico al terminar, en build_lite2_panel).
#
# DOS WEBHOOKS, MISMA TUBERIA (plantilla -> Gotenberg -> PDF):
#   · geopulse-pdf        PUBLICO (landing). Busca por { token } y SOLO runs
#                         origen='publico'. Sin auth: el token (opaco) es la credencial.
#   · geopulse-pdf-panel  PANEL. Busca por { run_id } cualquier run. Protegido con la
#                         MISMA credencial Header Auth que 'panel-db' (x-panel-secret),
#                         que el panel ya tiene configurada (N8N_PANEL_DB_SECRET). Lo
#                         llama la ruta autenticada /api/runs/[id]/pdf, que ya ha
#                         comprobado sesion + propiedad.
#
# POR QUE NO UN SOLO WEBHOOK CON $env (error real, 2026-11): la primera version
# validaba el secreto del panel con $env.PDF_PANEL_SECRET dentro de un nodo Code. En
# n8n 2.x (task runners) el acceso a variables de entorno desde los nodos esta
# bloqueado por defecto: el nodo fallaba, n8n respondia 200 con cuerpo VACIO y el
# panel no podia descargar. Separar el webhook del panel y protegerlo con Header Auth
# (comprobado por n8n antes de ejecutar nada) evita $env y no anade secretos nuevos.
#
# Uso:  python build_pdf.py   (escribe los dos JSON)
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel_common as pc  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
# Misma credencial que el webhook de panel-db (build_panel_db.CRED_HEADER_AUTH).
CRED_HEADER_AUTH = "GEOpulse Panel - Header Auth"

SQL_PUBLICO = (
    "select i.informe, (r.payload->>'email') as email "
    "from runs r join informes i on i.run_id = r.id "
    "where r.token = $1 and r.origen = 'publico' and r.estado = 'completado' limit 1"
)
SQL_PANEL = (
    "select i.informe, (r.payload->>'email') as email "
    "from runs r join informes i on i.run_id = r.id "
    "where r.id = $1::uuid and r.estado = 'completado' limit 1"
)

CODE_DATOS_PUBLICO = r"""// Token del cuerpo. El informe NO viene del cliente: se lee de la BD por token,
// asi la web no puede inyectar contenido en el PDF.
const b = $json.body || $json;
const token = String(b.token || '').trim().slice(0, 128);
if (!token) throw new Error('Falta token');
return [{ json: { clave: token } }];"""

CODE_DATOS_PANEL = r"""// run_id del cuerpo. La autenticacion ya la hizo el Webhook (Header Auth): si la
// peticion llega aqui, viene del panel. Se valida el formato para no meter texto
// arbitrario en la consulta.
const b = $json.body || $json;
const run_id = String(b.run_id || '').trim();
if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(run_id)) {
  throw new Error('run_id no valido');
}
return [{ json: { clave: run_id } }];"""

CODE_ERR = r"""return [{ json: { ok: false, error: 'servicio' } }];"""


def construir(nombre, path, webhook_extra, code_datos, sql, fichero):
    nodes, conns = [], {}

    def connect(a, b, out=0):
        conns.setdefault(a, {"main": []})
        while len(conns[a]["main"]) <= out:
            conns[a]["main"].append([])
        conns[a]["main"][out].append({"node": b, "type": "main", "index": 0})

    webhook = {
        "parameters": {"httpMethod": "POST", "path": path, "responseMode": "responseNode"},
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [180, 300],
        "name": "Webhook",
        "webhookId": path,
    }
    webhook["parameters"].update(webhook_extra.get("parameters", {}))
    if "credentials" in webhook_extra:
        webhook["credentials"] = webhook_extra["credentials"]
    nodes.append(webhook)
    nodes.append(pc.code("Datos PDF", code_datos, [360, 300]))
    nodes.append(pc.pg("Buscar Informe", sql, "={{ [$json.clave] }}", [540, 300]))
    nodes.append(pc.code("Plantilla PDF", pc.CODE_PLANTILLA_PDF, [720, 300]))
    nodes.append(pc.code("Preparar HTML", pc.CODE_PREP_HTML_PDF, [900, 300]))
    nodes.append(pc.nodo_gotenberg("Gotenberg PDF", [1080, 300]))  # onError continueErrorOutput
    nodes.append(
        {
            "parameters": {
                "respondWith": "binary",
                # El PDF viaja SIEMPRE en el campo binario 'data' (salida de Gotenberg).
                "responseBinaryPropertyName": "data",
                "options": {
                    "responseHeaders": {
                        "entries": [
                            {"name": "Content-Type", "value": "application/pdf"},
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
    err = pc.responder_headers("Responder Error", [1440, 420], [{"name": "X-Robots-Tag", "value": "noindex, nofollow"}])
    # 502, no 200: un fallo de Gotenberg no debe parecer una respuesta valida.
    err["parameters"]["options"]["responseCode"] = 502
    nodes.append(err)

    connect("Webhook", "Datos PDF")
    connect("Datos PDF", "Buscar Informe")
    connect("Buscar Informe", "Plantilla PDF")
    connect("Plantilla PDF", "Preparar HTML")
    connect("Preparar HTML", "Gotenberg PDF")
    connect("Gotenberg PDF", "Responder PDF", out=0)  # ok    -> devuelve el PDF
    connect("Gotenberg PDF", "Cuerpo Error", out=1)   # error -> json 502
    connect("Cuerpo Error", "Responder Error")

    wf = {
        "name": nombre,
        "nodes": nodes,
        "connections": conns,
        # No guardar ejecuciones correctas: el PDF binario no queda retenido en disco.
        "settings": {"executionOrder": "v1", "saveDataSuccessExecution": "none"},
    }
    salida = os.path.join(AQUI, fichero)
    with open(salida, "w", encoding="utf-8") as fh:
        json.dump(wf, fh, ensure_ascii=False, indent=2)
    print("OK -", path, "-", len(nodes), "nodos ->", salida)


construir(
    "GEOpulse PDF publico (token -> plantilla + Gotenberg)",
    "geopulse-pdf",
    {"parameters": {"options": {"allowedOrigins": "*"}}},
    CODE_DATOS_PUBLICO,
    SQL_PUBLICO,
    "geopulse-pdf-workflow.json",
)
construir(
    "GEOpulse PDF panel (run_id + Header Auth -> plantilla + Gotenberg)",
    "geopulse-pdf-panel",
    {
        "parameters": {"authentication": "headerAuth", "options": {}},
        "credentials": {"httpHeaderAuth": {"name": CRED_HEADER_AUTH}},
    },
    CODE_DATOS_PANEL,
    SQL_PANEL,
    "geopulse-pdf-panel-workflow.json",
)
print("Gotenberg:", pc.GOTENBERG_URL)

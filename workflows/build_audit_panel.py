#!/usr/bin/env python3
# GEOpulse COMPLETO - variante para el PANEL (ruta geopulse-audit-panel).
#
# Mismo patron que build_lite2_panel.py, sobre el informe completo (71 nodos):
# ack inmediato, marcar 'en_curso', correr el analisis TAL CUAL y guardar el
# informe en Postgres al terminar.
#
# LO QUE NO CAMBIA
#   · Prompts, modelos, sondeos, pesos y nota: identicos. Se reutilizan los nodos
#     de build_workflow_v10.py importandolo como modulo.
#   · El webhook publico 'geopulse-audit' NO se toca (ruta propia aqui).
#
# DOS DIFERENCIAS DELIBERADAS RESPECTO AL PUBLICO
#   1. Auth de Gemini: produccion usa la credencial predefinida googlePalmApi en
#      los 4 nodos D1-D4; el builder tenia Header Auth generica. Se aplica la de
#      produccion (misma deriva que ya se vio en el LITE).
#   2. SIN ENVIO DE EMAIL. El publico, al acabar, genera un PDF y lo envia por
#      SMTP a la direccion que venga en el body. Una auditoria interna lanzada
#      desde el panel no debe mandar correo a nadie (podria acabar en el buzon de
#      un cliente sin querer), asi que esa rama se elimina: 'Generar Informe
#      HTML' -> 'HTML a PDF' -> 'Enviar Informe'. Si algun dia se quiere "enviar
#      este informe al cliente", que sea una accion explicita del panel.
#
# Uso:  python build_audit_panel.py
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_workflow_v10  # noqa: E402  (reutiliza sus nodos: mismo analisis)
import panel_common as pc  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
WEBHOOK_PATH = "geopulse-audit-panel"

# Credenciales tal y como estan en el workflow de produccion (GEOpulse.json).
CREDENCIALES_PROD = {
    "D1 - ChatGPT": {"openAiApi": {"name": "OpenAi account"}},
    "D2 - ChatGPT": {"openAiApi": {"name": "OpenAi account"}},
    "D3 - ChatGPT": {"openAiApi": {"name": "OpenAi account"}},
    "D4 - ChatGPT": {"openAiApi": {"name": "OpenAi account"}},
    "D1 - Claude": {"anthropicApi": {"name": "Anthropic account"}},
    "D2 - Claude": {"anthropicApi": {"name": "Anthropic account"}},
    "D3 - Claude": {"anthropicApi": {"name": "Anthropic account"}},
    "D4 - Claude": {"anthropicApi": {"name": "Anthropic account"}},
    "D1 - Gemini": {"googlePalmApi": {"name": "Google Gemini BranDevs"}},
    "D2 - Gemini": {"googlePalmApi": {"name": "Google Gemini BranDevs"}},
    "D3 - Gemini": {"googlePalmApi": {"name": "Google Gemini BranDevs"}},
    "D4 - Gemini": {"googlePalmApi": {"name": "Google Gemini BranDevs"}},
    "D1 - Perplexity": {"httpHeaderAuth": {"name": "Perplexity"}},
    "D2 - Perplexity": {"httpHeaderAuth": {"name": "Perplexity"}},
    "D3 - Perplexity": {"httpHeaderAuth": {"name": "Perplexity"}},
    "D4 - Perplexity": {"httpHeaderAuth": {"name": "Perplexity"}},
}

# Gemini en produccion usa credencial predefinida, no Header Auth generica.
AUTH_PROD_GEMINI = {
    "authentication": "predefinedCredentialType",
    "nodeCredentialType": "googlePalmApi",
}

# La rama de PDF + email: fuera en la variante interna (ver cabecera).
NODOS_EMAIL = ["Generar Informe HTML", "HTML a PDF", "Enviar Informe"]

# ============================================================
# PARCHE: puntuacion de la dimension "competitivo"
# ============================================================
# BUG (medido en una ejecucion real, 2026-08-13):
#   const s_comp = mods === 0 ? 0 : (pm <= 3 ? 100 : (mods >= 2 ? 70 : 50));
#   Bastaba con que la marca fuese NOMBRADA por 2 modelos para sacar 70/100 en
#   competitivo, aunque no tuviese ninguna posicion atribuible. En esa ejecucion
#   el propio informe decia "No hay evidencia textual suficiente para situarla
#   frente a rivales" y aun asi puntuaba 70. Con los pesos de SOV
#   (desc .45 / comp .20 / conoc .20 / rep .15) ese 70 aportaba 14 de los 28,9
#   puntos: el 48% de la nota de visibilidad salia de una dimension sin evidencia.
#
# ARREGLO: manda la POSICION, no la mera mencion.
#   · Sin mencion            -> 0    (igual que antes: la ausencia SI es medible)
#   · Posicion <= 3          -> 100  (igual que antes: lidera de verdad)
#   · Posicion conocida > 3  -> escala con la posicion, en vez de un 70/50 plano
#   · Mencionada SIN posicion-> presencia debil proporcional a cuantos modelos la
#                               citan (2 de 4 -> 20), nunca un 70.
# Con los datos de esa ejecucion la visibilidad pasa de 29 a ~19, que es lo que
# el informe describe en palabras.
ORIGINAL_S_COMP = (
    "const s_comp = mods === 0 ? 0 : "
    "(typeof pm === 'number' && pm <= 3 ? 100 : (mods >= 2 ? 70 : 50));"
)
PARCHE_S_COMP = (
    "// [PARCHE PANEL] manda la posicion, no la mera mencion: ser nombrada sin\n"
    "// posicion atribuible es presencia debil, no un 70 (ver build_audit_panel.py).\n"
    "const s_comp = mods === 0 ? 0\n"
    "  : (typeof pm === 'number' && pm <= 3 ? 100\n"
    "  : (typeof pm === 'number' ? Math.max(20, Math.round(100 - (pm - 3) * 10))\n"
    "  : Math.round(40 * mods / 4)));"
)


def parchear_s_comp(js):
    """Corrige la puntuacion de 'competitivo' en el nodo Calcular Score."""
    if ORIGINAL_S_COMP not in js:
        raise SystemExit(
            "El parche de s_comp ya no aplica: 'Calcular Score' ha cambiado.\n"
            "Revisa la formula de s_comp antes de seguir."
        )
    return js.replace(ORIGINAL_S_COMP, PARCHE_S_COMP, 1)

# ============================================================
# CONSTRUCCION
# ============================================================
nodes = copy.deepcopy(build_workflow_v10.nodes)
conns = copy.deepcopy(build_workflow_v10.connections)
por_nombre = {n["name"]: n for n in nodes}

# 1. Credenciales reales de produccion (y correccion de la deriva de Gemini).
for nombre, creds in CREDENCIALES_PROD.items():
    if nombre in por_nombre:
        por_nombre[nombre]["credentials"] = creds
for nombre in [n for n in por_nombre if n.endswith("- Gemini")]:
    params = por_nombre[nombre]["parameters"]
    params.pop("genericAuthType", None)
    params.update(AUTH_PROD_GEMINI)

# 1.b Parche de la puntuacion competitiva (ver el bloque de arriba).
calcular = por_nombre["Calcular Score"]
calcular["parameters"]["jsCode"] = parchear_s_comp(calcular["parameters"]["jsCode"])

# 1.c Sondas en los modelos que usa hoy la version gratuita, y agentes de
#     analisis con menos temperatura (ver panel_common.py).
_cambios_modelo = pc.actualizar_modelos_sondeo(nodes)
_cambios_temp = pc.bajar_temperatura_analisis(nodes)

# 1.d Encabezados con parser real (el regex se tragaba el <h1>).
_cambios_head = pc.parchear_encabezados(nodes)

# 2. Ruta propia: el publico 'geopulse-audit' se queda intacto.
#    NO se renombra el nodo: en el completo se llama 'Webhook GEOpulse' y
#    renombrarlo romperia sus conexiones y las referencias $('...').
webhook = next(n for n in nodes if n["type"] == "n8n-nodes-base.webhook")
NOMBRE_WEBHOOK = webhook["name"]
webhook["parameters"]["path"] = WEBHOOK_PATH
webhook["webhookId"] = WEBHOOK_PATH

# 3. Fuera la rama de PDF + email y el Respond original (ya no devolvemos el
#    informe por HTTP: lo escribimos en Postgres).
pc.quitar_nodos(nodes, conns, NODOS_EMAIL + ["Respond to Webhook"])

# 4. Ciclo de vida asincrono. El analisis arranca en Y=464 (posiciones del
#    builder v10), asi que el ack va en Y=200: por encima => se ejecuta antes.
def connect(a, b, idx=0):
    conns.setdefault(a, {"main": [[]]})
    conns[a]["main"][0].append({"node": b, "type": "main", "index": idx})


pc.anadir_ciclo_de_vida(
    nodes,
    connect,
    nodo_final_informe="Ensamblar Reporte",
    nombre_webhook=NOMBRE_WEBHOOK,
    y_ack=200,
    x_fin=22000,  # a la derecha del ultimo nodo del lienzo v10
)
# rama_ack_primero YA crea la conexion (insertandola la primera), no hay que
# anadirla tambien con connect() o saldria duplicada.
pc.rama_ack_primero(conns, NOMBRE_WEBHOOK)

wf = {
    "name": "GEOpulse COMPLETO - panel (asincrono, escribe en Postgres)",
    "nodes": nodes,
    "connections": conns,
    "settings": {"executionOrder": "v1"},
    "pinData": {},
}

pc.comprobar_sin_clientes(wf)

salida = os.path.join(AQUI, "geopulse-audit-panel-workflow.json")
with open(salida, "w", encoding="utf-8") as fh:
    json.dump(wf, fh, ensure_ascii=False, indent=2)

print("OK - nodos:", len(nodes), "| conexiones:", sum(len(c["main"][0]) for c in conns.values()))
print("Ruta del webhook:", WEBHOOK_PATH)
print("Eliminada la rama de email:", ", ".join(NODOS_EMAIL))
print("Modelos de sondeo actualizados:", len(_cambios_modelo))
for c in _cambios_modelo:
    print("   ", c)
print("Agentes con temperatura bajada:", len(_cambios_temp))
print("Encabezados con parser real en:", ", ".join(_cambios_head))
print("Escrito en:", salida)

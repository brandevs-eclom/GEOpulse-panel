#!/usr/bin/env python3
# GEOpulse LITE - variante para el PANEL (ruta geopulse-lite2-panel).
#
# QUE ES
# El mismo analisis LITE que el webhook publico, pero con dos cambios de
# fontaneria (NUNCA de logica de analisis):
#   1. Responde AL INSTANTE con un ack, en vez de sostener la conexion 1-2 min.
#      El panel corre en serverless y no puede esperar tanto.
#   2. Escribe el resultado en Postgres (que esta en este mismo servidor), en vez
#      de limitarse a devolverlo. El panel luego lo lee por polling.
#
# LO QUE NO CAMBIA (importante, docs/04)
#   · Los sondeos, los prompts, los pesos y la nota son EXACTAMENTE los mismos:
#     se reutilizan los nodos de build_lite2.py tal cual, importandolo como modulo.
#   · El webhook publico 'geopulse-lite2' NO se toca: esta variante usa una ruta
#     propia, asi que los widgets de la web siguen funcionando igual.
#
# DERIVA CORREGIDA
# El JSON que corre en produccion se habia desviado del builder en la autenticacion
# de Gemini (el builder usa Header Auth generica; produccion usa la credencial
# predefinida googlePalmApi). Aqui se aplican las credenciales REALES de produccion
# para que la variante funcione y para que al importar queden enlazadas solas.
#
# La fontaneria comun con la variante del COMPLETO vive en panel_common.py.
#
# Uso:  python build_lite2_panel.py
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_lite2  # noqa: E402  (reutiliza sus nodos: misma logica de analisis)
import panel_common as pc  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
WEBHOOK_PATH = "geopulse-lite2-panel"

# Credenciales tal y como estan en el workflow de produccion (GEOpulse LITE.json).
CREDENCIALES_PROD = {
    "Sonda - ChatGPT": {"openAiApi": {"name": "OpenAi account"}},
    "Sonda - Claude": {"anthropicApi": {"name": "Anthropic account"}},
    "Sonda - Gemini": {"googlePalmApi": {"name": "Google Gemini BranDevs"}},
    "Sonda - Perplexity": {"httpHeaderAuth": {"name": "Perplexity"}},
    "Huella - Perplexity": {"httpHeaderAuth": {"name": "Perplexity"}},
    "Informe ChatGPT": {"openAiApi": {"name": "OpenAi account"}},
}
# Gemini en produccion usa credencial predefinida, no Header Auth generica.
AUTH_PROD = {
    "Sonda - Gemini": {
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "googlePalmApi",
        "_quitar": ["genericAuthType"],
    }
}

# ============================================================
# PARCHE: deteccion de marca en el mapa competitivo
# ============================================================
# BUG (medido en una ejecucion real, 2026-07-27):
#   'Ensamblar LITE2' hacia  es_marca: !!x.es_marca || norm(x.empresa) === norm(r.brand)
#   es decir, se creia el flag 'es_marca' que devuelve el agente LLM. En esa ejecucion
#   el agente marco como "tu marca" a 7 competidores (grandes operadores del sector).
#   Como el render coge el PRIMER es_marca para la cuota, el donut mostraba un 17%
#   de cuota propia cuando la marca real tenia 1 de 36 menciones = 3%.
#
# ARREGLO: no fiarse del LLM. Derivar es_marca del nombre, con el token distintivo
# que 'Recopilar Respuestas' YA calcula bien: excluye las palabras genericas del
# sector y del mercado, de modo que una marca cuyo nombre incluya su propio sector
# no cuente como mencion cualquier empresa de ese sector. Viaja en
# _diag.marca_distintivo.
#
# Se aplica SOLO AQUI a proposito: build_lite2.py no se toca, asi que el webhook
# publico y sus widgets siguen exactamente igual hasta que se decida migrarlos.
ORIGINAL_ES_MARCA = (
    "    es_marca: !!x.es_marca || norm(x.empresa) === norm(r.brand),"
)
PARCHE_ES_MARCA = """    es_marca: esMarcaEmpresa(x.empresa),"""

HELPER_ES_MARCA = r"""// [PARCHE PANEL] es_marca NO se toma del agente LLM: se deriva del nombre.
// El agente marcaba competidores como "tu marca" e inflaba la cuota del cliente.
const _distintivoMarca = (r._diag && r._diag.marca_distintivo) || null;
const _brandNorm = norm(r.brand);
function esMarcaEmpresa(nombre) {
  const n = norm(nombre);
  if (!n) return false;
  if (_brandNorm.length > 2 && n === _brandNorm) return true;
  // El distintivo ya viene depurado de palabras genericas del sector/mercado.
  if (_distintivoMarca && n.includes(_distintivoMarca)) return true;
  // Sin distintivo fiable, solo vale el nombre exacto: antes marcar de menos que
  // decirle al cliente que un competidor es su marca.
  return false;
}
let mapa = ("""


def parchear_es_marca(js):
    """Sustituye la deteccion de marca del mapa competitivo en el jsCode."""
    if ORIGINAL_ES_MARCA not in js:
        raise SystemExit(
            "El parche de es_marca ya no aplica: 'Ensamblar LITE2' ha cambiado en\n"
            "build_lite2.py. Revisa la linea de es_marca antes de seguir."
        )
    js = js.replace(ORIGINAL_ES_MARCA, PARCHE_ES_MARCA, 1)
    # El helper se inyecta justo antes de construir el mapa.
    ancla = "let mapa = ("
    if js.count(ancla) != 1:
        raise SystemExit("No encuentro (o hay varios) 'let mapa = (' en Ensamblar LITE2")
    return js.replace(ancla, HELPER_ES_MARCA, 1)


# ============================================================
# CONSTRUCCION: se parte de los nodos del LITE original
# ============================================================
nodes = copy.deepcopy(build_lite2.nodes)
conns = copy.deepcopy(build_lite2.conns)
por_nombre = {n["name"]: n for n in nodes}

# 1. Credenciales reales de produccion (y correccion de la deriva de Gemini).
for nombre, creds in CREDENCIALES_PROD.items():
    if nombre in por_nombre:
        por_nombre[nombre]["credentials"] = creds
for nombre, ajuste in AUTH_PROD.items():
    if nombre not in por_nombre:
        continue
    params = por_nombre[nombre]["parameters"]
    for k in ajuste.pop("_quitar", []):
        params.pop(k, None)
    params.update(ajuste)

# 2. Parche de es_marca (ver el bloque de arriba). Solo en la variante del panel.
ensamblar = por_nombre["Ensamblar LITE2"]
ensamblar["parameters"]["jsCode"] = parchear_es_marca(ensamblar["parameters"]["jsCode"])

# 2.b Sondas en los modelos que usa hoy la version gratuita (ver panel_common.py).
#     El LITE no tiene agentes de analisis con temperature configurable.
_cambios_modelo = pc.actualizar_modelos_sondeo(nodes)

# 2.c Encabezados con parser real (el regex se tragaba el <h1>).
_cambios_head = pc.parchear_encabezados(nodes)

# 3. El webhook usa ruta propia: el publico 'geopulse-lite2' se queda intacto.
wh = por_nombre["Webhook"]
wh["parameters"]["path"] = WEBHOOK_PATH
wh["webhookId"] = WEBHOOK_PATH

# 4. El 'Responder' original sobra: ya no devolvemos el informe por HTTP.
pc.quitar_nodos(nodes, conns, ["Responder"])


# 5. Ciclo de vida asincrono (ack + guardado). El analisis arranca en Y=460, asi
#    que el ack va en Y=200: por encima => n8n lo ejecuta antes.
def connect(a, b, idx=0):
    conns.setdefault(a, {"main": [[]]})
    conns[a]["main"][0].append({"node": b, "type": "main", "index": idx})


pc.anadir_ciclo_de_vida(
    nodes,
    connect,
    nodo_final_informe="Ensamblar LITE2",
    nombre_webhook="Webhook",
    y_ack=200,
    x_fin=3560,
)
pc.rama_ack_primero(conns, "Webhook")

wf = {
    "name": "GEOpulse LITE - panel (asincrono, escribe en Postgres)",
    "nodes": nodes,
    "connections": conns,
    "settings": {"executionOrder": "v1"},
}

pc.comprobar_sin_clientes(wf)

salida = os.path.join(AQUI, "geopulse-lite2-panel-workflow.json")
with open(salida, "w", encoding="utf-8") as fh:
    json.dump(wf, fh, ensure_ascii=False, indent=2)

print("OK - nodos:", len(nodes), "| conexiones:", sum(len(c["main"][0]) for c in conns.values()))
print("Ruta del webhook:", WEBHOOK_PATH)
print("Modelos de sondeo actualizados:", len(_cambios_modelo))
for c in _cambios_modelo:
    print("   ", c)
print("Encabezados con parser real en:", ", ".join(_cambios_head))
print("Escrito en:", salida)

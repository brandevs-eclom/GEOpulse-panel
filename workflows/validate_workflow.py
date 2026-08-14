#!/usr/bin/env python3
# Validador de workflows de n8n (lo pide docs/04, seccion "Validacion").
#
# Comprueba, sobre el JSON YA GENERADO, las reglas que en este proyecto han
# costado bugs reales de produccion. No sustituye a probar el workflow en n8n:
# solo detecta los fallos estructurales que se pueden ver sin ejecutarlo.
#
# Uso:
#   python validate_workflow.py                  -> valida todos los .json de esta carpeta
#   python validate_workflow.py fichero.json ... -> valida los indicados
#
# Salida: lista de ERROR (rompe el workflow) y AVISO (huele mal, revisalo).
# Codigo de salida 1 si hay algun ERROR.
import glob
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))

TIPO_HTTP = "n8n-nodes-base.httpRequest"
TIPO_MERGE = "n8n-nodes-base.merge"
TIPO_CODE = "n8n-nodes-base.code"

# Nodos que por definicion no se conectan a nada: no son huerfanos.
TIPOS_SIN_CONEXION = {"n8n-nodes-base.stickyNote"}

# Hosts de las APIs de modelos, para saber donde importa de verdad fullResponse.
HOSTS_LLM = (
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.perplexity.ai",
)


def texto_de(valor):
    """Aplana cualquier estructura a una cadena, para poder buscar patrones."""
    if isinstance(valor, str):
        return valor
    if isinstance(valor, dict):
        return " ".join(texto_de(v) for v in valor.values())
    if isinstance(valor, list):
        return " ".join(texto_de(v) for v in valor)
    return ""


def expresiones_de(valor):
    """Devuelve todas las expresiones '={{ ... }}' que aparezcan en el valor."""
    return re.findall(r"=\{\{.*?\}\}", texto_de(valor), flags=re.S)


def validar(ruta):
    errores, avisos = [], []
    with open(ruta, encoding="utf-8") as fh:
        try:
            wf = json.load(fh)
        except json.JSONDecodeError as exc:
            return ["JSON invalido: %s" % exc], []

    nodes = wf.get("nodes", [])
    conns = wf.get("connections", {})
    nombres = [n.get("name", "(sin nombre)") for n in nodes]

    # 1. Nombres de nodo unicos. n8n los usa como clave: un duplicado rompe
    #    silenciosamente las referencias $('Nodo').
    vistos = set()
    for n in nombres:
        if n in vistos:
            errores.append("Nombre de nodo duplicado: %r" % n)
        vistos.add(n)
    conjunto = set(nombres)

    # 2. Toda referencia $('Nodo') debe apuntar a un nodo existente.
    for nodo in nodes:
        cuerpo = texto_de(nodo.get("parameters", {}))
        for ref in re.findall(r"\$\(\s*['\"]([^'\"]+)['\"]\s*\)", cuerpo):
            if ref not in conjunto:
                errores.append(
                    "%s referencia $('%s'), que no existe" % (nodo.get("name"), ref)
                )

    # 3. Nada de '}}' dentro de una expresion '={{ }}': rompe el parseo de n8n.
    #    Solo aplica a expresiones; el jsCode de un nodo Code es JS normal.
    for nodo in nodes:
        params = dict(nodo.get("parameters", {}))
        params.pop("jsCode", None)
        for expr in expresiones_de(params):
            interior = expr[3:-2]
            if "}}" in interior:
                errores.append(
                    "%s tiene '}}' dentro de una expresion: %s"
                    % (nodo.get("name"), expr[:80])
                )

    # 4. Los destinos de las conexiones deben existir.
    for origen, salidas in conns.items():
        if origen not in conjunto:
            errores.append("Conexion desde un nodo inexistente: %r" % origen)
        for rama in salidas.get("main", []):
            for enlace in rama or []:
                destino = enlace.get("node")
                if destino not in conjunto:
                    errores.append(
                        "Conexion %s -> %r: el destino no existe" % (origen, destino)
                    )

    # 5. Reglas de oro de los GET a la web del cliente (docs/04): sin User-Agent
    #    de navegador los WAF devuelven 403 y el analisis tecnico sale vacio.
    for nodo in nodes:
        if nodo.get("type") != TIPO_HTTP:
            continue
        p = nodo.get("parameters", {})
        metodo = str(p.get("method", "GET")).upper()
        plano = texto_de(p)
        resp = p.get("options", {}).get("response", {}).get("response", {})
        if metodo == "GET":
            if "user-agent" not in plano.lower():
                errores.append("%s (GET) no envia User-Agent" % nodo.get("name"))
            if resp.get("outputPropertyName") != "body":
                errores.append(
                    "%s (GET) no tiene outputPropertyName='body'" % nodo.get("name")
                )
            if not resp.get("neverError"):
                avisos.append(
                    "%s (GET) sin neverError: un 4xx tumbaria el analisis"
                    % nodo.get("name")
                )
        # 6. Respuestas de LLM: sin fullResponse, pick() no encuentra el cuerpo
        #    (viene en .body). Solo aplica a las APIs de modelos: en un GET
        #    normal o en un servicio auxiliar, fullResponse es indiferente.
        if any(host in plano for host in HOSTS_LLM) and not resp.get("fullResponse"):
            avisos.append(
                "%s llama a una API de LLM sin fullResponse: pick() no encontrara el cuerpo"
                % nodo.get("name")
            )

    # 7. Los Merge deben declarar tantas entradas como conexiones reciben.
    entradas = {}
    for salidas in conns.values():
        for rama in salidas.get("main", []):
            for enlace in rama or []:
                if enlace.get("node"):
                    entradas.setdefault(enlace["node"], set()).add(
                        enlace.get("index", 0)
                    )
    for nodo in nodes:
        if nodo.get("type") != TIPO_MERGE:
            continue
        declaradas = nodo.get("parameters", {}).get("numberInputs")
        recibidas = len(entradas.get(nodo.get("name"), set()))
        if declaradas is not None and recibidas != declaradas:
            errores.append(
                "%s declara %s entradas pero recibe %d"
                % (nodo.get("name"), declaradas, recibidas)
            )

    # 8. Nodos huerfanos: ni reciben ni emiten. Casi siempre es un olvido.
    emisores = set(conns.keys())
    receptores = set(entradas.keys())
    for nodo in nodes:
        nombre = nodo.get("name")
        if nodo.get("type") in TIPOS_SIN_CONEXION:
            continue
        if nodo.get("type") == "n8n-nodes-base.webhook":
            continue
        if nombre not in emisores and nombre not in receptores:
            avisos.append("%s no esta conectado a nada" % nombre)

    return errores, avisos


def main():
    objetivos = sys.argv[1:] or sorted(glob.glob(os.path.join(AQUI, "*.json")))
    if not objetivos:
        print("No hay ficheros .json que validar.")
        return 0

    total_errores = 0
    for ruta in objetivos:
        errores, avisos = validar(ruta)
        total_errores += len(errores)
        estado = "FALLA" if errores else ("OK con avisos" if avisos else "OK")
        print("\n=== %s -> %s ===" % (os.path.basename(ruta), estado))
        for e in errores:
            print("  ERROR  %s" % e)
        for a in avisos:
            print("  aviso  %s" % a)

    print("\nTotal de errores: %d" % total_errores)
    return 1 if total_errores else 0


if __name__ == "__main__":
    sys.exit(main())

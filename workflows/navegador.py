# Identidad y RITMO de todas las peticiones del analisis a la web del cliente.
#
# POR QUE (error real, 2026-11): un analisis COMPLETO pedia ~170 URLs de la web del
# cliente en un par de minutos, en rafagas de 5 cada 400 ms, con un User-Agent de
# Chrome viejo y SIN el resto de cabeceras de un navegador. El antifuerza bruta del
# servidor lo tomo por un ataque y empezo a descartar las conexiones (timeouts en
# llms.txt y en la home). La solucion no es "colarse" (rotar IPs o proxies seria
# saltarse un control de seguridad del cliente), sino NO PARECER UN ATAQUE:
#   · cabeceras de un navegador real y actual (no solo el User-Agent),
#   · una peticion cada poco en vez de rafagas,
#   · menos volumen en los rastreos masivos.
# Si aun asi el servidor bloquea, lo correcto es pedir al cliente que ponga en lista
# blanca la IP del servidor de n8n.
#
# EXCEPCION a proposito: 'Fetch como Bot IA' usa los User-Agent de GPTBot, ClaudeBot...
# porque su trabajo es comprobar si a ESOS bots les dejan pasar.
#
# Mantenimiento: sube la version de Chrome cada pocos meses (un UA muy antiguo es en
# si mismo una senal de bot).

UA_NAVEGADOR = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)

# Lo que manda un Chrome real al pedir una pagina. Sin Accept-Encoding: la
# descompresion la gestiona n8n, y forzar 'br' puede romper la lectura del cuerpo.
CABECERAS_NAVEGADOR = [
    {"name": "User-Agent", "value": UA_NAVEGADOR},
    {"name": "Accept", "value": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"},
    {"name": "Accept-Language", "value": "es-ES,es;q=0.9,en;q=0.8"},
    {"name": "Upgrade-Insecure-Requests", "value": "1"},
]

# Tope de enlaces que se comprueban (antes 120). Las 30 paginas se mantienen: lo
# promete el texto de la landing.
CAP_ENLACES = 60


def cabeceras():
    """Copia fresca de las cabeceras (cada nodo la suya: nada de referencias compartidas)."""
    return [dict(h) for h in CABECERAS_NAVEGADOR]


def lote(intervalo_ms=900):
    """Ritmo educado para nodos que lanzan muchas peticiones: de una en una, con pausa."""
    return {"batch": {"batchSize": 1, "batchInterval": intervalo_ms}}

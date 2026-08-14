#!/usr/bin/env python3
"""Piezas compartidas por las variantes de workflow para el PANEL.

Las variantes (LITE y COMPLETO) hacen lo mismo sobre analisis distintos:
  1. Responden con un ack INMEDIATO (el panel corre en serverless y no puede
     sostener una conexion de minutos).
  2. Marcan la ejecucion 'en_curso'.
  3. Corren el analisis TAL CUAL (no se toca ni un prompt ni un peso).
  4. Al terminar guardan el informe en Postgres y cierran la fila como 'completado'.

Los webhooks publicos NO se tocan: cada variante registra su propia ruta.
"""

import json

# Credencial de Postgres ya existente en n8n. Fijarla hace que al reimportar el
# nodo quede enlazado solo, sin reasignarla a mano.
CRED_POSTGRES = "GEOpulse User"

# Salvaguarda: ningun nombre de cliente debe acabar en un workflow generado, ni
# siquiera dentro de un comentario. Los ejemplos van con nombres genericos o con
# la marca de la agencia. Anade aqui nombres concretos que quieras bloquear.
CLIENTES_PROHIBIDOS: list[str] = []


# ============================================================
# CODE NODES comunes
# ============================================================

# El nodo webhook no se llama igual en los dos workflows ('Webhook' en el LITE,
# 'Webhook GEOpulse' en el completo) y NO se renombra: hacerlo romperia todas las
# referencias $('...') y las conexiones existentes. Se sustituye el marcador.
MARCA_WEBHOOK = "__WEBHOOK__"

CODE_ACK = r"""// Ack inmediato para el panel. El run_id llega del panel; si no viene, el
// analisis se ejecuta igual pero no se podra guardar (se avisa en la respuesta).
const b = $json.body || $json;
const run_id = String(b.run_id || '').trim();
return [{ json: { ok: true, run_id: run_id || null, aceptado: !!run_id } }];"""


CODE_PREPARAR_GUARDADO = r"""// Extrae a columnas lo que la tabla necesita y prepara el informe para guardar.
// Tolerante a las DOS formas del informe:
//   LITE     -> nota, por_area, posicionamiento.veredicto, meta.sondeos
//   COMPLETO -> score.global, score.por_area, informe_llm.veredicto_visibilidad.nivel,
//               meta.sondeos_totales
// Si un dato no esta, se queda en null: el panel lo pinta como "-" en vez de
// inventarse un 0 (principio de honestidad del informe).
const informe = $json;
const run_id = String($('__WEBHOOK__').first().json.body.run_id || '').trim();
if (!run_id) throw new Error('Falta run_id: el panel no lo envio en el body');

const num = (v) => (typeof v === 'number' && isFinite(v)) ? Math.round(v) : null;
const score = informe.score || {};
const meta = informe.meta || {};

const nota = num(informe.nota) ?? num(score.global);
const area = informe.por_area || score.por_area || {};
const sov = num(area.sov);
const sondeos = num(meta.sondeos) ?? num(meta.sondeos_totales);

const vLite = informe.posicionamiento && informe.posicionamiento.veredicto;
const vCompleto = informe.informe_llm
  && informe.informe_llm.veredicto_visibilidad
  && informe.informe_llm.veredicto_visibilidad.nivel;
const veredicto = vLite || vCompleto || null;

const avisos = Array.isArray(informe.avisos) ? informe.avisos : [];

return [{ json: {
  run_id,
  informe_json: JSON.stringify(informe),
  nota, veredicto, sov, sondeos,
  tiene_avisos: avisos.length > 0
} }];"""


# ============================================================
# MODELOS DE LOS SONDEOS
# ============================================================
# La auditoria mide lo que obtiene un usuario REAL, asi que las sondas deben
# usar los modelos que sirve hoy la version gratuita de cada producto:
#   · ChatGPT gratis -> GPT-5.6 Luna   (por defecto para Free desde 2026-08)
#   · Gemini gratis  -> Gemini 3.5 Flash (por defecto en la app desde 2026-07)
# IDs verificados en la documentacion oficial de cada proveedor.
MODELO_CHATGPT_ANTERIOR = "gpt-5.4-mini"
MODELO_CHATGPT_SONDEO = "gpt-5.6-luna"
MODELO_GEMINI_ANTERIOR = "gemini-2.5-flash"
MODELO_GEMINI_SONDEO = "gemini-3.5-flash"

# Temperatura de los agentes de ANALISIS (no de las sondas). Bajarla reduce la
# varianza entre ejecuciones, que es lo que interesa en una auditoria que se
# repite en el tiempo y se compara consigo misma.
# Nota: docs/04 dice que gpt-5.4-mini rechaza temperature con 400; el usuario lo
# probo a mano y SI la acepta, asi que manda la prueba empirica. Si alguna
# ejecucion empezara a fallar con 400 en los agentes, este es el primer sitio
# donde mirar.
TEMPERATURA_ANALISIS = 0.2

# CRITICO (Gemini 3.x): 'thinkingBudget' esta deprecado y su sustituto es
# 'thinking_level'. Enviar LOS DOS devuelve un 400, asi que hay que sustituir,
# nunca anadir. No existe equivalente exacto a thinkingBudget:0 — 'minimal' es
# lo mas cercano y NO garantiza que el modelo no razone, por eso se mantiene un
# maxOutputTokens holgado (el motivo original del budget 0 era que Gemini
# gastaba los tokens pensando y cortaba la respuesta).
THINKING_ANTERIOR = "thinkingConfig: { thinkingBudget: 0 }"
THINKING_NUEVO = "thinkingConfig: { thinking_level: 'minimal' }"


def _sustituir(js, antes, despues, donde):
    if antes not in js:
        raise SystemExit(
            "No encuentro %r en %s.\n"
            "El workflow original ha cambiado: revisa el parche antes de seguir." % (antes, donde)
        )
    return js.replace(antes, despues)


# Solo las SONDAS cambian de modelo. Los agentes de analisis que tambien llaman
# a OpenAI ('Informe ChatGPT', 'Agente 5 - Huella Digital', 'Descubrir
# Directorios') NO son lo que ve un usuario gratuito: son el motor de la
# auditoria. Ademas dos usan la Responses API, donde un cambio de modelo es mas
# arriesgado. Se quedan como estan.
import re as _re

_ES_SONDA = _re.compile(r"^(D[1-4] - |Sonda - |Huella - )", _re.I)


def actualizar_modelos_sondeo(nodes):
    """Pone las SONDAS en los modelos que usa hoy la version gratuita.

    Devuelve un resumen de lo cambiado para poder auditarlo por consola.
    """
    cambios = []
    for n in nodes:
        if n.get("type") != "n8n-nodes-base.httpRequest":
            continue
        if not _ES_SONDA.match(n.get("name", "")):
            continue
        p = n.get("parameters", {})

        # ChatGPT: el modelo viaja en el cuerpo JSON.
        cuerpo = p.get("jsonBody")
        if cuerpo and MODELO_CHATGPT_ANTERIOR in cuerpo and "openai.com" in str(p.get("url", "")):
            p["jsonBody"] = cuerpo.replace(
                "'%s'" % MODELO_CHATGPT_ANTERIOR, "'%s'" % MODELO_CHATGPT_SONDEO
            )
            cambios.append("%s: %s -> %s" % (n["name"], MODELO_CHATGPT_ANTERIOR, MODELO_CHATGPT_SONDEO))

        # Gemini: el modelo viaja en la URL, y ademas hay que migrar thinking.
        url = p.get("url", "")
        if MODELO_GEMINI_ANTERIOR in str(url):
            p["url"] = url.replace(MODELO_GEMINI_ANTERIOR, MODELO_GEMINI_SONDEO)
            cuerpo = p.get("jsonBody") or ""
            if THINKING_ANTERIOR in cuerpo:
                p["jsonBody"] = _sustituir(cuerpo, THINKING_ANTERIOR, THINKING_NUEVO, n["name"])
            cambios.append(
                "%s: %s -> %s (+ thinking_level)"
                % (n["name"], MODELO_GEMINI_ANTERIOR, MODELO_GEMINI_SONDEO)
            )
    return cambios


def bajar_temperatura_analisis(nodes, valor=TEMPERATURA_ANALISIS):
    """Baja la temperatura de los agentes de analisis (nodos OpenAI de n8n)."""
    cambios = []
    for n in nodes:
        opciones = n.get("parameters", {}).get("options")
        if isinstance(opciones, dict) and "temperature" in opciones:
            antes = opciones["temperature"]
            if antes != valor:
                opciones["temperature"] = valor
                cambios.append("%s: temperature %s -> %s" % (n["name"], antes, valor))
    return cambios


# ============================================================
# PARCHE: deteccion de encabezados con parser real
# ============================================================
# BUG (medido en una home real, 2026-08-13):
#   El regex /<h([1-3])[^>]*>([\s\S]*?)<\/h\1>/gi escanea TODO el HTML, incluidos
#   <style>, <script> y comentarios. En esa home habia un comentario CSS que
#   mencionaba "<h2>" en prosa; el regex lo tomo por una etiqueta real, y su
#   captura perezosa se trago 4.237 caracteres hasta el siguiente </h2> — con el
#   <h1> de verdad DENTRO. Resultado: el informe decia "no hay H1" habiendolo.
#   Afecta a cualquier web con "<h2>" dentro de un comentario, un script de
#   tracking o un CSS inline, por eso se veia "en todas las auditorias".
#
# ARREGLO: parser de verdad en vez de regex.
#   · Si la instancia de n8n permite modulos externos, usa cheerio.
#   · Si no, cae a un tokenizador propio sin dependencias que salta comentarios
#     y elementos de texto crudo (script/style/textarea/noscript).
#   Asi el arreglo funciona con o sin NODE_FUNCTION_ALLOW_EXTERNAL, en vez de
#   romperse en ejecucion y desperdiciar una auditoria de pago.
#
# NO cambia el analisis: devuelve la misma forma [{nivel, texto}] que antes.
JS_EXTRAER_ENCABEZADOS = r"""// [PARCHE PANEL] Encabezados con parser real, no con regex.
// El regex anterior confundia un "<h2>" escrito dentro de un comentario CSS con
// una etiqueta real y se tragaba el <h1> que venia despues.
let __cheerio = null;
try { __cheerio = require('cheerio'); } catch (e) { __cheerio = null; }
const __CRUDOS = ['script', 'style', 'textarea', 'noscript'];

function extraerEncabezados(html, nivelMax, limite) {
  if (__cheerio) {
    try {
      // OJO: NO llamar a esto '$'. En un nodo Code de n8n el simbolo dolar es
      // una variable reservada (referencias a otros nodos, $json...) y
      // sombrearla romperia esas referencias.
      const __q = __cheerio.load(html);
      __q('script, style, noscript, textarea, template').remove();
      const sel = [];
      for (let k = 1; k <= nivelMax; k++) sel.push('h' + k);
      const out = [];
      __q(sel.join(',')).each(function () {
        if (out.length >= limite) return false;
        out.push({ nivel: this.tagName.toLowerCase(),
                   texto: stripTags(__q(this).html() || '').slice(0, 120) });
      });
      return out;
    } catch (e) { /* cae al tokenizador */ }
  }
  const out = [];
  const bajo = html.toLowerCase();
  const n = html.length;
  let i = 0;
  while (i < n && out.length < limite) {
    const lt = bajo.indexOf('<', i);
    if (lt === -1) break;
    if (bajo.startsWith('<!--', lt)) {                 // comentario
      const fin = bajo.indexOf('-->', lt + 4);
      i = fin === -1 ? n : fin + 3;
      continue;
    }
    let saltado = false;
    for (const tag of __CRUDOS) {                      // texto crudo
      if (bajo.startsWith('<' + tag, lt)) {
        const sig = bajo.charAt(lt + tag.length + 1);
        if (sig === '>' || sig === ' ' || sig === '\n' || sig === '\t' || sig === '\r' || sig === '/') {
          const cierre = bajo.indexOf('</' + tag, lt);
          i = cierre === -1 ? n : cierre + tag.length + 2;
          saltado = true;
          break;
        }
      }
    }
    if (saltado) continue;
    const m = /^<h([1-6])(?=[\s/>])/.exec(bajo.slice(lt, lt + 5));
    if (m) {
      const nivel = parseInt(m[1], 10);
      const finApertura = bajo.indexOf('>', lt);
      if (finApertura === -1) break;
      const cierre = bajo.indexOf('</h' + m[1], finApertura);
      if (cierre !== -1 && nivel <= nivelMax) {
        out.push({ nivel: 'h' + m[1],
                   texto: stripTags(html.slice(finApertura + 1, cierre)).slice(0, 120) });
        i = cierre + 4;
        continue;
      }
    }
    i = lt + 1;
  }
  return out;
}
"""

# El bucle de regex que hay que sustituir, y su reemplazo, por nodo.
BUCLES_ENCABEZADOS = {
    "Consolidar Senales Web": (
        "const headings = [];\n"
        "const reH = /<h([1-3])[^>]*>([\\s\\S]*?)<\\/h\\1>/gi;\n"
        "while ((m = reH.exec(html)) !== null && headings.length < 40) {\n"
        "  headings.push({ nivel: 'h' + m[1], texto: stripTags(m[2]).slice(0, 120) });\n"
        "}",
        "const headings = extraerEncabezados(html, 3, 40);",
    ),
    "Analizar Landings": (
        "  const headings = [];\n"
        "  const reH = /<h([1-6])[^>]*>([\\s\\S]*?)<\\/h\\1>/gi;\n"
        "  let m;\n"
        "  while ((m = reH.exec(html)) !== null && headings.length < 30) {\n"
        "    headings.push({ nivel: 'h' + m[1], texto: stripTags(m[2]).slice(0, 120) });\n"
        "  }",
        "  const headings = extraerEncabezados(html, 6, 30);",
    ),
    # El LITE usa otra forma de salida: nivel NUMERICO y corte a 90.
    "Parsear Home": (
        "const encabezados = [];\n"
        "const reH = /<h([1-6])[^>]*>([\\s\\S]*?)<\\/h\\1>/gi;\n"
        "let m;\n"
        "while ((m = reH.exec(html)) !== null && encabezados.length < 100) {\n"
        "  encabezados.push({ nivel: +m[1], texto: stripTags(m[2]).slice(0, 90) });\n"
        "}",
        "const encabezados = extraerEncabezados(html, 6, 100)\n"
        "  .map(x => ({ nivel: +x.nivel.slice(1), texto: x.texto.slice(0, 90) }));",
    ),
}


def parchear_encabezados(nodes):
    """Sustituye el regex de encabezados por el parser en los nodos que lo usan."""
    cambios = []
    por_nombre = {n["name"]: n for n in nodes}
    for nombre, (antes, despues) in BUCLES_ENCABEZADOS.items():
        # El nombre real puede llevar tilde ('Consolidar Senales Web').
        nodo = por_nombre.get(nombre) or next(
            (n for n in nodes if n["name"].replace("ñ", "n") == nombre), None
        )
        if nodo is None:
            continue
        js = nodo["parameters"].get("jsCode", "")
        if antes not in js:
            raise SystemExit(
                "El parche de encabezados ya no aplica en %r.\n"
                "El bucle de regex ha cambiado: revisalo antes de seguir." % nodo["name"]
            )
        nodo["parameters"]["jsCode"] = JS_EXTRAER_ENCABEZADOS + js.replace(
            antes, despues, 1
        )
        cambios.append(nodo["name"])
    return cambios


# ============================================================
# HELPERS DE NODOS
# ============================================================

def pg(name, sql, params_expr, pos, tolerar_fallo=False):
    """Nodo Postgres parametrizado ($1,$2...). UNA sola sentencia por nodo.

    tolerar_fallo=True solo donde un fallo de escritura NO invalida el resultado
    (p. ej. marcar 'en_curso'). En el guardado del informe y en el cierre de la
    fila NO se tolera: si no se pudo guardar, la ejecucion debe quedarse visible
    como no terminada, nunca marcarse 'completado' sin informe.
    """
    nodo = {
        "parameters": {
            "operation": "executeQuery",
            "query": sql,
            "options": {"queryReplacement": params_expr},
        },
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.6,
        "position": pos,
        "name": name,
        "credentials": {"postgres": {"name": CRED_POSTGRES}},
        # Un UPDATE/INSERT no devuelve filas: sin esto la cadena se corta aqui.
        "alwaysOutputData": True,
    }
    if tolerar_fallo:
        nodo["onError"] = "continueRegularOutput"
    return nodo


def code(name, js, pos):
    """Nodo Code que corre UNA vez aunque le lleguen 0 items."""
    return {
        "parameters": {"mode": "runOnceForAllItems", "jsCode": js},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": pos,
        "name": name,
    }


def responder(name, pos):
    return {
        "parameters": {"respondWith": "firstIncomingItem", "options": {}},
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1,
        "position": pos,
        "name": name,
    }


# ============================================================
# SQL del ciclo de vida
# ============================================================

SQL_EN_CURSO = (
    "update runs set estado = 'en_curso', started_at = now(), updated_at = now() "
    "where id = $1 and estado = 'pendiente'"
)

SQL_GUARDAR_INFORME = (
    "insert into informes (run_id, informe) values ($1, $2::jsonb) "
    "on conflict (run_id) do update set informe = excluded.informe"
)

# error_mensaje = null: si el panel habia marcado la fila en error (p.ej. por un
# timeout del ack) y el analisis SI acabo bien, dejar el mensaje viejo mostraria
# un informe correcto junto a un error falso.
SQL_COMPLETADO = (
    "update runs set estado = 'completado', finished_at = now(), updated_at = now(), "
    "error_mensaje = null, "
    "duracion_ms = (extract(epoch from (now() - coalesce(started_at, created_at))) * 1000)::int, "
    "nota = $2, veredicto = $3, sov = $4, sondeos = $5, tiene_avisos = $6 "
    "where id = $1"
)

# Forma explicita en vez de una funcion flecha: las expresiones de n8n con arrow
# functions son fragiles. $json en 'Marcar Completado' seria la salida de
# 'Guardar Informe' (vacia), por eso se referencia el nodo anterior.
PARAMS_COMPLETADO = (
    "={{ [$('Preparar Guardado').first().json.run_id,"
    " $('Preparar Guardado').first().json.nota,"
    " $('Preparar Guardado').first().json.veredicto,"
    " $('Preparar Guardado').first().json.sov,"
    " $('Preparar Guardado').first().json.sondeos,"
    " $('Preparar Guardado').first().json.tiene_avisos] }}"
)


def anadir_ciclo_de_vida(
    nodes, connect, nodo_final_informe, nombre_webhook="Webhook", y_ack=200, x_fin=3560
):
    """Anade a un workflow las dos cadenas que lo convierten en asincrono.

    · Rama de ACK: Webhook -> Preparar Ack -> Responder Ack -> Marcar En Curso.
      CRITICO: con executionOrder v1 n8n ejecuta ANTES la rama que esta mas
      ARRIBA en el lienzo. Si el ack queda por debajo del analisis, n8n corre el
      analisis entero primero y el ack llega minutos tarde (bug real observado).
      Por eso y_ack debe ser MENOR que la Y del inicio del analisis, y ademas la
      conexion se inserta la primera (lo hace quien llama).
    · Rama de GUARDADO: <nodo_final> -> Preparar Guardado -> Guardar Informe ->
      Marcar Completado.
    """
    nodes.append(code("Preparar Ack", CODE_ACK, [380, y_ack]))
    nodes.append(responder("Responder Ack", [560, y_ack]))
    nodes.append(
        pg(
            "Marcar En Curso",
            SQL_EN_CURSO,
            "={{ [$('Preparar Ack').first().json.run_id] }}",
            [740, y_ack],
            tolerar_fallo=True,  # cosmetico: si falla, el analisis debe seguir
        )
    )

    nodes.append(
        code(
            "Preparar Guardado",
            CODE_PREPARAR_GUARDADO.replace(MARCA_WEBHOOK, nombre_webhook),
            [x_fin, 300],
        )
    )
    nodes.append(
        pg(
            "Guardar Informe",
            SQL_GUARDAR_INFORME,
            "={{ [$json.run_id, $json.informe_json] }}",
            [x_fin + 180, 300],
        )
    )
    nodes.append(
        pg("Marcar Completado", SQL_COMPLETADO, PARAMS_COMPLETADO, [x_fin + 360, 300])
    )

    connect("Preparar Ack", "Responder Ack")
    connect("Responder Ack", "Marcar En Curso")
    for a, b in [
        (nodo_final_informe, "Preparar Guardado"),
        ("Preparar Guardado", "Guardar Informe"),
        ("Guardar Informe", "Marcar Completado"),
    ]:
        connect(a, b)


def rama_ack_primero(conns, nombre_webhook="Webhook"):
    """Inserta la conexion del ack como PRIMERA salida del webhook."""
    conns.setdefault(nombre_webhook, {"main": [[]]})
    conns[nombre_webhook]["main"][0].insert(
        0, {"node": "Preparar Ack", "type": "main", "index": 0}
    )


def quitar_nodos(nodes, conns, nombres):
    """Elimina nodos y todas las conexiones que entran o salen de ellos."""
    fuera = set(nombres)
    nodes[:] = [n for n in nodes if n["name"] not in fuera]
    for nombre in fuera:
        conns.pop(nombre, None)
    for salidas in conns.values():
        for rama in salidas.get("main", []):
            rama[:] = [e for e in rama if e.get("node") not in fuera]


def comprobar_sin_clientes(wf_json):
    plano = json.dumps(wf_json, ensure_ascii=False).lower()
    encontrados = [c for c in CLIENTES_PROHIBIDOS if c in plano]
    if encontrados:
        raise SystemExit(
            "El workflow generado contiene nombres de cliente: %s\n"
            "Usa ejemplos genericos en los comentarios del builder."
            % ", ".join(encontrados)
        )

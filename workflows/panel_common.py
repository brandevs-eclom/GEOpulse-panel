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
    # Guarda de inmutabilidad (seguridad docs/08 §2): solo una fila 'pendiente' o
    # 'en_curso' pasa a 'completado'. Un segundo callback de n8n (reintento, doble
    # ejecucion) no puede pisar un informe ya cerrado ni resucitar uno fallado.
    "where id = $1 and estado in ('pendiente', 'en_curso')"
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

# ============================================================
# REPORTE DE FASE (progreso real para la landing publica)
# ============================================================
# El analisis marca en que fase va (runs.progreso_idx), y la landing publica lo
# sondea para mover la barra con DATOS REALES en vez de un temporizador. Se escribe
# directo a Postgres (nodo local, como el resto del ciclo de vida), no por el
# webhook panel-db.
#
# MONOTONO ('$2 > coalesce(progreso_idx,-1)'): el analisis abre en abanico 4 ramas
# paralelas (motores, ficha, rastreo, enlaces), asi que las fases NO llegan en
# orden estricto. El guard hace que la barra solo avance y nunca retroceda; la
# landing muestra la fase mas avanzada alcanzada. La primera senal ademas pasa la
# fila a 'en_curso' y fija started_at (como 'Marcar En Curso', por si esa fallo).
SQL_PROGRESO = (
    "update runs set progreso_idx = $2, "
    "estado = case when estado = 'pendiente' then 'en_curso' else estado end, "
    "started_at = coalesce(started_at, now()), updated_at = now() "
    "where id = $1 and estado in ('pendiente', 'en_curso') "
    "and $2 > coalesce(progreso_idx, -1)"
)


def anadir_reporte_fases(nodes, connect, fases, nombre_ack="Preparar Ack"):
    """Cuelga de cada tramo del analisis un nodo que reporta su fase a runs.

    `fases` es una lista de (nodo_origen, idx, nombre, pos). Cada entrada crea un
    nodo Postgres colgado como RAMA MUERTA de nodo_origen (no alimenta a nadie), asi
    que no altera el flujo del analisis. El UPDATE es monotono (ver SQL_PROGRESO) y
    tolerar_fallo=True: un fallo al escribir el progreso es cosmetico y JAMAS debe
    abortar una auditoria.

    El run_id se toma de `nombre_ack` (Preparar Ack lo extrae y corre antes que el
    analisis, por rama_ack_primero), asi que esta disponible en todas las ramas.
    """
    for nodo_origen, idx, nombre, pos in fases:
        params = "={{ [$('%s').first().json.run_id, %d] }}" % (nombre_ack, idx)
        nodes.append(pg(nombre, SQL_PROGRESO, params, pos, tolerar_fallo=True))
        connect(nodo_origen, nombre)


# ============================================================
# AUTOCREAR RUN (canal publico: la web llama al webhook SIN run_id)
# ============================================================
# El MISMO webhook lo usan el panel (crea la fila antes y pasa run_id) y la web
# publica (llama directa, sin run_id). Cuando NO viene run_id, n8n crea el la fila
# aqui (origen='publico' + token). Es COMPATIBLE: si viene run_id, se usa tal cual
# (ON CONFLICT solo toca la fila existente). Sin esto, 'Preparar Guardado' lanza
# "Falta run_id" en cuanto la web llama directa (error real observado).
CODE_DATOS_WEB = r"""// Normaliza lo minimo del body para asegurar la fila del run. Corre en la rama del
// ACK (antes que el analisis), asi que NO puede usar 'Normalizar Input': hace su
// propia normalizacion ligera de lo que va a columnas del listado.
const b = $json.body || $json;
const h = $json.headers || {};
const run_id = String(b.run_id || '').trim();
const brand = String(b.brand || '').trim().slice(0, 80);
let d = String(b.domain || '').trim().slice(0, 253);
d = d.replace(/^https?:\/\//i, '').replace(/\/+$/, '').split('/')[0].replace(/^www\./i, '').toLowerCase();
const keyword = String(b.keyword || '').trim().slice(0, 120);
const pais = (String(b.pais || 'ES').trim().toUpperCase().slice(0, 2)) || 'ES';
const region = String(b.region || '').trim().slice(0, 80) || null;
const ip = String(h['x-forwarded-for'] || '').split(',')[0].trim() || null;
return [{ json: { run_id, brand, domain: d, keyword, pais, region, payload: JSON.stringify(b), ip } }];"""

# Si viene run_id (panel) la fila ya existe -> ON CONFLICT solo toca updated_at y
# devuelve su id. Si NO viene (web) -> id nuevo + token + INSERT origen='publico'.
SQL_ASEGURAR_RUN = (
    "insert into runs (id, tipo, brand, domain, keyword, pais, region, payload, estado, origen, token, ip) "
    "values (coalesce(nullif($1, '')::uuid, gen_random_uuid()), "
    "'lite', $2, $3, $4, $5, $6, $7::jsonb, 'pendiente', "
    "case when nullif($1, '') is null then 'publico' else 'panel' end, "
    "case when nullif($1, '') is null "
    "then replace(gen_random_uuid()::text, '-', '') || replace(gen_random_uuid()::text, '-', '') "
    "else null end, $8) "
    "on conflict (id) do update set updated_at = now() "
    "returning id, token"
)

PARAMS_ASEGURAR_RUN = (
    "={{ [$json.run_id, $json.brand, $json.domain, $json.keyword, "
    "$json.pais, $json.region, $json.payload, $json.ip] }}"
)

CODE_ACK_AUTOCREAR = r"""// Acuse inmediato. run_id/token vienen de 'Asegurar Run' (la fila ya existia
// -panel- o se acaba de crear -web-). Con esto ni el panel ni la web se quedan sin
// run_id, asi que 'Preparar Guardado' ya no puede fallar por falta de run_id.
const r = ($('Asegurar Run').first() || {}).json || {};
const run_id = r.id ? String(r.id) : null;
const token = r.token ? String(r.token) : null;
return [{ json: { ok: !!run_id, run_id, token, aceptado: !!run_id } }];"""


# ============================================================
# PLANTILLA PDF DEL INFORME (para Gotenberg)
# ============================================================
# Toma el informe (r) y genera HTML PRINT-FIRST: tipografia + tablas, robusto en
# Gotenberg y pensado para verse BIEN en PDF (sobre todo las preguntas de las IAs,
# que en el render web quedaban mal). NO copia la web: es una plantilla propia y
# controlada. La usan el auto-envio por correo (al terminar) y el boton de descarga
# -> mismo PDF. XSS-safe: escapa todo lo que viene del informe/LLM antes de formatear.
# Entrada: un item con { informe: <objeto>, email: <str> }  (o el informe en $json).
# Salida:  { html: <str>, email: <str> }.
CODE_PLANTILLA_PDF = r"""
let r = ($json && $json.informe !== undefined) ? $json.informe : $json;
if (typeof r === 'string') { try { r = JSON.parse(r); } catch (e) { r = {}; } }
if (!r || typeof r !== 'object') r = {};
const email = ($json && $json.email) || (r.meta && r.meta.email) || '';
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const num = (v) => (typeof v === 'number' && isFinite(v)) ? v : null;

// mini-markdown para las respuestas de las IAs (vienen en md). Escapa PRIMERO.
const md = (raw) => {
  let t = esc(raw == null ? '' : raw);
  t = t.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  t = t.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2">$1</a>');
  t = t.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>').replace(/__([^_\n]+)__/g, '<strong>$1</strong>');
  t = t.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
  const out = []; let lista = null;
  const cerrar = () => { if (lista) { out.push('</' + lista + '>'); lista = null; } };
  for (const ln of t.split('\n')) {
    const s2 = ln.trim();
    if (!s2) { cerrar(); continue; }
    let m;
    if (m = s2.match(/^#{1,6}\s+(.+)$/)) { cerrar(); out.push('<p class="h">' + m[1] + '</p>'); }
    else if (m = s2.match(/^[-*•]\s+(.+)$/)) { if (lista !== 'ul') { cerrar(); out.push('<ul>'); lista = 'ul'; } out.push('<li>' + m[1] + '</li>'); }
    else if (m = s2.match(/^\d+[.)]\s+(.+)$/)) { if (lista !== 'ol') { cerrar(); out.push('<ol>'); lista = 'ol'; } out.push('<li>' + m[1] + '</li>'); }
    else { cerrar(); out.push('<p>' + s2 + '</p>'); }
  }
  cerrar();
  return out.join('') || '<p class="muted">Sin respuesta</p>';
};

const meta = r.meta || {}, ap = r.aparicion || {}, area = r.por_area || {};
const VERED = { fuerte: 'Buena visibilidad en IA', parcial: 'Visibilidad parcial en IA', debil: 'Poca visibilidad en IA', ausente: 'La IA no te menciona' };
const nota = num(r.nota);
const veredicto = VERED[(r.posicionamiento || {}).veredicto] || 'Visibilidad en IA';
const filaKV = (t, v) => '<tr><td class="k">' + esc(t) + '</td><td class="v">' + esc(v == null ? '—' : v) + '</td></tr>';
const pct = (v) => (v == null ? '—' : Math.round(v) + '%');

let s = '';
s += '<div class="head"><div><div class="brand">' + esc(meta.brand || '') + '</div>'
  + '<div class="muted">' + esc(meta.host || meta.domain || '') + (meta.keyword ? ' · ' + esc(meta.keyword) : '')
  + (meta.mercado || meta.region || meta.pais ? ' · ' + esc(meta.mercado || meta.region || meta.pais) : '') + '</div></div>'
  + '<div class="nota"><span class="n">' + (nota == null ? '—' : nota) + '</span><span class="d">/100</span></div></div>';
s += '<div class="vered">' + esc(veredicto) + ' · te citan en ' + (ap.total_hits != null ? ap.total_hits : '—') + ' de ' + (ap.total_validas != null ? ap.total_validas : (meta.sondeos != null ? meta.sondeos : '—')) + ' sondeos</div>';
if (r.resumen_hallazgos) s += '<p class="resumen">' + esc(r.resumen_hallazgos) + '</p>';
const avisos = (r.avisos || []).filter(Boolean);
if (avisos.length) s += '<div class="avisos"><div class="lbl">' + avisos.length + (avisos.length === 1 ? ' aviso' : ' avisos') + '</div><ul>'
  + avisos.map(a => '<li>' + esc(typeof a === 'string' ? a : (a.texto || a.detalle || '')) + '</li>').join('') + '</ul></div>';

s += '<h2>Por área</h2><table class="kv">'
  + filaKV('SEO técnico', num(area.seo_tecnico)) + filaKV('Contenido', num(area.contenido))
  + filaKV('Cuota de voz', num(area.sov)) + filaKV('Huella digital', num(area.huella)) + '</table>';

const pm = ap.por_modelo || [];
if (pm.length) s += '<h2>Visibilidad motor a motor</h2><table class="grid"><thead><tr><th>Motor</th><th>Aparece</th><th>Tasa</th></tr></thead><tbody>'
  + pm.map(m => '<tr><td>' + esc(m.modelo) + '</td><td>' + (m.apariciones != null ? m.apariciones : '—') + ' de ' + (m.preguntas_validas != null ? m.preguntas_validas : '—') + '</td><td>' + pct(m.tasa) + '</td></tr>').join('')
  + '</tbody></table><p class="muted">Tasa global ' + pct(ap.tasa_global) + '.</p>';

const mc = r.mapa_competitivo || [];
if (mc.length) s += '<h2>Competencia (menciones)</h2><table class="grid"><tbody>'
  + mc.map(x => '<tr><td>' + esc(x.empresa) + (x.es_marca ? ' <strong>(tú)</strong>' : '') + '</td><td class="r">' + (x.menciones || 0) + '</td></tr>').join('') + '</tbody></table>';

const pts = (r.seo_tecnico || {}).puntos || [];
if (pts.length) s += '<h2>SEO técnico</h2><table class="grid"><tbody>'
  + pts.map(p => '<tr><td>' + esc(p.titulo) + (p.detalle ? '<br><span class="muted">' + esc(p.detalle) + '</span>' : '') + '</td><td class="r">' + esc(p.valor == null ? 'No verificable' : p.valor) + '</td></tr>').join('') + '</tbody></table>';

const hd = r.huella_digital || {}, ee = hd.eeatc || {};
if (Object.keys(ee).length) {
  s += '<h2>Huella digital (E-E-A-T-C)</h2><table class="kv">'
    + filaKV('Experiencia', num(ee.experiencia)) + filaKV('Especialización', num(ee.expertise))
    + filaKV('Autoridad', num(ee.autoridad)) + filaKV('Confianza', num(ee.confianza))
    + filaKV('Citabilidad', num(ee.citabilidad)) + '</table>';
  if ((hd.enlaces || []).length) s += '<p class="muted">Menciones: ' + hd.enlaces.map(l => esc(l.dominio || l.url)).join(', ') + '</p>';
}

const fg = r.ficha_google || {}, er = r.enlaces_rotos || {};
s += '<h2>Local y enlaces</h2><table class="kv">';
s += filaKV('Ficha de Google', fg.encontrada ? ((fg.rating != null ? fg.rating + '★' : '—') + ' · ' + (fg.resenas || 0) + ' reseñas') : 'No encontrada');
if (fg.categoria) s += filaKV('Categoría', fg.categoria);
if (er.revisados != null) s += filaKV('Enlaces rotos', (er.total_rotos || 0) + ' de ' + er.revisados + ' comprobados' + (er.cap_aplicado ? ' (límite)' : ''));
if (er.no_verificables) s += filaKV('No verificables', er.no_verificables);
if (meta.fecha) s += filaKV('Fecha', meta.fecha);
s += '</table>';

const pr = r.preguntas || [];
if (pr.length) {
  s += '<h2>Preguntas y respuestas</h2>';
  s += pr.map((p, i) => '<div class="q"><div class="qt">' + (i + 1) + '. ' + esc(p.pregunta) + '</div>'
    + (p.respuestas || []).map(rs => '<div class="a"><div class="am">' + esc(rs.modelo) + ' · '
      + (!rs.respondio ? 'sin respuesta' : (rs.aparece ? 'te cita' : 'no te cita')) + '</div>'
      + '<div class="ar">' + md(rs.respuesta || '') + '</div></div>').join('') + '</div>').join('');
}

const CSS = '@page{margin:16mm}*{box-sizing:border-box}'
  + 'body{margin:0;font:400 12px/1.5 Manrope,system-ui,sans-serif;color:#17130f;-webkit-print-color-adjust:exact;print-color-adjust:exact}'
  + 'h2{font:600 14px "Space Grotesk",Manrope,sans-serif;margin:20px 0 8px;padding-bottom:4px;border-bottom:2px solid #E74C57}'
  + '.head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;border-bottom:2px solid #17130f;padding-bottom:10px}'
  + '.brand{font:700 20px "Space Grotesk",sans-serif}'
  + '.nota .n{font:700 34px "Space Grotesk",sans-serif;color:#E74C57}.nota .d{font-size:12px;color:#8a8178}'
  + '.vered{margin-top:6px;font-weight:600}.muted{color:#8a8178}'
  + '.resumen{background:#f6f4f1;border-left:3px solid #E74C57;padding:10px 12px;margin:12px 0;border-radius:0 8px 8px 0}'
  + '.avisos{background:#fdf6e6;border:1px solid #e6cf90;border-radius:8px;padding:8px 12px;margin:12px 0}'
  + '.avisos .lbl{font-weight:700;color:#8c6510;font-size:10px;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px}'
  + '.avisos ul,.ar ul,.ar ol{margin:4px 0;padding-left:18px}'
  + 'table{width:100%;border-collapse:collapse;margin:4px 0}'
  + 'table.kv td{padding:6px 8px;border-bottom:1px solid #eee}.kv .k{color:#5b544c}.kv .v{text-align:right;font-weight:600;white-space:nowrap}'
  + 'table.grid th{background:#f6f4f1;text-align:left;padding:6px 8px;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:#5b544c}'
  + 'table.grid td{padding:6px 8px;border-bottom:1px solid #eee;vertical-align:top}.grid .r{text-align:right;white-space:nowrap;font-weight:600}'
  + '.q{border:1px solid #e7e2db;border-radius:8px;padding:10px 12px;margin:8px 0;break-inside:avoid;page-break-inside:avoid}'
  + '.qt{font-weight:700;margin-bottom:6px}.a{border-top:1px solid #eee;padding:6px 0}.a:first-of-type{border-top:0}'
  + '.am{font:700 10px Manrope;text-transform:uppercase;letter-spacing:.05em;color:#5b544c;margin-bottom:3px}'
  + '.ar p{margin:3px 0}.ar .h{font-weight:700;margin:6px 0 2px}.ar code{background:#f0ece7;border-radius:4px;padding:1px 4px;font-family:monospace}a{color:#E74C57}'
  // --- Marca BranDevs: cabecera, marca de agua y pie ---
  + '.wm{position:fixed;top:46%;left:50%;transform:translate(-50%,-50%) rotate(-27deg);font:800 96px "Space Grotesk",sans-serif;letter-spacing:-3px;color:#17130f;opacity:.045;z-index:0}'
  + '.wm span{color:#E74C57}.doc{position:relative;z-index:1}'
  + '.logo{font:800 16px "Space Grotesk",sans-serif;letter-spacing:-.5px}.logo i{color:#E74C57;font-style:normal}'
  + '.agc{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #eee;padding-bottom:8px;margin-bottom:12px}'
  + '.agc-t{font-size:10px;color:#8a8178;text-transform:uppercase;letter-spacing:.1em}'
  + '.ft{margin-top:26px;border-top:2px solid #17130f;padding-top:10px;display:flex;justify-content:space-between;align-items:flex-end;gap:16px;break-inside:avoid}'
  + '.ft .logo{font-size:18px}.ft-d{font-size:10px;color:#5b544c;text-align:right;line-height:1.7}';

// Marca de agua (fixed -> se repite en cada pagina en Chromium/Gotenberg), cabecera
// de agencia y pie con contacto+direccion. Datos de brandevs.com (JSON-LD).
const marca = 'brandevs<i>.</i>';
const wm = '<div class="wm">brandevs<span>.</span></div>';
const agc = '<div class="agc"><span class="logo">' + marca + '</span><span class="agc-t">Informe GeoPulse · Auditoría GEO</span></div>';
const ft = '<div class="ft"><div class="logo">' + marca + '</div>'
  + '<div class="ft-d">Travesía de la Fragua 2, nº 7 · 28470 Cercedilla, Madrid · España<br>'
  + '+34 918 523 960 · info@brandevs.com · brandevs.com</div></div>';

const html = '<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Informe GeoPulse · brandevs</title>'
  + '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
  + '<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">'
  + '<style>' + CSS + '</style></head><body>' + wm + '<div class="doc">' + agc + s + ft + '</div></body></html>';

return [{ json: { html, email } }];
"""


# ============================================================
# GOTENBERG + EMAIL (compartido: descarga en build_pdf, correo en el LITE)
# ============================================================
# GOTENBERG_URL: donde corre Gotenberg, alcanzable desde n8n. UNA sola fuente de
# verdad para la descarga y el correo automatico. SIN barra final (se concatena
# '/forms/...'). Instancia real del usuario (2026-09).
GOTENBERG_URL = "http://85.31.237.167:3000"
# EDITA: credencial SMTP de n8n. Si envias por Gmail/otro, cambia el nodo de email.
CRED_SMTP = "SMTP GEOpulse"
REMITENTE = "GEOpulse <info@brandevs.com>"

CODE_PREP_HTML_PDF = r"""// HTML de la plantilla -> fichero binario 'index.html' para Gotenberg (su ruta
// /forms/chromium/convert/html exige el fichero principal con ese nombre).
const html = String($json.html || '');
return [{ json: { email: $json.email || '' },
  binary: { index_html: { data: Buffer.from(html, 'utf8').toString('base64'),
    mimeType: 'text/html', fileName: 'index.html' } } }];"""


def nodo_gotenberg(name, pos, on_error="continueErrorOutput"):
    """Nodo HTTP que convierte el binario 'index_html' en PDF (salida binaria 'data')."""
    nodo = {
        "parameters": {
            "method": "POST",
            "url": GOTENBERG_URL + "/forms/chromium/convert/html",
            "sendBody": True,
            "contentType": "multipart-form-data",
            "bodyParameters": {
                "parameters": [
                    {"parameterType": "formBinaryData", "name": "files", "inputDataFieldName": "index_html"}
                ]
            },
            "options": {
                "timeout": 60000,
                "response": {"response": {"responseFormat": "file", "outputPropertyName": "data"}},
            },
        },
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": pos,
        "name": name,
    }
    if on_error:
        nodo["onError"] = on_error
    return nodo


def nodo_email(name, pos, to_expr, cred=CRED_SMTP):
    """Nodo emailSend (SMTP) que adjunta el binario 'data' (el PDF)."""
    return {
        "parameters": {
            "fromEmail": REMITENTE,
            "toEmail": to_expr,
            "subject": "Tu informe GEOpulse en PDF",
            "emailFormat": "html",
            "html": "<p>Hola,</p><p>Adjuntamos tu informe GEOpulse en PDF. Gracias por probar la herramienta.</p><p>— BranDevs</p>",
            "options": {"attachments": "data"},
        },
        "type": "n8n-nodes-base.emailSend",
        "typeVersion": 2.1,
        "position": pos,
        "name": name,
        "credentials": {"smtp": {"name": cred}},
    }


def anadir_correo_pdf(nodes, connect, nodo_disparador, nodo_informe, nombre_webhook="Webhook", x=3900, y=520):
    """Rama de correo automatico: al terminar (nodo_disparador), maqueta el informe
    con la plantilla, lo pasa por Gotenberg y lo envia por email. Solo si el run trae
    email valido (los lanzamientos internos del panel sin email no envian).

    nodo_informe = nodo cuyo $json es el informe (p. ej. 'Ensamblar LITE2').
    """
    datos = code(
        "Datos Correo",
        "// Si no hay email valido (p.ej. lanzamiento interno del panel), NO se envia.\n"
        "const informe = $('" + nodo_informe + "').first().json;\n"
        "const email = String((($('" + nombre_webhook + "').first().json || {}).body || {}).email || '').trim();\n"
        "if (!email || !/^[^\\s@]+@[^\\s@]+\\.[^\\s@]{2,}$/.test(email)) return [];\n"
        "return [{ json: { informe, email } }];",
        [x, y],
    )
    nodes.append(datos)
    nodes.append(code("Plantilla PDF Correo", CODE_PLANTILLA_PDF, [x + 180, y]))
    nodes.append(code("Preparar HTML Correo", CODE_PREP_HTML_PDF, [x + 360, y]))
    # on_error=None: si Gotenberg falla, la ejecucion queda como error VISIBLE (el
    # run ya esta guardado antes de esta rama, asi que no se pierde el analisis).
    nodes.append(nodo_gotenberg("Gotenberg Correo", [x + 540, y], on_error=None))
    nodes.append(nodo_email("Enviar Correo", [x + 720, y], "={{ $('Datos Correo').first().json.email }}"))
    for a, b in [
        (nodo_disparador, "Datos Correo"),
        ("Datos Correo", "Plantilla PDF Correo"),
        ("Plantilla PDF Correo", "Preparar HTML Correo"),
        ("Preparar HTML Correo", "Gotenberg Correo"),
        ("Gotenberg Correo", "Enviar Correo"),
    ]:
        connect(a, b)


def responder_headers(name, pos, headers):
    """Responder (firstIncomingItem) con cabeceras extra (p. ej. X-Robots-Tag)."""
    return {
        "parameters": {
            "respondWith": "firstIncomingItem",
            "options": {"responseHeaders": {"entries": headers}},
        },
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1,
        "position": pos,
        "name": name,
    }


def anadir_ciclo_de_vida(
    nodes,
    connect,
    nodo_final_informe,
    nombre_webhook="Webhook",
    y_ack=200,
    x_fin=3560,
    autocrear=False,
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

    autocrear=True (canal publico/web): antes del ack se insertan 'Datos Web' ->
    'Asegurar Run', que crea la fila si no viene run_id; el resto del ciclo usa ese
    id (via 'Preparar Ack'). El acuse ademas lleva X-Robots-Tag: noindex, nofollow.
    """
    if autocrear:
        nodes.append(code("Datos Web", CODE_DATOS_WEB, [300, y_ack]))
        nodes.append(pg("Asegurar Run", SQL_ASEGURAR_RUN, PARAMS_ASEGURAR_RUN, [460, y_ack]))
        nodes.append(code("Preparar Ack", CODE_ACK_AUTOCREAR, [620, y_ack]))
        nodes.append(
            responder_headers(
                "Responder Ack",
                [780, y_ack],
                [{"name": "X-Robots-Tag", "value": "noindex, nofollow"}],
            )
        )
        connect("Datos Web", "Asegurar Run")
        connect("Asegurar Run", "Preparar Ack")
        prep_guardado_js = (
            CODE_PREPARAR_GUARDADO.replace(MARCA_WEBHOOK, nombre_webhook).replace(
                "$('%s').first().json.body.run_id" % nombre_webhook,
                "$('Preparar Ack').first().json.run_id",
            )
        )
        x_marcar = 960
    else:
        nodes.append(code("Preparar Ack", CODE_ACK, [380, y_ack]))
        nodes.append(responder("Responder Ack", [560, y_ack]))
        prep_guardado_js = CODE_PREPARAR_GUARDADO.replace(MARCA_WEBHOOK, nombre_webhook)
        x_marcar = 740

    nodes.append(
        pg(
            "Marcar En Curso",
            SQL_EN_CURSO,
            "={{ [$('Preparar Ack').first().json.run_id] }}",
            [x_marcar, y_ack],
            tolerar_fallo=True,  # cosmetico: si falla, el analisis debe seguir
        )
    )

    nodes.append(code("Preparar Guardado", prep_guardado_js, [x_fin, 300]))
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


def rama_ack_primero(conns, nombre_webhook="Webhook", primero="Preparar Ack"):
    """Inserta la conexion del ack como PRIMERA salida del webhook."""
    conns.setdefault(nombre_webhook, {"main": [[]]})
    conns[nombre_webhook]["main"][0].insert(
        0, {"node": primero, "type": "main", "index": 0}
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

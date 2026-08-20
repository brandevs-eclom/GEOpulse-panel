#!/usr/bin/env python3
# GEOpulse LITE v2 (v3) — muestra publica con la estructura del informe completo.
#
# Esta version REUTILIZA el codigo probado en produccion del informe avanzado:
#   · asText()  y stripTags()          <- Consolidar Senales Web
#   · pick()    y pickCitations()      <- D1 - Unir
#   · Arquitectura de ITEMS: Sondas emite N items y cada nodo de modelo se ejecuta N veces,
#     y luego se leen con .all()[idx] indexado por pregunta   <- Sondas D1 + D1 - Unir
#   · Opciones HTTP identicas: fullResponse + responseFormat text + outputPropertyName body
#   · User-Agent de navegador en los GET (sin el, muchos WAF devuelven 403 y todo sale vacio)
#
# Coste: 3 sondas x 3 modelos (9 llamadas) + 1 sonda de huella + 1 informe = 11 llamadas.
import json

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# ============================================================
# HELPERS JS REUTILIZADOS DEL INFORME AVANZADO (verbatim)
# ============================================================
JS_ASTEXT = r"""// [reutilizado de 'Consolidar Senales Web' del informe avanzado]
const asText = (r) => { const b = r.body ?? r.data; return typeof b === 'string' ? b : JSON.stringify(b || ''); };
const stripTags = (h) => String(h)
  .replace(/<script[\s\S]*?<\/script>/gi, ' ').replace(/<style[\s\S]*?<\/style>/gi, ' ')
  .replace(/<noscript[\s\S]*?<\/noscript>/gi, ' ').replace(/<[^>]+>/g, ' ')
  .replace(/&nbsp;|&amp;|&quot;|&#\d+;|&[a-z]+;/gi, ' ').replace(/\s+/g, ' ').trim();"""

JS_PICK = r"""// [reutilizado de 'D1 - Unir' del informe avanzado]
// Responses API de OpenAI (web_search): el texto va en output[].content[].output_text
// (o en el atajo output_text). Sin esto, el ?? body.output stringificaria el array.
const respApi = (b) => {
  if (typeof b.output_text === 'string' && b.output_text) return b.output_text;
  if (Array.isArray(b.output)) {
    let t = '';
    for (const o of b.output) if (Array.isArray(o.content)) for (const c of o.content) if (c.type === 'output_text' && c.text) t += c.text;
    return t;
  }
  return '';
};
const pick = (arr, idx) => {
  const j = arr[idx] || {};
  const rawB = j.body ?? j.data;
  const body = rawB && typeof rawB === 'object' ? rawB : j;
  return String(
    body.choices?.[0]?.message?.content                                                                // chat/completions
    ?? (Array.isArray(body.content) ? (body.content.filter(c => typeof c.text === 'string' && c.text).map(c => c.text).join('\n') || null) : null)  // anthropic (solo bloques text; ignora server_tool_use / web_search_tool_result)
    ?? (Array.isArray(body.candidates?.[0]?.content?.parts) ? body.candidates[0].content.parts.map(p => p.text || '').join('') : null)  // gemini
    ?? (respApi(body) || null)                                                                          // openai responses (web_search)
    ?? body.message?.content ?? body.text ?? ''
  );
};
const pickCitations = (arr, idx) => {
  const j = arr[idx] || {};
  const rawB = j.body ?? j.data;
  const body = rawB && typeof rawB === 'object' ? rawB : j;
  if (Array.isArray(body.citations)) return body.citations;
  if (Array.isArray(body.search_results)) return body.search_results.map(s => s.url).filter(Boolean);
  return [];
};"""

# ============================================================
# CODE NODES
# ============================================================

CODE_NORMALIZAR = r"""// Normaliza y valida el input del webhook. Incluye user_location para Perplexity.
const b = $json.body || $json;
for (const f of ['brand', 'domain', 'keyword']) {
  if (!b[f] || !String(b[f]).trim()) throw new Error('Falta el campo obligatorio: ' + f);
}
let d = String(b.domain).trim();
if (!/^https?:\/\//i.test(d)) d = 'https://' + d;
d = d.replace(/\/+$/, '');
const m = d.match(/^(https?:\/\/[^\/]+)/i);
if (!m) throw new Error('Dominio no válido: ' + b.domain);
const origin = m[1].toLowerCase();
const host = origin.replace(/^https?:\/\//, '').replace(/^www\./, '');
const PAISES = { ES:'España', MX:'México', AR:'Argentina', CO:'Colombia', CL:'Chile', PE:'Perú',
  US:'Estados Unidos', GB:'Reino Unido', FR:'Francia', DE:'Alemania', IT:'Italia', PT:'Portugal' };
const cc = String(b.pais || b.country || 'ES').trim().toUpperCase();
const paisNom = PAISES[cc] || cc || 'España';
const region = String(b.region || '').trim();
const mercado = region ? region + ', ' + paisNom : paisNom;
return [{ json: {
  brand: String(b.brand).trim(), domain: origin, host, home_url: d,
  keyword: String(b.keyword).trim(), pais: paisNom, mercado,
  geo: { user_location: region ? { country: cc, region } : { country: cc } }
} }];"""

CODE_PARSEAR_HOME = r"""// Parsea la home. Nodo dedicado: en n8n puedes abrirlo y ver exactamente que se ha extraido.
// Lee la respuesta con el mismo asText() de 'Consolidar Senales Web' del informe avanzado.
const j = $input.first().json;

__ASTEXT__

const html = asText(j).slice(0, 400000);
const statusCode = j.statusCode ?? null;

// Bloqueo duro del servidor (el challenge se evalua mas abajo, con el contenido ya extraido)
const bloqueadoWaf = statusCode !== null && (statusCode === 403 || statusCode === 429 || statusCode >= 500);

const texto = stripTags(html);
const palabras = texto ? texto.split(' ').filter(Boolean).length : 0;

// Encabezados h1-h6 en orden de aparicion
const encabezados = [];
const reH = /<h([1-6])[^>]*>([\s\S]*?)<\/h\1>/gi;
let m;
while ((m = reH.exec(html)) !== null && encabezados.length < 100) {
  encabezados.push({ nivel: +m[1], texto: stripTags(m[2]).slice(0, 90) });
}

// Bloques JSON-LD (con @graph y arrays aplanados)
const jsonld = [];
let jsonld_malformados = 0;
const reLd = /<script[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
while ((m = reLd.exec(html)) !== null) {
  try {
    const p = JSON.parse(m[1].trim());
    if (p['@graph']) jsonld.push(...p['@graph']);
    else if (Array.isArray(p)) jsonld.push(...p);
    else jsonld.push(p);
  } catch(e){ jsonld_malformados++; }
}
const tipos_schema = [...new Set(jsonld.flatMap(b => {
  const t = b && b['@type'];
  return typeof t === 'string' ? [t] : (Array.isArray(t) ? t : []);
}))];

// Renderizado en cliente: si el contenido se pinta con JS, los modelos no lo ven
const spa = [];
if (/__NEXT_DATA__/.test(html)) spa.push('Next.js');
if (/window\.__NUXT__/.test(html)) spa.push('Nuxt');
if (/ng-version=/.test(html)) spa.push('Angular');
if (/<div[^>]+id=["'](root|app)["'][^>]*>\s*<\/div>/i.test(html)) spa.push('contenedor vacío');
const csr = (palabras < 150 && html.length > 50000) || spa.includes('contenedor vacío');

const cap = (re) => { const x = html.match(re); return x ? stripTags(x[1]).slice(0, 300) : ''; };
const title = cap(/<title[^>]*>([\s\S]*?)<\/title>/i);

// Pagina de desafio anti-bots. Se decide con lo YA EXTRAIDO, no buscando palabras en el
// HTML crudo: un reCAPTCHA en el formulario contiene "captcha" y NO es un challenge.
// Challenge = titulo tipico de muro de verificacion, o frases de challenge en el TEXTO
// visible de una pagina sin contenido real.
const titleChallenge = /^(just a moment|attention required|access denied|verifying you are human|please verify|un momento)/i.test(title);
const textoChallenge = /(checking your browser|verify(ing)? (that )?you are (a )?human|enable javascript and cookies to continue|cf-browser-verification|has been blocked|ddos protection)/i.test(texto);
const challenge = titleChallenge || (textoChallenge && palabras < 80 && encabezados.length <= 1);
// Red de seguridad: si hemos extraido contenido real, la pagina ES legible digan lo que
// digan los heuristicos. Excepcion: un titulo de muro inequivoco no se rescata.
const contenidoReal = encabezados.length > 0 && palabras >= 30;
const legible = !bloqueadoWaf && !titleChallenge && (contenidoReal || (!challenge && html.length > 200));

return [{ json: {
  statusCode, legible, bloqueado_waf: bloqueadoWaf, challenge,
  html_bytes: html.length, palabras, csr, spa,
  title,
  meta_description: cap(/<meta[^>]+name=["']description["'][^>]*content=["']([^"']*)["']/i),
  noindex: /<meta[^>]+name=["']robots["'][^>]*content=["'][^"']*noindex/i.test(html),
  encabezados, total_encabezados: encabezados.length,
  h1: encabezados.filter(x => x.nivel === 1).map(x => x.texto),
  jsonld_bloques: jsonld.length, jsonld_malformados, tipos_schema,
  texto: texto.slice(0, 5000)
} }];""".replace("__ASTEXT__", JS_ASTEXT)

CODE_PARSEAR_ROBOTS = r"""// Parsea robots.txt de verdad: agrupa los User-agent consecutivos con sus reglas y respeta
// la precedencia del grupo especifico sobre el comodin '*'. Nodo dedicado y depurable.
const j = $input.first().json;

__ASTEXT__

const txt = asText(j).slice(0, 20000);
const statusCode = j.statusCode ?? null;
const existe = statusCode === 200 && /user-agent/i.test(txt);

function parseRobots(t){
  const grupos = []; let actual = null, esperandoUA = true;
  for (const raw of String(t).split(/\r?\n/)) {
    const line = raw.replace(/#.*$/, '').trim();
    if (!line) continue;
    const m = line.match(/^([a-zA-Z-]+)\s*:\s*(.*)$/);
    if (!m) continue;
    const campo = m[1].toLowerCase(), valor = m[2].trim();
    if (campo === 'user-agent') {
      if (!esperandoUA) actual = null;
      if (!actual) { actual = { agentes: [], reglas: [] }; grupos.push(actual); }
      actual.agentes.push(valor.toLowerCase());
      esperandoUA = true;
    } else if (campo === 'disallow' || campo === 'allow') {
      if (!actual) continue;
      actual.reglas.push({ tipo: campo, ruta: valor });
      esperandoUA = false;
    }
  }
  return grupos;
}
function estaBloqueado(grupos, bot){
  const b = bot.toLowerCase();
  const g = grupos.find(x => x.agentes.includes(b)) || grupos.find(x => x.agentes.includes('*'));
  if (!g) return false;
  const cierra = g.reglas.some(r => r.tipo === 'disallow' && r.ruta === '/');
  const abre = g.reglas.some(r => r.tipo === 'allow' && r.ruta === '/');
  return cierra && !abre;
}
// Misma clasificacion que el informe avanzado: retrieval y user_fetch afectan a la citacion;
// bloquear solo los de training NO impide que la IA te cite.
const CATS = {
  retrieval:  ['OAI-SearchBot','Claude-SearchBot','PerplexityBot','DuckAssistBot','YouBot'],
  user_fetch: ['ChatGPT-User','Claude-User','Perplexity-User','MistralAI-User'],
  training:   ['GPTBot','ClaudeBot','CCBot','Bytespider','Google-Extended','Applebot-Extended','Amazonbot']
};
const grupos = existe ? parseRobots(txt) : [];
const bloqueados = { retrieval: [], user_fetch: [], training: [] };
if (existe) {
  for (const cat of Object.keys(CATS)) {
    for (const bot of CATS[cat]) if (estaBloqueado(grupos, bot)) bloqueados[cat].push(bot);
  }
}
return [{ json: { statusCode, existe, grupos: grupos.length, bloqueados,
  criticos: bloqueados.retrieval.length + bloqueados.user_fetch.length,
  contenido: txt.slice(0, 3000) } }];""".replace("__ASTEXT__", JS_ASTEXT)

CODE_PARSEAR_SITEMAP = r"""// Parsea el sitemap. Nodo dedicado.
const j = $input.first().json;

__ASTEXT__

const txt = asText(j).slice(0, 60000);
const statusCode = j.statusCode ?? null;
const esIndex = /<sitemapindex/i.test(txt);
const esUrlset = /<urlset/i.test(txt);
const urls = (txt.match(/<loc>/gi) || []).length;
return [{ json: { statusCode, existe: statusCode === 200 && (esIndex || esUrlset),
  tipo: esIndex ? 'sitemapindex' : esUrlset ? 'urlset' : null, urls } }];""".replace("__ASTEXT__", JS_ASTEXT)

CODE_PARSEAR_SCHEMA = r"""// Parsea la respuesta del validador OFICIAL de schema.org (mismo enfoque defensivo que
// 'Parsear Validacion Schema' del informe avanzado: el endpoint no esta documentado).
// Si el validador no responde, se cae con elegancia al JSON-LD extraido de la home.
const j = $input.first().json;
let out = { disponible: false, motivo: 'sin respuesta del validador', num_errores: null, num_warnings: null };
try {
  const rawV = j.body ?? j.data;
  let body = typeof rawV === 'string' ? rawV : JSON.stringify(rawV || '');
  if ((j.statusCode ?? 0) === 200 && body) {
    body = body.replace(/^\)\]\}'?\s*/, '').trim();   // el validador antepone un prefijo anti-JSONP
    const data = JSON.parse(body);
    const errores = [], warnings = [];
    const push = (e, propiedad) => {
      const item = { propiedad: propiedad || null, tipo: e.errorType || e.type || 'error',
        detalle: [propiedad, e.errorType || e.type, ...(Array.isArray(e.args) ? e.args : [])].filter(Boolean).join(' ') };
      (e.warning || e.isWarning ? warnings : errores).push(item);
    };
    for (const gTri of data.tripleGroups || []) {
      for (const n of gTri.nodes || []) {
        for (const e of n.errors || []) push(e, null);
        for (const p of n.properties || []) { for (const e of p.errors || []) push(e, p.pred || null); }
      }
    }
    out = { disponible: true,
      num_errores: typeof data.totalNumErrors === 'number' ? data.totalNumErrors : errores.length,
      num_warnings: typeof data.totalNumWarnings === 'number' ? data.totalNumWarnings : warnings.length,
      errores: errores.slice(0, 10), warnings: warnings.slice(0, 10) };
  } else { out.motivo = 'status ' + (j.statusCode ?? 'desconocido'); }
} catch (e) { out = { disponible: false, motivo: 'respuesta no parseable', num_errores: null, num_warnings: null }; }
return [{ json: out }];"""

CODE_CONSOLIDAR = r"""// Consolida lo que han extraido los nodos de parseo y construye los puntos del informe.
// Aqui ya no se parsea nada: solo se juzga. Si algo falta, se dice, no se inventa.
const norm = $('Normalizar Input').first().json;
const H = $('Parsear Home').first().json;
const R = $('Parsear Robots').first().json;
const S = $('Parsear Sitemap').first().json;
const V = $('Parsear Schema').first().json;

/* ---------- 1. ACCESO DE LOS BOTS DE IA (robots.txt + firewall) ---------- */
// Dos capas: lo que robots.txt DECLARA y lo que el servidor HACE. Si el WAF nos ha
// bloqueado o nos ha servido un muro de verificacion, los rastreadores de IA se
// encuentran exactamente lo mismo, diga lo que diga robots.txt.
const wafBloquea = !!H.bloqueado_waf || !!H.challenge;
let estBots, detBots, valBots;
if (!R.existe) {
  estBots = 'warning';
  detBots = R.statusCode === 404
    ? 'No hay robots.txt (404). Por defecto los bots pueden acceder, pero no existe control explícito.'
    : 'No se ha podido leer un robots.txt válido' + (R.statusCode ? ' (respuesta ' + R.statusCode + ')' : '') + '.';
} else if (R.criticos > 0) {
  estBots = 'error';
  const ps = [];
  if (R.bloqueados.retrieval.length) ps.push('Retrieval: ' + R.bloqueados.retrieval.join(', '));
  if (R.bloqueados.user_fetch.length) ps.push('User-fetch: ' + R.bloqueados.user_fetch.join(', '));
  detBots = 'Tu robots.txt bloquea bots que la IA necesita para citarte. ' + ps.join(' · ') + '.';
} else if (R.bloqueados.training.length) {
  estBots = 'ok';
  detBots = 'Bloqueas bots de entrenamiento (' + R.bloqueados.training.join(', ') + '), pero los de retrieval y user-fetch tienen acceso, que es lo que permite que la IA te cite.';
} else {
  estBots = 'ok';
  detBots = 'Ningún bot de IA está bloqueado en robots.txt.';
}
valBots = R.existe ? (R.criticos ? R.criticos + ' críticos bloqueados' : 'sin bloqueos críticos') : 'sin robots.txt';
// Segunda capa: el bloqueo EFECTIVO del firewall pisa a la declaracion de robots.txt
if (wafBloquea) {
  estBots = 'error';
  valBots = 'bloqueo del firewall';
  const motivoWaf = H.bloqueado_waf
    ? 'tu servidor ha respondido ' + H.statusCode + ' a una petición normal'
    : 'tu web sirve una página de verificación anti-bots en lugar del contenido';
  detBots = 'Más allá de robots.txt, ' + motivoWaf + ': los rastreadores de IA chocan con ese mismo muro y no pueden leerte ni citarte. ' + detBots;
} else if (estBots === 'ok') {
  detBots += ' El servidor entrega el contenido sin muros de verificación: los motores generativos pueden leerte y citarte.';
}
const punto_bots = { clave: 'rastreo_bots_ia', titulo: 'Acceso de los bots de IA', estado: estBots,
  valor: valBots, detalle: detBots, bloqueados_por_categoria: R.bloqueados,
  waf: { bloquea: wafBloquea, status: H.statusCode, challenge: !!H.challenge } };

/* ---------- 2. JERARQUIA DE ENCABEZADOS ---------- */
// La red de seguridad "los datos mandan" vive en Parsear Home: si se extrajo contenido
// real, legible ya es true. Aqui: legible + encabezados = evaluar. Un h1 suelto dentro
// de un muro de verificacion NO es jerarquia de la web.
let estJer = 'ok', detJer, valJer = null;
const h1 = H.h1 || [];
if (H.legible && H.total_encabezados) {
  valJer = h1.length + ' H1 · ' + H.total_encabezados + ' encabezados';
  let salto = false, prev = 1;
  for (const x of H.encabezados) { if (x.nivel > prev + 1) { salto = true; break; } prev = x.nivel; }
  const vacios = H.encabezados.filter(x => !x.texto).length;
  if (h1.length === 0) { estJer = 'error'; detJer = 'La home no tiene ningún H1: la IA no identifica el tema principal de la página.'; }
  else if (h1.length > 1) { estJer = 'warning'; detJer = 'Hay ' + h1.length + ' H1 (' + h1.slice(0,3).map(x => '“' + x + '”').join(', ') + '). Lo correcto es uno solo: varios diluyen el tema principal.'; }
  else if (salto) { estJer = 'warning'; detJer = 'Un único H1 (“' + h1[0] + '”), pero hay saltos de nivel entre encabezados que rompen la jerarquía semántica.'; }
  else { detJer = 'Estructura limpia: un único H1 (“' + h1[0] + '”) y jerarquía sin saltos.'; }
  if (vacios > 0 && estJer === 'ok') { estJer = 'warning'; detJer += ' Hay ' + vacios + ' encabezados vacíos que ensucian la estructura.'; }
} else if (!H.legible) {
  estJer = 'no_verificable';
  detJer = H.bloqueado_waf
    ? 'Tu servidor ha respondido ' + H.statusCode + ' a nuestra petición, así que no hemos podido leer el HTML. Suele ser un firewall o protección anti-bots: si bloquea a los rastreadores de IA igual que a nosotros, también les impide leerte.'
    : H.challenge
      ? 'Tu web ha devuelto una página de verificación anti-bots en lugar del contenido real. Los modelos de IA se encuentran exactamente lo mismo que nosotros.'
      : 'No hemos podido recuperar HTML suficiente de la home para analizar los encabezados.';
} else {
  estJer = H.csr ? 'error' : 'no_verificable';
  detJer = H.csr
    ? 'No hay encabezados en el HTML inicial' + (H.spa.length ? ' (' + H.spa.join(', ') + ')' : '') + ': el contenido se pinta con JavaScript. Los modelos que no ejecutan JS ven una página casi vacía.'
    : 'No se han encontrado encabezados en el HTML de la home.';
}
const punto_jerarquia = { clave: 'jerarquia_contenido', titulo: 'Jerarquía de encabezados', estado: estJer, valor: valJer, detalle: detJer };

/* ---------- 3. SCHEMA.ORG (JSON-LD propio + validador oficial) ---------- */
const tipos = H.tipos_schema || [];
const ENTIDAD = /Organization|LocalBusiness|Corporation|ProfessionalService|Store|Restaurant|EventVenue|NGO/i;
const tieneEntidad = tipos.some(t => ENTIDAD.test(t));
const ausentes = [];
if (!tieneEntidad) ausentes.push('Organization/LocalBusiness');
if (!tipos.some(t => /WebSite/i.test(t))) ausentes.push('WebSite');
let estSch, detSch;
if (H.legible && tipos.length) {
  // Hay tipos extraidos de una pagina legible: se juzgan.
  if (V.disponible && V.num_errores > 0) {
    estSch = 'error';
    detSch = 'El validador oficial de schema.org encuentra ' + V.num_errores + ' error(es) en tu marcado'
      + (V.errores && V.errores.length ? ': ' + V.errores.slice(0,3).map(e => e.detalle).join(' · ') : '') + '.';
  } else if (!tieneEntidad) {
    estSch = 'warning';
    detSch = 'Hay schema (' + tipos.slice(0,5).join(', ') + ') pero falta el tipo de entidad (Organization o LocalBusiness), que es el que identifica tu negocio ante la IA.';
  } else if (V.disponible && V.num_warnings > 0) {
    estSch = 'warning';
    detSch = 'Marcado con capa de entidad (' + tipos.slice(0,5).join(', ') + ') y sin errores, pero el validador oficial señala ' + V.num_warnings + ' aviso(s).';
  } else {
    estSch = 'ok';
    detSch = 'Schema con capa de entidad presente: ' + tipos.slice(0,6).join(', ') + '.'
      + (V.disponible ? ' Validado sin errores contra schema.org.' : '');
  }
} else if (!H.legible) {
  estSch = 'no_verificable';
  detSch = 'No hemos podido leer el HTML de la home, así que no se puede comprobar el marcado de datos estructurados.';
} else {
  estSch = 'error';
  detSch = H.jsonld_malformados
    ? 'Hay ' + H.jsonld_malformados + ' bloque(s) JSON-LD pero ninguno es parseable: el marcado está malformado y la IA no puede usarlo.'
    : 'No se detecta ningún dato estructurado (JSON-LD) en la home. La IA no tiene una capa de datos que le diga qué eres.';
}
const punto_schema = { clave: 'schema', titulo: 'Datos estructurados (Schema.org)', estado: estSch,
  valor: tipos.length ? tipos.length + ' tipos' : (H.legible ? 'ninguno' : null),
  detalle: detSch, tipos_detectados: tipos.slice(0, 8), campos_ausentes: ausentes,
  validador: { disponible: !!V.disponible, errores: V.num_errores, warnings: V.num_warnings } };

/* ---------- 4. INFRAESTRUCTURA ---------- */
const infra = { home_ok: H.legible, sitemap: !!S.existe, robots: !!R.existe, indexable: !H.noindex };
const score_infra = Math.round((Object.values(infra).filter(Boolean).length / 4) * 100);

const ESC = { ok: 100, warning: 50, error: 0 };
// El score de SEO tecnico ya NO se calcula aqui: con el criterio de pesos (jerarquia 40,
// schema 35, resto 25) necesita el indice de autoridad y la claridad, que llegan del
// agente de informe. Se calcula en 'Ensamblar LITE2'.

return [{ json: { ...norm,
  punto_bots, punto_jerarquia, punto_schema, infra, score_infra,
  pagina: { title: H.title, metaDesc: H.meta_description, texto_home: H.texto, palabras: H.palabras },
  _diag: { home_status: H.statusCode, robots_status: R.statusCode, sitemap_status: S.statusCode,
           html_bytes: H.html_bytes, palabras: H.palabras, home_legible: H.legible, csr: H.csr, spa: H.spa,
           encabezados: H.total_encabezados, jsonld_bloques: H.jsonld_bloques, robots_grupos: R.grupos,
           sitemap_urls: S.urls, validador_schema: V.disponible ? 'ok' : V.motivo }
} }];"""

# --- Sondas: emite UN ITEM POR PREGUNTA (patron del informe avanzado) ---
CODE_SONDAS = r"""// Emite un ITEM POR PREGUNTA: cada nodo de modelo se ejecutara una vez por item.
// Es el patron de 'Sondas D1' del informe avanzado, y es lo que permite leerlas
// despues con .all()[idx] indexado por pregunta, de forma fiable.
const r = $input.first().json;
const kw = r.keyword, mercado = r.mercado;
const preguntas = [
  '¿Cuáles son las mejores opciones de ' + kw + ' en ' + mercado + '? Nómbralas y explica brevemente por qué destacan.',
  'Estoy en ' + mercado + ' y busco ' + kw + '. ¿Qué empresas o proveedores concretos me recomiendas?',
  '¿Qué empresas destacan en ' + kw + ' en ' + mercado + ' por su reputación y experiencia? Nómbralas.'
];
return preguntas.map((p, i) => ({ json: { pregunta_id: i + 1, prompt: p } }));"""

CODE_SONDA_HUELLA = r"""// Un solo item: consulta de huella. Sus CITAS son enlaces reales de presencia externa.
const r = $input.first().json;
const prompt = '¿Dónde aparece mencionada la empresa ' + r.brand + ' (' + r.host + ') en internet? '
  + 'Busca menciones en directorios, medios, foros, reseñas y listas del sector. Cita las fuentes.';
return [{ json: { prompt } }];"""

# --- Ficha de Google Business (Places API New) ---
CODE_PARSEAR_FICHA = r"""// Analiza la ficha de Google Business (Places API New, nodo 'Ficha Google').
// HONESTIDAD: NO atribuye una ficha cualquiera como "la tuya". Casa por DOMINIO
// (confianza alta) o por NOMBRE (media); si no casa con seguridad, dice que no la
// encontro. Nunca presenta la ficha de un competidor como si fuera tuya (bug es_marca).
const _nm = s => String(s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '');
const _host = u => { const m = String(u || '').match(/^https?:\/\/([^\/:?#]+)/i); return m ? m[1].toLowerCase().replace(/^www\./, '') : ''; };
// Devuelve { place, confianza } o null. 'alta' = casa por dominio; 'media' = solo por nombre.
function matchFicha(places, brand, domain) {
  const arr = Array.isArray(places) ? places : [];
  const domN = _nm(_host('http://' + String(domain || '')) || domain);
  const brandN = _nm(brand);
  if (domN) for (const p of arr) { const h = _nm(_host(p && p.websiteUri)); if (h && (h.includes(domN) || domN.includes(h))) return { place: p, confianza: 'alta' }; }
  if (brandN.length > 2) for (const p of arr) { const n = _nm(p && p.displayName && p.displayName.text); if (n && (n.includes(brandN) || brandN.includes(n))) return { place: p, confianza: 'media' }; }
  return null;
}
// <<<FIN-FICHA-TESTABLE>>>
const N = $('Normalizar Input').first().json;
const raw = $('Ficha Google').first().json;
const body = (raw && (raw.body !== undefined ? raw.body : (raw.data !== undefined ? raw.data : raw))) || {};
const hit = matchFicha(body.places, N.brand, N.domain || N.host);
if (!hit) return [{ json: { ficha_google: { encontrada: false, candidatos: Array.isArray(body.places) ? body.places.length : 0,
  motivo: (Array.isArray(body.places) && body.places.length) ? 'Hay fichas parecidas pero ninguna casa con tu marca/dominio con seguridad.' : 'No encontramos ficha de Google Business para esta empresa en este mercado.' } } }];
const p = hit.place;
const oh = p.regularOpeningHours;
return [{ json: { ficha_google: {
  encontrada: true,
  confianza: hit.confianza,            // 'alta' = casa por dominio; 'media' = solo por nombre (menos seguro)
  nombre: p.displayName ? p.displayName.text : null,
  direccion: p.formattedAddress || null,
  rating: (typeof p.rating === 'number') ? p.rating : null,
  resenas: (typeof p.userRatingCount === 'number') ? p.userRatingCount : null,
  categoria: (p.primaryTypeDisplayName ? p.primaryTypeDisplayName.text : null) || (Array.isArray(p.types) ? p.types[0] : null) || null,
  web: p.websiteUri || null,
  telefono: p.nationalPhoneNumber || null,
  estado: p.businessStatus || null,    // OPERATIONAL | CLOSED_TEMPORARILY | CLOSED_PERMANENTLY
  horario_publicado: !!(oh && Array.isArray(oh.weekdayDescriptions) && oh.weekdayDescriptions.length),
  maps_url: p.googleMapsUri || null
} } }];"""

# --- Enlaces rotos (404) en TODO el sitio ---
_HELPERS_ENLACES = (
    "const hostOf = u => { try { return new URL(u).host.replace(/^www\\./, '').toLowerCase(); } catch (e) { return ''; } };\n"
    "const reg = h => h.split('.').slice(-2).join('.');\n"
)
CODE_PAGINAS = r"""// Descubre las PAGINAS del sitio a revisar (no solo la home): union de la home +
// las URLs del sitemap (urlset) + los enlaces internos de la home (fallback si el
// sitemap falta o es un indice). Acota a 30 paginas (avisado). Un item por pagina.
""" + _HELPERS_ENLACES + r"""const base = $('Consolidar Senales').first().json;
const homeUrl = base.home_url || base.domain || ('https://' + (base.host || ''));
const site = hostOf(homeUrl);
// 1) sitemap (XML crudo)
let sm = '';
try { const s = $('GET sitemap').first().json; sm = String((s && (s.body !== undefined ? s.body : s.data)) || ''); } catch (e) {}
const esIndex = /<sitemapindex/i.test(sm);
let locs = esIndex ? [] : (sm.match(/<loc>([\s\S]*?)<\/loc>/gi) || []).map(x => x.replace(/<\/?loc>/gi, '').replace(/&amp;/g, '&').trim());
// 2) enlaces internos de la home
let homeHtml = '';
try { const h = $('GET Home').first().json; homeHtml = String((h && (h.body !== undefined ? h.body : h.data)) || ''); } catch (e) {}
const homeLinks = [];
const re = /<a\b[^>]*\bhref\s*=\s*["']([^"']+)["']/gi; let m;
while ((m = re.exec(homeHtml)) !== null && homeLinks.length < 300) {
  let href = String(m[1]).trim();
  if (!href || /^(mailto:|tel:|javascript:|data:|#)/i.test(href)) continue;
  let abs; try { abs = new URL(href, homeUrl).href.split('#')[0]; } catch (e) { continue; }
  const h = hostOf(abs);
  if (/^https?:/i.test(abs) && h && site && reg(h) === reg(site)) homeLinks.push(abs);
}
// union home + sitemap + enlaces internos, dedup, cap
const cand = new Set();
const addC = u => { const c = String(u).split('#')[0]; if (/^https?:/i.test(c)) cand.add(c); };
addC(homeUrl); locs.forEach(addC); homeLinks.forEach(addC);
const todas = [...cand];
const CAP = 30;
const paginas = todas.slice(0, CAP);
return paginas.map(url => ({ json: { url, _paginas_encontradas: todas.length, _cap_paginas: CAP } }));"""

CODE_EXTRAER_ENLACES = r"""// Extrae los enlaces <a href> de TODAS las paginas crawleadas ('GET Pagina'),
// resolviendo cada uno contra la URL de SU pagina. Clasifica interno/externo, dedup
// entre paginas y CAPA a 120 (avisado). Un item por enlace; centinela si no hay.
""" + _HELPERS_ENLACES + r"""const paginasIn = $('Paginas a Revisar').all().map(i => i.json);
const htmls = $('GET Pagina').all().map(i => i.json);
const base = $('Consolidar Senales').first().json;
const homeUrl = base.home_url || base.domain || ('https://' + (base.host || ''));
const site = hostOf(homeUrl);
const CAP = 120;
const seen = new Set(), todos = [];
for (let pi = 0; pi < paginasIn.length; pi++) {
  const pageUrl = (paginasIn[pi] && paginasIn[pi].url) || homeUrl;
  const hj = htmls[pi];
  const html = String((hj && (hj.body !== undefined ? hj.body : hj.data)) || '');
  const re = /<a\b[^>]*\bhref\s*=\s*["']([^"']+)["']/gi; let m;
  while ((m = re.exec(html)) !== null) {
    let href = String(m[1]).trim();
    if (!href || /^(mailto:|tel:|javascript:|data:|#)/i.test(href)) continue;
    let abs; try { abs = new URL(href, pageUrl).href.split('#')[0]; } catch (e) { continue; }
    if (!/^https?:/i.test(abs) || seen.has(abs)) continue;
    seen.add(abs);
    const h = hostOf(abs);
    todos.push({ url: abs, tipo: (h && site && reg(h) === reg(site)) ? 'interno' : 'externo' });
  }
}
const encontrados = todos.length;
const paginasRev = paginasIn.length;
const out = todos.slice(0, CAP);
if (out.length === 0) return [{ json: { url: homeUrl, tipo: 'interno', _vacio: true, _encontrados: 0, _cap: CAP, _paginas: paginasRev } }];
out[0]._encontrados = encontrados; out[0]._cap = CAP; out[0]._paginas = paginasRev;
return out.map(e => ({ json: e }));"""

CODE_CLASIFICAR_ENLACES = r"""// Clasifica el estado de cada enlace comprobado. HONESTIDAD: 404/410 = ROTO (seguro);
// 403/429/5xx/timeout = NO VERIFICABLE (un WAF, un rate-limit o un lento NO es un enlace
// roto). 2xx/3xx y otros 4xx = accesible. No se cuenta el centinela (_vacio).
function clasificarStatus(sc) {
  sc = Number(sc);
  if (sc === 404 || sc === 410) return 'roto';
  if (!sc || sc === 403 || sc === 429 || sc >= 500) return 'no_verificable';
  return 'ok';
}
// <<<FIN-ENLACES-TESTABLE>>>
const entradas = $('Extraer Enlaces').all().map(i => i.json);
const resp = $('Comprobar Enlace').all().map(i => i.json);
const rotos = [];
let revisados = 0, noVerif = 0;
const cap = (entradas[0] && entradas[0]._cap) || 120;
const encontrados = (entradas[0] && entradas[0]._encontrados) || 0;
const paginas = (entradas[0] && entradas[0]._paginas) || 0;
for (let i = 0; i < entradas.length; i++) {
  const e = entradas[i];
  if (!e || e._vacio || !e.url) continue;
  revisados++;
  const r = resp[i] || {};
  let sc = Number(r.statusCode);
  if (!Number.isFinite(sc)) sc = 0;
  const cls = clasificarStatus(sc);
  if (cls === 'roto') rotos.push({ url: e.url, tipo: e.tipo, status: sc });
  else if (cls === 'no_verificable') noVerif++;
}
return [{ json: { enlaces_rotos: {
  revisados, encontrados, paginas_revisadas: paginas, cap_aplicado: encontrados > cap,
  total_rotos: rotos.length,
  internos_rotos: rotos.filter(x => x.tipo === 'interno').length,
  externos_rotos: rotos.filter(x => x.tipo === 'externo').length,
  no_verificables: noVerif,
  rotos: rotos.slice(0, 20)
} } }];"""

# --- Recopilar: usa .all() + pick/pickCitations del avanzado ---
CODE_RECOPILAR = r"""// DETERMINISTA (0 tokens). Lee las respuestas con el MISMO patron del informe avanzado:
// .all() indexado por pregunta + pick()/pickCitations() defensivos.
const r = $('Consolidar Senales').first().json;
const preguntas = $('Sondas').all().map(i => i.json);

__PICK__

const gpt = $('Sonda - ChatGPT').all().map(i => i.json);
const cla = $('Sonda - Claude').all().map(i => i.json);
const gem = $('Sonda - Gemini').all().map(i => i.json);
const per = $('Sonda - Perplexity').all().map(i => i.json);
let hue = [];
try { hue = $('Huella - Perplexity').all().map(i => i.json); } catch(e){ hue = []; }

/* ---------- Deteccion de marca: por nombre completo, tokens, token distintivo o dominio ----------
   El fallo anterior era exigir el nombre completo literal: una marca citada solo por su
   palabra distintiva no casaba con su nombre completo y salia 0 aunque estuviera bien
   posicionada. */
const norm = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
  .replace(/[^a-z0-9]+/g, ' ').replace(/\s+/g, ' ').trim();
const STOP = new Set(['la','el','los','las','de','del','y','sl','sa','slu','sau','srl','sociedad','limitada',
  'group','grupo','the','and','co','inc','ltd','llc','company','empresa']);
const brandNorm = norm(r.brand);
const brandTokens = brandNorm.split(' ').filter(t => t && !STOP.has(t));
const hostToken = norm(r.host).split(' ')[0];
// El token distintivo NO puede ser una palabra del sector ni del mercado: si la marca es
// una marca cuyo nombre incluye su propio sector, usar esa palabra generica contaria
// como mencion cualquier respuesta del sector aunque no te nombre.
const genericos = new Set([...norm(r.keyword).split(' '), ...norm(r.mercado).split(' ')].filter(Boolean));
const propios = brandTokens.filter(t => !genericos.has(t));
const distintivo = propios.filter(t => t.length >= 4).sort((a, b) => b.length - a.length)[0] || null;

function apareceEn(texto){
  const t = norm(texto);
  if (!t) return false;
  if (brandNorm.length > 2 && t.includes(brandNorm)) return true;                  // nombre completo
  // La regla de "todos los tokens" solo vale si la marca tiene alguna palabra propia:
  // con una marca tipo "Grupo Madrid Eventos" en el sector eventos y mercado Madrid,
  // cualquier frase que diga Madrid y eventos daria positivo sin nombrarte.
  if (propios.length && brandTokens.every(tok => t.includes(tok))) return true;
  if (distintivo && t.includes(distintivo)) return true;                            // token distintivo
  if (hostToken && hostToken.length >= 5 && t.includes(hostToken)) return true;      // dominio
  return false;
}

const MODELOS = [
  { clave: 'chatgpt', etiqueta: 'ChatGPT', arr: gpt },
  { clave: 'claude', etiqueta: 'Claude', arr: cla },
  { clave: 'gemini', etiqueta: 'Gemini', arr: gem },
  { clave: 'perplexity', etiqueta: 'Perplexity', arr: per }
];

const detalle = [];
let citasSector = [];
preguntas.forEach((p, idx) => {
  const respuestas = MODELOS.map(m => {
    const texto = pick(m.arr, idx);
    if (m.clave === 'perplexity') citasSector = citasSector.concat(pickCitations(m.arr, idx));
    const ok = !!texto.trim();
    return { modelo: m.etiqueta, clave: m.clave, respondio: ok,
             aparece: ok && apareceEn(texto), respuesta: texto.slice(0, 2500) };
  });
  detalle.push({ pregunta: p.prompt, respuestas });
});

const por_modelo = MODELOS.map(m => {
  const celdas = detalle.map(p => {
    const x = p.respuestas.find(z => z.clave === m.clave);
    return x ? { respondio: x.respondio, aparece: x.aparece } : { respondio: false, aparece: false };
  });
  const validas = celdas.filter(c => c.respondio).length;
  const hits = celdas.filter(c => c.aparece).length;
  return { modelo: m.etiqueta, clave: m.clave, apariciones: hits, preguntas_validas: validas,
           tasa: validas ? Math.round((hits / validas) * 100) : null, celdas };
});
const totalValidas = por_modelo.reduce((a, m) => a + m.preguntas_validas, 0);
const totalHits = por_modelo.reduce((a, m) => a + m.apariciones, 0);
const tasa_global = totalValidas ? Math.round((totalHits / totalValidas) * 100) : null;

/* ---------- ENLACES DE PRESENCIA EXTERNA ---------- */
const textoHuella = pick(hue, 0);
const citasHuella = pickCitations(hue, 0);
const hostOf = (u) => { const m = String(u || '').match(/^https?:\/\/([^\/:?#]+)/i); return m ? m[1].toLowerCase().replace(/^www\./, '') : null; };
const AGREG = /^(google|bing|duckduckgo|facebook|instagram|twitter|x|youtube)\./i;
const vistos = new Set(); const enlaces = [];
for (const u of citasHuella) {
  const h = hostOf(u);
  if (!h || h === r.host || AGREG.test(h) || vistos.has(h)) continue;
  vistos.add(h);
  enlaces.push({ dominio: h, url: String(u).slice(0, 300) });
  if (enlaces.length >= 12) break;
}
const propioCitado = citasHuella.some(u => hostOf(u) === r.host);

return [{ json: { ...r,
  preguntas_detalle: detalle,
  aparicion: { por_modelo, tasa_global, total_hits: totalHits, total_validas: totalValidas },
  presencia_externa: { enlaces, total: enlaces.length, dominio_propio_citado: propioCitado, texto_huella: textoHuella.slice(0, 2500) },
  _diag: { ...(r._diag || {}), respuestas_ok: por_modelo.map(m => m.modelo + ':' + m.preguntas_validas + '/3').join(' '),
           citas_sector: citasSector.length, citas_huella: citasHuella.length,
           marca_tokens: brandTokens.join('|'), marca_distintivo: distintivo }
} }];""".replace("__PICK__", JS_PICK)

CODE_PROMPTS = r"""// Construye los prompts del agente. Se hace en Code (no en la expresion del nodo HTTP)
// porque el esquema JSON contiene '}}' y eso rompe el parseo de las expresiones ={{ }} de n8n.
const r = $input.first().json;

const esquema = '{"resumen_hallazgos":"","veredicto":"parcial","indice_autoridad":{"estado":"warning","detalle":""},'
  + '"semantica":{"claridad_nucleo":0,"entidades":[]},'
  + '"eeatc":{"experiencia":0,"expertise":0,"autoridad":0,"confianza":0,"citabilidad":0,"puntuacion_global":0},'
  + '"mapa_competitivo":[{"empresa":"","es_marca":false,"menciones":0,"por_modelo":{"chatgpt":0,"claude":0,"gemini":0,"perplexity":0}}],'
  + '"variantes_marca":[]}';

const prompt_sistema = [
  'Eres un analista de visibilidad de marca en motores de IA (GEO). Recibes: el contenido real de la home de una marca,',
  'las respuestas que dieron ChatGPT, Claude, Gemini y Perplexity a tres preguntas de usuario sobre su sector, y los dominios',
  'externos donde se menciona a la marca. Responde siempre en español.',
  '',
  'Devuelve un análisis con estas partes:',
  '1) resumen_hallazgos: 2-3 frases describiendo lo encontrado (estado actual, sin recomendaciones ni plan de acción).',
  '2) veredicto: visible | parcial | invisible | sin_datos.',
  '3) indice_autoridad: juzga si el contenido de la home aporta datos verificables, cifras, casos o citas que la IA pueda',
  '   reutilizar al responder. Devuelve estado (ok|warning|error) y un detalle de una sola frase.',
  '4) semantica: claridad_nucleo (0-100: si el negocio se entiende sin ambigüedad a partir del texto) y entidades',
  '   (5-10 conceptos núcleo extraídos del contenido REAL recibido, nunca inventados).',
  '5) eeatc: puntúa de 0 a 100 experiencia, expertise, autoridad, confianza y citabilidad, más puntuacion_global.',
  '   Básate SOLO en las evidencias recibidas. Solo números, sin texto.',
  '6) mapa_competitivo: empresas mencionadas en las respuestas, con menciones totales y desglose por modelo.',
  '   Cuenta una marca como mencionada aunque aparezca con nombre abreviado o variante, y unifica esas variantes en una',
  '   sola entrada. Incluye SIEMPRE la marca auditada aunque tenga 0 menciones. Máximo 10.',
  '7) variantes_marca: las grafías, abreviaturas o erratas LITERALES con que los modelos escribieron SOLO la marca',
  '   auditada (NUNCA competidores) en sus respuestas. Copia el texto tal cual apareció. Si no viste ninguna variante,',
  '   deja la lista vacía; no inventes ni normalices: solo lo que aparezca literalmente en las respuestas recibidas.',
  '',
  'Si el contenido de la home llega vacío, no inventes: pon los campos que dependan de él a 0 y dilo en resumen_hallazgos.',
  '',
  'Devuelve SOLO un JSON válido, sin markdown ni texto alrededor, con esta forma exacta:',
  esquema
].join('\n');

const prompt_usuario = JSON.stringify({
  marca: r.brand, dominio: r.host, sector: r.keyword, mercado: r.mercado,
  home: { titulo: r.pagina.title, descripcion: r.pagina.metaDesc, palabras: r.pagina.palabras, texto: r.pagina.texto_home },
  menciones_externas: (r.presencia_externa.enlaces || []).map(x => x.dominio),
  contexto_menciones: r.presencia_externa.texto_huella,
  preguntas: (r.preguntas_detalle || []).map(p => ({
    pregunta: p.pregunta,
    respuestas: (p.respuestas || []).map(x => ({ modelo: x.modelo, texto: String(x.respuesta || '').slice(0, 1400) }))
  }))
});

return [{ json: { ...r, prompt_sistema, prompt_usuario } }];"""

CODE_ENSAMBLAR = r"""// Une el analisis del agente con lo determinista y arma el informe reducido.
const r = $('Preparar Informe').first().json;
const d = $input.first().json;

let A = {};
try {
  const rawB = d.body ?? d.data;
  const body = rawB && typeof rawB === 'object' ? rawB : d;
  let texto = String(body.choices?.[0]?.message?.content ?? body.text ?? '');
  texto = texto.replace(/```json|```/g, '').trim();
  const m = texto.match(/\{[\s\S]*\}/);
  if (m) A = JSON.parse(m[0]) || {};
} catch(e){ A = {}; }

const num = (v) => (typeof v === 'number' && isFinite(v)) ? Math.max(0, Math.min(100, Math.round(v))) : null;
const ap = r.aparicion || {};

let veredicto = A.veredicto || '';
if (!['visible','parcial','invisible','sin_datos'].includes(veredicto)) {
  const t = ap.tasa_global;
  veredicto = (t === null || t === undefined) ? 'sin_datos' : t >= 66 ? 'visible' : t >= 34 ? 'parcial' : 'invisible';
}

const ee = A.eeatc || {};
const eeatc = { experiencia: num(ee.experiencia), expertise: num(ee.expertise), autoridad: num(ee.autoridad),
  confianza: num(ee.confianza), citabilidad: num(ee.citabilidad), puntuacion_global: num(ee.puntuacion_global) };
if (eeatc.puntuacion_global === null) {
  const vs = ['experiencia','expertise','autoridad','confianza','citabilidad'].map(k => eeatc[k]).filter(v => v !== null);
  eeatc.puntuacion_global = vs.length ? Math.round(vs.reduce((a,b) => a+b, 0) / vs.length) : null;
}

const sem = A.semantica || {};
const claridad = num(sem.claridad_nucleo);
const entidades = Array.isArray(sem.entidades) ? sem.entidades.filter(x => typeof x === 'string').slice(0, 10) : [];
const ia = A.indice_autoridad || {};
const estAut = ['ok','warning','error'].includes(ia.estado) ? ia.estado : 'no_verificable';

const norm = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
let mapa = (Array.isArray(A.mapa_competitivo) ? A.mapa_competitivo : [])
  .filter(x => x && x.empresa)
  .map(x => ({ empresa: String(x.empresa).slice(0, 60),
    es_marca: !!x.es_marca || norm(x.empresa) === norm(r.brand),
    menciones: Number(x.menciones) || 0,
    por_modelo: { chatgpt: Number((x.por_modelo||{}).chatgpt) || 0, claude: Number((x.por_modelo||{}).claude) || 0, gemini: Number((x.por_modelo||{}).gemini) || 0, perplexity: Number((x.por_modelo||{}).perplexity) || 0 } }));
// La marca SIEMPRE en el mapa. Si el agente la cuenta por debajo de lo que hemos detectado
// de forma determinista, se queda el valor mayor (el determinista ya es una cota inferior real).
const marcaIdx = mapa.findIndex(x => x.es_marca);
const hitsDet = ap.total_hits || 0;
if (marcaIdx === -1) {
  mapa.unshift({ empresa: r.brand, es_marca: true, menciones: hitsDet,
    por_modelo: (ap.por_modelo || []).reduce((o, m) => { o[m.clave] = m.apariciones; return o; }, { chatgpt:0, claude:0, gemini:0, perplexity:0 }) });
} else if (mapa[marcaIdx].menciones < hitsDet) {
  mapa[marcaIdx].menciones = hitsDet;
}
mapa.sort((a, b) => b.menciones - a.menciones);

const V = { ok: 100, warning: 50, error: 0 };
const avg = (arr) => { const v = arr.filter(x => typeof x === 'number' && isFinite(x)); return v.length ? Math.round(v.reduce((a,b) => a+b, 0) / v.length) : null; };
const wavg = (pairs) => { let s = 0, w = 0; for (const [v, p] of pairs) { if (typeof v === 'number' && isFinite(v)) { s += v * p; w += p; } } return w ? Math.round(s / w) : null; };
const pe = r.presencia_externa || {};

/* SEO tecnico con pesos por gravedad (criterio 2026): una media simple diluia los fallos
   graves y una web con 2 H1 sacaba 80-90. Jerarquia 40% + schema 35% + resto 25%
   (el resto = acceso de bots, indice de autoridad, claridad semantica e infraestructura,
   en media; la infraestructura se fusiono en SEO tecnico por ser SEO en esencia). */
const vNum = (est) => (est in V) ? V[est] : null;   // no_verificable queda fuera
const scoreSeo = wavg([
  [vNum(r.punto_jerarquia.estado), 0.40],
  [vNum(r.punto_schema.estado), 0.35],
  [avg([vNum(r.punto_bots.estado), vNum(estAut), claridad, r.score_infra]), 0.25]
]);

const scoreContenido = avg([vNum(estAut), claridad]);

/* Huella (criterio 2026): E-E-A-T-C 40% + enlaces externos 35% (8+ fuentes = 100) +
   visibilidad del propio dominio entre las citas 25%. */
const scoreHuella = wavg([
  [eeatc.puntuacion_global, 0.40],
  [Math.min(100, (pe.total || 0) * 12), 0.35],
  [pe.dominio_propio_citado ? 100 : 0, 0.25]
]);

const por_area = { seo_tecnico: scoreSeo, contenido: scoreContenido, sov: ap.tasa_global, huella: scoreHuella };
/* Pesos globales (criterio 2026): 4 areas; SEO tecnico 25% tras absorber infraestructura. */
const PESOS = { seo_tecnico: 0.25, contenido: 0.15, sov: 0.35, huella: 0.25 };
let acum = 0, peso = 0;
for (const k of Object.keys(PESOS)) if (typeof por_area[k] === 'number') { acum += por_area[k] * PESOS[k]; peso += PESOS[k]; }
const nota = peso > 0 ? Math.round(acum / peso) : null;

const dg = r._diag || {};
const avisos = [];
// Con la nueva legibilidad (contenido real => legible), legible=false ya implica que
// no se pudo extraer nada util de la home.
if (dg.home_legible === false) avisos.push('No hemos podido leer el contenido de tu home' + (dg.home_status && dg.home_status !== 200 ? ' (respuesta ' + dg.home_status + ')' : ' (tu web sirve una página de verificación anti-bots)') + ', así que las comprobaciones que dependen de él quedan sin verificar.');
else if (dg.csr) avisos.push('Tu home entrega muy poco HTML inicial y pinta el contenido con JavaScript: los modelos que no ejecutan JS ven una página casi vacía.');
if ((ap.total_validas || 0) === 0) avisos.push('Ningún modelo devolvió respuesta en esta ejecución, así que la visibilidad no es concluyente.');
else if ((ap.total_validas || 0) < 9) avisos.push('Solo ' + ap.total_validas + ' de 9 sondeos devolvieron respuesta.');

// [E3] Estado por modulo (completed|partial|failed). Mismo contrato que el
// COMPLETO para que ambos informes sean comparables. Un modulo caido (un modelo
// que no respondio, un bloque sin datos) NO invalida el resto: se marca y el
// render lo dice, en vez de fingir un 0.
const ES_ESTADO = new Set(['ok', 'warning', 'error', 'no_verificable']);
function estadoModulo(b, opts) {
  opts = opts || {};
  if (b === null || b === undefined || typeof b !== 'object') return 'failed';
  if (b._error) return 'failed';
  const claves = Object.keys(b).filter(k => k[0] !== '_');
  if (!claves.length) return 'failed';                       // objeto vacio = no se pudo
  // Modulo de sondeo (visibilidad): parcial si ningun modelo respondio.
  if (opts.dimension) return (Number(b.total_validas) || 0) === 0 ? 'partial' : 'completed';
  // Modulo con lista de puntos (seo_tecnico): mirar los estados de los puntos.
  const puntos = Array.isArray(b.puntos) ? b.puntos : (Array.isArray(b) ? b : null);
  if (puntos) {
    const est = puntos.map(p => p && p.estado).filter(e => ES_ESTADO.has(e));
    if (!est.length) return 'failed';
    return est.every(e => e === 'no_verificable') ? 'partial' : 'completed';
  }
  // Fallback generico {clave:{estado}} (igual que el COMPLETO).
  const est = [];
  for (const k of claves) { const v = b[k]; if (v && typeof v === 'object' && ES_ESTADO.has(v.estado)) est.push(v.estado); }
  return (est.length && est.every(e => e === 'no_verificable')) ? 'partial' : 'completed';
}

// [C2] ¿La grafia v parece la marca AUDITADA (y no un competidor)? Mismo criterio
// determinista que el parche es_marca: nombre exacto, contiene/esta contenida en
// el distintivo, o comparte un prefijo largo con el (erratas). Conservador a
// proposito: antes dejar fuera una errata rara que colar un competidor como "tu
// marca" (bug es_marca). Auto-contenida (normaliza dentro) para poder testearla.
function pareceMarca(v, distintivo, brand) {
  const nm = s => String(s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '');
  const n = nm(v), d = nm(distintivo), b = nm(brand);
  if (!n) return false;
  if (b.length > 2 && n === b) return true;
  if (!d) return false;
  // Una errata/variante tiene longitud PARECIDA a la de la marca. Un nombre
  // compuesto mucho mas largo que contenga el distintivo (p.ej. un competidor
  // 'BrandevsKiller') NO es una variante: se rechaza para no repetir es_marca.
  if (n.length > Math.max(b.length, d.length) + 3) return false;
  if (n.includes(d) || d.includes(n)) return true;
  let i = 0; while (i < n.length && i < d.length && n[i] === d[i]) i++;
  return i >= Math.max(4, Math.ceil(d.length * 0.6));
}

// [E1] Coste por ejecucion. Igual que en el COMPLETO: tokens MEDIDOS (usage real
// de cada API) + coste ESTIMADO desde una tabla editable; un modelo sin precio no
// se inventa (se lista en 'sin_precio' y el total es un suelo). En LITE TODAS las
// llamadas son HTTP crudo con usage, asi que no hay hueco 'no_medido'.
const PRECIOS = {                          // USD por 1M tokens (estimado, editable en el builder)
  'gpt-5.4-mini':     { in: 0.25, out: 2.00 },
  'gpt-5.6-luna':     { in: 0.50, out: 3.00 },   // sonda del tier gratuito (panel)
  'claude-haiku-4-5': { in: 1.00, out: 5.00 },
  'gemini-2.5-flash': { in: 0.30, out: 2.50 },
  'gemini-3.5-flash': { in: 0.40, out: 3.00 },   // sonda del tier gratuito (panel)
  'sonar':            { in: 1.00, out: 1.00 },
};
const PRECIOS_META = { estimado: true, fecha: '2026-08', fuente: 'tarifa publica aproximada; ajustar en build_lite2.py' };
function tokensDe(body) {
  if (!body || typeof body !== 'object') return null;
  const um = body.usageMetadata;
  if (um) return { in: um.promptTokenCount || 0, out: um.candidatesTokenCount || 0 };
  const u = body.usage;
  if (!u || typeof u !== 'object') return null;
  if (u.input_tokens != null || u.output_tokens != null) return { in: u.input_tokens || 0, out: u.output_tokens || 0 };
  if (u.prompt_tokens != null || u.completion_tokens != null) return { in: u.prompt_tokens || 0, out: u.completion_tokens || 0 };
  return null;
}
// Modelo REALMENTE usado segun lo que reporta la API (openai/anthropic/perplexity
// en body.model; gemini en body.modelVersion). El panel cambia la sonda a otro
// modelo que el builder (p.ej. gemini-3.5-flash), asi que fiarse de la etiqueta
// hardcodeada mentiria; el fallback solo se usa si la respuesta no trae modelo.
function modeloDe(body, fallback) {
  if (body && typeof body === 'object') {
    const m = body.model || body.modelVersion;
    if (m) return String(m).replace(/^models\//, '');
  }
  return fallback;
}
// Tarifa por coincidencia exacta o por prefijo (absorbe sufijos de version tipo
// 'gpt-5.6-luna-2026-08'). Sin coincidencia -> null (el modelo va a sin_precio).
function precioDe(modelo) {
  if (PRECIOS[modelo]) return PRECIOS[modelo];
  let mejor = null;
  for (const k in PRECIOS) if (modelo && modelo.startsWith(k) && (!mejor || k.length > mejor.length)) mejor = k;
  return mejor ? PRECIOS[mejor] : null;
}
function agregarCoste(muestras) {
  const r6 = x => Math.round(x * 1e6) / 1e6;
  const porModelo = {};
  const sinPrecio = new Set();
  let requests = 0, fallos = 0, inTot = 0, outTot = 0, costeTot = 0;
  for (const m of (muestras || [])) {
    requests++;
    if (m.error || !m.tokens) { fallos++; continue; }
    const ti = m.tokens.in || 0, to = m.tokens.out || 0;
    inTot += ti; outTot += to;
    const p = precioDe(m.modelo);
    const coste = p ? (ti / 1e6) * p.in + (to / 1e6) * p.out : 0;
    if (p) costeTot += coste; else sinPrecio.add(m.modelo);
    const pm = porModelo[m.modelo] || (porModelo[m.modelo] =
      { modelo: m.modelo, requests: 0, input: 0, output: 0, coste_usd: 0, sin_precio: !p });
    pm.requests++; pm.input += ti; pm.output += to; pm.coste_usd += coste;
  }
  for (const k in porModelo) porModelo[k].coste_usd = r6(porModelo[k].coste_usd);
  return {
    token_usage: { input: inTot, output: outTot, total: inTot + outTot },
    estimated_cost_usd: r6(costeTot), completo: sinPrecio.size === 0,
    request_count: requests, fallos, reintentos: 0,
    por_modelo: Object.values(porModelo), sin_precio: [...sinPrecio], precios: PRECIOS_META,
  };
}
// <<<FIN-HELPERS-TESTABLES>>>
function leerNodo(nombre) {
  try { return $(nombre).all().map(i => i.json); } catch (e) { return null; }
}
const NODOS_LLM = [
  { nodo: 'Sonda - ChatGPT', modelo: 'gpt-5.4-mini' },
  { nodo: 'Sonda - Claude', modelo: 'claude-haiku-4-5' },
  { nodo: 'Sonda - Gemini', modelo: 'gemini-2.5-flash' },
  { nodo: 'Sonda - Perplexity', modelo: 'sonar' },
  { nodo: 'Huella - Perplexity', modelo: 'sonar' },
  { nodo: 'Informe ChatGPT', modelo: 'gpt-5.4-mini' },
];
const muestrasCoste = [];
for (const { nodo, modelo } of NODOS_LLM) {
  const items = leerNodo(nodo);
  if (items === null) continue;
  for (const it of items) {
    const body = (it && it.body !== undefined) ? it.body : it;
    const errApi = (it && it.statusCode && it.statusCode >= 400) || (body && body.error);
    const tk = errApi ? null : tokensDe(body);
    muestrasCoste.push({ modelo: modeloDe(body, modelo), tokens: tk, error: !!errApi || !tk });
  }
}
const coste = agregarCoste(muestrasCoste);

// [E3] Estado de cada modulo del informe LITE.
const estados_modulos = {
  seo_tecnico: estadoModulo({ puntos: [r.punto_bots, r.punto_jerarquia, r.punto_schema,
    { estado: estAut },
    { estado: claridad === null ? 'no_verificable' : claridad >= 75 ? 'ok' : claridad >= 50 ? 'warning' : 'error' }] }),
  huella_digital: (!((pe.enlaces || []).length) && !['experiencia', 'expertise', 'autoridad', 'confianza', 'citabilidad'].some(k => typeof eeatc[k] === 'number')) ? 'partial' : 'completed',
  visibilidad: estadoModulo(ap, { dimension: true }),
  // 'informe' = el analisis del agente LLM. Si devolvio JSON no parseable, A={} y
  // hoy quedaria invisible: E3 lo saca a la superficie como 'failed'. Es el caso
  // NUEVO que los avisos no cubren.
  informe: (A && Object.keys(A).length) ? 'completed' : 'failed',
};

// [C2] Variantes/erratas de marca. Separa lo MEDIDO (tokens deterministas de
// deteccion, derivados del nombre) de lo INFERIDO (las grafias que los modelos
// dicen haber usado). Las inferidas se FILTRAN con el mismo criterio que es_marca
// para que un competidor no se cuele como "tu marca". No tocan menciones ni SoV.
const _distintivoC2 = dg.marca_distintivo || '';
const variantes_marca = {
  deteccion: [...new Set([...(String(dg.marca_tokens || '').split('|')), _distintivoC2].map(x => x.trim()).filter(Boolean))],
  observadas: [...new Set((Array.isArray(A.variantes_marca) ? A.variantes_marca : [])
    .map(v => String(v || '').trim())
    .filter(v => v && pareceMarca(v, _distintivoC2, r.brand)))].slice(0, 12),
};

return [{ json: {
  meta: { brand: r.brand, domain: r.domain, host: r.host, keyword: r.keyword, mercado: r.mercado,
          version: 'lite2', fecha: new Date().toISOString(),
          // [E2] Versionado del analisis: distingue ejecuciones cuando cambia el
          // pipeline, el scoring o los prompts. scoring_version se mantiene igual
          // que en el COMPLETO porque la nota debe ser comparable entre ambos.
          analysis_version: 'lite-v3', scoring_version: 'score-v1', prompt_version: 'prompt-v2',  // v3: sondas GROUNDED (web search); re-baseliza la nota vs v2 paramétrico
          // [E1] Resumen de coste en meta (el detalle va en el bloque 'coste').
          estimated_cost_usd: coste.estimated_cost_usd, coste_completo: coste.completo,
          tokens_total: coste.token_usage.total,
          modelos: ['ChatGPT','Claude','Perplexity'], preguntas_lanzadas: 3, sondeos: ap.total_validas ?? 0 },
  coste,
  estados_modulos,
  nota, por_area,
  resumen_hallazgos: A.resumen_hallazgos || '',
  posicionamiento: { veredicto },
  avisos,
  seo_tecnico: { puntos: [ r.punto_bots, r.punto_jerarquia, r.punto_schema,
      { clave: 'indice_autoridad', titulo: 'Índice de autoridad', estado: estAut, valor: null, detalle: ia.detalle || null },
      { clave: 'semantica', titulo: 'Cómo lee la IA tu web',
        estado: claridad === null ? 'no_verificable' : claridad >= 75 ? 'ok' : claridad >= 50 ? 'warning' : 'error',
        valor: claridad === null ? null : claridad + ' / 100', detalle: null, entidades } ],
    bloqueados: 4 },
  huella_digital: { enlaces: pe.enlaces || [], dominio_propio_citado: !!pe.dominio_propio_citado, eeatc, bloqueados: 3 },
  preguntas: r.preguntas_detalle,
  aparicion: ap,
  mapa_competitivo: mapa.slice(0, 10),
  variantes_marca,
  // [Ficha Google] Se lee del nodo 'Parsear Ficha' (rama paralela). Defensivo: si
  // el nodo no corrio (sin credencial de Places), queda null y el render lo omite.
  ficha_google: (() => { try { return $('Parsear Ficha').first().json.ficha_google; } catch (e) { return null; } })(),
  // [Enlaces 404] rama paralela; defensivo si el nodo no corrio.
  enlaces_rotos: (() => { try { return $('Clasificar Enlaces').first().json.enlaces_rotos; } catch (e) { return null; } })(),
  _diag: r._diag || {}
} }];"""

# ============================================================
# HELPERS DE CONSTRUCCION
# ============================================================
def code(name, js, pos):
    return {"parameters": {"jsCode": js}, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos, "name": name}

def http_get(name, url_expr, pos):
    # Opciones IDENTICAS a los GET del informe avanzado (incluido outputPropertyName)
    # + User-Agent de navegador: sin el, muchos WAF devuelven 403 y todo el analisis sale vacio.
    return {"parameters": {"url": url_expr,
        "sendHeaders": True, "headerParameters": {"parameters": [{"name": "User-Agent", "value": UA}]},
        "options": {"timeout": 20000, "response": {"response": {
            "fullResponse": True, "neverError": True, "responseFormat": "text", "outputPropertyName": "body"}}}},
        "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "onError": "continueRegularOutput",
        "position": pos, "name": name}

def nodo_chatgpt(name, pos):
    # GROUNDED: web search de OpenAI para gpt-5.x va por la Responses API con tools:[{web_search}],
    # no por chat/completions. La respuesta viene en output[].content[].output_text (pick lo parsea).
    return {"parameters": {"method": "POST", "url": "https://api.openai.com/v1/responses",
        "authentication": "predefinedCredentialType", "nodeCredentialType": "openAiApi",
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ model: 'gpt-5.4-mini', tools: [{ type: 'web_search' }], input: $json.prompt }) }}",
        "options": {"timeout": 120000, "response": {"response": {"fullResponse": True, "neverError": True}}}},
        "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "onError": "continueRegularOutput", "position": pos, "name": name}

def nodo_claude(name, pos):
    # GROUNDED: server tool web_search. haiku-4-5 es anterior a Sonnet 4.6, asi que usa la
    # variante BASICA web_search_20250305 (la 20260209 requiere Opus 4.6+/Sonnet 4.6+).
    # pick() extrae solo los bloques text (ignora server_tool_use/web_search_tool_result).
    # max_tokens sube (una respuesta grounded con citas es mas larga; cortarla pierde empresas).
    return {"parameters": {"method": "POST", "url": "https://api.anthropic.com/v1/messages",
        "authentication": "predefinedCredentialType", "nodeCredentialType": "anthropicApi",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "anthropic-version", "value": "2023-06-01"}]},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ model: 'claude-haiku-4-5', max_tokens: 2500, temperature: 0.4, tools: [{ type: 'web_search_20250305', name: 'web_search' }], messages: [{ role: 'user', content: $json.prompt }] }) }}",
        "options": {"timeout": 120000, "response": {"response": {"fullResponse": True, "neverError": True}}}},
        "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "onError": "continueRegularOutput", "position": pos, "name": name}

def nodo_perplexity(name, pos, ctx="low"):
    return {"parameters": {"method": "POST", "url": "https://api.perplexity.ai/chat/completions",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ model: 'sonar', messages: [{ role: 'user', content: $json.prompt }], web_search_options: { search_context_size: '" + ctx + "', user_location: $('Normalizar Input').first().json.geo.user_location } }) }}",
        "options": {"timeout": 90000, "response": {"response": {"fullResponse": True, "neverError": True}}}},
        "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "onError": "continueRegularOutput", "position": pos, "name": name}

def nodo_gemini(name, pos):
    # Gemini usa la API de Google: cuerpo { contents:[{ parts:[{ text }] }] } y la respuesta
    # viene en candidates[].content.parts[].text (pick() ya lo lee).
    # Auth: Header Auth generica con el header 'x-goog-api-key' = tu clave de Gemini.
    # GROUNDED: tools:[{google_search:{}}] hace que responda buscando en la web (no de memoria).
    return {"parameters": {"method": "POST",
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ contents: [{ parts: [{ text: $json.prompt }] }], tools: [{ google_search: {} }], generationConfig: { temperature: 0.4, maxOutputTokens: 1400, thinkingConfig: { thinkingBudget: 0 } } }) }}",
        "options": {"timeout": 90000, "response": {"response": {"fullResponse": True, "neverError": True}}}},
        "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "onError": "continueRegularOutput", "position": pos, "name": name}

def nodo_validador_schema(pos):
    # Validador OFICIAL de schema.org, mismo nodo que usa el informe avanzado.
    return {"parameters": {"method": "POST", "url": "https://validator.schema.org/validate",
        "sendBody": True, "contentType": "form-urlencoded",
        "bodyParameters": {"parameters": [{"name": "url", "value": "={{ $('Normalizar Input').first().json.home_url }}"}]},
        "options": {"timeout": 20000, "response": {"response": {
            "fullResponse": True, "neverError": True, "responseFormat": "text", "outputPropertyName": "body"}}}},
        "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "onError": "continueRegularOutput",
        "position": pos, "name": "Validar Schema.org"}

nodes, conns = [], {}
def connect(a, b, idx=0):
    conns.setdefault(a, {"main": [[]]})
    conns[a]["main"][0].append({"node": b, "type": "main", "index": idx})

N = "$('Normalizar Input').first().json"

nodes.append({"parameters": {"httpMethod": "POST", "path": "geopulse-lite2", "responseMode": "responseNode", "options": {}},
    "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [200, 460], "name": "Webhook", "webhookId": "geopulse-lite2"})
nodes.append(code("Normalizar Input", CODE_NORMALIZAR, [380, 460]))
# Cadena tecnica: cada GET va seguido de SU nodo de parseo, para poder inspeccionar
# en n8n exactamente que se ha extraido de cada fuente antes de juzgar nada.
nodes.append(http_get("GET Home", "={{ " + N + ".home_url }}", [560, 300]))
nodes.append(code("Parsear Home", CODE_PARSEAR_HOME, [740, 300]))
nodes.append(http_get("GET robots", "={{ " + N + ".domain }}/robots.txt", [920, 300]))
nodes.append(code("Parsear Robots", CODE_PARSEAR_ROBOTS, [1100, 300]))
nodes.append(http_get("GET sitemap", "={{ " + N + ".domain }}/sitemap.xml", [1280, 300]))
nodes.append(code("Parsear Sitemap", CODE_PARSEAR_SITEMAP, [1460, 300]))
nodes.append(nodo_validador_schema([1640, 300]))
nodes.append(code("Parsear Schema", CODE_PARSEAR_SCHEMA, [1820, 300]))
nodes.append(code("Consolidar Senales", CODE_CONSOLIDAR, [2000, 300]))

nodes.append(code("Sondas", CODE_SONDAS, [2200, 220]))
nodes.append(code("Sonda Huella", CODE_SONDA_HUELLA, [2200, 540]))
nodes.append(nodo_chatgpt("Sonda - ChatGPT", [2420, 80]))
nodes.append(nodo_claude("Sonda - Claude", [2420, 220]))
nodes.append(nodo_gemini("Sonda - Gemini", [2420, 360]))
nodes.append(nodo_perplexity("Sonda - Perplexity", [2420, 500]))
nodes.append(nodo_perplexity("Huella - Perplexity", [2420, 560], ctx="medium"))

# --- Ficha de Google Business (Places API New) ---
# Auth: Header Auth generica con el header 'X-Goog-Api-Key' = tu clave de Google Cloud
# (Places API New habilitada). El X-Goog-FieldMask es OBLIGATORIO (sin el, 400).
nodes.append({"parameters": {"method": "POST", "url": "https://places.googleapis.com/v1/places:searchText",
    "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
    "sendHeaders": True, "headerParameters": {"parameters": [
        {"name": "X-Goog-FieldMask", "value": "places.displayName,places.formattedAddress,places.rating,places.userRatingCount,places.types,places.primaryTypeDisplayName,places.websiteUri,places.googleMapsUri,places.businessStatus,places.regularOpeningHours,places.nationalPhoneNumber"}]},
    "sendBody": True, "specifyBody": "json",
    "jsonBody": "={{ JSON.stringify({ textQuery: (($('Normalizar Input').first().json.brand || '') + ' ' + ($('Normalizar Input').first().json.mercado || '')).trim() }) }}",
    "options": {"timeout": 20000, "response": {"response": {"fullResponse": True, "neverError": True}}}},
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "onError": "continueRegularOutput",
    "position": [2420, 700], "name": "Ficha Google"})
nodes.append(code("Parsear Ficha", CODE_PARSEAR_FICHA, [2640, 700]))

# --- Enlaces rotos (404) en TODO el sitio --- rama paralela; se sincroniza en Merge Sondeos.
nodes.append(code("Paginas a Revisar", CODE_PAGINAS, [1980, 860]))
nodes.append({"parameters": {"url": "={{ $json.url }}", "method": "GET",
    "sendHeaders": True, "headerParameters": {"parameters": [{"name": "User-Agent", "value": UA}]},
    "options": {"timeout": 15000, "response": {"response": {"fullResponse": True, "neverError": True,
        "responseFormat": "text", "outputPropertyName": "body"}}}},
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "onError": "continueRegularOutput",
    "position": [2100, 940], "name": "GET Pagina"})
nodes.append(code("Extraer Enlaces", CODE_EXTRAER_ENLACES, [2200, 860]))
nodes.append({"parameters": {"url": "={{ $json.url }}", "method": "GET",
    "sendHeaders": True, "headerParameters": {"parameters": [{"name": "User-Agent", "value": UA}]},
    "options": {"timeout": 12000, "response": {"response": {"fullResponse": True, "neverError": True,
        "responseFormat": "text", "outputPropertyName": "body"}}}},
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "onError": "continueRegularOutput",
    "position": [2420, 860], "name": "Comprobar Enlace"})
nodes.append(code("Clasificar Enlaces", CODE_CLASIFICAR_ENLACES, [2640, 860]))

nodes.append({"parameters": {"mode": "append", "numberInputs": 7}, "type": "n8n-nodes-base.merge",
    "typeVersion": 3, "position": [2660, 300], "name": "Merge Sondeos"})
nodes.append(code("Recopilar Respuestas", CODE_RECOPILAR, [2840, 300]))
nodes.append(code("Preparar Informe", CODE_PROMPTS, [3020, 300]))
nodes.append({"parameters": {"method": "POST", "url": "https://api.openai.com/v1/chat/completions",
    "authentication": "predefinedCredentialType", "nodeCredentialType": "openAiApi",
    "sendBody": True, "specifyBody": "json",
    "jsonBody": "={{ JSON.stringify({ model: 'gpt-5.4-mini', messages: [{ role: 'system', content: $json.prompt_sistema }, { role: 'user', content: $json.prompt_usuario }] }) }}",
    "options": {"timeout": 120000, "response": {"response": {"fullResponse": True, "neverError": True}}}},
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "onError": "continueRegularOutput",
    "position": [3200, 300], "name": "Informe ChatGPT"})
nodes.append(code("Ensamblar LITE2", CODE_ENSAMBLAR, [3380, 300]))
nodes.append({"parameters": {"respondWith": "firstIncomingItem", "options": {"responseHeaders": {"entries": [
    {"name": "Access-Control-Allow-Origin", "value": "*"}]}}},
    "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1, "position": [3560, 300], "name": "Responder"})

CADENA = ["Webhook", "Normalizar Input",
          "GET Home", "Parsear Home",
          "GET robots", "Parsear Robots",
          "GET sitemap", "Parsear Sitemap",
          "Validar Schema.org", "Parsear Schema",
          "Consolidar Senales"]
for a, b in zip(CADENA, CADENA[1:]):
    connect(a, b)
connect("Consolidar Senales", "Sondas")
connect("Consolidar Senales", "Sonda Huella")
connect("Consolidar Senales", "Ficha Google")
connect("Ficha Google", "Parsear Ficha")
connect("Consolidar Senales", "Paginas a Revisar")
connect("Paginas a Revisar", "GET Pagina")
connect("GET Pagina", "Extraer Enlaces")
connect("Extraer Enlaces", "Comprobar Enlace")
connect("Comprobar Enlace", "Clasificar Enlaces")
connect("Sondas", "Sonda - ChatGPT")
connect("Sondas", "Sonda - Claude")
connect("Sondas", "Sonda - Gemini")
connect("Sondas", "Sonda - Perplexity")
connect("Sonda Huella", "Huella - Perplexity")
connect("Sonda - ChatGPT", "Merge Sondeos", 0)
connect("Sonda - Claude", "Merge Sondeos", 1)
connect("Sonda - Gemini", "Merge Sondeos", 2)
connect("Sonda - Perplexity", "Merge Sondeos", 3)
connect("Huella - Perplexity", "Merge Sondeos", 4)
connect("Parsear Ficha", "Merge Sondeos", 5)
connect("Clasificar Enlaces", "Merge Sondeos", 6)
for a, b in [("Merge Sondeos","Recopilar Respuestas"), ("Recopilar Respuestas","Preparar Informe"),
             ("Preparar Informe","Informe ChatGPT"), ("Informe ChatGPT","Ensamblar LITE2"),
             ("Ensamblar LITE2","Responder")]:
    connect(a, b)

wf = {"name": "GEOpulse LITE v2 - muestra del informe completo", "nodes": nodes,
      "connections": conns, "settings": {"executionOrder": "v1"}}

# El guard permite `import build_lite2` desde build_lite2_panel.py para reutilizar
# 'nodes' y 'conns' sin regenerar este fichero. Ejecutarlo directo se comporta igual.
if __name__ == "__main__":
    # encoding explicito: sin el, en Windows se escribe en cp1252 y los acentos rompen
    # el JSON (deja de ser UTF-8 valido). build_workflow_v10.py ya lo hacia asi.
    with open("geopulse-lite2-workflow.json", "w", encoding="utf-8") as _f:
        json.dump(wf, _f, ensure_ascii=False, indent=2)
    print("OK - nodos:", len(nodes), "| conexiones:", sum(len(c["main"][0]) for c in conns.values()))

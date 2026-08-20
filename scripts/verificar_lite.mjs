// Verifica E1 (coste por run) en el workflow LITE generado, sin lanzar n8n.
// La logica de normalizacion/agregacion es la misma que en el COMPLETO (ya
// probada en verificar_ensamblar.mjs); aqui se comprueba lo especifico de LITE:
// la tarifa de claude-haiku-4-5 y que el gather apunta a los nodos correctos.
//
// Uso:  node scripts/verificar_lite.mjs
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..");
const wf = JSON.parse(
  readFileSync(join(RAIZ, "workflows", "geopulse-lite2-panel-workflow.json"), "utf8"),
);
const nodo = wf.nodes.find((n) => n.name === "Ensamblar LITE2");
if (!nodo) throw new Error("no encuentro el nodo 'Ensamblar LITE2'");
const codigo = nodo.parameters.jsCode;

let fallos = 0;
const linea = (ok, txt) => {
  if (!ok) fallos++;
  console.log(`${ok ? "OK   " : "FALLA"} ${txt}`);
};

// Extrae los helpers testables (de tokensDe al centinela).
const ini = codigo.indexOf("const PRECIOS =");
const fin = codigo.indexOf("// <<<FIN-HELPERS-TESTABLES>>>");
if (ini < 0 || fin < 0) throw new Error("no encuentro el bloque de helpers de coste en LITE");
const { tokensDe, agregarCoste, modeloDe, precioDe } = new Function(
  codigo.slice(ini, fin) + "\nreturn { tokensDe, agregarCoste, modeloDe, precioDe };",
)();

console.log("=== E1 LITE · normalizacion de usage ===");
const j = (o) => JSON.stringify(o);
linea(j(tokensDe({ usage: { prompt_tokens: 100, completion_tokens: 50 } })) === j({ in: 100, out: 50 }), "openai (prompt/completion_tokens)");
linea(j(tokensDe({ usage: { input_tokens: 200, output_tokens: 80 } })) === j({ in: 200, out: 80 }), "anthropic (input/output_tokens)");
linea(j(tokensDe({ usageMetadata: { promptTokenCount: 300, candidatesTokenCount: 90 } })) === j({ in: 300, out: 90 }), "gemini (usageMetadata)");
linea(tokensDe({}) === null, "sin usage -> null");

console.log("\n=== E1 LITE · agregacion con tarifa de haiku ===");
const c = agregarCoste([
  { modelo: "claude-haiku-4-5", tokens: { in: 1_000_000, out: 1_000_000 }, error: false },
  { modelo: "sonar", tokens: { in: 500_000, out: 0 }, error: false },
  { modelo: "sonar", tokens: null, error: true },
]);
// haiku: 1*1.00 + 1*5.00 = 6.00 ; sonar: 0.5*1.00 = 0.50 -> 6.50
linea(c.request_count === 3, `request_count (${c.request_count})`);
linea(c.fallos === 1, `fallos (${c.fallos})`);
linea(c.estimated_cost_usd === 6.5, `coste con precio de haiku (${c.estimated_cost_usd})`);
linea(c.completo === true && c.sin_precio.length === 0, "todos los modelos de LITE tienen precio");

console.log("\n=== E1 LITE · modelo real de la API (el panel usa gemini-3.5-flash) ===");
linea(modeloDe({ model: "gpt-5.6-luna" }, "gpt-5.4-mini") === "gpt-5.6-luna", "openai -> body.model");
linea(modeloDe({ modelVersion: "gemini-3.5-flash" }, "gemini-2.5-flash") === "gemini-3.5-flash", "gemini -> body.modelVersion (el panel lo cambia)");
linea(modeloDe({}, "sonar") === "sonar", "sin modelo -> fallback");
linea(precioDe("gemini-3.5-flash") != null && precioDe("gpt-5.6-luna") != null, "los modelos del tier gratuito (panel) tienen tarifa");
linea(precioDe("gpt-5.6-luna-2026-08") != null, "tarifa por prefijo absorbe el sufijo de version");

console.log("\n=== E1 LITE · el gather apunta a los nodos reales ===");
for (const n of ["Sonda - ChatGPT", "Sonda - Claude", "Sonda - Gemini", "Sonda - Perplexity", "Huella - Perplexity", "Informe ChatGPT"]) {
  const existe = wf.nodes.some((x) => x.name === n);
  const referenciado = codigo.includes("'" + n + "'");
  linea(existe && referenciado, `${n.padEnd(20)} existe y se lee`);
}
linea(codigo.includes("coste,"), "el informe LITE incluye el bloque coste");

console.log("\n=== E3 LITE · estado por modulo ===");
// Extrae estadoModulo del jsCode real (de su definicion al centinela) y lo
// ejerce aislado, como en verificar_ensamblar.mjs. ES_ESTADO se prepende.
const iniE3 = codigo.indexOf("function estadoModulo");
if (iniE3 < 0) throw new Error("no encuentro function estadoModulo en 'Ensamblar LITE2'");
const { estadoModulo } = new Function(
  "const ES_ESTADO = new Set(['ok','warning','error','no_verificable']);\n" +
    codigo.slice(iniE3, fin) +
    "\nreturn { estadoModulo };",
)();
linea(estadoModulo(null) === "failed", "bloque null -> failed");
linea(estadoModulo({}) === "failed", "objeto vacio -> failed");
linea(estadoModulo({ _error: "x" }) === "failed", "bloque con _error -> failed");
linea(
  estadoModulo({ puntos: [{ estado: "no_verificable" }, { estado: "no_verificable" }] }) === "partial",
  "seo con todos los puntos no_verificable -> partial",
);
linea(
  estadoModulo({ puntos: [{ estado: "ok" }, { estado: "no_verificable" }] }) === "completed",
  "seo con algun punto ok -> completed",
);
linea(estadoModulo({ total_validas: 0 }, { dimension: true }) === "partial", "visibilidad sin sondeos validos -> partial");
linea(estadoModulo({ total_validas: 9 }, { dimension: true }) === "completed", "visibilidad con sondeos -> completed");
// El informe se construye con las 4 claves LITE.
for (const clave of ["seo_tecnico", "huella_digital", "visibilidad", "informe"]) {
  linea(codigo.includes(clave + ":"), `estados_modulos incluye '${clave}'`);
}

console.log("\n=== C2 · variantes de marca (filtro anti es_marca) ===");
const iniC2 = codigo.indexOf("function pareceMarca");
if (iniC2 < 0) throw new Error("no encuentro function pareceMarca en 'Ensamblar LITE2'");
const { pareceMarca } = new Function(codigo.slice(iniC2, fin) + "\nreturn { pareceMarca };")();
linea(pareceMarca("brandevs", "brandevs", "BranDevs") === true, "nombre exacto -> es marca");
linea(pareceMarca("brandevz", "brandevs", "BranDevs") === true, "errata cercana (comparte prefijo) -> es marca");
linea(pareceMarca("Brand Devs", "brandevs", "BranDevs") === true, "variante con espacios/mayusculas -> es marca");
linea(pareceMarca("Acme Studio", "brandevs", "BranDevs") === false, "competidor -> descartado (no contamina)");
linea(pareceMarca("BrandevsKiller", "brandevs", "BranDevs") === false, "competidor que CONTIENE el distintivo pero mas largo -> descartado");
linea(pareceMarca("", "brandevs", "BranDevs") === false, "vacio -> descartado");
// El bloque de variantes va DESPUES del mapa y no lo toca: no contamina menciones/SoV.
linea(codigo.indexOf("variantes_marca") > codigo.indexOf("let mapa = ("), "variantes_marca se construye tras el mapa (no lo altera)");
linea(codigo.includes("pareceMarca(v,"), "las observadas se filtran con pareceMarca");
linea(codigo.includes("variantes_marca,"), "el informe LITE incluye el bloque variantes_marca");
// El prompt del agente pide las variantes literales (nodo 'Preparar Informe').
const prep = wf.nodes.find((n) => n.name === "Preparar Informe");
linea(!!prep && prep.parameters.jsCode.includes('"variantes_marca":[]'), "el esquema del agente pide variantes_marca");

console.log("\n=== GROUNDING · sondas LITE con búsqueda web ===");
// Las sondas ChatGPT/Claude/Gemini deben ir grounded (Perplexity ya lo estaba).
const nodo2 = (n) => wf.nodes.find((x) => x.name === n);
const bodyDe = (n) => (nodo2(n)?.parameters?.jsonBody) || "";
linea(bodyDe("Sonda - ChatGPT").includes("web_search") && (nodo2("Sonda - ChatGPT")?.parameters?.url || "").includes("/v1/responses"), "ChatGPT grounded (Responses API + web_search)");
linea(bodyDe("Sonda - Claude").includes("web_search_20250305"), "Claude grounded (web_search_20250305, variante haiku)");
linea(bodyDe("Sonda - Gemini").includes("google_search"), "Gemini grounded (google_search)");
linea(bodyDe("Sonda - Perplexity").includes("web_search_options"), "Perplexity sigue grounded");
// El redactor NO se groundea (escribe con los datos ya recogidos).
linea(!bodyDe("Informe ChatGPT").includes("web_search") && !(nodo2("Informe ChatGPT")?.parameters?.url || "").includes("/v1/responses"), "el redactor 'Informe ChatGPT' NO se groundea");

console.log("\n=== GROUNDING · pick() parsea las 4 formas (incl. Responses API) ===");
const rec = nodo2("Recopilar Respuestas");
const codR = rec ? rec.parameters.jsCode : "";
const iniR = codR.indexOf("const respApi");
const finR = codR.indexOf("const pickCitations");
if (iniR < 0 || finR < 0) throw new Error("no encuentro respApi/pick en 'Recopilar Respuestas'");
const { pick } = new Function(codR.slice(iniR, finR) + "\nreturn { pick };")();
const wrap = (b) => [{ body: b }];
linea(pick(wrap({ choices: [{ message: { content: "chat ok" } }] }), 0) === "chat ok", "openai chat/completions");
linea(pick(wrap({ content: [{ type: "server_tool_use" }, { type: "text", text: "claude ok" }] }), 0) === "claude ok", "anthropic web_search (solo text)");
linea(pick(wrap({ candidates: [{ content: { parts: [{ text: "gemini ok" }] } }] }), 0) === "gemini ok", "gemini grounded (parts)");
linea(pick(wrap({ output: [{ type: "web_search_call" }, { type: "message", content: [{ type: "output_text", text: "openai grounded ok" }] }] }), 0) === "openai grounded ok", "openai RESPONSES API -> output_text");

console.log("\n=== FICHA GOOGLE · nodo Places + matchFicha (anti misatribución) ===");
const fichaNode = nodo2("Ficha Google");
linea(!!fichaNode && (fichaNode.parameters.url || "").includes("places.googleapis.com/v1/places:searchText"), "nodo 'Ficha Google' llama a Places API (New) searchText");
const fmHeader = JSON.stringify(fichaNode?.parameters?.headerParameters || {});
linea(fmHeader.includes("X-Goog-FieldMask") && fmHeader.includes("userRatingCount"), "envía el X-Goog-FieldMask obligatorio (con rating/reseñas)");
const parseFicha = nodo2("Parsear Ficha");
const codF = parseFicha ? parseFicha.parameters.jsCode : "";
const iniF = codF.indexOf("const _nm");
const finF = codF.indexOf("// <<<FIN-FICHA-TESTABLE>>>");
if (iniF < 0 || finF < 0) throw new Error("no encuentro matchFicha en 'Parsear Ficha'");
const { matchFicha } = new Function(codF.slice(iniF, finF) + "\nreturn { matchFicha };")();
const j2 = (o) => JSON.stringify(o);
linea(matchFicha([{ websiteUri: "https://www.brandevs.com", displayName: { text: "BranDevs" } }], "BranDevs", "brandevs.com")?.confianza === "alta", "casa por dominio -> confianza alta");
linea(matchFicha([{ websiteUri: "https://otra.com", displayName: { text: "BranDevs Studio" } }], "BranDevs", "brandevs.com")?.confianza === "media", "solo por nombre -> confianza media");
linea(matchFicha([{ websiteUri: "https://acme.com", displayName: { text: "Acme Corp" } }], "BranDevs", "brandevs.com") === null, "competidor -> null (no se atribuye como tuya)");
linea(matchFicha([], "BranDevs", "brandevs.com") === null, "sin resultados -> null");
// El dominio gana al nombre: si hay una que casa por dominio, esa es (aunque el nombre difiera).
linea(matchFicha([{ websiteUri: "https://x.com", displayName: { text: "BranDevs" } }, { websiteUri: "https://brandevs.com", displayName: { text: "BD" } }], "BranDevs", "brandevs.com")?.confianza === "alta", "prioriza la coincidencia por dominio");
linea(codF.includes("ficha_google"), "el nodo emite el bloque ficha_google");

console.log("\n=== ENLACES 404 · TODO el sitio + clasificación honesta ===");
for (const n of ["Paginas a Revisar", "GET Pagina", "Extraer Enlaces", "Comprobar Enlace", "Clasificar Enlaces"]) {
  linea(!!nodo2(n), `nodo '${n}' existe`);
}
// El descubrimiento de paginas lee el sitemap y la home (no solo la home).
const pag = nodo2("Paginas a Revisar");
linea(!!pag && /GET sitemap/.test(pag.parameters.jsCode) && /GET Home/.test(pag.parameters.jsCode), "descubre páginas del sitemap + home");
linea(!!nodo2("Extraer Enlaces") && /GET Pagina/.test(nodo2("Extraer Enlaces").parameters.jsCode), "extrae enlaces de todas las páginas crawleadas");
const clasNode = nodo2("Clasificar Enlaces");
const codC = clasNode ? clasNode.parameters.jsCode : "";
const iniC = codC.indexOf("function clasificarStatus");
const finC = codC.indexOf("// <<<FIN-ENLACES-TESTABLE>>>");
if (iniC < 0 || finC < 0) throw new Error("no encuentro clasificarStatus en 'Clasificar Enlaces'");
const { clasificarStatus } = new Function(codC.slice(iniC, finC) + "\nreturn { clasificarStatus };")();
linea(clasificarStatus(404) === "roto" && clasificarStatus(410) === "roto", "404/410 -> roto");
linea(clasificarStatus(200) === "ok" && clasificarStatus(301) === "ok", "2xx/3xx -> ok");
linea(clasificarStatus(403) === "no_verificable" && clasificarStatus(429) === "no_verificable", "403/429 (WAF/rate) -> no verificable, NO roto");
linea(clasificarStatus(500) === "no_verificable" && clasificarStatus(0) === "no_verificable", "5xx/timeout -> no verificable, NO roto");
linea(clasificarStatus(401) === "ok", "otros 4xx (401) no se marcan como roto");
linea(codC.includes("enlaces_rotos"), "el nodo emite el bloque enlaces_rotos");

console.log(`\n${fallos ? `${fallos} COMPROBACIONES FALLAN` : "TODO CORRECTO"}`);
process.exit(fallos ? 1 : 0);

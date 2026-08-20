// Ejerce el jsCode REAL del nodo "Ensamblar Reporte" del workflow COMPLETO
// generado, contra el informe real de docs/, para validar E2 (versionado) y
// E3 (estado por modulo) sin lanzar n8n.
//
// Uso:  node scripts/verificar_ensamblar.mjs
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..");
const wf = JSON.parse(
  readFileSync(join(RAIZ, "workflows", "geopulse-audit-panel-workflow.json"), "utf8"),
);
const nodo = wf.nodes.find((n) => n.name === "Ensamblar Reporte");
if (!nodo) throw new Error("no encuentro el nodo 'Ensamblar Reporte'");

const informe = JSON.parse(
  readFileSync(join(RAIZ, "docs", "ejemplo-informe-completo.json"), "utf8"),
);
// El director (sintesis) va como $input; el resto lo lee de $('...').
const director = informe.sintesis ?? { diagnostico_ejecutivo: "x" };

// Mocks de n8n: $('Nodo').first().json y $input.first().json.
// .all() vacio: en este banco no hay nodos de sondeo, asi que el coste sale a
// cero (la logica de coste se prueba aparte, con muestras sinteticas, abajo).
const nodoRef = { first: () => ({ json: informe }), all: () => [] };
const $ = () => nodoRef;
const $input = { first: () => ({ json: director }) };

const salida = new Function("$", "$input", nodo.parameters.jsCode)($, $input);
const out = salida[0].json;

let fallos = 0;
const linea = (ok, txt) => {
  if (!ok) fallos++;
  console.log(`${ok ? "OK   " : "FALLA"} ${txt}`);
};

console.log("=== E2 · versionado en meta ===");
linea(out.meta.analysis_version === "completo-v11", `analysis_version = ${out.meta.analysis_version}`);
linea(out.meta.scoring_version === "score-v1", `scoring_version = ${out.meta.scoring_version}`);
linea(out.meta.prompt_version === "prompt-v2", `prompt_version = ${out.meta.prompt_version}`);
linea(out.meta.brand === informe.meta.brand, "meta original preservada (brand)");

console.log("\n=== E3 · estado por modulo ===");
const em = out.estados_modulos || {};
const VALIDOS = new Set(["completed", "partial", "failed"]);
const modulos = [
  "seo_tecnico", "infraestructura_geo", "contenido_geo", "huella_digital",
  "fuentes_sector", "descubrimiento", "competitivo", "conocimiento",
  "reputacion", "informe_llm", "sintesis",
];
for (const m of modulos) {
  const v = em[m];
  linea(VALIDOS.has(v), `${m.padEnd(20)} ${v}`);
}
// En el informe REAL de BranDevs, todos los modulos corrieron: no deberia haber
// 'failed' (seria senal de que el heuristico marca de mas).
const fallidos = modulos.filter((m) => em[m] === "failed");
linea(fallidos.length === 0, `ningun modulo marcado 'failed' en un informe completo real (${fallidos.join(",") || "ninguno"})`);

console.log("\n=== E3 · casos simulados (modulo caido) ===");
// Se ejercen los helpers aislados: se re-extraen del jsCode (de estadoModulo al
// centinela) para probar sus limites sin montar todo el nodo.
const codigo = nodo.parameters.jsCode;
const iniFn = codigo.indexOf("function estadoModulo");
const finFn = codigo.indexOf("// <<<FIN-HELPERS-TESTABLES>>>");
if (finFn < 0) throw new Error("no encuentro el centinela FIN-HELPERS-TESTABLES");
const bloqueFn =
  "const ES_ESTADO = new Set(['ok','warning','error','no_verificable']);\n" +
  codigo.slice(iniFn, finFn) +
  "\nreturn { estadoModulo, tokensDe, agregarCoste, modeloDe, precioDe };";
const { estadoModulo, tokensDe, agregarCoste, modeloDe, precioDe } = new Function(bloqueFn)();
linea(estadoModulo(null) === "failed", "bloque null -> failed");
linea(estadoModulo({ _error: "x" }) === "failed", "bloque con _error -> failed");
linea(estadoModulo({}) === "failed", "bloque vacio -> failed");
linea(
  estadoModulo({ a: { estado: "no_verificable" }, b: { estado: "no_verificable" } }) === "partial",
  "tecnico con todo no_verificable -> partial",
);
linea(
  estadoModulo({ a: { estado: "ok" }, b: { estado: "no_verificable" } }) === "completed",
  "tecnico con algun ok -> completed",
);
linea(
  estadoModulo({ veredicto: null, por_modelo: {}, detalle_preguntas: [] }, { dimension: true }) === "partial",
  "dimension sin respuesta de ningun modelo -> partial",
);
linea(
  estadoModulo({ por_modelo: { chatgpt: { tasa_aparicion: 25 } } }, { dimension: true }) === "completed",
  "dimension con datos de un modelo -> completed",
);

console.log("\n=== E1 · normalizacion de usage por proveedor ===");
const j = (o) => JSON.stringify(o);
linea(j(tokensDe({ usage: { prompt_tokens: 100, completion_tokens: 50 } })) === j({ in: 100, out: 50 }), "openai/perplexity (prompt/completion_tokens)");
linea(j(tokensDe({ usage: { input_tokens: 200, output_tokens: 80 } })) === j({ in: 200, out: 80 }), "anthropic/responses (input/output_tokens)");
linea(j(tokensDe({ usageMetadata: { promptTokenCount: 300, candidatesTokenCount: 90 } })) === j({ in: 300, out: 90 }), "gemini (usageMetadata)");
linea(tokensDe({}) === null, "sin usage -> null");
linea(tokensDe(null) === null, "body null -> null");

console.log("\n=== E1 · agregacion de coste ===");
const c = agregarCoste([
  { modelo: "gpt-5.4-mini", tokens: { in: 1_000_000, out: 1_000_000 }, error: false },
  { modelo: "claude-sonnet-4-6", tokens: { in: 1_000_000, out: 0 }, error: false },
  { modelo: "modelo-desconocido", tokens: { in: 1_000_000, out: 0 }, error: false },
  { modelo: "sonar", tokens: null, error: true },
]);
linea(c.request_count === 4, `request_count cuenta todas las llamadas (${c.request_count})`);
linea(c.fallos === 1, `fallos cuenta la que no midio (${c.fallos})`);
linea(c.token_usage.input === 3_000_000 && c.token_usage.output === 1_000_000, `tokens suman solo las medidas (in=${c.token_usage.input}, out=${c.token_usage.output})`);
// gpt: 1*0.25 + 1*2.00 = 2.25 ; claude: 1*3.00 = 3.00 ; desconocido: sin precio -> 0
linea(c.estimated_cost_usd === 5.25, `coste estimado de las tarifadas (${c.estimated_cost_usd})`);
linea(c.completo === false && c.sin_precio.length === 1 && c.sin_precio[0] === "modelo-desconocido", "modelo sin precio se marca y baja 'completo'");
linea(c.precios.estimado === true, "las tarifas van marcadas como estimadas");

console.log("\n=== E1 · modelo real de la API (el panel cambia sondas) ===");
linea(modeloDe({ model: "gpt-5.6-luna" }, "gpt-5.4-mini") === "gpt-5.6-luna", "openai/anthropic/perplexity -> body.model");
linea(modeloDe({ modelVersion: "gemini-3.5-flash" }, "gemini-2.5-flash") === "gemini-3.5-flash", "gemini -> body.modelVersion");
linea(modeloDe({ model: "models/gemini-3.5-flash" }, "x") === "gemini-3.5-flash", "quita el prefijo 'models/'");
linea(modeloDe({}, "gpt-5.4-mini") === "gpt-5.4-mini", "sin modelo en la respuesta -> fallback");
// Tarifa por prefijo: un id con sufijo de version se tarifa por su base.
linea(precioDe("gpt-5.6-luna-2026-08") != null, "tarifa por prefijo absorbe el sufijo de version");
linea(precioDe("gemini-3.5-flash") != null && precioDe("gpt-5.6-luna") != null, "los modelos del tier gratuito (panel) tienen tarifa");
const cPanel = agregarCoste([{ modelo: "gpt-5.6-luna-2026-08", tokens: { in: 1_000_000, out: 0 }, error: false }]);
linea(cPanel.completo === true && cPanel.estimated_cost_usd === 0.5, "sonda del panel con sufijo se tarifa (no cae a sin_precio)");

console.log("\n=== E1 · coste en el informe ensamblado ===");
linea(!!out.coste && typeof out.coste.token_usage === "object", "el informe trae bloque coste");
linea(out.meta.tokens_total === out.coste.token_usage.total, "meta.tokens_total cuadra con el bloque coste");
linea(Array.isArray(out.coste.no_medido.agentes) && out.coste.no_medido.agentes.length === 8, "los 8 agentes internos quedan declarados sin medir");

console.log("\n=== B2 · answer-first / intent mismatch (informativo, no toca la nota) ===");
const a3 = wf.nodes.find((n) => n.name === "Agente 3 - Contenido y Entidades");
const promptA3 = a3 ? JSON.stringify(a3.parameters) : "";
linea(promptA3.includes("answer_first") && promptA3.includes("intent_mismatch"), "el Agente 3 pide answer_first e intent_mismatch en su esquema");
// Pesos CONGELADOS: el nodo que calcula la nota NO puede referenciar los campos nuevos.
const score = wf.nodes.find((n) => n.name === "Calcular Score");
const jsScore = score ? score.parameters.jsCode : "";
linea(!jsScore.includes("answer_first") && !jsScore.includes("intent_mismatch"), "'Calcular Score' NO usa los campos nuevos (nota intacta)");
// El informe ensamblado conserva contenido_geo con los campos nuevos (vienen del fixture).
const cg = out.contenido_geo || {};
linea(!!cg.answer_first && !!cg.answer_first.estado, "el informe conserva contenido_geo.answer_first");
linea(!!cg.intent_mismatch && !!cg.intent_mismatch.intencion_keyword, "el informe conserva contenido_geo.intent_mismatch (con intencion_keyword)");

console.log("\n=== GROUNDING · pick() parsea las 4 formas de respuesta (sondas) ===");
// Extrae respApi+pick del nodo real 'D1 - Unir' y las ejerce con respuestas sinteticas
// de cada proveedor. Lo critico es la Responses API grounded de OpenAI (forma nueva).
const unir = wf.nodes.find((n) => n.name === "D1 - Unir");
if (!unir) throw new Error("no encuentro el nodo 'D1 - Unir'");
const codU = unir.parameters.jsCode;
const iniP = codU.indexOf("const respApi");
const finP = codU.indexOf("const pickCitations");
if (iniP < 0 || finP < 0) throw new Error("no encuentro respApi/pick en 'D1 - Unir'");
const { pick } = new Function(codU.slice(iniP, finP) + "\nreturn { pick };")();
const wrap = (b) => [{ body: b }];
linea(pick(wrap({ choices: [{ message: { content: "hola chat" } }] }), 0) === "hola chat", "openai chat/completions");
linea(pick(wrap({ content: [{ type: "server_tool_use" }, { type: "text", text: "resp claude" }] }), 0) === "resp claude", "anthropic con web_search (ignora tool blocks, coge el text)");
linea(pick(wrap({ candidates: [{ content: { parts: [{ text: "resp gemini" }] } }] }), 0) === "resp gemini", "gemini grounded (parts)");
linea(pick(wrap({ output: [{ type: "web_search_call" }, { type: "message", content: [{ type: "output_text", text: "resp openai grounded" }] }] }), 0) === "resp openai grounded", "openai RESPONSES API (web_search) -> output_text");
linea(pick(wrap({ output_text: "atajo output_text" }), 0) === "atajo output_text", "openai responses atajo output_text");
linea(pick([], 0) === "", "respuesta ausente -> cadena vacia (no rompe)");

console.log("\n=== FICHA GOOGLE · nodo Places + matchFicha (anti misatribución) ===");
const fichaNode = wf.nodes.find((n) => n.name === "Ficha Google");
linea(!!fichaNode && (fichaNode.parameters.url || "").includes("places.googleapis.com/v1/places:searchText"), "nodo 'Ficha Google' llama a Places API (New) searchText");
linea(JSON.stringify(fichaNode?.parameters?.headerParameters || {}).includes("X-Goog-FieldMask"), "envía el X-Goog-FieldMask obligatorio");
const parseFicha = wf.nodes.find((n) => n.name === "Parsear Ficha");
const codF = parseFicha ? parseFicha.parameters.jsCode : "";
const iniF = codF.indexOf("const _nm");
const finF = codF.indexOf("// <<<FIN-FICHA-TESTABLE>>>");
if (iniF < 0 || finF < 0) throw new Error("no encuentro matchFicha en 'Parsear Ficha'");
const { matchFicha } = new Function(codF.slice(iniF, finF) + "\nreturn { matchFicha };")();
linea(matchFicha([{ websiteUri: "https://www.brandevs.com", displayName: { text: "BranDevs" } }], "BranDevs", "brandevs.com")?.confianza === "alta", "casa por dominio -> confianza alta");
linea(matchFicha([{ websiteUri: "https://otra.com", displayName: { text: "BranDevs Studio" } }], "BranDevs", "brandevs.com")?.confianza === "media", "solo por nombre -> confianza media");
linea(matchFicha([{ websiteUri: "https://acme.com", displayName: { text: "Acme Corp" } }], "BranDevs", "brandevs.com") === null, "competidor -> null (no se atribuye como tuya)");
// La ficha se sincroniza en Merge Bloques (input 4) antes de consolidar.
const mb = wf.nodes.find((n) => n.name === "Merge Bloques");
linea(mb && Number(mb.parameters.numberInputs) >= 5, "Merge Bloques sincroniza la ficha (>=5 entradas)");
linea(!!out.ficha_google, "el informe ensamblado incluye ficha_google");

console.log("\n=== ENLACES 404 · TODO el sitio + clasificación honesta ===");
for (const n of ["Paginas a Revisar", "GET Pagina", "Extraer Enlaces", "Comprobar Enlace", "Clasificar Enlaces"]) {
  linea(wf.nodes.some((x) => x.name === n), `nodo '${n}' existe`);
}
const pagN = wf.nodes.find((x) => x.name === "Paginas a Revisar");
linea(!!pagN && /GET Sitemap Páginas/.test(pagN.parameters.jsCode) && /GET Home/.test(pagN.parameters.jsCode), "descubre páginas del sitemap + home");
const clasNode = wf.nodes.find((n) => n.name === "Clasificar Enlaces");
const codC = clasNode ? clasNode.parameters.jsCode : "";
const iniC = codC.indexOf("function clasificarStatus");
const finC = codC.indexOf("// <<<FIN-ENLACES-TESTABLE>>>");
if (iniC < 0 || finC < 0) throw new Error("no encuentro clasificarStatus en 'Clasificar Enlaces'");
const { clasificarStatus } = new Function(codC.slice(iniC, finC) + "\nreturn { clasificarStatus };")();
linea(clasificarStatus(404) === "roto" && clasificarStatus(410) === "roto", "404/410 -> roto");
linea(clasificarStatus(200) === "ok" && clasificarStatus(301) === "ok", "2xx/3xx -> ok");
linea(clasificarStatus(403) === "no_verificable" && clasificarStatus(500) === "no_verificable" && clasificarStatus(0) === "no_verificable", "403/5xx/timeout -> no verificable, NO roto");
linea(mb && (mb.parameters.numberInputs === 6 || mb.parameters.numberInputs === "6"), "Merge Bloques tiene 6 entradas (4 evaluadores + ficha + enlaces)");
linea(!!out.enlaces_rotos, "el informe ensamblado incluye enlaces_rotos");

console.log(`\n${fallos ? `${fallos} COMPROBACIONES FALLAN` : "TODO CORRECTO"}`);
process.exit(fallos ? 1 : 0);

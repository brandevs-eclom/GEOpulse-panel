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

console.log(`\n${fallos ? `${fallos} COMPROBACIONES FALLAN` : "TODO CORRECTO"}`);
process.exit(fallos ? 1 : 0);

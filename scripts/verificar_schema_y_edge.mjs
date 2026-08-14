// Ejerce el jsCode REAL del workflow COMPLETO generado, contra los dos casos que
// produjeron informes falsos en la auditoria de BranDevs (2026-08).
//
// QUE PRUEBA, Y POR QUE
//  1. Deteccion de Organization/LocalBusiness. El informe listo como ausentes los
//     siete campos cuando los siete estaban en la home. Aqui se comprueba contra
//     la estructura REAL que sirve la web (@graph de Yoast, @type en array).
//  2. Veredicto de acceso_edge. El informe marcaba "error" porque el WAF bloquea
//     GPTBot y ClaudeBot, que son rastreadores de ENTRENAMIENTO: bloquearlos no
//     cuesta citaciones. Medido a mano contra brandevs.com: GPTBot y ClaudeBot
//     reciben la conexion cortada; OAI-SearchBot, PerplexityBot, ChatGPT-User y
//     Claude-User responden 200.
//
// Uso:  node scripts/verificar_schema_y_edge.mjs
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..");
const wf = JSON.parse(
  readFileSync(join(RAIZ, "workflows", "geopulse-audit-panel-workflow.json"), "utf8"),
);
const nodo = (n) => {
  const x = wf.nodes.find((y) => y.name === n);
  if (!x) throw new Error(`no encuentro el nodo ${n}`);
  return x.parameters.jsCode;
};

let fallos = 0;
const linea = (ok, txt) => {
  if (!ok) fallos++;
  console.log(`${ok ? "OK   " : "FALLA"} ${txt}`);
};

// --- 1. Helpers de schema, extraidos del nodo tal cual viajan ---
const jsConsolidar = nodo("Consolidar Señales Web");
const corte = jsConsolidar.indexOf("// Consolida todas las");
if (corte < 1) throw new Error("no encuentro el limite del bloque de helpers de schema");
const { analizarOrg, aplanarLd } = new Function(
  jsConsolidar.slice(0, corte) + "\nreturn { analizarOrg, aplanarLd };",
)();

/** Extrae los bloques ld+json de un HTML igual que hace el workflow. */
function nodosDe(html) {
  const re = /<script[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
  let m;
  let nodos = [];
  while ((m = re.exec(html)) !== null) {
    try {
      nodos = aplanarLd(JSON.parse(m[1].trim()), nodos, 0);
    } catch {
      /* bloque malformado: el workflow lo cuenta aparte */
    }
  }
  return nodos;
}

// Estructura REAL de la home de brandevs.com: @graph estilo Yoast, con el
// Organization declarado como @type array junto a ProfessionalService.
const HOME = `<html><head>
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[
 {"@type":"Place","address":{"@type":"PostalAddress","addressLocality":"Cercedilla"},"geo":{},"hasMap":"x"},
 {"@type":["ProfessionalService","Organization"],"name":"BranDevs","url":"https://www.brandevs.com/",
  "logo":{"@type":"ImageObject","url":"https://www.brandevs.com/logo.png"},
  "description":"Agencia de diseno web","sameAs":["https://www.linkedin.com/company/brandevs"],
  "address":{"@type":"PostalAddress","streetAddress":"Calle X"},"telephone":"+34600000000",
  "email":"hola@brandevs.com","priceRange":"$$","aggregateRating":{"@type":"AggregateRating"}},
 {"@type":"WebSite","name":"BranDevs","url":"https://www.brandevs.com/"},
 {"@type":"WebPage","name":"Inicio"}]}</script>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[]}</script>
</head><body></body></html>`;

// Estructura REAL de /diseno-tiendas-online: sin Organization por ningun lado.
const LANDING = `<html><head>
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[
 {"@type":"BreadcrumbList","itemListElement":[]},
 {"@type":"Service","name":"Diseno de tiendas online"}]}</script>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[]}</script>
</head><body></body></html>`;

console.log("=== schema: la home de BranDevs (el caso que fallaba) ===");
{
  const org = analizarOrg(nodosDe(HOME));
  linea(org.encontrado, `encuentra la organizacion: tipo=${org.tipo}`);
  linea(
    org.ausentes.length === 0,
    `campos ausentes: ${org.ausentes.length ? org.ausentes.join(", ") : "ninguno"} ` +
      `(presentes: ${org.presentes.join(", ")})`,
  );
  linea(
    org.tipo === "ProfessionalService+Organization",
    "reconoce @type en ARRAY (antes un check === 'Organization' fallaba)",
  );
}

console.log("\n=== schema: la landing que se analizo por error ===");
{
  const org = analizarOrg(nodosDe(LANDING));
  linea(!org.encontrado, "no encuentra organizacion (correcto: no la tiene)");
  linea(
    org.ausentes.length === 7,
    `los 7 campos salen como ausentes, que aqui SI es verdad`,
  );
}

console.log("\n=== schema: casos que antes se escapaban ===");
{
  const anidado = `<script type="application/ld+json">{"@context":"https://schema.org","@type":"WebPage",
   "publisher":{"@type":"Organization","name":"X","url":"https://x.com","logo":"l","description":"d",
   "sameAs":["s"],"address":"a","telephone":"t"}}</script>`;
  linea(analizarOrg(nodosDe(anidado)).encontrado, "Organization anidado dentro de publisher");

  const arrayRaiz = `<script type="application/ld+json">[{"@type":"LocalBusiness","name":"Y"}]</script>`;
  const o2 = analizarOrg(nodosDe(arrayRaiz));
  linea(o2.encontrado && o2.presentes.join() === "name", "array en la raiz, solo name presente");

  const vacios = `<script type="application/ld+json">{"@type":"Organization","name":"Z","sameAs":[],"logo":""}</script>`;
  const o3 = analizarOrg(nodosDe(vacios));
  linea(
    o3.ausentes.includes("sameAs") && o3.ausentes.includes("logo"),
    "sameAs:[] y logo:'' cuentan como AUSENTES, no como presentes",
  );

  const soloService = `<script type="application/ld+json">{"@type":"Service","name":"S"}</script>`;
  linea(!analizarOrg(nodosDe(soloService)).encontrado, "'Service' a secas NO cuenta como organizacion");
}

// --- 2. Veredicto de acceso edge ---
const jsEdge = nodo("Analizar Acceso Edge");
const BOTS = [
  { ua_name: "GPTBot", categoria: "training" },
  { ua_name: "ClaudeBot", categoria: "training" },
  { ua_name: "OAI-SearchBot", categoria: "retrieval" },
  { ua_name: "PerplexityBot", categoria: "retrieval" },
  { ua_name: "ChatGPT-User", categoria: "user_fetch" },
  { ua_name: "Claude-User", categoria: "user_fetch" },
];

function edge(baselineStatus, statuses) {
  const ctx = (n) => {
    if (n === "GET Home") {
      return { first: () => ({ json: { statusCode: baselineStatus, body: "x".repeat(1000) } }) };
    }
    if (n === "Preparar Fetch Bots") return { all: () => BOTS.map((json) => ({ json })) };
    throw new Error("nodo inesperado: " + n);
  };
  const input = {
    all: () =>
      statuses.map((s) => ({
        json: { statusCode: s, body: s === 200 ? "x".repeat(1000) : "" },
      })),
  };
  return new Function("$", "$input", jsEdge)(ctx, input)[0].json;
}

console.log("\n=== acceso edge: lo medido de verdad en brandevs.com ===");
{
  // GPTBot y ClaudeBot: conexion cortada (status null). El resto, 200.
  const r = edge(200, [null, null, 200, 200, 200, 200]);
  linea(r.veredicto === "ok", `veredicto=${r.veredicto} (antes era "error")`);
  linea(
    r.bloqueados_por_categoria.training.join() === "GPTBot,ClaudeBot",
    `bloqueados de training: ${r.bloqueados_por_categoria.training.join(", ")}`,
  );
  linea(
    r.bloqueados_por_categoria.retrieval.length === 0 &&
      r.bloqueados_por_categoria.user_fetch.length === 0,
    "ninguno de retrieval ni user_fetch bloqueado",
  );
  linea(/NO cuesta\s+citaciones/.test(r.motivo), "el motivo explica que no cuesta citaciones");
}

console.log("\n=== acceso edge: los casos que SI deben doler ===");
{
  const r = edge(200, [null, null, null, 200, 200, 200]);
  linea(r.veredicto === "error", `retrieval bloqueado -> veredicto=${r.veredicto}`);
  linea(r.bloqueados_por_categoria.retrieval.includes("OAI-SearchBot"), "  lo nombra");
}
{
  const r = edge(200, [200, 200, 200, 200, 403, 200]);
  linea(r.veredicto === "error", `user_fetch bloqueado -> veredicto=${r.veredicto}`);
}
{
  const r = edge(200, [200, 200, 200, 200, 200, 200]);
  linea(r.veredicto === "ok", "nadie bloqueado -> ok");
  linea(r.bloqueados_por_categoria.training.length === 0, "  y sin bloqueados de training");
}

console.log("\n=== acceso edge: baseline roto (WAF filtrando por IP) ===");
{
  // Es lo que pasa desde una IP de datacenter: el UA de navegador recibe 403
  // mientras los bots declarados pasan. Sin baseline no se puede concluir nada.
  const r = edge(403, [null, null, 200, 200, 200, 200]);
  linea(r.veredicto === "no_verificable", `veredicto=${r.veredicto}`);
  linea(r.baseline_valido === false, "baseline_valido=false");
  linea(
    r.resultados.every((x) => x.bloqueado_edge === null),
    "bloqueado_edge=null en todos (ausencia de dato, no ausencia de bloqueo)",
  );
}

console.log("\n=== acceso edge: 429 no es 'te bloquean los bots de IA' ===");
{
  const r = edge(200, [429, 200, 200, 200, 200, 200]);
  linea(r.resultados[0].posible_rate_limit === true, "el 429 se marca como posible rate limit");
}

console.log(`\n${fallos ? `${fallos} COMPROBACIONES FALLAN` : "TODO CORRECTO"}`);
process.exit(fallos ? 1 : 0);

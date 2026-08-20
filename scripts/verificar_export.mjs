// Verifica los helpers de export (G12) contra los fixtures reales de docs/, sin
// navegador. Importa el modulo TS real (Node 24 corre .ts nativo); export.ts no
// tiene imports de runtime, asi que carga sin el resolutor de alias de Next.
//
// Uso:  node scripts/verificar_export.mjs
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { filasCsv, informeAFilaCsv, informeAJson, nombreFichero } from "../src/lib/report/export.ts";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..");
const lite = JSON.parse(readFileSync(join(RAIZ, "docs", "ejemplo-informe-lite.json"), "utf8"));
const completo = JSON.parse(readFileSync(join(RAIZ, "docs", "ejemplo-informe-completo.json"), "utf8"));

let fallos = 0;
const linea = (ok, txt) => {
  if (!ok) fallos++;
  console.log(`${ok ? "OK   " : "FALLA"} ${txt}`);
};
const col = (filas, k) => (filas.find(([c]) => c === k) || [])[1];

// Envuelve un informe en un RunDetail minimo con escalares de fila conocidos.
const run = (informe, extra) => ({
  id: "11111111-2222-3333-4444-555555555555",
  tipo: extra.tipo, estado: "completado",
  createdAt: "2026-08-19T10:00:00.000Z", finishedAt: "2026-08-19T10:02:00.000Z",
  duracionMs: 120000, brand: extra.brand, domain: "brandevs.com", keyword: "agencia",
  pais: "ES", region: null, nota: extra.nota, veredicto: extra.veredicto, sov: extra.sov,
  sondeos: 12, tieneAvisos: false, errorMensaje: null, lanzadoPor: null, lanzadoPorEmail: null,
  updatedAt: "", startedAt: null, httpStatus: 200, payload: {}, rawBody: null,
  informe,
});

console.log("=== G12 · JSON sin perdida ===");
const rL = run(lite, { tipo: "lite", brand: "BranDevs", nota: 48, veredicto: "parcial", sov: 33 });
linea(JSON.stringify(JSON.parse(informeAJson(rL))) === JSON.stringify(lite), "informeAJson round-trip (LITE)");
const rC = run(completo, { tipo: "completo", brand: "BranDevs", nota: 48, veredicto: "emergente", sov: 40 });
linea(JSON.stringify(JSON.parse(informeAJson(rC))) === JSON.stringify(completo), "informeAJson round-trip (COMPLETO)");

console.log("\n=== G12 · CSV tolerante LITE vs COMPLETO ===");
const fL = filasCsv(rL);
const fC = filasCsv(rC);
linea(fL.length === fC.length && fL.length > 20, `misma rejilla de columnas en ambos (${fL.length})`);
// Escalares de fila (canonicos de la API).
linea(col(fL, "nota") === "48", "LITE nota desde run.nota");
linea(col(fL, "veredicto") === "parcial", "LITE veredicto desde run.veredicto");
// por_area: LITE en por_area.*, COMPLETO en score.por_area.*
linea(col(fL, "area_seo_tecnico") === String(lite.por_area.seo_tecnico), "LITE area_seo desde por_area");
linea(col(fC, "area_seo_tecnico") === String(completo.score.por_area.seo_tecnico), "COMPLETO area_seo desde score.por_area");
// tasa por modelo: LITE array, COMPLETO objeto
const tasaLiteChat = (lite.aparicion?.por_modelo || []).find((m) => m.clave === "chatgpt")?.tasa;
linea(col(fL, "tasa_chatgpt") === (tasaLiteChat == null ? "" : String(tasaLiteChat)), "LITE tasa_chatgpt desde aparicion.por_modelo[]");
const tasaCompChat = completo.sondeo_llm?.descubrimiento?.por_modelo?.chatgpt?.tasa_aparicion;
linea(col(fC, "tasa_chatgpt") === (tasaCompChat == null ? "" : String(tasaCompChat)), "COMPLETO tasa_chatgpt desde sondeo_llm.descubrimiento");
// versionado y coste (E2/E1) presentes desde meta
linea(col(fC, "analysis_version") === (completo.meta?.analysis_version ?? ""), "COMPLETO analysis_version desde meta");
linea(col(fC, "coste_usd") === (completo.meta?.estimated_cost_usd == null ? "" : String(completo.meta.estimated_cost_usd)), "COMPLETO coste_usd desde meta");

console.log("\n=== G12 · honestidad: null/ausente -> celda VACIA, nunca 0 ===");
const rNull = run(
  { por_area: { seo_tecnico: null, contenido: null, sov: null, huella: null }, aparicion: { por_modelo: [] }, meta: {} },
  { tipo: "lite", brand: "X", nota: null, veredicto: null, sov: null },
);
const fN = filasCsv(rNull);
linea(col(fN, "nota") === "", "nota null -> celda vacia (no 0)");
linea(col(fN, "area_seo_tecnico") === "", "area null -> celda vacia (no 0)");
linea(col(fN, "tasa_chatgpt") === "", "tasa ausente -> celda vacia (no 0)");
linea(col(fN, "coste_usd") === "", "coste ausente -> celda vacia (no 0)");
linea(!fN.some(([, v]) => v === "0"), "ninguna celda es un 0 fabricado");

console.log("\n=== G12 · CSV escapado y nombre de fichero ===");
const rComa = run({ meta: {} }, { tipo: "lite", brand: 'Ac"me, Inc', nota: 1, veredicto: 'a"b', sov: 1 });
const csv = informeAFilaCsv(rComa);
linea(csv.startsWith("\uFEFF"), "la CSV empieza por BOM (Excel UTF-8)");
linea(csv.includes('"Ac""me, Inc"'), "escapa comillas y comas dentro de un valor");
const filasCsvTxt = csv.replace(/^\uFEFF/, "").trim().split("\r\n");
linea(filasCsvTxt.length === 2, "la CSV tiene cabecera + 1 fila de datos");
linea(nombreFichero(rL, "csv") === "geopulse-brandevs-11111111-2222-3333-4444-555555555555.csv", "nombreFichero: slug seguro y estable");

console.log(`\n${fallos ? `${fallos} COMPROBACIONES FALLAN` : "TODO CORRECTO"}`);
process.exit(fallos ? 1 : 0);

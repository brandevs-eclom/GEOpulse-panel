// Ejerce el jsCode REAL de 'Resolver Operacion' extraido del workflow generado.
//
// Que comprueba, y por que importa:
//   1. Que cada operacion devuelve tantos parametros como placeholders $N tiene
//      su SQL. Un desajuste aqui no lo detecta ni el validador ni TypeScript:
//      revienta en produccion con un error del driver de Postgres.
//   2. Que las validaciones rechazan lo que deben (uuid malo, rol invalido...).
//   3. Que 'migrate' sigue partiendo el DDL en una sentencia por item.
//
// Uso:  node scripts/verificar_panel_db.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const AQUI = dirname(fileURLToPath(import.meta.url));
const RUTA = join(AQUI, "..", "workflows", "panel-db-workflow.json");

const wf = JSON.parse(readFileSync(RUTA, "utf8"));
const nodo = wf.nodes.find((n) => n.name === "Resolver Operacion");
if (!nodo) throw new Error("No encuentro el nodo 'Resolver Operacion'");

/** Ejecuta el jsCode tal cual viaja en el workflow, con el $json que le pasemos. */
function resolver(entrada) {
  const fn = new Function("$json", nodo.parameters.jsCode);
  return fn(entrada);
}

/** Mayor $N que aparece en el SQL: cuantos parametros espera de verdad. */
function placeholders(sql) {
  const nums = [...sql.matchAll(/\$(\d+)/g)].map((m) => Number(m[1]));
  return nums.length ? Math.max(...nums) : 0;
}

const UUID = "3f2504e0-4f89-11d3-9a0c-0305e82c3301";
const OTRO_UUID = "7c9e6679-7425-40de-944b-e07fc1f90ae7";

// Un caso por operacion. `params` son los que enviaria el panel.
const CASOS = [
  ["ping", {}],
  ["check", {}],
  ["whoami", {}],
  ["count_active", {}],
  ["create_run", { tipo: "lite", brand: "BranDevs", domain: "brandevs.com", keyword: "agencia" }],
  ["create_run (con dueno)", {}, "create_run", {
    tipo: "completo", brand: "BranDevs", domain: "brandevs.com", keyword: "agencia",
    pais: "es", region: "Murcia", payload: { a: 1 }, lanzado_por: UUID,
  }],
  ["list_runs (admin)", {}, "list_runs", {}],
  ["list_runs (miembro)", {}, "list_runs", { limit: 10, offset: 20, solo_de: UUID }],
  ["get_run (admin)", {}, "get_run", { id: UUID }],
  ["get_run (miembro)", {}, "get_run", { id: UUID, solo_de: OTRO_UUID }],
  ["delete_run", {}, "delete_run", { id: UUID, solo_de: UUID }],
  ["fail_run", {}, "fail_run", { id: UUID, mensaje: "boom" }],
  ["count_users", {}],
  ["count_admins", {}],
  ["get_user_by_email", { email: "  Ana@BranDevs.com " }],
  ["get_user", { id: UUID }],
  ["list_users", {}],
  ["create_user", { email: "ANA@x.com", password_hash: "scrypt$...", rol: "MIEMBRO", nombre: " Ana " }],
  ["update_user_rol", { id: UUID, rol: "admin" }],
  ["update_user_password", { id: UUID, password_hash: "scrypt$..." }],
  ["delete_user", { id: UUID }],
];

let fallos = 0;
const linea = (ok, txt) => {
  if (!ok) fallos++;
  console.log(`${ok ? "OK   " : "FALLA"} ${txt}`);
};

console.log("=== parametros vs placeholders ===");
for (const caso of CASOS) {
  const etiqueta = caso[0];
  const op = caso.length > 2 ? caso[2] : caso[0];
  const params = caso.length > 2 ? caso[3] : caso[1];
  let items;
  try {
    items = resolver({ body: { op, params } });
  } catch (e) {
    linea(false, `${etiqueta.padEnd(26)} lanza: ${e.message}`);
    continue;
  }
  const { sql, params: vals } = items[0].json;
  const esperados = placeholders(sql);
  const ok = vals.length === esperados;
  linea(ok, `${etiqueta.padEnd(26)} $N=${esperados} params=${vals.length}`);
  if (!ok) console.log(`        sql: ${sql.slice(0, 160)}`);
}

console.log("\n=== normalizacion ===");
{
  const p = resolver({ body: { op: "get_user_by_email", params: { email: "  Ana@BranDevs.com " } } })[0].json.params;
  linea(p[0] === "ana@brandevs.com", `email se normaliza a minusculas -> ${JSON.stringify(p[0])}`);
}
{
  const p = resolver({ body: { op: "create_user", params: { email: "ANA@x.com", password_hash: "h", rol: "MIEMBRO" } } })[0].json.params;
  linea(p[0] === "ana@x.com", `create_user normaliza email -> ${JSON.stringify(p[0])}`);
  linea(p[3] === "miembro", `create_user normaliza rol -> ${JSON.stringify(p[3])}`);
  linea(p[2] === null, `nombre vacio se guarda como null -> ${JSON.stringify(p[2])}`);
}
{
  const p = resolver({ body: { op: "list_runs", params: {} } })[0].json.params;
  linea(p[2] === null, `list_runs sin solo_de -> filtro null (admin lo ve todo)`);
}
{
  const p = resolver({ body: { op: "create_run", params: { tipo: "lite", brand: "b", domain: "d", keyword: "k" } } })[0].json.params;
  linea(p[7] === null, `create_run sin sesion -> lanzado_por null (reintento por curl)`);
}

console.log("\n=== lo que tiene que fallar ===");
const debeFallar = [
  ["op inexistente", { op: "drop_everything", params: {} }],
  ["get_run sin id", { op: "get_run", params: {} }],
  ["get_run con id no uuid", { op: "get_run", params: { id: "1 or 1=1" } }],
  ["solo_de no uuid", { op: "list_runs", params: { solo_de: "'; delete from runs --" } }],
  ["rol invalido", { op: "create_user", params: { email: "a@b.c", password_hash: "h", rol: "root" } }],
  ["create_run tipo invalido", { op: "create_run", params: { tipo: "gratis", brand: "b", domain: "d", keyword: "k" } }],
  ["create_user sin hash", { op: "create_user", params: { email: "a@b.c", rol: "admin" } }],
];
for (const [etiqueta, body] of debeFallar) {
  let lanzo = false;
  let mensaje = "";
  try {
    resolver({ body });
  } catch (e) {
    lanzo = true;
    mensaje = e.message;
  }
  linea(lanzo, `${etiqueta.padEnd(26)} ${lanzo ? `rechazado: ${mensaje.slice(0, 70)}` : "NO fallo (deberia)"}`);
}

console.log("\n=== cerrojo del ultimo admin (va en el SQL, no solo en el panel) ===");
{
  const sqlRol = resolver({ body: { op: "update_user_rol", params: { id: UUID, rol: "miembro" } } })[0].json.sql;
  const sqlDel = resolver({ body: { op: "delete_user", params: { id: UUID } } })[0].json.sql;
  const otroAdmin = /exists\s*\(\s*select 1 from users a where a\.rol = 'admin' and a\.id <> \$1\s*\)/i;
  linea(otroAdmin.test(sqlRol), "update_user_rol exige que quede OTRO admin");
  linea(/\$2 = 'admin' or/i.test(sqlRol), "  ...salvo cuando se ASCIENDE a admin");
  linea(otroAdmin.test(sqlDel), "delete_user exige que quede OTRO admin");
  linea(/rol <> 'admin' or/i.test(sqlDel), "  ...salvo si la cuenta no era admin");
}

console.log("\n=== migrate ===");
{
  const items = resolver({ body: { op: "migrate", params: {} } });
  const multi = items.filter((i) => /;\s*\S/.test(i.json.sql.replace(/--[^\n]*/g, "")));
  linea(items.length > 1, `se parte en ${items.length} sentencias, una por item`);
  linea(multi.length === 0, `ningun item lleva mas de una sentencia`);
  linea(
    items.every((i) => Array.isArray(i.json.params) && i.json.params.length === 0),
    `todos los items van con params []`,
  );
  linea(
    items.some((i) => /create table.*"users"/is.test(i.json.sql)),
    `la migracion incluye la tabla users`,
  );
}

console.log(`\n${fallos ? `${fallos} COMPROBACIONES FALLAN` : "TODO CORRECTO"}`);
process.exit(fallos ? 1 : 0);

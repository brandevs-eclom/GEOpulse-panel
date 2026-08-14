// Pone una contrasena nueva a una cuenta del panel, desde la terminal.
//
// POR QUE EXISTE
// El panel no envia correo, asi que no hay "he olvidado mi contrasena". Si la
// pierde un miembro, se la resetea un admin desde /usuarios. Pero si la pierde
// el UNICO admin, no habria forma de entrar: esta es la salida de emergencia.
//
// Habla directamente con el webhook `panel-db` usando N8N_PANEL_DB_SECRET, es
// decir, se ejecuta desde donde tengas el .env.local. No concede nada nuevo:
// quien tiene ese secreto ya puede escribir en la base de datos.
//
// La contrasena NUNCA se pasa como argumento (quedaria en el historial del shell
// y en la lista de procesos): o se teclea sin eco, o se genera.
//
// Uso:
//   node scripts/reset_password.mjs --email tu@brandevs.com            (la pide)
//   node scripts/reset_password.mjs --email tu@brandevs.com --generar  (la genera)
import { readFileSync } from "node:fs";
import { randomBytes, scrypt, timingSafeEqual } from "node:crypto";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { createInterface } from "node:readline";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..");

// ---------------------------------------------------------------------------
// Criptografia. DEBE coincidir con src/server/auth/password.ts, o el panel no
// reconocera el hash. `scripts/verificar_auth.mjs` comprueba precisamente eso:
// genera un hash con esta funcion y lo verifica con la del panel. Si tocas los
// parametros de un lado y no del otro, ese check falla.
// ---------------------------------------------------------------------------
const N = 32768;
const R = 8;
const P = 1;
const KEYLEN = 32;
const MAXMEM = 128 * 1024 * 1024;
const scryptAsync = promisify(scrypt);

export async function hashPassword(password) {
  const salt = randomBytes(16);
  const hash = await scryptAsync(password.normalize("NFKC"), salt, KEYLEN, {
    N,
    r: R,
    p: P,
    maxmem: MAXMEM,
  });
  return ["scrypt", N, R, P, salt.toString("base64"), hash.toString("base64")].join("$");
}

/** Mismo alfabeto sin caracteres ambiguos que el panel: estas se dictan a mano. */
export function generarPassword(longitud = 18) {
  const abc = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const limite = Math.floor(256 / abc.length) * abc.length;
  let out = "";
  while (out.length < longitud) {
    for (const b of randomBytes(longitud * 2)) {
      if (b >= limite) continue;
      out += abc[b % abc.length];
      if (out.length === longitud) break;
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Entorno y transporte
// ---------------------------------------------------------------------------
function leerEnv() {
  let texto;
  try {
    texto = readFileSync(join(RAIZ, ".env.local"), "utf8");
  } catch {
    salir("No encuentro .env.local. Ejecuta esto desde la raíz del proyecto.");
  }
  const val = (clave) => {
    const m = new RegExp(`^${clave}=(.*)$`, "m").exec(texto);
    return m ? m[1].trim() : "";
  };
  const base = val("N8N_BASE_URL");
  const secreto = val("N8N_PANEL_DB_SECRET");
  const path = val("N8N_PANEL_DB_PATH") || "panel-db";
  if (!base) salir("Falta N8N_BASE_URL en .env.local");
  if (!secreto) salir("Falta N8N_PANEL_DB_SECRET en .env.local");
  return { url: `${base.replace(/\/+$/, "")}/webhook/${path}`, secreto };
}

async function panelDb({ url, secreto }, op, params = {}) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-panel-secret": secreto },
    body: JSON.stringify({ op, params }),
  });
  const texto = await res.text();
  if (!res.ok) salir(`n8n devolvió HTTP ${res.status}: ${texto.slice(0, 300)}`);
  if (!texto.trim()) {
    salir(
      `n8n respondió sin cuerpo a "${op}". Lo más probable: el workflow panel-db ` +
        `importado no conoce esa operación. Reimporta workflows/panel-db-workflow.json.`,
    );
  }
  let datos;
  try {
    datos = JSON.parse(texto);
  } catch {
    salir(`Respuesta de n8n que no es JSON: ${texto.slice(0, 300)}`);
  }
  const cuerpo = Array.isArray(datos) ? datos[0] : datos;
  if (!cuerpo || cuerpo.ok !== true) salir(`Respuesta inesperada: ${texto.slice(0, 300)}`);
  return cuerpo.rows ?? [];
}

function salir(mensaje) {
  console.error(`\n  ${mensaje}\n`);
  process.exit(1);
}

/** Pide la contraseña sin que se vea al teclearla. */
function preguntarOculto(prompt) {
  return new Promise((resolve) => {
    const rl = createInterface({ input: process.stdin, output: process.stdout, terminal: true });
    // Se silencia el eco interceptando la escritura del propio readline.
    const salidaReal = rl.output;
    let silenciar = false;
    rl.output = {
      write: (s) => {
        if (!silenciar) salidaReal.write(s);
      },
    };
    salidaReal.write(prompt);
    silenciar = true;
    rl.question("", (respuesta) => {
      silenciar = false;
      salidaReal.write("\n");
      rl.close();
      resolve(respuesta);
    });
  });
}

// ---------------------------------------------------------------------------
async function main() {
  const args = process.argv.slice(2);
  const arg = (nombre) => {
    const i = args.indexOf(`--${nombre}`);
    return i >= 0 ? args[i + 1] : undefined;
  };
  const email = arg("email");
  const generar = args.includes("--generar");

  if (!email) {
    salir(
      "Uso: node scripts/reset_password.mjs --email tu@brandevs.com [--generar]\n" +
        "  Sin --generar, la contraseña se teclea (no se ve y no queda en el historial).",
    );
  }

  const cfg = leerEnv();

  const filas = await panelDb(cfg, "get_user_by_email", { email });
  if (filas.length === 0) {
    salir(`No hay ninguna cuenta con el email ${email}. Míralas con la op list_users.`);
  }
  const usuario = filas[0];

  let password;
  if (generar) {
    password = generarPassword();
  } else {
    password = await preguntarOculto(`Contraseña nueva para ${usuario.email}: `);
    const repetida = await preguntarOculto("Repítela: ");
    if (password !== repetida) salir("No coinciden.");
    if (password.length < 12) salir("Mínimo 12 caracteres (la regla del panel).");
  }

  const hash = await hashPassword(password);
  const actualizadas = await panelDb(cfg, "update_user_password", {
    id: usuario.id,
    password_hash: hash,
  });
  if (actualizadas.length === 0) salir("La actualización no tocó ninguna fila.");

  // Comprobación de verdad: se relee el hash guardado y se verifica contra la
  // contraseña. Sin esto, el script diría "hecho" aunque el hash no sirviera.
  const [releida] = await panelDb(cfg, "get_user_by_email", { email });
  const ok = await verificar(password, String(releida?.password_hash ?? ""));

  console.log(`\n  Cuenta:     ${usuario.email}  (rol ${usuario.rol})`);
  if (generar) console.log(`  Contraseña: ${password}`);
  console.log(`  Guardada y verificada contra la base de datos: ${ok ? "sí" : "NO"}`);
  if (!ok) salir("El hash guardado no valida la contraseña. NO entres a producción con esto.");
  console.log(
    "\n  Aviso: la sesión que esa persona ya tuviera abierta sigue activa hasta\n" +
      "  que caduque (máx. 12 h). Para cerrarla en el acto, rota AUTH_SECRET.\n",
  );
}

async function verificar(password, almacenado) {
  const partes = almacenado.split("$");
  if (partes.length !== 6 || partes[0] !== "scrypt") return false;
  const salt = Buffer.from(partes[4], "base64");
  const esperado = Buffer.from(partes[5], "base64");
  const calc = await scryptAsync(password.normalize("NFKC"), salt, esperado.length, {
    N: Number(partes[1]),
    r: Number(partes[2]),
    p: Number(partes[3]),
    maxmem: MAXMEM,
  });
  return calc.length === esperado.length && timingSafeEqual(calc, esperado);
}

// Solo corre si se invoca directamente: verificar_auth.mjs lo importa para
// comprobar que su hash sigue siendo compatible con el del panel.
if (process.argv[1] && import.meta.url === new URL(`file://${process.argv[1].replace(/\\/g, "/")}`).href) {
  await main();
}

// Comprueba las dos piezas de criptografia del panel SIN levantar el servidor y
// SIN tocar n8n: el hash de contrasena (scrypt) y la firma de la cookie (jose).
//
// Se compilan los .ts a mano con el compilador de TypeScript ya instalado para no
// depender de un runner de tests, que este proyecto no tiene.
//
// Uso:  node scripts/verificar_auth.mjs
import { execFileSync } from "node:child_process";
import {
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { join, dirname, relative } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..");
// Dentro del proyecto a propósito, no en el temp del sistema: así Node encuentra
// `jose` subiendo a node_modules desde el fichero compilado.
const salida = join(RAIZ, "node_modules", ".cache", "gp-verificar-auth");
const configTmp = join(RAIZ, "tsconfig.verificar-auth.json");
rmSync(salida, { recursive: true, force: true });
mkdirSync(salida, { recursive: true });

let fallos = 0;
const linea = (ok, txt) => {
  if (!ok) fallos++;
  console.log(`${ok ? "OK   " : "FALLA"} ${txt}`);
};

/** Todos los .js emitidos, en profundidad. */
function jsEmitidos(dir) {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    return statSync(p).isDirectory() ? jsEmitidos(p) : p.endsWith(".js") ? [p] : [];
  });
}

try {
  // Se hereda el tsconfig del proyecto (por el alias '@/*') y solo se cambia la
  // salida. Compilar los .ts sueltos no vale: tsc no resuelve el alias sin él.
  writeFileSync(
    configTmp,
    JSON.stringify({
      extends: "./tsconfig.json",
      compilerOptions: {
        noEmit: false,
        declaration: false,
        module: "es2022",
        moduleResolution: "bundler",
        target: "es2022",
        outDir: relative(RAIZ, salida).split("\\").join("/"),
        rootDir: "src",
        skipLibCheck: true,
        // El tsconfig del proyecto es incremental. Heredarlo aquí hace que, tras
        // borrar la carpeta de salida, tsc mire su .tsbuildinfo, crea que está
        // todo al día y NO emita nada: el script fallaría con un
        // "cannot find module" desconcertante en vez de compilar.
        incremental: false,
        composite: false,
      },
      include: ["src/server/auth/**/*", "src/lib/shared/auth.ts"],
    }),
    "utf8",
  );
  execFileSync(
    process.execPath,
    [join(RAIZ, "node_modules", "typescript", "bin", "tsc"), "-p", configTmp],
    { cwd: RAIZ, stdio: "pipe" },
  );

  // tsc NO reescribe el alias '@/...' al emitir: se hace aquí para que Node
  // pueda importar lo compilado. Y un package.json con type:module para que
  // trate los .js emitidos como ESM.
  writeFileSync(join(salida, "package.json"), '{"type":"module"}', "utf8");
  for (const fichero of jsEmitidos(salida)) {
    const texto = readFileSync(fichero, "utf8").replace(
      /(from\s+")@\/([^"]+)(")/g,
      (_m, a, ruta, c) => {
        let rel = relative(dirname(fichero), join(salida, ruta)).split("\\").join("/");
        if (!rel.startsWith(".")) rel = `./${rel}`;
        return `${a}${rel}.js${c}`;
      },
    );
    writeFileSync(fichero, texto, "utf8");
  }

  const url = (p) => pathToFileURL(join(salida, p)).href;
  const { hashPassword, verifyPassword, generarPassword } = await import(
    url("server/auth/password.js")
  );
  const { firmarSesion, verificarSesion } = await import(url("server/auth/session.js"));

  console.log("=== contrasenas (scrypt) ===");
  const t0 = Date.now();
  const hash = await hashPassword("una contrasena larga de prueba");
  const msHash = Date.now() - t0;
  linea(/^scrypt\$32768\$8\$1\$/.test(hash), `formato del hash: ${hash.slice(0, 22)}…`);
  linea(await verifyPassword("una contrasena larga de prueba", hash), "la correcta pasa");
  linea(!(await verifyPassword("otra cosa", hash)), "una incorrecta no pasa");
  linea(
    (await hashPassword("misma")) !== (await hashPassword("misma")),
    "dos hashes de la misma contrasena difieren (hay salt)",
  );
  linea(msHash > 20, `coste real de derivacion: ${msHash} ms (freno a la fuerza bruta)`);

  console.log("\n=== hashes corruptos: false, nunca excepcion ===");
  for (const malo of ["", "nada", "scrypt$x$8$1$aa$bb", "bcrypt$2$3$4$5$6", "scrypt$32768$8$1$$"]) {
    let ok = false;
    try {
      ok = (await verifyPassword("x", malo)) === false;
    } catch (e) {
      ok = false;
    }
    linea(ok, `hash ${JSON.stringify(malo).slice(0, 24).padEnd(26)} -> false`);
  }

  console.log("\n=== el script de rescate no se ha desviado del panel ===");
  {
    // reset_password.mjs implementa scrypt por su cuenta (es una herramienta de
    // terminal y no puede importar TypeScript). Si alguien toca los parametros
    // de un lado y no del otro, el panel dejaria de reconocer los hashes que
    // genera ese script, y no se notaria hasta que alguien quedase fuera.
    const rescate = await import(pathToFileURL(join(RAIZ, "scripts", "reset_password.mjs")).href);
    const suyo = await rescate.hashPassword("contrasena de prueba larga");
    linea(
      await verifyPassword("contrasena de prueba larga", suyo),
      "el panel valida un hash hecho por reset_password.mjs",
    );
    linea(
      !(await verifyPassword("otra distinta", suyo)),
      "  ...y rechaza una contrasena incorrecta contra ese mismo hash",
    );
    const mio = await hashPassword("x");
    linea(
      suyo.split("$").slice(0, 4).join("$") === mio.split("$").slice(0, 4).join("$"),
      `mismos parametros scrypt en los dos: ${mio.split("$").slice(0, 4).join("$")}`,
    );
    const genRescate = rescate.generarPassword();
    linea(
      genRescate.length === 18 && !/[0O1lI]/.test(genRescate),
      "generarPassword del script: misma longitud y mismo alfabeto",
    );
  }

  console.log("\n=== contrasenas generadas ===");
  const gen = generarPassword();
  linea(gen.length === 18, `longitud ${gen.length}`);
  linea(!/[0O1lI]/.test(gen), "sin caracteres ambiguos (0/O, 1/l/I)");
  linea(new Set(Array.from({ length: 50 }, () => generarPassword())).size === 50, "50 generadas, 50 distintas");

  console.log("\n=== ?next= del login: nada puede salir del panel ===");
  {
    const { rutaInternaSegura } = await import(url("lib/shared/auth.js"));
    // Todos estos acaban FUERA del dominio si se resuelven con el parser del
    // navegador. Es exactamente lo que hace window.location.href en LoginForm.
    const fuera = [
      "https://evil.com",
      "//evil.com",
      "/\\evil.com",
      "/\\\\evil.com",
      "\\\\evil.com",
      "/\t//evil.com",
      "/\n//evil.com",
      "/\r\n//evil.com",
      "javascript:alert(1)",
      "http:/evil.com",
    ];
    for (const d of fuera) {
      const r = rutaInternaSegura(d);
      linea(r === "/", `${JSON.stringify(d).padEnd(20)} -> ${JSON.stringify(r)}`);
    }
    // Y estos son internos: se conservan. Ojo con "/\tevil.com": una sola barra
    // es una RUTA de este panel (acaba en /evil.com y da 404), no una salida.
    const dentro = [
      ["/", "/"],
      ["/runs/3f2504e0-4f89-11d3-9a0c-0305e82c3301", "/runs/3f2504e0-4f89-11d3-9a0c-0305e82c3301"],
      ["/runs?page=2", "/runs?page=2"],
      ["/usuarios#alta", "/usuarios#alta"],
      ["/\tevil.com", "/evil.com"],
      [undefined, "/"],
      [null, "/"],
      ["", "/"],
    ];
    for (const [d, esperado] of dentro) {
      const r = rutaInternaSegura(d);
      linea(
        r === esperado,
        `${String(JSON.stringify(d)).padEnd(20)} -> ${JSON.stringify(r)} (interno)`,
      );
    }
  }

  console.log("\n=== cookie de sesion (jose) ===");
  process.env.AUTH_SECRET = "a".repeat(64);
  const sesion = { id: "3f2504e0-4f89-11d3-9a0c-0305e82c3301", email: "a@b.c", nombre: "Ana", rol: "admin" };
  const token = await firmarSesion(sesion);
  const leida = await verificarSesion(token);
  linea(leida?.id === sesion.id && leida?.rol === "admin", "ida y vuelta conserva id y rol");

  linea((await verificarSesion(null)) === null, "sin token -> null");
  linea((await verificarSesion("no-es-un-jwt")) === null, "token basura -> null");
  linea(
    (await verificarSesion(token.slice(0, -3) + "aaa")) === null,
    "firma manipulada -> null",
  );

  // El ataque clasico: cambiar el rol en el payload. Sin la firma no cuela.
  const [h, p, s] = token.split(".");
  const payload = JSON.parse(Buffer.from(p, "base64url").toString());
  payload.rol = "admin";
  const falso = [h, Buffer.from(JSON.stringify({ ...payload, sub: "otro" })).toString("base64url"), s].join(".");
  linea((await verificarSesion(falso)) === null, "payload alterado con la firma vieja -> null");

  process.env.AUTH_SECRET = "b".repeat(64);
  linea(
    (await verificarSesion(token)) === null,
    "token firmado con OTRO secreto -> null (rotar AUTH_SECRET cierra sesiones)",
  );

  delete process.env.AUTH_SECRET;
  linea((await verificarSesion(token)) === null, "sin AUTH_SECRET -> null, no lanza");
} finally {
  rmSync(salida, { recursive: true, force: true });
  rmSync(configTmp, { force: true });
}

console.log(`\n${fallos ? `${fallos} COMPROBACIONES FALLAN` : "TODO CORRECTO"}`);
process.exit(fallos ? 1 : 0);

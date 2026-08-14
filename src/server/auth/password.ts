/**
 * Hash y verificación de contraseñas con scrypt de `node:crypto`.
 *
 * POR QUÉ scrypt Y NO bcrypt/argon2
 * Viene en Node, así que no añade dependencia ni binario nativo (un binario
 * nativo complica el despliegue serverless). scrypt es un KDF con coste de
 * memoria, que es justo lo que hace cara la fuerza bruta con GPU.
 *
 * RUNTIME: **solo Node**. `node:crypto` no existe en el runtime Edge, así que
 * este fichero NO se puede importar desde `src/middleware.ts` ni desde nada que
 * arrastre el middleware. Si lo haces, el build de Edge rompe.
 *
 * Los parámetros van DENTRO del propio hash (`scrypt$N$r$p$salt$hash`), así que
 * se pueden subir en el futuro sin invalidar los hashes ya guardados: basta con
 * rehashear en el siguiente login correcto.
 */

import { randomBytes, scrypt, timingSafeEqual } from "node:crypto";
import { promisify } from "node:util";

const scryptAsync = promisify(scrypt) as (
  password: string | Buffer,
  salt: string | Buffer,
  keylen: number,
  options: { N: number; r: number; p: number; maxmem: number },
) => Promise<Buffer>;

const N = 32768; // 2^15 → ~32 MB y ~100 ms por verificación.
const R = 8;
const P = 1;
const KEYLEN = 32;
const SALT_BYTES = 16;
// El maxmem por defecto de Node (32 MB) se queda JUSTO con N=2^15 y a veces
// falla con un error poco descriptivo. Se pasa explícito con margen.
const MAXMEM = 128 * 1024 * 1024;

const ETIQUETA = "scrypt";

async function derivar(
  password: string,
  salt: Buffer,
  n: number,
  r: number,
  p: number,
): Promise<Buffer> {
  return scryptAsync(password.normalize("NFKC"), salt, KEYLEN, {
    N: n,
    r,
    p,
    maxmem: MAXMEM,
  });
}

/** Devuelve `scrypt$N$r$p$saltB64$hashB64`. */
export async function hashPassword(password: string): Promise<string> {
  const salt = randomBytes(SALT_BYTES);
  const hash = await derivar(password, salt, N, R, P);
  return [
    ETIQUETA,
    N,
    R,
    P,
    salt.toString("base64"),
    hash.toString("base64"),
  ].join("$");
}

/**
 * Verifica en tiempo constante. Devuelve false ante cualquier hash malformado en
 * vez de lanzar: una fila corrupta en la BD no debe tumbar el login de todos.
 */
export async function verifyPassword(
  password: string,
  almacenado: string,
): Promise<boolean> {
  try {
    const partes = String(almacenado).split("$");
    if (partes.length !== 6 || partes[0] !== ETIQUETA) return false;
    const n = Number(partes[1]);
    const r = Number(partes[2]);
    const p = Number(partes[3]);
    if (!Number.isFinite(n) || !Number.isFinite(r) || !Number.isFinite(p)) {
      return false;
    }
    // Tope de cordura: un N absurdo en la BD colgaría la función serverless.
    if (n > 1 << 20 || r > 32 || p > 16) return false;

    const salt = Buffer.from(partes[4], "base64");
    const esperado = Buffer.from(partes[5], "base64");
    if (salt.length === 0 || esperado.length === 0) return false;

    const calculado = await derivar(password, salt, n, r, p);
    if (calculado.length !== esperado.length) return false;
    return timingSafeEqual(calculado, esperado);
  } catch {
    return false;
  }
}

/**
 * Genera una contraseña legible y fuerte para dar de alta a alguien.
 * Alfabeto sin caracteres ambiguos (0/O, 1/l/I): estas contraseñas se dictan o
 * se copian a mano, y confundir un carácter cuesta un soporte.
 */
export function generarPassword(longitud = 18): string {
  const abc = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const bytes = randomBytes(longitud * 2);
  let out = "";
  // Rechaza los bytes del último bloque incompleto para no sesgar el reparto.
  const limite = Math.floor(256 / abc.length) * abc.length;
  for (const b of bytes) {
    if (b >= limite) continue;
    out += abc[b % abc.length];
    if (out.length === longitud) break;
  }
  return out.length === longitud ? out : out + generarPassword(longitud - out.length);
}

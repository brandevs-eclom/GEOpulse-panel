/**
 * Sesión del panel: un JWT firmado (HS256) dentro de una cookie httpOnly.
 *
 * RUNTIME: este fichero tiene que funcionar TAMBIÉN en Edge, porque lo importa
 * `src/middleware.ts`. Por eso solo usa `jose` (Web Crypto) y no toca
 * `node:crypto` ni el cliente de n8n. NO importes aquí `./password` ni
 * `@/server/n8n/client`: romperías el build de Edge.
 *
 * POR QUÉ UN JWT Y NO UNA TABLA DE SESIONES
 * La base de datos vive dentro de n8n y solo se alcanza por HTTP. Una tabla de
 * sesiones obligaría a un HTTP a n8n en CADA petición, y el panel hace polling
 * cada 2,5 s: sería un coste desproporcionado. El precio de esta decisión, que
 * conviene tener presente, es que una sesión NO se puede revocar de una en una
 * (ver README): el único botón rojo es rotar AUTH_SECRET, que cierra la sesión
 * de todo el mundo a la vez.
 */

import { SignJWT, jwtVerify } from "jose";

import { esRol, type Sesion } from "@/lib/shared/auth";

export const COOKIE_SESION = "gp_sesion";

/** 12 h: acota la ventana de una cookie robada a menos de un día laboral. */
export const TTL_SEGUNDOS = 12 * 60 * 60;

const ALG = "HS256";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Lectura perezosa: si se leyera al importar, cualquier ruta reventaría al
 * arrancar en vez de fallar solo donde de verdad hace falta el secreto.
 */
function clave(): Uint8Array {
  const secreto = process.env.AUTH_SECRET;
  if (!secreto || secreto.length < 16) {
    throw new Error(
      "Falta AUTH_SECRET (o es demasiado corto). Genera uno con: openssl rand -hex 32",
    );
  }
  return new TextEncoder().encode(secreto);
}

/** Firma la cookie de sesión. */
export async function firmarSesion(sesion: Sesion): Promise<string> {
  return new SignJWT({
    email: sesion.email,
    nombre: sesion.nombre,
    rol: sesion.rol,
  })
    .setProtectedHeader({ alg: ALG })
    .setSubject(sesion.id)
    .setIssuedAt()
    .setExpirationTime(`${TTL_SEGUNDOS}s`)
    .sign(clave());
}

/**
 * Verifica la cookie. Devuelve null ante CUALQUIER problema (firma inválida,
 * caducada, secreto ausente, payload raro). Nunca devuelve una sesión por
 * defecto: si algo no cuadra, no hay sesión.
 */
export async function verificarSesion(
  token: string | undefined | null,
): Promise<Sesion | null> {
  if (!token) return null;
  try {
    const { payload } = await jwtVerify(token, clave(), { algorithms: [ALG] });
    const id = payload.sub;
    const email = payload.email;
    const rol = payload.rol;
    // El id tiene que ser un UUID de verdad, no solo "una cadena". Un `sub`
    // vacío se colaría y aguas abajo `filtroPropiedad` devolvería "", que el
    // workflow interpreta como "sin filtro": un miembro vería las ejecuciones de
    // todos. Hoy es inalcanzable (el token lo firmamos nosotros con el id de la
    // BD), pero el fallo sería ABRIR en vez de cerrar, y eso no se deja al azar.
    if (typeof id !== "string" || !UUID_RE.test(id)) return null;
    if (typeof email !== "string" || !email || !esRol(rol)) return null;
    return {
      id,
      email,
      nombre: typeof payload.nombre === "string" ? payload.nombre : null,
      rol,
    };
  } catch {
    return null;
  }
}

/** Opciones de la cookie. `secure` solo en producción para que funcione en local. */
export function opcionesCookie(maxAge: number) {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge,
  };
}

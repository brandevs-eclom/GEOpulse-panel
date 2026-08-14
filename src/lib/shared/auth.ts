/**
 * Contratos de autenticación compartidos entre cliente y servidor.
 *
 * Aquí NO hay nada de criptografía ni ningún secreto: este fichero lo importan
 * componentes de cliente, así que todo lo que ponga acaba en el navegador.
 */

export const ROLES = ["admin", "miembro"] as const;
export type Rol = (typeof ROLES)[number];

export function esRol(v: unknown): v is Rol {
  return typeof v === "string" && (ROLES as readonly string[]).includes(v);
}

/**
 * Lo que viaja dentro de la cookie de sesión y lo que ve el cliente.
 * Nunca incluye el hash de la contraseña.
 */
export interface Sesion {
  id: string;
  email: string;
  nombre: string | null;
  rol: Rol;
}

/** Fila de la pantalla de usuarios. */
export interface UsuarioListItem {
  id: string;
  email: string;
  nombre: string | null;
  rol: Rol;
  createdAt: string;
  /** Cuántas ejecuciones ha lanzado: es lo que se queda sin dueño si lo borras. */
  ejecuciones: number;
}

export interface CrearUsuarioInput {
  email: string;
  /** Si se omite (o va vacía), el servidor genera una y la devuelve UNA vez. */
  password?: string;
  nombre?: string;
  rol: Rol;
}

export interface LoginInput {
  email: string;
  password: string;
}

/**
 * Longitud mínima de contraseña. No hay reglas de composición a propósito:
 * imponer "una mayúscula y un símbolo" produce contraseñas peores y más difíciles
 * de recordar que exigir longitud. Como las genera el admin, que sean largas.
 */
export const PASSWORD_MIN = 12;

export function validarPassword(v: unknown): string | null {
  if (typeof v !== "string" || v.length < PASSWORD_MIN) {
    return `La contraseña debe tener al menos ${PASSWORD_MIN} caracteres`;
  }
  return null;
}

/** Validación de email deliberadamente laxa: solo descarta lo que no lo es. */
export function validarEmail(v: unknown): string | null {
  const s = typeof v === "string" ? v.trim() : "";
  if (!s) return "El email es obligatorio";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s)) return "Email no válido";
  return null;
}

/** Base ficticia: solo sirve para comparar el origen resultante. */
const BASE_INTERNA = "https://interno.invalid";

/**
 * Devuelve `destino` solo si es una ruta DE ESTE panel; si no, la home.
 *
 * Se usa con el `?next=` del login. Sin esto, `/login?next=…` sería un
 * redirector abierto: un enlace con el dominio del panel que, tras un login
 * correcto de verdad, deja al usuario en una página ajena. Es la mitad de un
 * phishing, y el dominio del enlace supera el filtro visual de cualquiera.
 *
 * Se valida resolviendo con `new URL`, es decir CON EL MISMO PARSER que usará
 * el navegador en `window.location.href`, en vez de mirar los primeros
 * caracteres. Una comprobación tipo `/^\/(?!\/)/` parece suficiente y no lo es:
 *   · `/\evil.com` la pasa, y para esquemas http(s) el parser trata `\` como
 *     `/`, así que acaba en `https://evil.com/`.
 *   · `/<TAB>//evil.com` la pasa, porque el parser descarta TAB/CR/LF ANTES de
 *     parsear y se queda `//evil.com`.
 */
export function rutaInternaSegura(destino: string | undefined | null): string {
  if (!destino) return "/";
  // Se quitan primero los caracteres que el parser eliminaría de todos modos.
  const limpio = destino.replace(/[\t\n\r]/g, "");
  try {
    const u = new URL(limpio, BASE_INTERNA);
    if (u.origin !== BASE_INTERNA) return "/";
    return u.pathname + u.search + u.hash;
  } catch {
    return "/";
  }
}

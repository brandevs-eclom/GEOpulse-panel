/**
 * Repositorio de usuarios. Como el resto del panel, no toca Postgres: habla con
 * el workflow `panel-db` de n8n, que es la única puerta a la base de datos.
 *
 * El hash de la contraseña se calcula y se verifica AQUÍ (runtime Node); por el
 * webhook solo viaja el hash ya hecho, nunca la contraseña en claro.
 */

import type { Rol, Sesion, UsuarioListItem } from "@/lib/shared/auth";
import { esRol } from "@/lib/shared/auth";
import { hashPassword } from "@/server/auth/password";
import { callPanelDb } from "@/server/n8n/client";

type DbRow = Record<string, unknown>;

const str = (v: unknown): string | null =>
  v === null || v === undefined ? null : String(v);

const num = (v: unknown): number => {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
};

/** Un rol desconocido en la BD se degrada a 'miembro': nunca se asciende solo. */
function rolDe(v: unknown): Rol {
  return esRol(v) ? v : "miembro";
}

function aListItem(r: DbRow): UsuarioListItem {
  return {
    id: String(r.id),
    email: String(r.email),
    nombre: str(r.nombre),
    rol: rolDe(r.rol),
    createdAt: String(r.created_at),
    ejecuciones: num(r.ejecuciones),
  };
}

/** Usuario tal cual está en la BD, con el hash. Solo para el login. */
export interface UsuarioConHash extends Sesion {
  passwordHash: string;
}

/** Busca por email (el workflow ya normaliza a minúsculas). null si no existe. */
export async function getUserByEmail(
  email: string,
): Promise<UsuarioConHash | null> {
  const rows = await callPanelDb<DbRow>("get_user_by_email", { email });
  const r = rows[0];
  if (!r) return null;
  return {
    id: String(r.id),
    email: String(r.email),
    nombre: str(r.nombre),
    rol: rolDe(r.rol),
    passwordHash: String(r.password_hash),
  };
}

/** Existe esa cuenta? Se usa para distinguir "no existe" de "es el último admin". */
export async function getUser(id: string): Promise<UsuarioListItem | null> {
  const rows = await callPanelDb<DbRow>("get_user", { id });
  return rows[0] ? aListItem(rows[0]) : null;
}

export async function listUsers(): Promise<UsuarioListItem[]> {
  const rows = await callPanelDb<DbRow>("list_users");
  return rows.map(aListItem);
}

export async function countUsers(): Promise<number> {
  const rows = await callPanelDb<DbRow>("count_users");
  return num(rows[0]?.total);
}

/** Cuántos admins quedan. Se usa para no dejar el panel sin ninguno. */
export async function countAdmins(): Promise<number> {
  const rows = await callPanelDb<DbRow>("count_admins");
  return num(rows[0]?.total);
}

export async function createUser(input: {
  email: string;
  password: string;
  nombre?: string | null;
  rol: Rol;
}): Promise<UsuarioListItem> {
  const rows = await callPanelDb<DbRow>("create_user", {
    email: input.email,
    password_hash: await hashPassword(input.password),
    nombre: input.nombre ?? null,
    rol: input.rol,
  });
  const r = rows[0];
  if (!r) throw new Error("create_user no devolvió la fila creada");
  return { ...aListItem(r), ejecuciones: 0 };
}

/**
 * Cambia el rol. Devuelve null si la sentencia no tocó ninguna fila, que puede
 * ser por dos motivos: la cuenta no existe, o es el último admin y el cerrojo
 * del SQL ha impedido degradarla. Quien llama los distingue con `getUser`.
 */
export async function updateUserRol(
  id: string,
  rol: Rol,
): Promise<UsuarioListItem | null> {
  const rows = await callPanelDb<DbRow>("update_user_rol", { id, rol });
  const r = rows[0];
  return r ? { ...aListItem(r), ejecuciones: num(r.ejecuciones) } : null;
}

export async function updateUserPassword(
  id: string,
  password: string,
): Promise<boolean> {
  const rows = await callPanelDb<DbRow>("update_user_password", {
    id,
    password_hash: await hashPassword(password),
  });
  return rows.length > 0;
}

/**
 * Borra la cuenta. Sus ejecuciones NO se borran: `runs.lanzado_por` es
 * ON DELETE SET NULL, así que se quedan sin dueño y pasan a verlas solo los
 * admins.
 *
 * false si no tocó ninguna fila: o no existe, o es el último admin (el SQL lo
 * impide). Quien llama los distingue con `getUser`.
 */
export async function deleteUser(id: string): Promise<boolean> {
  const rows = await callPanelDb<DbRow>("delete_user", { id });
  return rows.length > 0;
}

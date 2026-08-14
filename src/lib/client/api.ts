/**
 * Helpers de fetch para el cliente (navegador → API del panel).
 * ApiError conserva el status y el cuerpo para que los formularios puedan
 * mostrar errores de validación o el caso "at_capacity" tal cual.
 */

import type {
  CrearUsuarioInput,
  Rol,
  Sesion,
  UsuarioListItem,
} from "@/lib/shared/auth";
import type {
  HealthResponse,
  LanzarRunInput,
  LanzarRunResponse,
  RunDetail,
  RunsPage,
} from "@/lib/shared/dto";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
  ) {
    super(`HTTP ${status}`);
    this.name = "ApiError";
  }
}

/**
 * Rutas que NO deben rebotar al login cuando devuelven 401: son las que forman
 * parte del propio flujo de entrada.
 */
const SIN_REBOTE = ["/api/auth/login", "/api/auth/logout"];

/** Evita reasignar `location` una vez por cada consulta en vuelo. */
let yendoAlLogin = false;

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  const body = (await res.json().catch(() => null)) as unknown;

  // La sesión dura 12 h y el panel hace polling: caducar con una pestaña abierta
  // es un caso normal, no una avería. Sin esto se pintaría "no se pudo cargar,
  // ¿está n8n accesible?", que manda a diagnosticar el problema equivocado.
  if (
    res.status === 401 &&
    typeof window !== "undefined" &&
    !SIN_REBOTE.some((r) => url.startsWith(r))
  ) {
    if (!yendoAlLogin) {
      yendoAlLogin = true;
      const destino = window.location.pathname + window.location.search;
      window.location.href = `/login?next=${encodeURIComponent(destino)}`;
    }
    // Promesa que nunca resuelve, a propósito. La navegación ya está en marcha
    // y tarda un momento; si aquí se lanzara un ApiError, React Query lo
    // marcaría como fallo y durante ese hueco la pantalla enseñaría el error de
    // "¿está n8n accesible?", y además reintentaría (retry) volviendo a entrar
    // aquí. Dejarla colgada mantiene el estado en "cargando" hasta que la
    // página se va.
    return new Promise<never>(() => {});
  }

  if (!res.ok) throw new ApiError(res.status, body);
  return body as T;
}

export function fetchHealth(): Promise<HealthResponse> {
  return jsonFetch<HealthResponse>("/api/health");
}

export function fetchRuns(page = 1, pageSize = 50): Promise<RunsPage> {
  return jsonFetch<RunsPage>(`/api/runs?page=${page}&pageSize=${pageSize}`);
}

export function fetchRun(id: string): Promise<RunDetail> {
  return jsonFetch<RunDetail>(`/api/runs/${id}`);
}

export function lanzarRun(input: LanzarRunInput): Promise<LanzarRunResponse> {
  return jsonFetch<LanzarRunResponse>("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function eliminarRun(id: string): Promise<{ ok: true }> {
  return jsonFetch<{ ok: true }>(`/api/runs/${id}`, { method: "DELETE" });
}

// --- Sesión ---

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export function login(email: string, password: string): Promise<Sesion> {
  return jsonFetch<Sesion>("/api/auth/login", json({ email, password }));
}

export function logout(): Promise<{ ok: true }> {
  return jsonFetch<{ ok: true }>("/api/auth/logout", { method: "POST" });
}

// --- Usuarios (solo admin) ---

/** La contraseña solo viene cuando la ha generado el servidor: se ve una vez. */
export interface UsuarioCreado {
  usuario: UsuarioListItem;
  password?: string;
}

export function fetchUsuarios(): Promise<{ items: UsuarioListItem[] }> {
  return jsonFetch<{ items: UsuarioListItem[] }>("/api/usuarios");
}

export function crearUsuario(input: CrearUsuarioInput): Promise<UsuarioCreado> {
  return jsonFetch<UsuarioCreado>("/api/usuarios", json(input));
}

export function cambiarRol(
  id: string,
  rol: Rol,
): Promise<{ usuario: UsuarioListItem }> {
  return jsonFetch<{ usuario: UsuarioListItem }>(`/api/usuarios/${id}`, {
    ...json({ rol }),
    method: "PATCH",
  });
}

export function resetearPassword(
  id: string,
  password?: string,
): Promise<{ ok: true; password?: string; aviso?: string }> {
  return jsonFetch(`/api/usuarios/${id}`, {
    ...json({ password: password ?? "" }),
    method: "PATCH",
  });
}

export function eliminarUsuario(
  id: string,
): Promise<{ ok: true; aviso?: string }> {
  return jsonFetch(`/api/usuarios/${id}`, { method: "DELETE" });
}

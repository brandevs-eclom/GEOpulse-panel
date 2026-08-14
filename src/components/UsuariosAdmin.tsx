"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  ApiError,
  cambiarRol,
  crearUsuario,
  eliminarUsuario,
  fetchUsuarios,
  resetearPassword,
} from "@/lib/client/api";
import { PASSWORD_MIN, type Rol, type Sesion } from "@/lib/shared/auth";

const CLAVE = ["usuarios"];

/** Mensaje legible de un error de la API. */
function mensajeDe(err: unknown, porDefecto: string): string {
  if (err instanceof ApiError) {
    const body = err.body as
      | { detalle?: string; errores?: Record<string, string> }
      | null;
    if (body?.detalle) return body.detalle;
    if (body?.errores) return Object.values(body.errores).join(" · ");
    return `${porDefecto} (error ${err.status})`;
  }
  return err instanceof Error ? err.message : porDefecto;
}

export function UsuariosAdmin({ sesion }: { sesion: Sesion }) {
  const qc = useQueryClient();
  const [aviso, setAviso] = useState<string | null>(null);
  /** Contraseña recién generada. Se enseña UNA vez: no se guarda en claro. */
  const [credencial, setCredencial] = useState<{
    email: string;
    password: string;
  } | null>(null);

  const lista = useQuery({ queryKey: CLAVE, queryFn: fetchUsuarios });

  const tras = (accion: () => void) => {
    accion();
    qc.invalidateQueries({ queryKey: CLAVE });
  };

  const mutRol = useMutation({
    mutationFn: ({ id, rol }: { id: string; rol: Rol }) => cambiarRol(id, rol),
    onSuccess: () => tras(() => setAviso(null)),
    onError: (e) => setAviso(mensajeDe(e, "No se pudo cambiar el rol")),
  });

  const mutReset = useMutation({
    mutationFn: (u: { id: string; email: string }) => resetearPassword(u.id),
    onSuccess: (res, u) =>
      tras(() => {
        setAviso(res.aviso ?? null);
        if (res.password) setCredencial({ email: u.email, password: res.password });
      }),
    onError: (e) => setAviso(mensajeDe(e, "No se pudo resetear la contraseña")),
  });

  const mutBorrar = useMutation({
    mutationFn: (id: string) => eliminarUsuario(id),
    onSuccess: (res) => tras(() => setAviso(res.aviso ?? null)),
    onError: (e) => setAviso(mensajeDe(e, "No se pudo borrar la cuenta")),
  });

  return (
    <>
      <AltaUsuario
        onCreado={(email, password) => {
          setAviso(null);
          if (password) setCredencial({ email, password });
          qc.invalidateQueries({ queryKey: CLAVE });
        }}
        onError={setAviso}
      />

      {credencial && (
        <div className="gp-card gp-credencial">
          <span className="gp-eyebrow">Contraseña generada</span>
          <p className="gp-sub">
            Anótala y pásasela a <b>{credencial.email}</b> por un canal privado.
            No se guarda en claro en ningún sitio: si la pierdes, hay que
            resetearla.
          </p>
          <div className="gp-credencial-valor">
            <code>{credencial.password}</code>
            <button
              type="button"
              className="gp-btn-ghost"
              onClick={() => navigator.clipboard?.writeText(credencial.password)}
            >
              Copiar
            </button>
            <button
              type="button"
              className="gp-btn-ghost"
              onClick={() => setCredencial(null)}
            >
              Ocultar
            </button>
          </div>
        </div>
      )}

      {aviso && <div className="gp-error-box gp-aviso-info">{aviso}</div>}

      <div className="gp-card" style={{ marginTop: 18 }}>
        <h2 className="gp-h2">Cuentas</h2>
        {lista.isPending && <div className="gp-empty">Cargando…</div>}
        {lista.isError && (
          <div className="gp-error-box">
            {mensajeDe(lista.error, "No se pudo cargar la lista de usuarios")}
          </div>
        )}
        {lista.data && (
          <div className="gp-table-wrap">
            <table className="gp-table">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Nombre</th>
                  <th>Rol</th>
                  <th>Ejecuciones</th>
                  <th>Alta</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {lista.data.items.map((u) => {
                  const soyYo = u.id === sesion.id;
                  const ocupado =
                    mutRol.isPending || mutReset.isPending || mutBorrar.isPending;
                  return (
                    <tr key={u.id}>
                      <td className="gp-mono">
                        {u.email}
                        {soyYo && <span className="gp-badge-tu">tú</span>}
                      </td>
                      <td>{u.nombre ?? "—"}</td>
                      <td>
                        <span className={`gp-rol gp-rol-${u.rol}`}>{u.rol}</span>
                      </td>
                      <td>{u.ejecuciones}</td>
                      <td className="gp-mono">
                        {new Date(u.createdAt).toLocaleDateString("es-ES")}
                      </td>
                      <td className="gp-acciones">
                        <button
                          type="button"
                          className="gp-btn-ghost"
                          // Quitarte a ti mismo el admin deja un estado
                          // confuso: la cookie seguiría diciendo admin hasta
                          // 12 h, así que verías esta pantalla sin poder usarla.
                          // Que lo haga otro admin.
                          disabled={ocupado || (soyYo && u.rol === "admin")}
                          title={
                            soyYo && u.rol === "admin"
                              ? "No puedes quitarte el admin a ti mismo: pídeselo a otro administrador"
                              : undefined
                          }
                          onClick={() =>
                            mutRol.mutate({
                              id: u.id,
                              rol: u.rol === "admin" ? "miembro" : "admin",
                            })
                          }
                        >
                          {u.rol === "admin" ? "Quitar admin" : "Hacer admin"}
                        </button>
                        <button
                          type="button"
                          className="gp-btn-ghost"
                          disabled={ocupado}
                          onClick={() => {
                            if (
                              confirm(
                                `Generar una contraseña nueva para ${u.email}? La actual dejará de servir.`,
                              )
                            ) {
                              mutReset.mutate({ id: u.id, email: u.email });
                            }
                          }}
                        >
                          Resetear
                        </button>
                        <button
                          type="button"
                          className="gp-btn-ghost gp-peligro"
                          disabled={ocupado || soyYo}
                          title={
                            soyYo ? "No puedes borrar tu propia cuenta" : undefined
                          }
                          onClick={() => {
                            if (
                              confirm(
                                `Quitar el acceso a ${u.email}?\n\n` +
                                  `Sus ${u.ejecuciones} ejecuciones NO se borran: se quedan sin dueño ` +
                                  `y pasan a verlas solo los admins.\n\n` +
                                  `Su sesión sigue activa hasta que caduque (máx. 12 h).`,
                              )
                            ) {
                              mutBorrar.mutate(u.id);
                            }
                          }}
                        >
                          Quitar acceso
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

const VACIO = { email: "", nombre: "", password: "" };

function AltaUsuario({
  onCreado,
  onError,
}: {
  onCreado: (email: string, password?: string) => void;
  onError: (m: string) => void;
}) {
  const [form, setForm] = useState({ ...VACIO });
  const [rol, setRol] = useState<Rol>("miembro");
  const [errores, setErrores] = useState<Record<string, string>>({});

  const mut = useMutation({
    mutationFn: crearUsuario,
    onSuccess: (res) => {
      setForm({ ...VACIO });
      setRol("miembro");
      setErrores({});
      onCreado(res.usuario.email, res.password);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 400) {
        const body = err.body as { errores?: Record<string, string> };
        setErrores(body.errores ?? {});
      } else {
        onError(mensajeDe(err, "No se pudo crear la cuenta"));
      }
    },
  });

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <form
      className="gp-card"
      onSubmit={(e) => {
        e.preventDefault();
        setErrores({});
        mut.mutate({
          email: form.email,
          nombre: form.nombre || undefined,
          password: form.password || undefined,
          rol,
        });
      }}
    >
      <span className="gp-eyebrow">Nueva cuenta</span>
      <h2 className="gp-h2">Dar de alta a un compañero</h2>
      <p className="gp-sub">
        No hay envío de correo: la contraseña se la pasas tú. Déjala en blanco y
        el panel genera una fuerte.
      </p>

      <div className="gp-grid">
        <div className="gp-field">
          <label htmlFor="u-email">Email *</label>
          <input
            id="u-email"
            type="email"
            value={form.email}
            onChange={set("email")}
            placeholder="nombre@brandevs.com"
            aria-invalid={errores.email ? "true" : undefined}
            required
          />
          {errores.email ? (
            <div className="gp-err">{errores.email}</div>
          ) : (
            <div className="gp-ayuda">Con el que iniciará sesión.</div>
          )}
        </div>

        <div className="gp-field">
          <label htmlFor="u-nombre">Nombre (opcional)</label>
          <input
            id="u-nombre"
            type="text"
            value={form.nombre}
            onChange={set("nombre")}
            placeholder="Nombre y apellido"
          />
          <div className="gp-ayuda">Solo para reconocerlo en la cabecera.</div>
        </div>

        <div className="gp-field">
          <label htmlFor="u-password">Contraseña (opcional)</label>
          <input
            id="u-password"
            type="text"
            value={form.password}
            onChange={set("password")}
            placeholder="se genera sola si la dejas vacía"
            autoComplete="off"
            aria-invalid={errores.password ? "true" : undefined}
          />
          {errores.password ? (
            <div className="gp-err">{errores.password}</div>
          ) : (
            <div className="gp-ayuda">Mínimo {PASSWORD_MIN} caracteres.</div>
          )}
        </div>

        <div className="gp-field">
          <label htmlFor="u-rol">Rol</label>
          <select
            id="u-rol"
            value={rol}
            onChange={(e) => setRol(e.target.value as Rol)}
          >
            <option value="miembro">Miembro</option>
            <option value="admin">Admin</option>
          </select>
          <div className="gp-ayuda">
            El miembro ve solo sus ejecuciones. El admin las ve todas y gestiona
            cuentas.
          </div>
        </div>
      </div>

      <div style={{ marginTop: 18 }}>
        <button className="gp-btn" type="submit" disabled={mut.isPending}>
          {mut.isPending ? "Creando…" : "Crear cuenta"}
        </button>
      </div>
    </form>
  );
}

"use client";

import { useState } from "react";

import { ApiError, login } from "@/lib/client/api";

/**
 * Formulario de entrada. Al acertar navega con `window.location` y no con el
 * router de Next a propósito: hace falta una carga completa para que el layout
 * (server component) vuelva a leer la cookie y pinte la cabecera con la sesión.
 */
export function LoginForm({ siguiente }: { siguiente: string }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      await login(email, password);
      window.location.href = siguiente;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        // Mismo mensaje exista o no la cuenta: el panel no confirma qué emails
        // están dados de alta.
        setError("Email o contraseña incorrectos.");
      } else if (err instanceof ApiError) {
        const body = err.body as { detalle?: string } | null;
        setError(
          body?.detalle ??
            `No se pudo entrar (error ${err.status}). Si persiste, comprueba que n8n responde.`,
        );
      } else {
        setError(err instanceof Error ? err.message : "Error desconocido");
      }
      setEnviando(false);
    }
  }

  return (
    <form className="gp-card gp-login" onSubmit={enviar}>
      <span className="gp-eyebrow">Acceso</span>
      <h2 className="gp-h2">Entrar en el panel</h2>
      <p className="gp-sub">
        Panel interno de BranDevs. Las cuentas las crea un administrador; no hay
        registro.
      </p>

      <div className="gp-field">
        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoFocus
        />
      </div>

      <div className="gp-field">
        <label htmlFor="password">Contraseña</label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </div>

      {error && (
        <div className="gp-error-box" style={{ marginTop: 16 }}>
          {error}
        </div>
      )}

      <div style={{ marginTop: 18 }}>
        <button className="gp-btn" type="submit" disabled={enviando}>
          {enviando ? "Entrando…" : "Entrar"}
        </button>
      </div>
    </form>
  );
}

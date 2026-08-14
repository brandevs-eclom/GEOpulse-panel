"use client";

import Link from "next/link";
import { useState } from "react";

import { logout } from "@/lib/client/api";
import type { Sesion } from "@/lib/shared/auth";

/** Quién eres y cómo salir. Solo se monta cuando hay sesión. */
export function SesionChip({ sesion }: { sesion: Sesion }) {
  const [saliendo, setSaliendo] = useState(false);

  async function salir() {
    setSaliendo(true);
    try {
      await logout();
    } catch {
      // Da igual si falla: se navega igual y el middleware mandará al login.
    }
    // Carga completa para que el layout vuelva a leer la cookie (ya borrada).
    window.location.href = "/login";
  }

  return (
    <div className="gp-sesion">
      {sesion.rol === "admin" && (
        <Link href="/usuarios" className="gp-sesion-link">
          Usuarios
        </Link>
      )}
      <span className="gp-sesion-quien" title={sesion.email}>
        {sesion.nombre || sesion.email}
        {sesion.rol === "admin" && <span className="gp-sesion-rol">admin</span>}
      </span>
      <button
        type="button"
        className="gp-btn-ghost"
        onClick={salir}
        disabled={saliendo}
      >
        {saliendo ? "Saliendo…" : "Salir"}
      </button>
    </div>
  );
}

import Link from "next/link";
import { redirect } from "next/navigation";

import { UsuariosAdmin } from "@/components/UsuariosAdmin";
import { leerSesion } from "@/server/auth/guard";

export const dynamic = "force-dynamic";

export const metadata = { title: "Usuarios · GEOpulse Panel" };

/**
 * Gestión de cuentas. Solo admin.
 *
 * El middleware ya exige sesión, pero el ROL se comprueba aquí y otra vez en
 * cada ruta de /api/usuarios: quien entre por URL sin ser admin no ve nada, y
 * aunque llamase a la API a mano tampoco.
 */
export default async function UsuariosPage() {
  const sesion = await leerSesion();
  if (!sesion) redirect("/login?next=%2Fusuarios");

  if (sesion.rol !== "admin") {
    return (
      <main className="gp-main">
        <div className="gp-card">
          <h2 className="gp-h2">Solo para administradores</h2>
          <p className="gp-sub">
            Esta sección la gestiona un administrador del panel. Si necesitas dar
            de alta a alguien, pídeselo.
          </p>
          <Link href="/" className="gp-btn-ghost">
            Volver al panel
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="gp-main">
      <UsuariosAdmin sesion={sesion} />
    </main>
  );
}

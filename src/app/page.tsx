import { redirect } from "next/navigation";

import { LaunchForm } from "@/components/LaunchForm";
import { RunsTable } from "@/components/RunsTable";
import { leerSesion } from "@/server/auth/guard";

export const dynamic = "force-dynamic";

export default async function Home() {
  // El middleware ya lo garantiza; esto es para tener la sesión a mano (y por si
  // algún día el matcher cambia y esta página se queda fuera por descuido).
  const sesion = await leerSesion();
  if (!sesion) redirect("/login?next=%2F");

  const esAdmin = sesion.rol === "admin";

  return (
    <main className="gp-main">
      <LaunchForm />
      <div style={{ marginTop: 28 }}>
        <h2 className="gp-h2" style={{ marginBottom: 4 }}>
          Ejecuciones
        </h2>
        <p className="gp-sub">
          {esAdmin
            ? "Todas las de la agencia, incluidas las anteriores a la autenticación (sin dueño)."
            : "Las que has lanzado tú."}
        </p>
        <div className="gp-card" style={{ padding: 0 }}>
          <RunsTable esAdmin={esAdmin} />
        </div>
      </div>
    </main>
  );
}

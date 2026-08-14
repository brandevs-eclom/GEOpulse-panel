import { redirect } from "next/navigation";

import { LoginForm } from "@/components/LoginForm";
import { rutaInternaSegura } from "@/lib/shared/auth";
import { leerSesion } from "@/server/auth/guard";

export const dynamic = "force-dynamic";

export const metadata = { title: "Entrar · GEOpulse Panel" };

/**
 * Página de entrada. Es la única (junto al healthcheck) que el middleware deja
 * pasar sin sesión, así que su `?next=` lo controla quien fabrique el enlace:
 * de ahí que se sanee con `rutaInternaSegura` y no se use tal cual.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  // Ya dentro: no tiene sentido enseñar el formulario.
  if (await leerSesion()) redirect("/");

  const { next } = await searchParams;

  return (
    <main className="gp-main gp-main-login">
      <LoginForm siguiente={rutaInternaSegura(next)} />
    </main>
  );
}

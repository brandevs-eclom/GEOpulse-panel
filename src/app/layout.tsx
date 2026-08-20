import type { Metadata } from "next";
import Link from "next/link";

import { HealthPill } from "@/components/HealthPill";
import { SesionChip } from "@/components/SesionChip";
import { leerSesion } from "@/server/auth/guard";
import "./globals.css";
import "./panel.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "GEOpulse Panel",
  description: "Panel de control interno de BranDevs para auditorías GEO",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // El layout es server component, así que puede leer la cookie directamente:
  // no hace falta un provider de sesión en cliente.
  //
  // Sin sesión la cabecera va desnuda. Efecto secundario buscado: el HealthPill
  // no se monta, así que la página de login deja de sondear /api/health cada
  // 30 s desde un navegador que aún no ha entrado.
  const sesion = await leerSesion();
  return (
    <html lang="es">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Manrope:wght@400;500;600;700;800&family=Inter:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <Providers>
          <header className="gp-header">
            <div className="gp-header-in">
              <Link href="/" className="gp-logo">
                GEO<span>pulse</span> Panel
              </Link>
              <span className="gp-header-sp" />
              {sesion && (
                <>
                  <HealthPill />
                  <SesionChip sesion={sesion} />
                </>
              )}
            </div>
          </header>
          {children}
        </Providers>
      </body>
    </html>
  );
}

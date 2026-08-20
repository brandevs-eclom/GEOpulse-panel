import Link from "next/link";

import { InformeCompletoView } from "@/lib/report/InformeCompletoView";
import { InformeLiteView } from "@/lib/report/InformeLiteView";
import type { InformeLite } from "@/lib/shared/report";
import type { InformeCompleto } from "@/lib/shared/report-completo";
// Fixtures (docs/): permiten verificar el render de punta a punta sin llamar a
// n8n ni gastar una ejecucion de pago (docs/05).
import fixtureCompleto from "../../../docs/ejemplo-informe-completo.json";
import fixtureLite from "../../../docs/ejemplo-informe-lite.json";

/**
 * Página de verificación del render. Provisional: el detalle de ejecución usa
 * exactamente los mismos componentes, pero leyendo el informe de la BD.
 */
export default async function PreviewInforme({
  searchParams,
}: {
  searchParams: Promise<{ tipo?: string }>;
}) {
  const { tipo } = await searchParams;
  const completo = tipo === "completo";

  return (
    // 1100px: el mismo ancho que .gp-main en el detalle de ejecución, para que
    // lo que se ve aquí sea lo que se verá de verdad (el original usa 1140).
    <main style={{ maxWidth: 1100, margin: "0 auto", padding: "28px 20px 64px" }}>
      <div
        style={{
          display: "flex",
          gap: 10,
          alignItems: "center",
          marginBottom: 22,
        }}
      >
        <span style={{ color: "var(--muted)", fontSize: 13 }}>
          Previsualización con fixture ·
        </span>
        <Link
          href="/preview-informe"
          className="gp-badge"
          style={{
            background: completo ? "var(--muted-soft)" : "var(--dark)",
            color: completo ? "var(--text-muted)" : "#fff",
            textDecoration: "none",
          }}
        >
          LITE
        </Link>
        <Link
          href="/preview-informe?tipo=completo"
          className="gp-badge"
          style={{
            background: completo ? "var(--dark)" : "var(--muted-soft)",
            color: completo ? "#fff" : "var(--text-muted)",
            textDecoration: "none",
          }}
        >
          Completo
        </Link>
      </div>

      {/* La jerarquia del informe empieza en h2 (cada seccion). Sin un h1 en la
          pagina, el documento arrancaria en h2 y el indice de encabezados de un
          lector de pantalla quedaria descabezado. El detalle de ejecucion ya
          tiene el suyo. */}
      <h1 className="gp-h2" style={{ marginBottom: 18 }}>
        Previsualización del informe {completo ? "COMPLETO" : "LITE"}
      </h1>

      {completo ? (
        <InformeCompletoView
          informe={fixtureCompleto as unknown as InformeCompleto}
        />
      ) : (
        <InformeLiteView informe={fixtureLite as unknown as InformeLite} />
      )}
    </main>
  );
}

/**
 * Convierte el informe TAL COMO SE VE en el panel en un documento HTML autónomo
 * para Gotenberg.
 *
 * Por qué así y no con una plantilla aparte: el PDF debe llevar EXACTAMENTE lo que
 * genera el análisis (LITE o COMPLETO). Mantener una segunda maqueta del COMPLETO
 * en n8n (la vista tiene ~2.000 líneas) se desincronizaría al primer cambio, y de
 * hecho la primera versión pasaba el COMPLETO por la plantilla del LITE y salía casi
 * vacío. Aquí se reutiliza el mismo render de React:
 *   · se clona el DOM del informe (sin el chrome del panel: .gp-no-print),
 *   · se incrusta TODO el CSS de la página (con las url() hechas absolutas, para
 *     que Gotenberg encuentre fuentes e imágenes de /_next/static, que son públicas),
 *   · las hojas de otros dominios (Google Fonts) van como <link>,
 *   · se añade la marca brandevs: cabecera, marca de agua y pie con contacto.
 * Gotenberg imprime en modo "print", así que se aplican los @media print que ya
 * traen las vistas (desplegables abiertos, sin botones).
 */

const MARCA_CSS = `
.gp-pdf-wm{position:fixed;top:48%;left:50%;transform:translate(-50%,-50%) rotate(-27deg);
  font:800 110px "Space Grotesk",sans-serif;letter-spacing:-3px;color:#17130f;opacity:.045;
  z-index:9999;pointer-events:none;white-space:nowrap}
.gp-pdf-wm span{color:#E74C57}
.gp-pdf-logo{font:800 17px "Space Grotesk",sans-serif;letter-spacing:-.5px;color:#17130f}
.gp-pdf-logo i{color:#E74C57;font-style:normal}
.gp-pdf-agc{display:flex;justify-content:space-between;align-items:center;
  border-bottom:1px solid #e7e2db;padding-bottom:8px;margin-bottom:14px}
.gp-pdf-agc-t{font:600 10px Manrope,sans-serif;color:#8a8178;text-transform:uppercase;letter-spacing:.1em}
.gp-pdf-ft{margin-top:28px;border-top:2px solid #17130f;padding-top:10px;display:flex;
  justify-content:space-between;align-items:flex-end;gap:16px;break-inside:avoid}
.gp-pdf-ft-d{font:500 10px/1.7 Manrope,sans-serif;color:#5b544c;text-align:right}
body.gp-pdf{background:#fff;margin:0}
.gp-pdf-doc{padding:0 2px}
`;

const PIE =
  '<div class="gp-pdf-ft"><div class="gp-pdf-logo">brandevs<i>.</i></div>' +
  '<div class="gp-pdf-ft-d">Travesía de la Fragua 2, nº 7 · 28470 Cercedilla, Madrid · España<br>' +
  "+34 918 523 960 · info@brandevs.com · brandevs.com</div></div>";

function absolutizarUrls(css: string, base: string): string {
  return css.replace(/url\(\s*(['"]?)([^'")]+)\1\s*\)/g, (todo, _q, u: string) => {
    if (/^(data:|https?:|blob:|#)/i.test(u)) return todo;
    try {
      return `url("${new URL(u, base).href}")`;
    } catch {
      return todo;
    }
  });
}

export function htmlDelInforme(raiz: HTMLElement): string {
  const css: string[] = [];
  const enlaces: string[] = [];

  for (const hoja of Array.from(document.styleSheets)) {
    try {
      const reglas = Array.from(hoja.cssRules)
        .map((r) => r.cssText)
        .join("\n");
      css.push(absolutizarUrls(reglas, hoja.href || window.location.href));
    } catch {
      // Hoja de otro dominio (p. ej. Google Fonts): el navegador no deja leer sus
      // reglas, pero Gotenberg puede descargarla.
      if (hoja.href) enlaces.push(`<link rel="stylesheet" href="${hoja.href}">`);
    }
  }

  const clon = raiz.cloneNode(true) as HTMLElement;
  clon.querySelectorAll(".gp-no-print, script, noscript").forEach((n) => n.remove());
  // Red de seguridad además del @media print: ningún desplegable cerrado en el PDF.
  clon.querySelectorAll("details").forEach((d) => d.setAttribute("open", ""));
  clon.querySelectorAll<HTMLImageElement>("img[src]").forEach((img) => {
    img.setAttribute("src", img.src); // .src ya es absoluta
  });

  return (
    '<!doctype html><html lang="es"><head><meta charset="utf-8">' +
    "<title>Informe GeoPulse · brandevs</title>" +
    enlaces.join("") +
    `<style>${css.join("\n")}</style><style>${MARCA_CSS}</style>` +
    '</head><body class="gp-pdf">' +
    '<div class="gp-pdf-wm" aria-hidden="true">brandevs<span>.</span></div>' +
    '<div class="gp-pdf-doc">' +
    '<div class="gp-pdf-agc"><span class="gp-pdf-logo">brandevs<i>.</i></span>' +
    '<span class="gp-pdf-agc-t">Informe GeoPulse · Auditoría GEO</span></div>' +
    clon.outerHTML +
    PIE +
    "</div></body></html>"
  );
}

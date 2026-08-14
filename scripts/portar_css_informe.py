#!/usr/bin/env python3
"""Porta el CSS del informe del frontend original, acotandolo a la raiz del
render COMPLETO. No se reescribe a mano: se transcribe para no introducir
erratas de copia.

La raiz es `.informe.informe-completo` (dos clases) a proposito: report.css ya
define `.informe .dark`, `.informe .card`... para el LITE, y en Next.js los CSS
globales de ambos componentes acaban en el mismo bundle. Con una clase mas gana
siempre esta hoja, sin depender del orden de importacion.

Uso:  python scripts/portar_css_informe.py
Salida: src/lib/report/report-completo.css (se sobrescribe entero).
"""
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "C:/Users/Lenovo/Desktop/Claude Code/panel-starter/"
RAIZ = ".informe.informe-completo"

html = open(BASE + "workflows/geopulse-frontend-brandevs.html", encoding="utf-8").read()
css = re.search(r"<style>([\s\S]*?)</style>", html).group(1)
lineas = css.split("\n")
# Desde "/* Aviso de error */" hasta el final: antes solo hay reset, :root y el
# chrome de la pagina publica (cabecera, formulario, loader), que aqui no aplica.
cuerpo = "\n".join(lineas[73:])

# Reglas que no viajan: son del documento publico, no del informe.
DESCARTAR = re.compile(r"^(#results\b|footer\b|\.errbox \.btn\b)")
COMENTARIO = re.compile(r"/\*[\s\S]*?\*/")


def separar_comentarios(selector):
    """Los comentarios preceden al selector en el CSS original; el troceador los
    arrastra dentro. Se devuelven aparte para reemitirlos en su propia linea."""
    return COMENTARIO.findall(selector), COMENTARIO.sub("", selector).strip()


def trocear(texto):
    """Parte un bloque CSS en (selector, cuerpo) respetando anidamiento."""
    fuera = []
    prof = 0
    ini = 0
    sel_ini = 0
    for i, ch in enumerate(texto):
        if ch == "{":
            if prof == 0:
                sel_ini = ini
                sel = texto[sel_ini:i]
                cuerpo_ini = i + 1
            prof += 1
        elif ch == "}":
            prof -= 1
            if prof == 0:
                fuera.append((sel.strip(), texto[cuerpo_ini:i]))
                ini = i + 1
    return fuera


def prefijar(selector):
    partes = []
    for p in selector.split(","):
        p = p.strip()
        if not p:
            continue
        if DESCARTAR.match(p):
            return None
        partes.append(RAIZ + " " + p)
    return ", ".join(partes) if partes else None


salida = [
    "/*",
    " * Estilos del informe COMPLETO, portados 1:1 de",
    " * workflows/geopulse-frontend-brandevs.html (el frontend que genero el PDF",
    " * original). Se conserva su disposicion y su orden de bloques.",
    " *",
    " * GENERADO por scripts/portar_css_informe.py a partir del HTML de referencia.",
    " * Si hay que retocar el estilo base, mejor volver a portarlo que parchear aqui.",
    " * Los anadidos propios del panel van al final, marcados.",
    " *",
    f" * Todo cuelga de `{RAIZ}` para no pisar el render LITE,",
    " * que usa las mismas clases (.card, .dark, .sec...) con otras medidas.",
    " */",
    "",
]

for bruto, dentro in trocear(cuerpo):
    comentarios, selector = separar_comentarios(bruto)
    for c in comentarios:
        salida.append("\n" + c)
    if selector.startswith("@media"):
        internas = []
        for b2, d2 in trocear(dentro):
            c2, s2 = separar_comentarios(b2)
            p2 = prefijar(s2)
            if p2:
                internas.append("  %s{%s}" % (p2, d2.strip()))
        if internas:
            salida.append("%s{\n%s\n}" % (selector, "\n".join(internas)))
    elif selector.startswith("@"):
        continue
    else:
        p = prefijar(selector)
        if p:
            salida.append("%s{%s}" % (p, dentro.strip()))

EXTRAS = """

/* ============================================================
   A partir de aqui, anadidos del panel que el original no tenia.
   ============================================================ */

/* Base tipografica del documento original (vivia en su reset global; aqui se
   acota al informe para no tocar el resto del panel). `:where` no suma
   especificidad, asi que cualquier regla portada de arriba sigue ganando. */
.informe.informe-completo :where(p,h1,h2,h3,h4,ul,ol,li,figure,blockquote,table){margin:0;padding:0}
.informe.informe-completo h1, .informe.informe-completo h2,
.informe.informe-completo h3, .informe.informe-completo h4{font-family:var(--display);font-weight:800;
  letter-spacing:-.025em;line-height:1.15;color:var(--text)}
.informe.informe-completo .eyebrow{display:inline-block;font-size:.7rem;font-weight:700;letter-spacing:.14em;
  text-transform:uppercase;color:var(--accent);margin-bottom:12px}
.informe.informe-completo .eyebrow-dark{color:var(--accent)}

/* El aviso de confusion de entidad solo se monta cuando hay confusion: en el
   original vivia oculto y lo desvelaba JS. */
.informe.informe-completo .errbox{display:block}

/* Cruce que el workflow no hace: marcar si un sitio recomendado ya se tiene o
   si en realidad es la web de un competidor (no te puedes dar de alta ahi). */
.informe.informe-completo .marca-sitio{font:700 .58rem var(--ui);letter-spacing:.06em;text-transform:uppercase;
  padding:3px 9px;border-radius:var(--pill);white-space:nowrap}
.informe.informe-completo .m-presente{background:var(--ok-soft);color:var(--ok)}
.informe.informe-completo .m-falta{background:var(--muted-soft);color:var(--muted)}
.informe.informe-completo .m-competidor{background:var(--err-soft);color:var(--err)}

/* La pregunta que se le hizo a la IA, encima de la respuesta. Deliberadamente
   pequena y en gris: solo situa. El enfasis se lo queda la respuesta (.q-t),
   que conserva su tamano y su tipografia de display. */
.informe.informe-completo .quote .q-p{font-size:.78rem;font-weight:600;line-height:1.5;
  color:var(--muted);margin-bottom:8px}
.informe.informe-completo .quote .q-p::before{content:'P. ';font-weight:700;color:var(--accent)}

/* Ausencia de dato: se dice, no se disimula con un cero. */
.informe.informe-completo .sin-datos{color:var(--muted);font-style:italic}

/* JSON crudo para depurar. Va FUERA del div del informe (lo monta la pagina de
   detalle al final), asi que no lleva el prefijo de la raiz. */
.gp-json{margin-top:36px;border-top:1px solid var(--border);padding-top:18px}
.gp-json summary{cursor:pointer;font:700 .72rem var(--ui);letter-spacing:.08em;
  text-transform:uppercase;color:var(--muted)}
.gp-json pre{margin-top:14px;max-height:460px;overflow:auto;background:var(--muted-soft);
  border:1px solid var(--border);border-radius:var(--r-sm);padding:16px;font-size:.72rem;line-height:1.6}
"""

texto = "\n".join(salida) + "\n" + EXTRAS

# La primitiva Barra de React pinta <i>, el original pintaba <span>.
texto = texto.replace(".bar span{", ".bar i{")

open(BASE + "src/lib/report/report-completo.css", "w", encoding="utf-8").write(texto)
print("Escrito report-completo.css:", len(texto.splitlines()), "lineas")

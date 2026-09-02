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
import pathlib
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# La raiz del repo, deducida de la ubicacion de este fichero (scripts/..). Antes
# era una ruta absoluta de la maquina en la que se escribio, asi que el script
# solo funcionaba alli: en cualquier otro equipo reventaba con FileNotFoundError
# y, peor, un BASE mal puesto escribe el CSS fuera del repo sin avisar.
BASE = pathlib.Path(__file__).resolve().parent.parent.as_posix() + "/"
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
   Sistema de diseno del informe COMPLETO.
   Portado del mockup informe-brandevs-completo(2).html: paleta,
   layout de sidebar izquierdo, tarjetas de bloque con carril de
   estado, pestanas de dimensiones, etc.
   EXCEPCION del encargo: la fuente de titulares es Space Grotesk en
   TODAS las secciones (el mockup usaba Manrope; se mantiene Space
   Grotesk por peticion). Las secciones "16 preguntas" y "cuota de voz"
   conservan su estructura; solo heredan estos tokens.
   ============================================================ */

/* ------------------------------------------------------------------
   1. TOKENS  (paleta de brandevs.com, acotada a la raiz del informe para
   no repintar el chrome del panel). Los nombres antiguos se mantienen
   apuntando a los nuevos: la hoja portada de arriba sigue funcionando.

   REGLA DE LOS DOS ROJOS, que no se puede saltar sin romper AA:
     --accent (#E74C57) es el rojo de la web y da 3,53:1 sobre el papel:
     vale para FONDOS, iconos, trazos y bordes, NUNCA para texto.
     --accent-ink (#C62C38, 5,15:1 sobre papel / 5,50 sobre blanco) es el
     mismo tono con menos luz, y es el que se usa cuando el acento es
     texto. Es el mismo patron que ya existia con #EF3B2D / #D22C1F.
   El coral --accent-2 (#FF6A3D) da 2,67:1: en claro es SOLO relleno de
   degradado o fondo con texto oscuro encima; sobre el bloque oscuro si
   vale como texto (6,77:1).

   Los colores de estado NO vienen de la web: la web solo tiene verde y
   resuelve cualquier aviso con su propio rojo. Un informe necesita
   ok/warn/err/no-verificable distinguibles, asi que se conservan los del
   informe oscurecidos hasta pasar AA sobre los fondos nuevos.
   ------------------------------------------------------------------ */
.informe.informe-completo{
  --wrap:1000px;         /* columna de contenido (subida de 840: la tabla
                             de 7 columnas de cuota de voz no cabia) */
  --rail:260px;          /* sidebar izquierdo */
  --shell:1360px;        /* sidebar + contenido, centrado en el viewport */
  --head:70px;

  --paper:#FAF7F4;
  --card-bg:#FFFFFF;
  --panel-bg:#F0ECE8;    /* tercera superficie de la web (secciones alternas) */
  --ink:#17130F;
  --ink-soft:#6E675F;    /* 5,22:1 sobre papel */
  --faint:#76716A;       /* 4,53:1. Subido de #8A857D (3,43:1), que pintaba los th
                             de la tabla de cuota de voz, que no son decorativos */
  --line-c:rgba(23,19,15,.10);
  --line-soft:rgba(23,19,15,.05);
  --line-fuerte:rgba(23,19,15,.46);   /* 3,04:1 - bordes que SON el control */
  --dark:#100E0C;

  --accent:#E74C57;                    /* fondos, iconos, trazos. NO texto */
  --accent-2:#FF6A3D;                  /* coral: solo degradado o fondo */
  --accent-ink:#C62C38;                /* acento como TEXTO sobre papel, AA */
  --accent-soft:#FCECEE;

  --ok:#17734B;    --ok-soft:#E9F3EE;
  --warn:#8C6510;  --warn-soft:#FAF1DF;
  --err:#B42318;   --err-soft:#FBECEA;   /* granate: el error NO es el rojo de marca */
  --neu:#787168;   --neu-soft:#F1EEE9;
  --focus:#E74C57;

  /* El borde de un fondo suave: cada estado mezclado al 30% sobre su propio
     fondo. Antes eran ocho hex sueltos, con dos verdes y dos rosas distintos
     para exactamente lo mismo. */
  --ok-borde:#AACDBD;  --warn-borde:#D9C7A1;
  --err-borde:#E6B0AB; --accent-borde:#F6BCC1;

  /* Carril de las barras de dato. La web lo tiene solido (#E6E0D8) y no
     translucido: aqui la barra ES el dato, y --line-c a .10 de alpha da
     1,23:1 contra el papel, o sea que el carril no se veria. */
  --track:#E6E0D8;

  /* Escala de radios de la web (el radio crece con el padding). */
  --r:18px;  --r-sm:12px;  --r-xs:8px;
  --r-lg:26px;                          /* paneles y bloques oscuros */
  --pill:100px;

  /* Tipografia de la web: Space Grotesk en titulares, Manrope en cuerpo,
     Newsreader cursiva para el acento rojo dentro de un titular. */
  --display:'Space Grotesk',system-ui,sans-serif;
  --ui:'Manrope',system-ui,sans-serif;
  --serif:'Newsreader',Georgia,serif;

  /* Curva de easing de marca y sombra de elevacion (roja, no neutra). */
  --curva:cubic-bezier(.2,.7,.2,1);
  --sombra-hover:0 36px 64px -32px rgba(231,76,87,.42);
  --sombra-panel:0 30px 70px -46px rgba(23,19,15,.45);

  /* Puentes con los nombres que usa la hoja portada de arriba. */
  --bg:var(--paper);
  --surface:var(--card-bg);
  --text:var(--ink);
  --text-muted:var(--ink-soft);
  --muted:var(--ink-soft);
  --muted-soft:var(--neu-soft);
  --border:var(--line-c);
  --border-strong:var(--line-fuerte);
  --on-dark:#FFFFFF;
  --on-dark-muted:rgba(255,255,255,.66);   /* 8,60:1 sobre --dark */
  --on-dark-faint:rgba(255,255,255,.55);   /* 6,26:1 - rotulos y th sobre oscuro */
  --dark-soft:rgba(255,255,255,.14);
  --dark-line:rgba(255,255,255,.12);
  --accent-dark:var(--accent-ink);
  --accent-light:var(--accent-2);
  --r-card:var(--r);
  --r-card-lg:var(--r-lg);
  --r-panel:var(--r-lg);
  --r-item:var(--r-sm);

  background:var(--paper);
  color:var(--ink);
  font-family:var(--ui);
  font-size:15px;
  line-height:1.6;
}

/* Modo oscuro. El gancho `html.brandevs-dark` es EXACTAMENTE la clase que
   pone el conmutador de brandevs.com (la aplica a documentElement y guarda
   'brandevs-theme' en localStorage), asi que si este informe se sirve dentro
   de la web hereda el tema sin codigo nuevo. En el panel no hay interruptor
   todavia, asi que hoy este bloque solo se activa desde la web. */
html.brandevs-dark .informe.informe-completo,
[data-theme="dark"] .informe.informe-completo{
  --paper:#0E0C0A; --card-bg:#1B1714; --panel-bg:#1A1613;
  --ink:#F3F0EB; --ink-soft:var(--on-dark-faint);
  --faint:#8A8378;                       /* 4,75:1 sobre la tarjeta oscura */
  --line-c:rgba(255,255,255,.12); --line-soft:rgba(255,255,255,.07);
  --line-fuerte:rgba(255,255,255,.42);
  --accent-ink:#FF8A93; --accent-soft:rgba(231,76,87,.20);
  --ok:#48C98A; --ok-soft:#12271C; --warn:#E8A33C; --warn-soft:#2A1E08;
  --err:#FF8F84; --err-soft:#2B1310; --neu:var(--on-dark-faint); --neu-soft:rgba(255,255,255,.07);
  --border-strong:var(--line-fuerte);
  --sombra-panel:0 30px 70px -46px rgba(0,0,0,.7);
}

/* ------------------------------------------------------------------
   2. TIPOGRAFIA  (Space Grotesk en titulares, Manrope en cuerpo)

   El peso de los titulares baja de 800 a 600, que es el de la web. No es
   un capricho: layout.tsx solo carga Space Grotesk hasta 700, asi que el
   800 se estaba renderizando como negrita SINTETICA (el navegador engorda
   la cara de 700). Con 600 el titular es el real y ademas casa con
   brandevs.com, que nunca pasa de 600 en un titular.
   ------------------------------------------------------------------ */
.informe.informe-completo h1,
.informe.informe-completo h2,
.informe.informe-completo h3,
.informe.informe-completo h4{font-family:var(--display);letter-spacing:-.02em;color:var(--ink)}
.informe.informe-completo .sec h2{font:600 clamp(1.5rem,3.2vw,1.95rem)/1.08 var(--display);letter-spacing:-.02em;margin:0 0 10px}
.informe.informe-completo .panel h3,
.informe.informe-completo .card h3{font:600 1.05rem/1.25 var(--display);letter-spacing:-.02em}
.informe.informe-completo .ring-num,
.informe.informe-completo .t-val,
.informe.informe-completo .d-pct{font-family:var(--display)}
.informe.informe-completo .eyebrow{color:var(--accent-ink)}

/* Los 800 que quedan en la parte transcrita. Se listan uno a uno con la MISMA
   especificidad que alli (p.ej. `.tile .t-val`, dos clases) porque si no gana
   la regla transcrita, que va antes pero pesa mas. */
.informe.informe-completo .ring-num,
.informe.informe-completo .tile .t-val,
.informe.informe-completo .v-chip,
.informe.informe-completo .d-pct,
.informe.informe-completo .act .num,
.informe.informe-completo .sb-score-n,
.informe.informe-completo .ee-global b,
.informe.informe-completo .wins h4{font-weight:600}

/* Acento en Newsreader cursiva dentro de un titular: el gesto tipografico
   de la marca. En la web el <em> repite literalmente el shorthand del
   padre y solo cambia familia, estilo y color, SIN heredar el tracking
   negativo; aqui se hace igual con font-style/family/color y
   letter-spacing:normal. Sale en --accent-ink, no en --accent: es texto. */
.informe.informe-completo .sec h2 em,
.informe.informe-completo .hero-verdict em,
.informe.informe-completo .score-row h3 em{
  font-family:var(--serif);font-style:italic;font-weight:500;
  letter-spacing:normal;color:var(--accent-ink)}
.informe.informe-completo .dark em{color:var(--accent-2)}   /* 6,77:1 sobre --dark */

/* El texto se ajusta a su contenedor; solo se acota la entradilla. */
.informe.informe-completo .exec,
.informe.informe-completo .card-text,
.informe.informe-completo .m-detail,
.informe.informe-completo .q-body li{max-width:100%;overflow-wrap:anywhere}
.informe.informe-completo .sec p{max-width:62ch}

/* ------------------------------------------------------------------
   3. LAYOUT  ·  sidebar izquierdo + columna de contenido
   El conjunto se sale del ancho de .gp-main y se centra en el viewport.
   ------------------------------------------------------------------ */
@media(min-width:1000px){
  .informe.informe-completo{
    position:relative;
    left:50%;
    transform:translateX(-50%);
    width:min(var(--shell), calc(100vw - 40px));
  }
  .informe.informe-completo .con-indice{
    display:grid;
    grid-template-columns:var(--rail) minmax(0,1fr);
    gap:0;
    align-items:start;
  }
  /* el contenido se acota a la medida de lectura, centrado en su columna */
  .informe.informe-completo .con-indice > div:not(.indice){
    max-width:var(--wrap);
    margin:0 auto;
    padding:0 28px;
    min-width:0;
  }
}
@media(max-width:999px){
  .informe.informe-completo .con-indice > div:not(.indice){min-width:0}
}

/* ------------------------------------------------------------------
   4. SIDEBAR  ·  .indice re-estilizado como nav numerada del mockup
   ------------------------------------------------------------------ */
.informe.informe-completo .indice{margin:0 0 24px}
.informe.informe-completo .indice h2{font:700 .64rem var(--ui);letter-spacing:.12em;text-transform:uppercase;color:var(--faint);margin:0 0 12px}
.informe.informe-completo .indice ol{list-style:none;display:flex;flex-wrap:wrap;gap:6px;margin:0;padding:0;counter-reset:idx}
.informe.informe-completo .indice a{counter-increment:idx;display:inline-flex;align-items:center;gap:9px;
  padding:8px 13px;border:1px solid var(--line-c);border-radius:var(--pill);background:var(--card-bg);
  font:600 .84rem var(--ui);color:var(--ink-soft);text-decoration:none;line-height:1.3;transition:.15s}
.informe.informe-completo .indice a::before{content:counter(idx,decimal-leading-zero);font:700 .66rem var(--display);color:var(--faint)}
.informe.informe-completo .indice a:hover{border-color:var(--faint);color:var(--ink)}
.informe.informe-completo .indice a[aria-current="true"],
.informe.informe-completo .indice a.active{color:var(--accent-ink);background:var(--err-soft);border-color:transparent}

@media(min-width:1000px){
  .informe.informe-completo .con-indice > .indice{
    position:sticky;
    top:calc(var(--head) + 12px);
    align-self:start;
    max-height:calc(100vh - var(--head) - 24px);
    overflow:auto;
    margin:0;
    padding:26px 22px 34px;
    border-right:1px solid var(--line-c);
  }
  .informe.informe-completo .con-indice > .indice ol{flex-direction:column;flex-wrap:nowrap;gap:1px}
  .informe.informe-completo .con-indice > .indice a{width:100%;border:none;background:none;border-radius:8px;
    border-left:2px solid transparent;padding:8px 12px}
  .informe.informe-completo .con-indice > .indice a:hover{background:var(--card-bg)}
  .informe.informe-completo .con-indice > .indice a[aria-current="true"],
  .informe.informe-completo .con-indice > .indice a.active{border-left-color:var(--accent);background:var(--err-soft)}
}

/* Mini-anillo de score al pie del sidebar (lo pinta IndiceInforme). */
.informe.informe-completo .sb-score{display:flex;align-items:center;gap:12px;margin-top:24px;padding-top:20px;border-top:1px solid var(--line-c)}
.informe.informe-completo .sb-score-ring{width:48px;height:48px;flex:0 0 auto;position:relative;display:flex;align-items:center;justify-content:center}
.informe.informe-completo .sb-score-ring svg{position:absolute;inset:0}
.informe.informe-completo .sb-score-n{position:relative;font:600 1.05rem var(--display)}
.informe.informe-completo .sb-score-l{font:400 .66rem/1.3 var(--ui);color:var(--ink-soft)}
.informe.informe-completo .sb-score-l b{display:block;font:700 .82rem var(--display);color:var(--ink)}

/* ------------------------------------------------------------------
   5. DESTINO DE ANCLA
   ------------------------------------------------------------------ */
.informe.informe-completo [id]{scroll-margin-top:calc(var(--head) + 20px)}

/* ------------------------------------------------------------------
   6. HERO  ·  bloque oscuro de diagnostico
   ------------------------------------------------------------------ */
/* El bloque oscuro de la web lleva SIEMPRE un halo rojo radial que entra
   desde arriba y se recorta con overflow:hidden. Se reproduce con ::before
   para no tocar el markup del render. */
.informe.informe-completo .dark{position:relative;overflow:hidden;background:var(--dark);color:var(--on-dark);border-radius:var(--r-lg);padding:clamp(26px,4vw,42px);margin:0 0 18px;box-shadow:none}
.informe.informe-completo .dark::before{content:"";position:absolute;top:-150px;left:50%;transform:translateX(-50%);width:520px;height:380px;background:radial-gradient(circle,rgba(231,76,87,.30),transparent 70%);pointer-events:none}
.informe.informe-completo .dark > *{position:relative}
/* Los colores de estado estan calculados para leerse sobre PAPEL: sobre el
   bloque oscuro se quedan cortos (--err #B42318 sobre #100E0C da 2,93:1, y el
   anillo de un GEO Score bajo casi no se veria). Se reasignan a la variante
   clara del mismo tono. tono() devuelve var(--ok)/var(--warn)/var(--err), asi
   que el anillo pintado desde React hereda la sustitucion sin tocar TSX. */
.informe.informe-completo .dark,
.informe.informe-completo .panel-dark{--ok:#35B07A;--warn:#D9A340;--err:#F0736A;--neu:#9E978C;--muted:#9E978C}
.informe.informe-completo .score-row{display:flex;gap:30px;align-items:flex-start}
.informe.informe-completo .dark .eyebrow{color:var(--accent);display:block;margin-bottom:7px}
.informe.informe-completo .score-row h2,
.informe.informe-completo .score-row h3,
.informe.informe-completo .hero-verdict{font:600 clamp(1.3rem,3vw,1.6rem)/1.15 var(--display);color:var(--on-dark);margin-bottom:11px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
/* Pildora del veredicto. Antes era texto blanco sobre --accent (3,77:1, no
   pasa AA en un texto de 10px). Ahora el fondo es --accent-ink (5,50:1). */
.informe.informe-completo .verdict-tag{font:700 .64rem var(--ui);letter-spacing:.1em;text-transform:uppercase;padding:5px 12px;border-radius:var(--pill);background:var(--accent-ink);color:#fff}
.informe.informe-completo .verdict-tag.n-invisible{background:var(--accent-ink);color:#fff}
.informe.informe-completo .verdict-tag.n-emergente{background:var(--warn);color:#fff}
.informe.informe-completo .verdict-tag.n-competitiva{background:#2F5B75;color:#fff}
.informe.informe-completo .verdict-tag.n-dominante{background:var(--ok);color:#fff}
.informe.informe-completo .diagnostico{font:400 .95rem/1.7 var(--ui);color:var(--on-dark-muted);max-width:none;margin:0}
.informe.informe-completo .diagnostico b{color:var(--on-dark);font-weight:600}
.informe.informe-completo .ring{width:118px;height:118px;flex:0 0 118px}
.informe.informe-completo .ring-in{background:var(--dark)}
.informe.informe-completo .ring-num{font-size:2.4rem;font-weight:600;color:var(--on-dark)}
.informe.informe-completo .ring-lbl{color:var(--on-dark-muted)}
@media(max-width:560px){
  .informe.informe-completo .score-row{flex-direction:column;align-items:center;text-align:center}
  .informe.informe-completo .score-row h3{justify-content:center}
}

/* ------------------------------------------------------------------
   7. TARJETAS DE AREA  ·  score por area, clicables
   ------------------------------------------------------------------ */
.informe.informe-completo .areas{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 8px}
.informe.informe-completo .areas .tile{flex:1 1 calc(25% - 8px);background:var(--card-bg);border:1px solid var(--line-c);border-radius:var(--r-sm);padding:16px 15px;box-shadow:none;transition:transform .5s var(--curva),box-shadow .5s,border-color .5s}
/* Elevacion de la web: sube 8px y la sombra es ROJA, no neutra. */
.informe.informe-completo a.tile-link:hover{transform:translateY(-4px);box-shadow:var(--sombra-hover);border-color:rgba(231,76,87,.35)}
.informe.informe-completo .t-lbl{font:700 .66rem var(--ui);letter-spacing:.09em;text-transform:uppercase;color:var(--ink-soft)}
.informe.informe-completo .t-val{font:600 2rem/1.1 var(--display);letter-spacing:-.02em;margin:6px 0 8px}
.informe.informe-completo .bar{height:5px;border-radius:3px;background:var(--track,#E6E0D8)}
.informe.informe-completo .bar i{border-radius:3px}
@media(max-width:640px){.informe.informe-completo .areas .tile{flex:1 1 calc(50% - 5px)}}

/* ------------------------------------------------------------------
   8. CABECERA DE SECCION
   ------------------------------------------------------------------ */
.informe.informe-completo .sec{margin:52px 0 22px}
/* El eyebrow de la web es un punto rojo de 7px + versalitas rojas con
   tracking .16em. El punto se pinta con ::before para no tocar el markup.
   Aqui NUNCA pulsa: en la web solo pulsa donde hay una accion que hacer,
   y un informe no la tiene. */
.informe.informe-completo .sec .eyebrow{display:inline-flex;align-items:center;gap:9px;font:600 .72rem/1 var(--ui);letter-spacing:.16em;text-transform:uppercase;margin-bottom:14px}
/* El punto se declara para TODO eyebrow (tambien el del bloque oscuro, que
   es display:block) y en inline-block: un ::before inline ignora width y
   height, y el punto desapareceria sin avisar. */
.informe.informe-completo .eyebrow::before{content:"";display:inline-block;vertical-align:middle;margin-bottom:1px;width:7px;height:7px;border-radius:50%;background:var(--accent);flex:0 0 7px;margin-right:9px}
.informe.informe-completo .sec .eyebrow::before{margin-right:0}
.informe.informe-completo .sec p{color:var(--ink-soft);font-size:.95rem;line-height:1.6;margin:0}

/* ------------------------------------------------------------------
   9. TARJETAS DE BLOQUE  ·  .card / .panel con cabecera y punto de estado
   ------------------------------------------------------------------ */
.informe.informe-completo .card,
.informe.informe-completo .panel:not(.panel-dark){background:var(--card-bg);border:1px solid var(--line-c);border-radius:var(--r);padding:6px 22px 16px;margin-bottom:12px;box-shadow:none}
.informe.informe-completo .panel:not(.panel-dark){padding:18px 20px}
.informe.informe-completo .card-top{padding:14px 0 4px;display:flex;align-items:center;gap:10px;border:none}
.informe.informe-completo .card-eyebrow{font:700 .64rem var(--ui);letter-spacing:.1em;text-transform:uppercase;color:var(--accent-ink)}
.informe.informe-completo .card h3{margin:0 0 2px;padding:0;border:none}
.informe.informe-completo .card > h3{padding:2px 0 8px}
/* punto de estado a la derecha de la cabecera */
.informe.informe-completo .card-top .dot{margin-left:auto}
.informe.informe-completo .dot{width:16px;height:16px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:10px;color:#fff;font-weight:700}
.informe.informe-completo .dot-ok{background:var(--ok)} .informe.informe-completo .dot-warning{background:var(--warn)}
.informe.informe-completo .dot-error{background:var(--err)} .informe.informe-completo .dot-muted{background:var(--neu)}

/* ------------------------------------------------------------------
   10. METRICA  ·  fila con carril de estado a la izquierda
   ------------------------------------------------------------------ */
.informe.informe-completo .metric{position:relative;padding:13px 0 13px 14px;border-top:1px solid var(--line-soft)}
.informe.informe-completo .metric:first-of-type{border-top:none}
/* el carril: color por estado, leido de la clase del contenedor */
.informe.informe-completo .metric::before{content:'';position:absolute;left:0;top:13px;bottom:13px;width:3px;border-radius:3px;background:var(--neu);opacity:.85}
.informe.informe-completo .metric.st-ok::before{background:var(--ok)}
.informe.informe-completo .metric.st-warning::before{background:var(--warn)}
.informe.informe-completo .metric.st-error::before{background:var(--err)}
.informe.informe-completo .m-row{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
.informe.informe-completo .m-lbl{font-weight:600;font-size:.92rem;color:var(--ink)}
.informe.informe-completo .m-val{font-size:.82rem;font-weight:600;text-align:right}
.informe.informe-completo .m-val.v-ok{color:var(--ok)} .informe.informe-completo .m-val.v-warning{color:var(--warn)}
.informe.informe-completo .m-val.v-error{color:var(--err)} .informe.informe-completo .m-val.v-muted{color:var(--ink-soft)}
.informe.informe-completo .m-detail{font-size:.83rem;color:var(--ink-soft);line-height:1.5;margin-top:4px}
.informe.informe-completo .m-detail a,
.informe.informe-completo .srcs a{color:var(--ink-soft);word-break:break-all;text-decoration:underline;text-underline-offset:2px}

/* etiquetas / chips */
.informe.informe-completo .tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}
.informe.informe-completo .tag{font:500 .73rem var(--ui);padding:3px 9px;border-radius:var(--pill);background:var(--neu-soft);color:var(--ink-soft);border:none}
.informe.informe-completo .tag-ok{background:var(--ok-soft);color:var(--ok)}
.informe.informe-completo .tag-neg{background:var(--err-soft);color:var(--err)}
.informe.informe-completo .tag-accent{background:var(--accent-soft);color:var(--accent-ink)}

/* ------------------------------------------------------------------
   11. E-E-A-T-C  ·  barras
   ------------------------------------------------------------------ */
.informe.informe-completo .eeatc{margin-bottom:11px}
.informe.informe-completo .eeatc .m-row{margin-bottom:6px}
.informe.informe-completo .eeatc .bar{height:7px;border-radius:4px;background:var(--line-c)}
.informe.informe-completo .ee-global{display:flex;align-items:center;justify-content:space-between;margin-top:14px;padding-top:14px;border-top:1px solid var(--line-c)}
.informe.informe-completo .ee-global b{font:600 1.5rem var(--display)}

/* ------------------------------------------------------------------
   12. TABLAS  (Modelo por modelo, KPIs). Cuota de voz KEEP.
   ------------------------------------------------------------------ */
.informe.informe-completo .tw table{font-size:.85rem}
.informe.informe-completo .tw th{font:700 .66rem var(--ui);letter-spacing:.05em;text-transform:uppercase;color:var(--faint);padding:8px 10px;border-bottom:1px solid var(--line-c)}
.informe.informe-completo .tw td{padding:11px 10px;border-bottom:1px solid var(--line-soft);color:var(--ink)}
.informe.informe-completo .tw td.strong{font-family:var(--display);font-weight:700;color:var(--ink)}
.informe.informe-completo td a{color:var(--accent-ink);text-decoration:underline;text-underline-offset:2px}

/* ------------------------------------------------------------------
   13. GAPS · OPORTUNIDADES · CITAS · PLAN · QUICKWINS · KPIs
   ------------------------------------------------------------------ */
.informe.informe-completo .gap{padding:13px 0;border-top:1px solid var(--line-soft)}
.informe.informe-completo .gap:first-of-type{border-top:none}
.informe.informe-completo .g-t{font:600 .92rem var(--ui);color:var(--err);margin-bottom:5px;display:flex;gap:8px;align-items:baseline}
.informe.informe-completo .g-t::before{content:'';width:7px;height:7px;border-radius:50%;background:var(--err);flex:0 0 auto}
.informe.informe-completo .g-b{font-size:.82rem;color:var(--ink-soft);line-height:1.5}
.informe.informe-completo .g-b b{color:var(--ink)}

.informe.informe-completo .wins{background:var(--ok-soft);border:1px solid var(--ok-borde);border-radius:var(--r);padding:16px 18px;margin-top:12px}
.informe.informe-completo .wins h4{font:600 1rem var(--display);color:var(--ok);margin-bottom:10px}
.informe.informe-completo .wins ul{list-style:none;display:flex;flex-direction:column;gap:8px;padding:0;margin:0}
.informe.informe-completo .wins li{font-size:.86rem;line-height:1.5;padding-left:18px;position:relative}
.informe.informe-completo .wins li::before{content:'→';position:absolute;left:0;color:var(--ok);font-weight:700}

.informe.informe-completo .quote{border-left:3px solid var(--line-c);padding:4px 0 4px 14px;margin:12px 0}
.informe.informe-completo .quote .q-p{font-size:.8rem;color:var(--ink-soft);margin-bottom:5px}
.informe.informe-completo .quote .q-p::before{content:'P. ';font-weight:700;color:var(--accent-ink)}
.informe.informe-completo .quote .q-t{font:600 .98rem/1.45 var(--display);color:var(--ink)}
.informe.informe-completo .quote .q-m{font:700 .68rem var(--ui);letter-spacing:.06em;text-transform:uppercase;color:var(--faint);margin-top:5px}

.informe.informe-completo .act{display:flex;gap:14px;padding:16px 0;border-top:1px solid var(--line-soft);align-items:flex-start}
.informe.informe-completo .act:first-of-type{border-top:none}
.informe.informe-completo .act .num{flex:0 0 auto;width:26px;height:26px;border-radius:50%;background:var(--dark);color:var(--on-dark);font:600 .82rem var(--display);display:flex;align-items:center;justify-content:center}
.informe.informe-completo .act .num.p-alta{background:var(--accent)}
.informe.informe-completo .act .a-tag{font:700 .6rem var(--ui);letter-spacing:.06em;text-transform:uppercase;color:var(--accent-ink);margin-bottom:4px}
.informe.informe-completo .act .a-txt{font:600 .94rem/1.4 var(--ui);color:var(--ink)}
.informe.informe-completo .act .a-sub,.informe.informe-completo .act .a-ev{font-size:.82rem;color:var(--ink-soft);line-height:1.5;margin-top:4px}

.informe.informe-completo .gp-kpi-actual{color:var(--err);font-weight:600}
.informe.informe-completo .gp-kpi-objetivo{color:var(--ok);font-weight:600}

/* ------------------------------------------------------------------
   14. PLAN DE ENLACES  (donde ganar presencia)
   ------------------------------------------------------------------ */
.informe.informe-completo .reco-cat{font:700 .66rem var(--ui);letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin:14px 0 6px}
.informe.informe-completo .reco-item{padding:12px 0;border-top:1px solid var(--line-soft)}
.informe.informe-completo .reco-item:first-child{border-top:none}
.informe.informe-completo .reco-site{font:700 .9rem var(--display);color:var(--ink)}
.informe.informe-completo .reco-link{text-decoration:underline;text-underline-offset:2px;color:var(--accent-ink)}
.informe.informe-completo .reco-why{font-size:.82rem;color:var(--ink-soft);line-height:1.5;margin-top:5px}
.informe.informe-completo .reco-src,.informe.informe-completo .marca-sitio{font:700 .6rem var(--ui);letter-spacing:.03em;text-transform:uppercase;padding:2px 7px;border-radius:4px}
.informe.informe-completo .src-cita{background:var(--dark);color:#fff}
.informe.informe-completo .src-desc{background:#EDF2F6;color:#2F5B75}
.informe.informe-completo .m-presente{background:var(--ok-soft);color:var(--ok)}
.informe.informe-completo .m-falta{background:var(--neu-soft);color:var(--neu)}
.informe.informe-completo .m-competidor{background:var(--err-soft);color:var(--err)}
.informe.informe-completo .reco-pri{font:700 .62rem var(--ui);letter-spacing:.04em;text-transform:uppercase;margin-left:auto}
.informe.informe-completo .reco-pri.pri-alta{color:var(--err)} .informe.informe-completo .reco-pri.pri-media{color:var(--warn)} .informe.informe-completo .reco-pri.pri-baja{color:var(--neu)}
.informe.informe-completo .sin-datos{color:var(--faint);font-style:italic}

/* ------------------------------------------------------------------
   15. PESTANAS de las 4 dimensiones
   ------------------------------------------------------------------ */
.informe.informe-completo .tabs{display:flex;gap:4px;border-bottom:1px solid var(--line-c);margin:0 0 4px;overflow-x:auto;scrollbar-width:none}
.informe.informe-completo .tabs::-webkit-scrollbar{display:none}
.informe.informe-completo .tab{flex:0 0 auto;background:none;border:none;font:600 .85rem var(--ui);color:var(--ink-soft);padding:11px 14px;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;white-space:nowrap;display:flex;align-items:center;gap:7px}
.informe.informe-completo .tab .d{width:7px;height:7px;border-radius:50%;background:var(--neu)}
.informe.informe-completo .tab.st-ok .d{background:var(--ok)} .informe.informe-completo .tab.st-warning .d{background:var(--warn)} .informe.informe-completo .tab.st-error .d{background:var(--err)}
.informe.informe-completo .tab[aria-selected="true"]{color:var(--ink);border-bottom-color:var(--accent)}
.informe.informe-completo .tab-panel{padding:16px 0 4px}
.informe.informe-completo .tab-panel .card{border:none;padding:0;margin:0}
.informe.informe-completo .dim-impl{background:var(--neu-soft);border-radius:var(--r-sm);padding:11px 14px;margin-top:12px;font-size:.83rem;line-height:1.5}
.informe.informe-completo .dim-impl b{color:var(--accent-ink)}

/* ------------------------------------------------------------------
   16. ACCESIBILIDAD
   ------------------------------------------------------------------ */
.informe.informe-completo .sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.informe.informe-completo a:focus-visible,
.informe.informe-completo button:focus-visible,
.informe.informe-completo summary:focus-visible,
.informe.informe-completo [tabindex]:focus-visible{outline:2px solid var(--focus);outline-offset:2px;border-radius:var(--r-xs)}
@media (prefers-reduced-motion: reduce){
  .informe.informe-completo *,.informe.informe-completo *::before,.informe.informe-completo *::after{animation-duration:.001ms !important;animation-iteration-count:1 !important;transition-duration:.001ms !important;scroll-behavior:auto !important}
}

/* ------------------------------------------------------------------
   17. ESTADISTICAS ENLAZADAS  (areas y KPIs con ancla)
   ------------------------------------------------------------------ */
.informe.informe-completo .tile-link{display:block;text-decoration:none;color:inherit;transition:.15s}

/* ------------------------------------------------------------------
   18. IMPRESION
   ------------------------------------------------------------------ */
@media print{
  .informe.informe-completo{--paper:#fff;--card-bg:#fff;--panel-bg:#fff;--ink:#000;position:static;left:auto;transform:none;width:auto;max-width:none}
  /* Los dos bloques de fondo oscuro (hero .dark y cuota de voz .panel-dark)
     traen su texto en blanco. Sin esto el navegador tira el fondo al imprimir
     y queda texto blanco sobre papel blanco: el hero se salvaba por la regla
     de report.css:585, la cuota de voz no. Se fuerza el fondo en los dos. */
  .informe.informe-completo .dark,
  .informe.informe-completo .panel-dark{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .informe.informe-completo .dark::before{display:none}   /* el halo rojo no aporta en papel */
  .informe.informe-completo .con-indice{display:block}
  .informe.informe-completo .con-indice > .indice{position:static;border-right:none;max-height:none;overflow:visible}
  .informe.informe-completo .card,.informe.informe-completo .panel{box-shadow:none;border-color:#bbb}
  .informe.informe-completo .q-body{display:block !important}
  .informe.informe-completo tr.hide{display:table-row !important}
  .informe.informe-completo .toggle,.informe.informe-completo .q-pm{display:none}
  .informe.informe-completo .tab-panel{display:block !important}
  .informe.informe-completo .card,.informe.informe-completo .act,.informe.informe-completo .gap,.informe.informe-completo .quote{break-inside:avoid}
  .informe.informe-completo section{break-before:page}
  .informe.informe-completo section:first-of-type{break-before:auto}
  .informe.informe-completo thead{display:table-header-group}
  .informe.informe-completo .srcs a::after,.informe.informe-completo .reco-link::after{content:' (' attr(href) ')';font-size:.72em;color:#555;word-break:break-all}
  .gp-json{display:none}
}

/* JSON crudo (fuera del div del informe). */
.gp-json{margin-top:36px;border-top:1px solid var(--border);padding-top:18px}
.gp-json summary{cursor:pointer;font:700 .72rem var(--ui);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.gp-json pre{margin-top:14px;max-height:460px;overflow:auto;background:var(--muted-soft);border:1px solid var(--border);border-radius:var(--r-sm);padding:16px;font-size:.72rem;line-height:1.6}


/* --faint es decorativo (no pasa AA a tamano de cuerpo). El TEXTO informativo
   que el mockup pintaba en faint (cabeceras de tabla, categoria del plan de
   enlaces, modelo de la cita) se sube a --ink-soft, que si pasa AA. */
.informe.informe-completo .tw th{color:var(--ink-soft)}
.informe.informe-completo .reco-cat{color:var(--ink-soft)}
.informe.informe-completo .quote .q-m{color:var(--ink-soft)}


/* Backstop movil: nada dentro de la columna de contenido crea scroll horizontal
   del documento. Las piezas anchas de verdad (tablas, pestanas) tienen su propio
   overflow-x:auto interno, asi que se siguen pudiendo desplazar dentro de su caja. */
@media(max-width:999px){
  .informe.informe-completo .con-indice > div:not(.indice){overflow-x:clip}
  .informe.informe-completo .panel:not(.panel-dark),
  .informe.informe-completo .card{min-width:0}
}

/* ------------------------------------------------------------------
   19. BLINDAJE contra la fuga de report.css (hoja del informe LITE)
   El COMPLETO comparte la clase `.informe`, asi que reglas `.informe .X`
   del LITE se cuelan cuando el COMPLETO no fija esa misma propiedad.
   Aqui se neutralizan las que rompen las secciones EXCEPTUADAS.
   ------------------------------------------------------------------ */
/* La leyenda de cuota de voz: el LITE la pone en columna; debe ir en fila. */
.informe.informe-completo .legend{flex-direction:row}
.informe.informe-completo .leg{flex:0 1 auto}
/* El acordeon de preguntas del COMPLETO abre/cierra con display, no con
   max-height: el LITE le metia max-height:0 y lo dejaba colapsado aunque
   estuviera "abierto". */
.informe.informe-completo .q-body{max-height:none;overflow:visible}

/* ------------------------------------------------------------------
   20. TABLA DE CUOTA DE VOZ en pantallas medianas
   El estilo base convierte la tabla en fichas apiladas por debajo de 760px
   (de ahi los "bordes grandes" y las filas sueltas). En la columna estrecha
   del nuevo layout eso saltaba demasiado pronto: se mantiene como TABLA
   normal (con scroll horizontal propio si hace falta) hasta el movil real.
   ------------------------------------------------------------------ */
@media(max-width:760px) and (min-width:521px){
  .informe.informe-completo .tw{overflow-x:auto}
  .informe.informe-completo .tw table{display:table;width:100%}
  .informe.informe-completo .tw thead{display:table-header-group}
  .informe.informe-completo .tw tbody{display:table-row-group}
  .informe.informe-completo .tw tr{display:table-row;border:none;border-radius:0;padding:0;margin:0}
  .informe.informe-completo .tw td{display:table-cell;width:auto;border:none;border-bottom:1px solid var(--line-soft);padding:10px}
  .informe.informe-completo .tw td::before{display:none}
  .informe.informe-completo .tw tr.hide{display:none}
  .informe.informe-completo .tw tr.hide.show{display:table-row}
  .informe.informe-completo .tw tr.brand td{background:rgba(231,76,87,.16)}
}

/* ------------------------------------------------------------------
   21. CUOTA DE VOZ (seccion EXCEPTUADA): restauracion de su aspecto
   original. Los overrides de tabla/color del rediseno se le colaban
   (texto oscuro sobre el panel oscuro). Aqui se reinstaura el look del
   panel oscuro con selectores `.panel-dark ...`, que tienen MAS
   especificidad que mis `.tw td` genericos y ganan pase lo que pase.
   ------------------------------------------------------------------ */
.informe.informe-completo .panel-dark{background:var(--dark);border-color:var(--dark-line);color:var(--on-dark)}
.informe.informe-completo .panel-dark h3{color:var(--on-dark)}
.informe.informe-completo .panel-dark .eyebrow{color:var(--accent-light)}
.informe.informe-completo .panel-dark .card-text{color:var(--on-dark-muted)}
.informe.informe-completo .panel-dark .donut-t{color:var(--on-dark-faint)}
.informe.informe-completo .panel-dark .d-lbl{fill:var(--on-dark-faint)}
.informe.informe-completo .panel-dark .legend{border-top-color:rgba(255,255,255,.14)}
.informe.informe-completo .panel-dark .leg{color:var(--on-dark-muted)}
.informe.informe-completo .panel-dark .leg-brand{color:var(--on-dark)}
/* tabla de competidores sobre el panel oscuro */
.informe.informe-completo .panel-dark .tw th{color:var(--on-dark-faint);border-bottom-color:rgba(255,255,255,.2)}
.informe.informe-completo .panel-dark .tw td{color:var(--on-dark-muted);border-bottom-color:rgba(255,255,255,.09)}
.informe.informe-completo .panel-dark .tw td.strong{color:var(--on-dark)}
.informe.informe-completo .panel-dark tr.brand td{background:rgba(231,76,87,.16)}
.informe.informe-completo .panel-dark tr.brand td.strong{color:var(--accent-light)}
/* el boton "Ver las N empresas restantes" tambien va sobre fondo oscuro */
.informe.informe-completo .panel-dark .toggle{border-color:rgba(255,255,255,.24);color:var(--on-dark)}
.informe.informe-completo .panel-dark .toggle:hover{border-color:var(--accent);color:var(--accent-light)}
.informe.informe-completo .panel-dark .toggle .pm{color:var(--accent-light)}
/* en la version de tarjeta (movil real) las etiquetas tambien deben verse */
@media(max-width:760px){
  .informe.informe-completo .panel-dark .tw tr{border-color:rgba(255,255,255,.16)}
  .informe.informe-completo .panel-dark .tw td::before{color:var(--on-dark-faint)}
  .informe.informe-completo .panel-dark .tw tr.brand{background:rgba(231,76,87,.16);border-color:var(--accent)}
}

/* ------------------------------------------------------------------
   22. DESPLEGABLES  ·  patron <details> del mockup para bloques densos
   (analisis pagina por pagina, dominios citados, sitios donde ganar
   presencia). Nativo y accesible; arranca CERRADO. En impresion se abre.
   ------------------------------------------------------------------ */
.informe.informe-completo details.disc{margin-top:10px;border-top:1px solid var(--line-soft);padding-top:6px}
.informe.informe-completo details.disc summary{cursor:pointer;list-style:none;padding:6px 0;
  font:600 .84rem var(--ui);color:var(--accent-ink);display:flex;align-items:center;gap:8px}
.informe.informe-completo details.disc summary::-webkit-details-marker{display:none}
.informe.informe-completo details.disc summary .chev{transition:transform .2s;font-size:.7rem;color:var(--faint)}
.informe.informe-completo details.disc[open] summary .chev{transform:rotate(90deg)}
.informe.informe-completo details.disc summary .count{margin-left:auto;font-weight:500;color:var(--ink-soft)}
.informe.informe-completo details.disc summary:hover{color:var(--accent)}
.informe.informe-completo .disc-body{padding-top:4px}
.informe.informe-completo details.disc:not([open]) .disc-body{display:none}
/* en impresion, todo abierto: un PDF no se despliega */
@media print{
  .informe.informe-completo details.disc{border-top:none}
  .informe.informe-completo details.disc > .disc-body{display:block !important}
  .informe.informe-completo details.disc summary .chev{display:none}
}

/* Pie de versionado del analisis (E2): metadato discreto al final. */
.informe.informe-completo .version-foot{margin-top:32px;padding-top:14px;border-top:1px solid var(--line-c);
  font:500 .72rem var(--ui);color:var(--faint);text-align:right;letter-spacing:.02em}
"""

texto = "\n".join(salida) + "\n" + EXTRAS

# La primitiva Barra de React pinta <i>, el original pintaba <span>.
texto = texto.replace(".bar span{", ".bar i{")

# Colores literales que quedan en la parte TRANSCRITA (lineas 1-311). Vienen del
# HTML del mockup, que es anterior a la paleta de brandevs.com y no tiene tokens.
# No se pueden arreglar en el fuente (es el frontend del PDF, que no se toca) ni
# a mano en el CSS generado (se perderia en la siguiente regeneracion), asi que
# se traducen aqui, que es donde el arreglo sobrevive. Mismo sitio y mismo motivo
# que el reemplazo de .bar span de arriba.
COLORES_HEREDADOS = {
    "#F0CFCB": "var(--err-borde)",     # borde de fondo suave de error
    "#F6CFCA": "var(--accent-borde)",  # borde de chip de acento
    "#CDE6DA": "var(--ok-borde)",      # borde de fondo suave de ok
    "#96918A": "var(--on-dark-faint)",  # rotulo atenuado sobre el panel oscuro
}
for _viejo, _nuevo in COLORES_HEREDADOS.items():
    texto = texto.replace(_viejo, _nuevo)

open(BASE + "src/lib/report/report-completo.css", "w", encoding="utf-8").write(texto)
print("Escrito report-completo.css:", len(texto.splitlines()), "lineas")

# 09 · Prompt para Claude Design — landing de GeoPulse con la herramienta dentro

Este fichero **es** el prompt. Se copia entero y se pega en el proyecto de diseño de BranDevs (el que
tiene los `.dc.html` y su propio `CLAUDE.md`).

Está escrito contra el código real del panel (`docs/08`), así que los campos del formulario, los
estados y los pasos del progreso son los que la herramienta puede cumplir de verdad. **Si se cambia
un campo aquí, hay que cambiarlo también en `src/lib/shared/validate.ts`**, o la página pedirá algo
que la API no acepta.

---

## ▼ COPIAR DESDE AQUÍ ▼

Crea una página nueva en el sitio: **`GeoPulse Herramienta.dc.html`**. Es la página donde el
visitante lanza su propia auditoría GEO y ve el informe, sin salir del sitio y sin registrarse.

Convive con `Auditoria SEO GEO - GeoPulse.dc.html`, que es la landing comercial y **se queda como
está**. Esta es la página de producto: aquí se usa la herramienta. Enlázalas entre sí (desde la
landing, el CTA «Analizar mi web gratis» pasa a apuntar aquí).

### 1. Hechos que no puedes cambiar ni adornar

Esto viene de auditar el motor de análisis. El informe que verá el visitante lo dice todo, así que
cualquier promesa que no case se ve a la primera pantalla.

- **Son CUATRO motores: ChatGPT, Claude, Gemini y Perplexity.** No cinco. **Copilot no se consulta.**
  La landing actual dice «cinco motores» en seis sitios y lista tres combinaciones distintas: está
  mal y hay que corregirlo también allí. Escribe siempre los cuatro, en ese orden.
- **Se lanzan 3 preguntas a cada motor: 12 sondeos.** El informe enseña cuántos respondieron de 12.
- **No prometas 60 segundos.** El típico es **1-2 minutos** y hay colas que pueden alargarlo. Di
  «normalmente 1-2 minutos» y enséñale un cronómetro real, nunca una cuenta atrás.
- **La versión gratuita es la LITE.** La COMPLETA no se lanza desde la web: se explica, y su CTA es
  hablar con el equipo.
- Un análisis puede terminar con **avisos** o con métricas **no verificables**. Eso no es un fallo:
  es el sello de la herramienta. Nunca lo escondas ni lo conviertas en un cero.
- Hay un **cupo diario de análisis gratuitos**. Cuando se agota, la página lo dice y ofrece dejar un
  email, no finge estar rota.

### 2. Sistema visual

El de siempre, el del `CLAUDE.md` del proyecto. Resumido para que no tengas que ir a buscarlo:

- **Color.** `--accent:#E74C57` · `--accent-2:#FF6A3D`. Degradados de botón siempre
  `linear-gradient(90deg,var(--accent) 0%,var(--accent-2) 100%)`.
  Claro: `--paper:#FAF7F4` · `--panel:#F0ECE8` · `--card:#fff` · `--ink:#17130F` · `--ink-soft:#6E675F`
  · `--dark:#100E0C` · `--line:rgba(23,19,15,.10)` · `--track:#E6E0D8`.
  Oscuro (`.brandevs-dark`): `--paper:#0E0C0A` · `--panel:#1A1613` · `--card:#1B1714` · `--ink:#F3F0EB`
  · `--ink-soft:#A29B91` · `--line:rgba(255,255,255,.12)`. `--dark` y los dos acentos **no** se
  redefinen en oscuro.
- **Tipografía.** Space Grotesk 500/600 en titulares con `letter-spacing:-.02em` (nunca 700+ para un
  titular grande). Manrope en cuerpo. Newsreader cursiva en `--accent` para el acento dentro de un
  titular: un `<em>` que repite literalmente el `font` del padre, cambia familia + `italic` + color, y
  **no** hereda el tracking negativo.
- **Ritmo.** Bloque `max-width:1290px`, `padding-inline:clamp(20px,4vw,40px)`. Sección
  `padding-block:clamp(64px,8vw,110px)`. Hero `padding:clamp(150px,15vw,206px) … clamp(80px,8.5vw,116px)`.
- **Radios.** 12px fila · 16px tarjeta pequeña · **22px tarjeta estándar** · 26px panel · 34px bloque
  CTA oscuro · 100px píldoras y botones. Bordes 1px `var(--line)`; **1.5px** si el elemento es
  seleccionable o es un botón outline.
- **Tarjetas.** Sin sombra en reposo, solo `border:1px solid var(--line)`. La sombra es de hover y es
  **roja**: `transform:translateY(-8px); box-shadow:0 36px 64px -32px rgba(231,76,87,.42);
  border-color:rgba(231,76,87,.35)`, con `transition …  .5s cubic-bezier(.2,.7,.2,1)`.
- **Botón primario.** `padding:14px 15px 14px 28px` (asimétrico), degradado, `border-radius:100px`,
  `font:600 16px Manrope`, `box-shadow:0 16px 32px -12px rgba(231,76,87,.6)`, hover
  `translateY(-2px)`. Lleva **siempre** la pastilla circular blanca de 34px con la flecha
  `M5 12h13M12 5l7 7-7 7` al final.
- **Eyebrow.** `inline-flex; gap:9px`, punto de 7px en `--accent`, texto
  `600 12.5px/1 Manrope; letter-spacing:.16em; uppercase; color:var(--accent)`. El punto **solo pulsa**
  (`animation:pulseDot 1.8s infinite`) en el hero y en el CTA final; en las secciones intermedias es
  estático.
- **Bloque oscuro.** `background:var(--dark); border-radius:34px; overflow:hidden` con un hijo
  absoluto de halo: `top:-150px; left:50%; translateX(-50%); width:520px; height:380px;
  background:radial-gradient(circle,rgba(231,76,87,.3),transparent 70%)`. Dentro, blancos por escalera
  de opacidad: `.82` enlace · `.62` párrafo · `.45` nota fina.
- **Movimiento.** Curva de marca `cubic-bezier(.2,.7,.2,1)`. Entrada por `data-reveal` con
  IntersectionObserver (`opacity:0; translateY(30px)`, `.8s`), escalonada con `data-delay`. Respeta
  `prefers-reduced-motion`, como el resto del sitio.
- Cabecera y pie **idénticos** a los del resto de páginas, y hay que inyectar la nueva entrada de nav
  en las demás. El CTA del header de esta página apunta a `#analizar`.

**Nota sobre estados:** el sistema de la web solo tiene verde. Esta página necesita además ámbar
(en curso / aviso) y granate (error). Usa estos, que están medidos contra los fondos de la casa:
`ok #17734B` · `aviso #8C6510` · `error #B42318` · `neutro #787168`; y sobre fondo oscuro, sus
variantes claras `#35B07A` · `#D9A340` · `#F0736A` · `#9E978C`. **El estado nunca viaja solo en el
color:** siempre glifo o palabra al lado.

### 3. Estructura de la página

**1 · Hero, con el formulario dentro.** Dos columnas (`1.05fr 0.95fr`). Izquierda: eyebrow con punto
pulsante «GeoPulse · Herramienta», `<h2>` con el acento en Newsreader — algo del tipo «Comprueba si
la IA recomienda *tu marca* o la de tu competencia» —, entradilla corta y una tira de cuatro chips con
los motores (ChatGPT · Claude · Gemini · Perplexity). Derecha: **la tarjeta del formulario**, elevada
(`--sombra-panel`), que es el corazón de la página. Nada de mockups decorativos aquí: el formulario
es el contenido.

**2 · Qué te vas a llevar.** Rejilla de 4-6 tarjetas con lo que trae el informe gratuito: nota GEO
global, visibilidad por motor, cuota de voz frente a competidores, SEO técnico de la home, huella
digital externa, ficha de Google Business y enlaces rotos. Cada una con su etiqueta, su `<h3>` y una
línea de descripción.

**3 · Las dos versiones.** Dos tarjetas grandes, lado a lado. La de la izquierda (LITE) es la
destacada (`border:1.5px solid rgba(231,76,87,.4)`), porque es la que se puede usar ahí mismo:

| | **Auditoría gratuita** (LITE) | **Auditoría completa** |
|---|---|---|
| Cómo se lanza | Aquí mismo, sin registro | Con el equipo, dentro del servicio de SEO y GEO |
| Duración | 1-2 minutos | 3-5 minutos de proceso, entrega comentada |
| Preguntas | 3 por motor · 12 sondeos | 16 preguntas · 48 sondeos, con 4 dimensiones |
| Qué mide | Nota GEO, visibilidad por motor, cuota de voz, SEO técnico de la home, huella externa, ficha de Google, enlaces rotos | Todo lo anterior más verificación factual de lo que dice la IA, análisis de landings, plan de acción priorizado, plan de enlaces y KPIs de seguimiento |
| Frecuencia | Foto puntual | Medición mensual con evolución |

CTA de la izquierda: «Analizar mi web gratis» → `#analizar`. CTA de la derecha: «Hablar con el
equipo» → `/contacto/`. **No pongas precios**: la landing de GeoPulse no habla de dinero, eso vive en
Tarifas.

**4 · Cómo funciona / qué pasa mientras esperas.** Tres pasos numerados, con el número fantasma
grande en `--line`. Sirve de doble uso: explica el proceso y prepara la espera. Paso 1 «Nos dices tu
marca y tu sector» · paso 2 «Preguntamos a los cuatro motores como lo haría tu cliente» · paso 3
«Te devolvemos la nota y el plan».

**5 · FAQ.** Acordeón a `max-width:900px`, con `<details>` reales, y su `FAQPage` en JSON-LD.
Preguntas obligadas: qué motores analiza (cuatro, y por qué no Copilot), cuánto tarda, si hay que
instalar algo, qué pasa si un motor no responde, si el informe se puede descargar, y qué diferencia
hay con la auditoría completa.

**6 · CTA final** en bloque oscuro con halo, punto pulsante, que devuelve a `#analizar`.

### 4. El formulario

Vive en el hero y se repite (o se ancla) en `#analizar`. **Los campos son estos exactamente**,
porque son los que acepta la API:

| Campo | Obligatorio | Notas |
|---|---|---|
| **Marca** | sí | «Tal y como la citaría alguien al recomendarla». Máx. 80 caracteres |
| **Dominio** | sí | «Con o sin https». Máx. 253. Solo dominios públicos |
| **Sector** | sí | «A qué se dedica, como lo diría un cliente». Máx. 120 |
| **País** | sí | Selector, por defecto España |
| **Ciudad o región** | no | Máx. 80. Afina el resultado en negocios locales |
| **Email** | sí | Para enviarle el informe y poder recuperarlo |
| **Privacidad** | sí | Checkbox con enlace a la política, como en Contacto |
| **Captcha** | sí | Turnstile. Es el único freno que distingue a una persona de un bucle |

Estilo de campo, el de `Contacto.dc.html`: `width:100%; background:var(--card); border:1px solid
var(--line); border-radius:12px; padding:14px; font:400 14px Manrope`. Label
`font:600 11px Manrope; color:var(--ink-soft); margin-bottom:7px`. Botón de envío a ancho completo,
degradado, píldora.

**Validación en el cliente antes de enviar**, con el error debajo del campo y `aria-describedby`
(nunca solo en rojo). Bajo el botón, microcopy honesto: «Gratis · Sin registro · Normalmente tarda
1-2 minutos».

### 5. La máquina de estados (esto es lo que hay que clavar)

La página tiene **cinco** estados. Diséñalos todos, no solo el bonito.

**a) Reposo** — el formulario.

**b) Enviando** — el botón pasa a spinner y se desactiva. Un segundo, como mucho.

**c) Analizando** — el estado largo, y el que hace que la espera se lleve bien. Sustituye la tarjeta
del formulario por un **panel de progreso** con:

- **Cronómetro real** contando desde que empezó (mm:ss), y debajo «suele tardar 1-2 minutos». Nunca
  una cuenta atrás, nunca un porcentaje inventado.
- **Una lista de pasos** en la que cada línea tiene tres estados visibles: pendiente (punto hueco,
  texto en `--ink-soft`), en curso (punto ámbar pulsando, texto en `--ink`, negrita) y hecho (check
  verde y, **si lo hay, el dato real que se sacó en ese paso**). El dato es lo que hace que esto no
  sea decoración.
- Los pasos, con ejemplo de lo que se ve al completarse:

  1. **Leyendo tu web** → «620 palabras · 8 encabezados · 3 bloques de datos estructurados · 40 URLs en el sitemap»
  2. **Preguntando a ChatGPT** → «3 preguntas enviadas»
  3. **Preguntando a Claude** → «3 preguntas enviadas»
  4. **Preguntando a Gemini** → «3 preguntas enviadas»
  5. **Preguntando a Perplexity** → «3 preguntas enviadas»
  6. **Buscando tu ficha de Google** → «Encontrada · 4,7★ · 128 reseñas» / «No encontrada»
  7. **Rastreando tu sitio** → «30 de 84 páginas (límite de 30)»
  8. **Comprobando enlaces** → «120 de 341 enlaces. Este paso es el más largo.»
  9. **Contando respuestas** → «Respondieron 11 de 12 sondeos · ChatGPT 3/3 · Claude 3/3 · Gemini 2/3 · Perplexity 3/3»
  10. **Redactando el informe** → «Última llamada, la más larga»

  Los textos exactos los manda el servidor en `progreso_texto`; tú diseña el componente para que
  acepte una línea de hasta ~110 caracteres sin romperse.

- **Regla de honestidad del paso 8:** ese tramo se queda quieto un rato largo porque comprueba hasta
  120 enlaces dentro de un solo bloque y no da señales hasta acabar. Que el diseño lo diga («esto
  tarda»), en vez de fingir movimiento.
- **Regla de honestidad general:** si pasan más de 90 s sin que cambie el paso, la línea en curso
  cambia a «sin novedades desde hace 2:14». No sigas animando algo que puede estar parado.
- Mientras espera, aprovecha el hueco: una tarjeta lateral con un dato del sector, o el resumen de
  qué va a recibir. **Sin juegos ni animaciones que compitan** con la lista de pasos.

**d) Listo** — el panel se sustituye por el informe renderizado, precedido de una barra con la nota
grande, el veredicto y los botones «Descargar JSON», «Descargar CSV» e «Imprimir». Si el informe
trae **avisos**, salen arriba, en tarjeta ámbar, antes que nada.

**e) Error, en cuatro sabores distintos**, cada uno con su salida:
- *No hemos podido leer tu web* → sugiere revisar el dominio, botón de reintentar.
- *El análisis se ha quedado a medias* → «lo hemos parado, no se ha cobrado nada», reintentar.
- *Cupo diario agotado* → «hoy ya se han hecho todos los análisis gratuitos. Déjanos tu email y te
  avisamos mañana» + campo de email. **Este no es un error: es una lista de espera.**
- *Demasiadas peticiones desde tu conexión* → di cuándo puede volver a intentarlo.

### 6. Accesibilidad

Es un formulario público: esto no es opcional.

- Cada campo con su `<label>` asociado; los errores con `aria-describedby` y `aria-invalid`.
- El panel de progreso es una **región viva**: `role="status"` y `aria-live="polite"` en la línea del
  paso actual, para que un lector de pantalla cante el avance sin interrumpir.
- El estado de cada paso, con glifo o palabra además del color.
- Foco visible en todo lo interactivo, contraste AA en todo el texto, y `prefers-reduced-motion`
  respetado (con movimiento reducido, los pasos aparecen de golpe y el punto no pulsa).
- Jerarquía correcta: el eyebrow es el `<h1>`, el titular grande el `<h2>`, y cada sección un `<h2>`
  con `aria-labelledby`.

### 7. Qué entregar

- `GeoPulse Herramienta.dc.html`, con `<helmet>` (title, description, canonical, Open Graph),
  `SoftwareApplication` + `FAQPage` en JSON-LD, la nav y el footer comunes, y modo claro/oscuro.
- Los cinco estados maquetados y conmutables desde el `DCLogic` con datos de ejemplo, para poder
  verlos sin backend. Deja el punto de conexión marcado con un comentario claro:
  `POST /api/publico/lite` para lanzar y `GET /api/publico/runs/:token` cada pocos segundos para
  el progreso.
- La nav actualizada en el resto de páginas y el CTA «Analizar mi web gratis» de la landing comercial
  apuntando aquí.

### 8. Tono

El de la casa: directo, en segunda persona, frases cortas, cifras concretas, cero emojis, cero
superlativos. Y la marca de la casa en la parte transaccional: **prudente y verificable**. «Las
consultas sin resultado verificable quedan fuera del promedio para no distorsionar la nota» es el
registro exacto. Si algo no se ha podido medir, se dice.

## ▲ COPIAR HASTA AQUÍ ▲

---

## Lo que este prompt da por hecho y todavía no existe

Para que quede claro qué falta del lado del panel antes de que la página funcione de verdad. El
detalle está en `docs/08`:

- `POST /api/publico/lite` y `GET /api/publico/runs/:token` — no existen.
- Las columnas `origen`, `token_publico` y las cinco de `progreso_*` en `runs` — no existen.
- Los marcadores de progreso en el workflow — no existen (hoy solo hay `en_curso` y `completado`).
- El cupo diario y el captcha — no existen.
- Y los bloqueantes del apartado 1 de `docs/08`: webhook sin autenticar, sin watchdog, sin longitudes
  máximas.

Se puede maquetar la página entera antes que nada de eso, porque los cinco estados se conmutan con
datos de ejemplo. Lo que **no** se puede es publicarla conectada.

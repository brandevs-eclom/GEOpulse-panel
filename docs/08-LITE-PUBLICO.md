# 08 · Sacar el LITE a la web pública

**Qué responde este documento:** cómo se expone la versión LITE de GeoPulse en la web de BranDevs
para que cualquier visitante lance su propia auditoría, sin abrir la base de datos de la agencia ni
la factura de LLMs, y con una espera que se pueda contar honestamente mientras corre.

El COMPLETO **no** se toca: sigue lanzándose solo desde el panel. Todo lo de aquí es del LITE.

> Escrito el 2026-09-02, contrastado contra el código, no contra la documentación. Donde el código y
> los `docs/` no coinciden, se dice cuál de los dos está desfasado.

---

## 0 · Tres cosas que hay que decidir antes de escribir una línea

Salieron al auditar el repo contra la landing actual (`Auditoria SEO GEO - GeoPulse.dc.html` del
export de diseño). No son detalles de implementación: cambian lo que se puede prometer.

### 0.1 La web promete cinco motores. La herramienta consulta cuatro.

La landing dice **cinco motores** en seis sitios, y los lista de tres formas distintas:

| Dónde | Qué dice |
|---|---|
| `meta description`, sección Servicios | ChatGPT, Gemini, Perplexity, **Copilot** y Claude |
| FAQ (y su JSON-LD `FAQPage`) | ChatGPT, Gemini, Perplexity, **Google AI** y **Copilot** |
| Hero, «Qué revisa», «Frecuencia de mención» | ChatGPT, Gemini, Perplexity y **Copilot** (sin Claude) |

El workflow LITE lanza **cuatro sondas**: ChatGPT, Claude, Gemini y Perplexity
(`workflows/geopulse-lite2-panel-workflow.json`, nodos `Sonda - *`). **Copilot no se consulta nunca.**
El informe lo dice solo: `meta.sondeos: 12` = 4 modelos × 3 preguntas, y `_diag.respuestas_ok`
enumera exactamente esos cuatro.

Hoy eso no se ve porque la landing no enseña ningún informe. **En cuanto el visitante reciba su
informe de verdad, la página y el informe se contradicen en la primera pantalla.** Es el problema
más caro de esta lista y no se arregla con código: o se añade Copilot como sonda, o la web pasa a
decir cuatro. Mi recomendación es **decir cuatro**, porque es lo que se mide y porque el propio
informe ya presume de no promediar lo que no puede verificar.

### 0.2 Dos bugs del builder que el informe público delataría

Los dos están en `workflows/build_lite2.py`, o sea que por la regla del proyecto se arreglan ahí, no
en el panel:

- **Línea 991** — `meta.modelos: ['ChatGPT','Claude','Perplexity']`. **Falta Gemini**, que sí se
  consulta. Un informe que diga «3 modelos» habiendo lanzado 12 sondeos contra 4 no se sostiene.
- **Línea 816** — el aviso `'Solo X de 9 sondeos devolvieron respuesta'` con la condición `< 9`,
  cuando el máximo real es **12**. Una ejecución con 10 de 12 (dos modelos caídos) **no dispara
  ningún aviso**: el informe sale como si todo hubiera ido bien. Y el comentario de la línea 12
  («3 sondas x 3 modelos (9 llamadas)») es de cuando había tres modelos.

Los dos son de una línea. Hay que hacerlos **antes** de publicar, no después.

### 0.3 El coste real del LITE es el triple del que dice `docs/07`

`docs/07-COSTE-GROUNDED-LITE.md` presenta el *grounding* como decisión pendiente y marca las sondas
de ChatGPT/Claude/Gemini como «paramétricas». **Es falso desde hace tiempo**: `build_lite2.py:1039,
1053, 1074` ya genera `tools:[{type:'web_search'}]` (OpenAI, por la Responses API),
`tools:[{type:'web_search_20250305'}]` (Claude) y `tools:[{google_search:{}}]` (Gemini), y esos
parámetros están en el JSON desplegado. El propio informe lo sella: `analysis_version: 'lite-v3'`,
con el comentario «v3: sondas GROUNDED».

Consecuencia práctica: las tarifas de búsqueda que `docs/07` llamaba «aumento futuro» (~0,10 $/run)
**ya se están pagando**. El coste por LITE está en el entorno de **0,19 € (rango honesto 0,14-0,26 €)**,
no en los 0,05-0,07 € que se manejaba. Todo cálculo de volumen y de abuso va multiplicado por tres.

> Y una advertencia sobre el propio número: es una estimación derivada de la tabla de tarifas del
> builder, no una medición. **Nadie ha medido nunca un LITE real**: los fixtures de `docs/` son
> anteriores al bloque `[E1]` y no traen `coste`. El informe ya emite
> `informe.coste.estimated_cost_usd` en cada ejecución; guardarlo en una columna y sumarlo por mes
> es la única cifra que no será una estimación. Hasta entonces, presupuestar con la banda alta.

---

## 1 · Por qué hoy no se puede publicar tal cual

Cinco agujeros, verificados uno a uno en el código. Los tres primeros ya estaban escritos como deuda
en el README; los dos últimos son nuevos.

| # | Agujero | Verificado en | Qué cuesta |
|---|---|---|---|
| 1 | **Los webhooks de análisis no tienen autenticación.** El nodo `Webhook` de `geopulse-lite2-panel` y `geopulse-audit-panel` no lleva `authentication`. `trigger.ts:61` manda `x-panel-secret`, pero **nadie lo comprueba**. | `workflows/geopulse-lite2-panel-workflow.json` (nodo Webhook, sin `authentication` ni `credentials`) frente a `panel-db-workflow.json`, que sí lo tiene | A 1 pet/s son 3.600 análisis/hora ≈ **680 €/hora**. Y saltándose `MAX_CONCURRENT_RUNS`, que solo existe en `/api/runs` |
| 2 | **El análisis corre aunque el `run_id` sea inválido.** El webhook abre en abanico a `Preparar Ack` **y** a `Normalizar Input` a la vez. La comprobación `if (!run_id) throw` está en `Preparar Guardado`, el penúltimo nodo: cuando falla, el dinero ya se gastó. | conexiones del JSON generado: `Webhook → [Preparar Ack, Normalizar Input]` | Un POST basura cuesta 0,19 € en vez de 0 € |
| 3 | **No hay watchdog.** `STALE_MINUTES` está en `.env.example` y no lo lee nadie. Los workflows solo escriben `en_curso` y `completado`. | grep en todo `src/` | **DoS permanente de coste cero**: `validate.ts` solo exige que `domain` no esté vacío, así que `domain:"/"` crea la fila, n8n la marca `en_curso` y `Normalizar Input` revienta. La fila se queda `en_curso` para siempre y `count_active` la sigue contando. **Dos peticiones bloquean el lanzamiento a toda la agencia** |
| 4 | **Ningún campo tiene longitud máxima.** `brand`, `keyword` y `region` entran en el prompt de las 14 llamadas de pago. | `src/lib/shared/validate.ts:16` | 1 MB en `brand` = **~2,30 € en una sola petición**, 12× un análisis normal |
| 5 | **`SQL_COMPLETADO` no tiene guarda de estado** (`where id = $1`, sin más). Con el webhook abierto, un tercero puede sobrescribir el informe de una ejecución ajena y marcarla completada. | `workflows/panel_common.py:393`, frente a `SQL_EN_CURSO`, que sí la tiene | Integridad del histórico de clientes |

Añádase que `MAX_CONCURRENT_RUNS` **no es un tope de gasto**: es un tope de *concurrencia*, es único
y global (agencia y público comparten el mismo), y su comprobación es un TOCTOU —
`countActiveRuns()` y `createRun()` son dos POST HTTP independientes, sin transacción.

---

## 2 · El orden de trabajo

Cada paso deja algo verificable. Los pasos 1-5 son fontanería previa: no entregan nada visible, pero
sin ellos cualquier defensa que se ponga en el panel es decorativa, porque la URL del motor está a
un «ver código fuente» de distancia.

### Paso 0 — Hoy, 1 hora, sin tocar código

**Límite de gasto mensual en las consolas de OpenAI, Anthropic, Google AI y Perplexity.** Es la única
defensa cuyo peor caso está acotado de verdad; todo lo demás es un freno que alguien puede puentear.

Y **desactivar en n8n el workflow público del COMPLETO** (`geopulse-audit`). El panel no lo usa
—llama a `geopulse-audit-panel`— y, al terminar, genera un PDF y lo envía por SMTP a la dirección
que venga en el body: es un relé de correo abierto con el dominio de la agencia. Cinco minutos.

### Paso 1 — Cerrar el webhook (~30 min, orden obligatorio)

`authentication='headerAuth'` en el nodo Webhook de `build_lite2_panel.py` y `build_audit_panel.py`,
copiando literalmente lo que ya hace `build_panel_db.py`. **En este orden:**

1. crear la credencial en n8n con **Name = `x-panel-secret`**;
2. rellenar `N8N_WEBHOOK_TOKEN` en Vercel (Production **y** Preview);
3. regenerar y reimportar los dos JSON.

Al revés, el panel deja de poder lanzar análisis.

### Paso 2 — Validación de entrada, en las dos capas (~1 h)

Es el arreglo con mejor relación coste/beneficio de toda la lista, porque cierra a la vez la
amplificación de coste y el SSRF.

- **Longitudes máximas** en `src/lib/shared/validate.ts` (marca ≤ 80, dominio ≤ 253, sector ≤ 120,
  país exactamente 2 letras, región ≤ 80) **y repetidas con `.slice()`** en el nodo
  `Normalizar Input` de `build_lite2.py`. Las dos capas hacen falta porque el webhook es alcanzable
  sin pasar por el panel.
- **Blocklist de hosts** en `Normalizar Input`: forzar `https`, rechazar puerto explícito, y rechazar
  el host si no tiene punto, si acaba en `.local`/`.internal`, o si casa con
  `^(127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|169\.254\.|0\.|\[?::1)`.
  Hoy no hay ninguna: n8n hace `GET` a lo que le digas en cinco nodos, y en la variante del panel el
  resultado **se persiste en Postgres**.

  > Honestidad: esto **no** cierra el DNS rebinding, que requeriría resolver y validar la IP en el
  > momento de la petición. Cierra el caso directo, que es el 99% del riesgo real aquí.

- **Guarda de estado** en `SQL_COMPLETADO` (`and estado in ('pendiente','en_curso')`) y
  `tolerar_fallo=False` en `Marcar En Curso`, para que la ejecución aborte si ese `UPDATE` toca cero
  filas. Dos líneas, y hace inmutable un informe ya guardado.
- **Mover `if (!run_id) throw`** de `Preparar Guardado` a `Preparar Ack`. Un POST sin `run_id` pasa a
  costar 0 €.

### Paso 3 — Watchdog (~2 h)

Op `fail_stale` en `build_panel_db.py`, junto a `fail_run`:

```sql
update runs set estado='error', error_mensaje='Sin novedades tras N minutos',
       finished_at=now(), updated_at=now()
 where estado in ('pendiente','en_curso')
   and coalesce(started_at, created_at) < now() - ($1 || ' minutes')::interval
returning id
```

Más una ruta `/api/cron/stale` disparada por **Vercel Cron** cada 5 min (hoy no existe `vercel.json`;
hay que crearlo). Ese mismo cron es la pieza que hace falta de todas formas para F3 (alertas) en
`docs/06`.

### Paso 4 — Tope de gasto real, no de concurrencia (~2 h)

Convertir `create_run` en un **INSERT condicional** que lleve dentro las dos comprobaciones. Cierra
la carrera TOCTOU y pone un techo absoluto a la factura, las dos cosas con un solo cambio:

```sql
insert into runs (...)
select $1, $2, ...
 where (select count(*) from runs
         where estado in ('pendiente','en_curso') and origen = $9) < $10
   and (select count(*) from runs
         where origen = 'publico' and created_at > now() - interval '24 hours') < $11
returning id, estado, created_at
```

Cero filas devueltas ⇒ el panel responde 429 diciendo **cuál** de los dos topes se ha alcanzado.

Requiere una columna **`origen`** (`'panel' | 'publico'`) en `runs`, para que el público y la agencia
tengan cupos separados y para poder medir cuánto gasta el canal.

> **Bloqueo conocido:** `docs/03` avisa de que la op `migrate` **no es idempotente**: reaplica todo y
> falla si las tablas existen, así que hoy no se puede lanzar una migración `0001`. Lo barato y
> honesto es aplicar este `ALTER TABLE` **una vez a mano** contra el Postgres del servidor de n8n
> (está en la misma máquina), dejarlo anotado en `docs/03`, y arreglar `migrate` como trabajo aparte.
> Lo que **no** hay que hacer es meter estos campos dentro de `runs.payload` con `jsonb_set` para
> esquivar la migración: `payload` está documentado como «el body EXACTO enviado al webhook» y
> ensuciarlo rompe la reproducibilidad y el reintento.

**Dimensionar el cupo.** Con 0,19 €/LITE: 100 análisis/mes = 19 € · 500 = 95 € · 1.000 = 190 € ·
5.000 = 950 €. Escala lineal y sin techo. Un cupo de **50 análisis públicos al día** deja la factura
máxima del canal en **~285 €/mes**, que es un número con el que se puede vivir. Sin cupo, el máximo
lo decide quien ataque.

### Paso 5 — Rate limiting (~10 min, sin código)

Regla del **WAF de Vercel** por IP sobre `/api/publico/lite` (p. ej. 3/hora) y, ya que se está,
sobre `/api/auth/login`, que hoy no tiene límite de intentos. Y un **captcha** (Turnstile o hCaptcha)
en el formulario público: es el único freno que distingue a una persona de un bucle.

---

## 3 · La arquitectura, ya con los agujeros cerrados

**Regla de diseño innegociable: la página pública llama SIEMPRE a una route handler del panel
(runtime `nodejs`), nunca a n8n.** `N8N_PANEL_DB_SECRET` da lectura y escritura a toda la base de
datos, incluidos los `password_hash` de `users` y la creación de cuentas. Si alguna vez toca el
navegador, se acabó.

```
Navegador                Panel (Next.js, Vercel)              n8n
────────────────────────────────────────────────────────────────────────────
POST /api/publico/lite ─► captcha + validación + cupo
                          create_run(origen='publico') ──────► panel-db
                       ◄─ { token }                             (Postgres)
                          dispara en 2º plano ───────────────► geopulse-lite2-panel
                                                                 (Header Auth)
GET  /api/publico/runs/:token (polling)
                       ─► get_run_publico ────────────────────► panel-db
                       ◄─ { estado, progreso, informe }
```

Cuatro piezas nuevas, todas pequeñas:

1. **`src/app/api/publico/lite/route.ts`** y **`.../runs/[token]/route.ts`**, más `api/publico` en las
   exclusiones del matcher de `src/middleware.ts`.
2. **Op `get_run_publico`** en `build_panel_db.py`. **No reutilizar `get_run`**: hace `JOIN` con
   `users` y devuelve `lanzado_por_email`, o sea que filtraría quién de la agencia lanzó cada
   auditoría interna. La op nueva devuelve exactamente
   `select r.id, r.estado, r.error_mensaje, r.progreso_*, i.informe from runs r left join informes i
   on i.run_id = r.id where r.token_publico = $1 and r.origen = 'publico'`
   — sin `JOIN`, sin `payload`, sin respuestas crudas.
3. **Columna `token_publico`** en `runs`, distinta del `id` interno. El uuid del run sería si no el
   único control de acceso al informe, y es un secreto que se filtra por `Referer` y por historial
   del navegador. Con un token propio, además, un id interno adivinado no responde nunca. En la
   página del informe, `<meta name="referrer" content="no-referrer">`.
4. **Polling con backoff**, no intervalo fijo: 2,5 s los primeros 30 s, luego 5 s, luego 10 s, y
   parar a los 6 min con un botón de «volver a comprobar». **Cada tick de polling es una ejecución
   de n8n**: 50 visitantes esperando a la vez con el intervalo fijo del panel son ~1.200 ejecuciones
   por minuto contra la misma instancia que corre los análisis. El cuello de botella es ese, mucho
   antes que la factura de LLM.

**Dónde vive la landing.** Servirla desde el propio Next (mismo origen) y no necesitar CORS en
absoluto. Si tiene que vivir en WordPress, allowlist explícita de **un** origen en `next.config.ts`
— nunca `Access-Control-Allow-Origin: *`, que convertiría el endpoint de gasto en invocable desde
cualquier web.

---

## 4 · Contar la espera sin mentir

El objetivo de producto: que el minuto y medio de espera se haga corto porque el visitante ve qué
está pasando. La regla del proyecto: **no vale una barra temporizada vendida como progreso real.**

### Lo que se puede enseñar, y de dónde sale

La granularidad mínima de progreso en n8n es el **nodo**, no el item. Estos son los cortes donde ya
existe un dato calculado que enseñar:

| Tras el nodo | Lo que se dice | Dato real que lo respalda |
|---|---|---|
| `Marcar En Curso` *(ya existe)* | «Análisis aceptado. Empezando.» | `started_at` — el t0 fiable del cronómetro |
| `Consolidar Señales` | «Web leída: 620 palabras, 8 encabezados, 3 bloques JSON-LD, 40 URLs en el sitemap» | `_diag` completo, ya calculado |
| `Sonda - ChatGPT/Claude/Gemini/Perplexity` | «Consultando modelos: 2 de 4» | el nodo terminó. **Decir “consultados”, nunca “respondieron”**: con `neverError:true` un fallo también produce item |
| `Parsear Ficha` | «Ficha de Google: encontrada (4,7★, 128 reseñas)» | `ficha_google.encontrada` + `.confianza`. Si la confianza es `media` (casó por nombre, no por dominio), hay que decirlo |
| `Paginas a Revisar` | «Rastreando 30 de 84 páginas (límite de 30)» | `_paginas_encontradas`, `_cap_paginas` |
| `Extraer Enlaces` | «Comprobando 120 de 341 enlaces. Este paso es el más largo.» | `_encontrados`, `_cap`, `_paginas` |
| `Clasificar Enlaces` | «Revisados 38 enlaces: 2 rotos, 3 no verificables» | `enlaces_rotos.*` |
| `Recopilar Respuestas` | «Respondieron 11 de 12 sondeos: ChatGPT 3/3, Claude 3/3, Gemini 2/3, Perplexity 3/3» | `_diag.respuestas_ok`, que es literalmente esa cadena. **El marcador de más valor de la lista** |
| `Preparar Informe` | «Redactando el informe. Es la última llamada y la más larga.» | el nodo terminó |
| `Marcar Completado` *(ya existe)* | «Informe listo.» | `duracion_ms` real |

### Cómo se escribe y se lee: **cero ejecuciones de n8n añadidas**

- **Escritura:** cinco columnas nuevas en `runs` (`progreso_paso`, `progreso_texto`,
  `progreso_indice`, `progreso_total`, `progreso_at`) y un helper `SQL_PROGRESO` en
  `panel_common.py`, junto a `anadir_ciclo_de_vida`, para que el COMPLETO lo herede gratis. Los
  marcadores son nodos Postgres **dentro de la misma ejecución** que ya se lanza.
- **Enganche:** nunca en línea dentro de la cadena — si metes el nodo Postgres entre
  `Consolidar Señales` y `Sondas`, `Sondas` recibiría su salida vacía y reventaría. Van como **rama
  muerta**: una segunda conexión de salida que termina ahí. Con `executionOrder v1` n8n ordena las
  ramas por posición en el lienzo (arriba primero), que es la misma regla ya documentada para el ack:
  el nodo de progreso va **con Y por encima** de la rama que anuncia. Y `executeOnce: true`, porque
  colgado de `Sonda - ChatGPT` (que emite 3 items) correría tres veces.
- **Tolerancia a fallo:** `tolerar_fallo=True` en todos. Un fallo escribiendo progreso **jamás**
  puede matar un análisis de pago.
- **Lectura:** añadir las cinco columnas al `select` de la op `get_run` / `get_run_publico`. El
  navegador **ya** hace ese polling; mientras el run está vivo `informe` es `NULL`, así que la fila
  sigue siendo ligera. Piggyback, no endpoint nuevo. Un endpoint `/progreso` aparte **duplicaría** el
  coste de polling.

Coste total: **0 ejecuciones de n8n nuevas**, +10 nodos Postgres por UPDATE de clave primaria contra
un Postgres local ≈ 0,1-0,4 s sobre una ejecución de 60-120 s.

### Dos límites que hay que decir en voz alta

1. **`Comprobar Enlace` corre hasta 120 veces dentro de un solo nodo** y no devuelve control hasta
   acabar. No se puede enseñar «enlace 47 de 120» en vivo. Lo honesto es anunciar **antes** cuántos
   se van a comprobar y avisar de que ese tramo tarda.
2. **Si un nodo revienta, el último marcador se queda congelado.** La UI debe leer `progreso_at` y
   decir «sin novedades desde hace 4 min», no seguir animando una barra. Es justo lo que el
   watchdog del paso 3 acabará convirtiendo en `error`.

### Cuánto tarda de verdad

**No hay ni una sola medición.** Lo único declarado es «lite 1-2 min», repetido en README, `docs/01`
y `CLAUDE.md`. Lo que sí está verificado son los conteos: hasta **14 llamadas LLM + hasta 155 HTTP =
~169 peticiones salientes**, todas secuenciales (n8n no paraleliza items ni ramas). Sumando los
timeouts, el tope teórico pasa de los 50 minutos. O sea: **1-2 min es un típico, no una garantía**,
y por eso no se puede convertir en una barra temporizada.

La landing dice hoy «Informe en 2 minutos» y «En 60 segundos sabrás…». Los 60 segundos hay que
quitarlos. En cuanto existan los marcadores, habrá por primera vez tiempos reales por tramo y se
podrá sustituir la estimación por una mediana medida (`runs.duracion_ms` ya se calcula al completar).

### Por fases, para no meter 10 nodos de golpe

- **Fase A:** los **3 marcadores** que cubren las tres esperas percibidas — tras
  `Consolidar Señales`, tras `Recopilar Respuestas` y tras `Preparar Informe` — más el cronómetro
  real desde `started_at`. Valida el mecanismo de punta a punta con cirugía mínima.
- **Fase B:** los 7 restantes, que es donde el relato se vuelve entretenido (los cuatro modelos uno a
  uno, el rastreo, los enlaces).

Y mientras no haya nada de esto, hay un **escalón 0 que no miente y se puede hacer hoy**: cronómetro
real desde `started_at` + la lista **estática** de lo que hace el análisis, sin afirmar en qué paso
va. «Este análisis lee tu web, pregunta a 4 modelos (3 preguntas cada uno), busca tu ficha de Google,
rastrea hasta 30 páginas y comprueba hasta 120 enlaces, y por último redacta el informe.» Es una
descripción verdadera más un cronómetro verdadero.

---

## 5 · Resumen ejecutable

| # | Trabajo | Dónde | Esfuerzo | Bloquea publicar |
|---|---|---|---|---|
| 0 | Tope de gasto en las 4 consolas · desactivar el COMPLETO público | consolas, n8n | 1 h | **Sí** |
| 0.1 | Decidir «4 motores» y corregir la landing | copy de la web | — | **Sí** |
| 0.2 | `meta.modelos` sin Gemini · aviso «de 9 sondeos» | `build_lite2.py:991, 816` | 15 min | **Sí** |
| 1 | `headerAuth` en los dos webhooks | `build_lite2_panel.py`, `build_audit_panel.py` | 30 min | **Sí** |
| 2 | Longitudes máximas · blocklist SSRF · guarda de `SQL_COMPLETADO` · `run_id` en `Preparar Ack` | `validate.ts`, `build_lite2.py`, `panel_common.py` | 1 h | **Sí** |
| 3 | `fail_stale` + Vercel Cron | `build_panel_db.py`, `vercel.json` | 2 h | **Sí** |
| 4 | `origen` + `token_publico` + INSERT condicional con cupo diario | `schema.ts`, `build_panel_db.py` | 2 h | **Sí** |
| 5 | WAF por IP + captcha | Vercel, formulario | 1 h | **Sí** |
| 6 | Rutas `/api/publico/*` + `get_run_publico` + polling con backoff | `src/app/api/publico/`, `build_panel_db.py` | 3 h | — |
| 7 | Progreso, fase A (3 marcadores) | `panel_common.py`, `build_panel_db.py`, `repo.ts` | 3 h | — |
| 8 | Landing nueva con formulario y relato de espera | ver `docs/09` | — | — |
| 9 | Progreso, fase B (7 marcadores más) | `panel_common.py` | 2 h | — |
| 10 | Guardar `coste_usd` por run y sumarlo por mes | `schema.ts`, `panel_common.py` | 1 h | — |

Del 0 al 5 son **~8 horas** y no entregan nada visible. Son el precio de abrir la puerta.

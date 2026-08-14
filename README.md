# GEOpulse Panel

Panel de control interno de **BranDevs** para **GEOpulse**, la herramienta de auditoría GEO que corre sobre n8n. Permite lanzar análisis, ver todas las ejecuciones y abrir el detalle de cada informe.

El análisis **no vive aquí**: lo hacen los workflows de n8n. El panel los orquesta y consulta los resultados.

## La restricción que define la arquitectura

**El PostgreSQL de GEOpulse está dentro del servidor de n8n y no tiene salida al exterior.** El panel corre en Vercel, así que **no puede abrir una conexión directa a la base de datos**. Toda lectura y escritura pasa por un workflow de n8n (`panel-db`) que ejecuta la consulta con el nodo Postgres local.

Consecuencias que conviene tener presentes:

- Si n8n está caído, el panel **no puede mostrar nada**, ni siquiera el histórico.
- El webhook `panel-db` es **la única puerta a la base de datos y está expuesto a internet**. Va protegido con Header Auth; sin ese secreto, cualquiera que descubra la URL lee y escribe el histórico de auditorías.
- No hay transacciones entre operaciones: cada una es una llamada HTTP independiente.
- Cada consulta es una ejecución de n8n. Con polling, una pestaña de detalle abierta genera decenas por minuto: **pon el workflow en "Save successful executions: none"** para no inflar el historial.

A cambio, esto **simplifica el ciclo del análisis**: como n8n tiene la BD al lado, escribe él mismo el resultado al terminar. No hace falta que devuelva el informe al panel por callback.

## Stack

| Pieza | Elección | Por qué |
|---|---|---|
| UI + API | **Next.js (App Router) + TypeScript** | Despliegue serverless (Vercel): UI y rutas de API en un solo deploy. |
| Acceso a datos | **Workflow `panel-db` de n8n** | Es la única vía posible: el Postgres no es alcanzable desde fuera. |
| Esquema | **Drizzle como "esquema como código"** | `schema.ts` es la fuente de verdad; `db:generate` produce el SQL. **Nunca conecta**: el SQL se aplica desde n8n. |
| Estado servidor | **TanStack Query** *(fase 1)* | `refetchInterval` resuelve el polling sin `setInterval` a mano. |
| Auth | **Propia: cookie JWT firmada (`jose`) + scrypt** | Se descartó Auth.js: su adaptador de base de datos necesita conectarse a Postgres, y aquí no se puede. Sin adaptador aportaba poco más que el envoltorio. `scrypt` viene en Node, así que no añade binarios nativos al despliegue serverless. |
| Render del informe | Portado del vanilla + SVG existente | ~1.350 líneas ya probadas contra payloads reales; se conserva la paleta BranDevs. |

## Arranque (fase 0)

Necesitas **Node 20.12+** (probado con Node 24) y **Python 3** (solo para generar workflows).

```bash
npm install
```

Copia las variables de entorno y rellénalas:

```bash
cp .env.example .env.local
```

### Dar de alta la capa de datos en n8n

Esto hay que hacerlo **una vez**, y es lo que crea las tablas:

1. Genera el workflow (empaqueta dentro el SQL del esquema):

   ```bash
   python workflows/build_panel_db.py
   ```

2. Comprueba que ha salido bien:

   ```bash
   python workflows/validate_workflow.py workflows/panel-db-workflow.json
   ```

3. Importa `workflows/panel-db-workflow.json` en n8n y **actívalo**.
   - Al **reimportar** para actualizar, hazlo *dentro* del workflow abierto (⋯ → Import from File), no desde la lista (crearía un duplicado). Y reasigna la credencial de Postgres si al importar se suelta.
4. En n8n crea una credencial **Header Auth** llamada `GEOpulse Panel - Header Auth`, con **Name** = `x-panel-secret` (¡el nombre de la cabecera, no `authorization`!) y **Value** = un secreto fuerte en hex (`openssl rand -hex 32`; evita base64 con `=`, se pega mal). Asígnala al nodo Webhook.
5. Pon ese mismo valor en `N8N_PANEL_DB_SECRET` de tu `.env.local`.
6. Configura la credencial de Postgres del nodo `Ejecutar SQL` apuntando al Postgres **local** de ese servidor.
7. **Permisos de la base** (una vez, como superusuario). Desde PostgreSQL 15 el usuario normal no puede crear en el schema `public`. Da permiso al usuario de n8n:

   ```sql
   GRANT USAGE, CREATE ON SCHEMA public TO <usuario_de_n8n>;
   ```

   Si no sabes qué usuario es, lánzale al webhook `{"op":"whoami"}`: te devuelve `usuario`, `base` y `puede_crear_en_public`. El usuario crea y queda dueño de las tablas, así que luego los INSERT/SELECT/UPDATE del panel funcionan sin más permisos.

8. Lanza la migración una sola vez. Con PowerShell en Windows, `curl.exe` con `-d "{...}"` rompe el JSON: usa un fichero de cuerpo (`--data-binary "@body.json"`) o `Invoke-WebRequest`. Ejemplo con fichero:

   ```bash
   curl.exe -X POST "$N8N_BASE_URL/webhook/panel-db" \
     -H "Content-Type: application/json" \
     -H "x-panel-secret: $N8N_PANEL_DB_SECRET" \
     --data-binary '{"op":"migrate"}'
   ```

   Verifica con `{"op":"check"}`: debe devolver las tablas `informes`, `runs`, `users`.

   `migrate` **no es idempotente a propósito**: si las tablas ya existen falla, en vez de fingir que ha hecho algo. La migración se parte en una sentencia por item (el nodo Postgres de n8n solo ejecuta la primera sentencia de un SQL con varias).

### Levantar el panel

```bash
npm run dev
```

```bash
curl http://localhost:3000/api/health
```

Debe responder `{"ok":true,"n8n":true,"db":true}`. Son **tres hechos distintos a propósito**: que el panel viva no implica que n8n responda, y que n8n responda no implica que pueda consultar la BD. Si algo falla, devuelve `503` diciendo exactamente qué eslabón se ha roto. Es la única ruta pública; sin sesión no incluye el mensaje de error de n8n.

## Usuarios y acceso

El panel está cerrado: sin sesión, las páginas redirigen a `/login` y las rutas de API devuelven `401`. **No hay registro público**: las cuentas las crea un admin.

Cómo está montado, y por qué:

- **Sesión**: un JWT firmado (HS256, `jose`) dentro de una cookie httpOnly `gp_sesion`, con 12 h de vida. No hay tabla de sesiones porque la BD solo se alcanza por HTTP a través de n8n: consultarla en cada petición, con el polling del panel cada 2,5-3 s, sería un coste desproporcionado.
- **Contraseñas**: `scrypt` de `node:crypto` (N=2^15), con los parámetros dentro del propio hash para poder subirlos más adelante sin invalidar los existentes.
- **Middleware** (`src/middleware.ts`): corre en **runtime Edge** y solo verifica la firma de la cookie. **Nunca** consulta la BD ni importa `node:crypto`.
- **Roles**: `admin` y `miembro`. El miembro ve **solo sus ejecuciones**; el admin las ve todas y gestiona cuentas en `/usuarios`. El filtro se aplica en el SQL, no en el panel.

### Crear la primera cuenta

Problema del huevo y la gallina: `/usuarios` exige ser admin y al principio no hay ninguno. Para eso está `/api/auth/bootstrap`, que **solo funciona mientras no exista ningún usuario** y exige el secreto de `panel-db` (quien lo tiene ya puede escribir en la BD de todas formas, así que no concede nada nuevo):

En PowerShell, **no uses `curl.exe`**: rompe el JSON con comillas escapadas (`\"`) y acabas con `{"error":"json_invalido"}` y un error de puerto. Usa `Invoke-RestMethod`, y **canaliza a `ConvertTo-Json`** o PowerShell formatea la respuesta como tabla y recorta la contraseña fuera del ancho de consola:

```powershell
Invoke-RestMethod -Uri "http://localhost:3000/api/auth/bootstrap" -Method Post -ContentType "application/json" -Headers @{ "x-panel-secret" = "TU_SECRETO" } -Body '{"email":"tu@brandevs.com","nombre":"Tu nombre"}' | ConvertTo-Json -Depth 5
```

Devuelve la cuenta creada y una contraseña generada **que se enseña una sola vez**. Si mandas `"password"` en el cuerpo, usa esa (mínimo 12 caracteres). A partir de ahí, das de alta al resto desde `/usuarios`.

### Si te quedas fuera

Un miembro que pierda su contraseña se la resetea un admin desde `/usuarios`. Pero si la pierde el **único admin**, no hay forma de entrar por la interfaz. Para eso está la salida de emergencia, que se ejecuta desde donde tengas el `.env.local`:

```bash
node scripts/reset_password.mjs --email tu@brandevs.com --generar
```

Sin `--generar` la teclea (no se ve al escribir y no queda en el historial del shell). El script hashea en local, escribe por el webhook `panel-db` y **relee el hash para comprobar que valida de verdad** antes de decir que ha terminado. No concede ningún permiso nuevo: usa `N8N_PANEL_DB_SECRET`, y quien lo tiene ya puede escribir en la base de datos.

### Dar de alta a un compañero

En `/usuarios` (solo admin): email, nombre opcional, rol y contraseña opcional. Si la dejas en blanco, el panel genera una fuerte y la muestra una vez — **no se guarda en claro en ningún sitio**, así que anótala antes de cerrar el aviso. No hay envío de correo en el proyecto: se la pasas tú por un canal privado.

Desde ahí también puedes cambiar el rol, resetear la contraseña y quitar el acceso.

### Límites que conviene conocer antes de repartir cuentas

- **Quitar el acceso no es inmediato.** La cookie está firmada y no se consulta la BD en cada petición, así que quien ya tenga sesión abierta sigue dentro hasta que caduque (máx. 12 h). Lo mismo al resetear una contraseña. Para cortar **en el acto**: cambia `AUTH_SECRET` en Vercel — eso invalida las sesiones de **todo el mundo**, incluida la tuya, y todos vuelven a entrar con su contraseña. Con 4-5 personas el coste es bajo; es el compromiso que se aceptó para no consultar la BD en cada petición.
- **Borrar una cuenta no borra sus ejecuciones.** `runs.lanzado_por` es `ON DELETE SET NULL`: se quedan sin dueño y pasan a verlas solo los admins.
- **Las ejecuciones anteriores a la autenticación no tienen dueño** y, por lo mismo, solo las ven los admins. No se pueden reconstruir.
- **No hay recuperación de contraseña por correo**, porque no hay proveedor de email. Un "se me ha olvidado" lo resuelve un admin desde `/usuarios`; si el que la pierde es el único admin, `scripts/reset_password.mjs` (ver arriba).
- **No hay límite de intentos de login.** En serverless no hay memoria compartida entre invocaciones, así que un contador en memoria sería falso, y persistirlo costaría una ejecución de n8n por cada intento fallido. El freno real es el coste de scrypt (~100 ms por intento), que el error no distinga entre "email inexistente" y "contraseña mala", y que las contraseñas las generas tú. Si algún día hace falta más, el sitio es el WAF de Vercel, no el código del panel.
- **Si n8n está caído no se puede ni entrar**, porque la tabla de usuarios vive detrás de él. Es consecuencia directa de la arquitectura; de todos modos, con n8n caído el panel no sirve para nada.
- **El login del panel no protege la base de datos.** El webhook `panel-db` sigue expuesto con su secreto compartido, y ahora ese secreto permite además leer los hashes de contraseña y crear cuentas. Son hashes con salt, no contraseñas, pero trata `N8N_PANEL_DB_SECRET` como la credencial más sensible del proyecto.

## Dos agujeros que el login NO cierra

Salieron en la revisión de la autenticación, pero son **anteriores** a ella y viven en los workflows de análisis, no en el panel. Se dejan escritos aquí para que no se olviden:

1. **Los webhooks de análisis del panel no tienen autenticación.** `geopulse-lite2-panel` y `geopulse-audit-panel` aceptan cualquier POST. `trigger.ts` ya envía la cabecera `x-panel-secret` con `N8N_WEBHOOK_TOKEN`, pero **el nodo Webhook no la valida**: nadie que descubra la ruta necesita credencial. Y el hermano público (`geopulse-lite2`) es conocido desde los widgets de la web, así que la variante del panel solo añade el sufijo `-panel`. Consecuencia concreta: un POST a `geopulse-audit-panel` dispara ~64 llamadas LLM **de pago**, sin sesión y **sin pasar por `MAX_CONCURRENT_RUNS`** (ese tope solo existe en `/api/runs`). Poner un login al panel y dejar esto abierto deja la puerta de gasto sin cerrar.
   *Arreglo:* añadir `authentication: "headerAuth"` al nodo Webhook en `build_lite2_panel.py` y `build_audit_panel.py`, crear la credencial en n8n con **Name** = `x-panel-secret`, poner ese valor en `N8N_WEBHOOK_TOKEN` y reimportar los dos workflows. **Ojo con el orden**: si reimportas antes de crear la credencial y rellenar la variable, dejas de poder lanzar análisis.

2. **No existe el watchdog de ejecuciones colgadas.** `STALE_MINUTES` está documentado en `.env.example` pero no lo lee nadie. Los workflows de análisis solo escriben `en_curso` y `completado`; si uno muere a mitad (fallo de un nodo LLM, reinicio de n8n), la fila se queda en `en_curso` **para siempre**. Como `count_active` cuenta `pendiente` y `en_curso`, dos ejecuciones colgadas con `MAX_CONCURRENT_RUNS=2` **bloquean el lanzamiento a todo el mundo** sin que nada lo explique. Hoy la única salida es borrar la fila a mano.
   *Arreglo:* una op `fail_stale` en `panel-db` (`update runs set estado='error' … where estado in ('pendiente','en_curso') and started_at < now() - interval`) llamada desde un Vercel Cron.

## El workflow de análisis del panel

El webhook público (`geopulse-lite2`) responde **síncrono**: se queda abierto 1-2 min hasta terminar. Los widgets de la web dependen de eso, así que **no se toca**.

El panel usa una **variante propia** con ruta `geopulse-lite2-panel`, generada por `workflows/build_lite2_panel.py`, que reutiliza los nodos del builder original y solo cambia la fontanería:

1. Responde con un **ack inmediato** (el panel corre en serverless y no puede esperar minutos).
2. Marca la ejecución `en_curso`.
3. Corre **el mismo análisis** (mismos sondeos, prompts, pesos y nota).
4. Al terminar escribe el informe en `informes` y las columnas (`nota`, `veredicto`, `sov`, `sondeos`, `tiene_avisos`) en `runs`, marcando `completado`.

```bash
python workflows/build_lite2_panel.py
```

```bash
python workflows/build_audit_panel.py
```

Después importa en n8n `geopulse-lite2-panel-workflow.json` y `geopulse-audit-panel-workflow.json`, y actívalos. Las credenciales van fijadas en los builders, así que se enlazan solas al importar. La fontanería común de las dos variantes vive en `workflows/panel_common.py`.

> **La variante del COMPLETO no envía email.** El workflow público, al terminar, genera un PDF y lo manda por SMTP a la dirección que venga en la petición. Una auditoría interna lanzada desde el panel no debe enviar correo a nadie (podría acabar en el buzón de un cliente sin querer), así que esa rama —`Generar Informe HTML` → `HTML a PDF` → `Enviar Informe`— se elimina. Si algún día quieres "enviar este informe al cliente", que sea una acción explícita del panel.

> **Coste:** un COMPLETO son ~64 llamadas LLM de pago por ejecución. El tope `MAX_CONCURRENT_RUNS` es la defensa.

> **Si el guardado del informe falla, la ejecución NO se marca `completado`.** Se queda visible como no terminada. Es deliberado: marcarla completada sin informe sería fingir un resultado.

> **Deriva conocida:** el JSON de producción se había desviado del builder en la autenticación de Gemini (producción usa la credencial `googlePalmApi`; el builder, Header Auth genérica). La variante aplica la configuración **de producción**. Si vuelves a tocar auth en el editor de n8n, actualiza `CREDENCIALES_PROD` en el builder.

### Parche de `es_marca` (solo en la variante del panel)

El nodo `Ensamblar LITE2` original hace `es_marca: !!x.es_marca || …`, es decir, **se cree el flag que devuelve el agente LLM**. En una ejecución real el agente marcó como "tu marca" a 7 competidores; como el render toma el primer `es_marca` para la cuota, el donut mostraba un **17% de cuota propia** cuando la marca real tenía 1 de 36 menciones (**3%**).

La variante del panel lo corrige: ignora el flag del LLM y deriva `es_marca` del nombre usando `_diag.marca_distintivo`, el token distintivo que `Recopilar Respuestas` ya calcula excluyendo las palabras genéricas del sector y del mercado (así, una marca cuyo nombre incluya su propio sector no cuenta como mención cualquier empresa del sector).

**El workflow público sigue con la lógica antigua a propósito**, hasta validar el panel. Cuando se quiera migrar, el arreglo se mueve a `build_lite2.py` y afectará también a los widgets. El parche vive en `PARCHE_ES_MARCA`/`HELPER_ES_MARCA` de `build_lite2_panel.py` y **falla ruidosamente** si esa línea cambia en el builder original, para que no se aplique en silencio sobre código distinto.

> Esto no afecta a la nota: `nota`, `por_area.sov` y la matriz de `aparicion` usan otra detección que sí funciona.

### Parche de la puntuación competitiva (solo en la variante del COMPLETO)

`Calcular Score` puntuaba así la dimensión competitiva:

```js
const s_comp = mods === 0 ? 0 : (pm <= 3 ? 100 : (mods >= 2 ? 70 : 50));
```

Bastaba con que la marca fuese **nombrada** por 2 modelos para sacar **70/100**, aunque no tuviera ninguna posición atribuible. En una ejecución real el informe decía textualmente *"No hay evidencia textual suficiente para situarla frente a rivales"* y aun así puntuaba 70: con los pesos de SOV, ese 70 aportaba **14 de los 28,9 puntos — el 48% de la nota de visibilidad**.

La variante del panel lo corrige para que mande la **posición**, no la mención: ausencia → 0 (igual), posición ≤3 → 100 (igual), posición conocida >3 → escala, y **mencionada sin posición → presencia débil** proporcional a cuántos modelos la citan (2 de 4 → 20).

Con los datos de esa ejecución, la visibilidad pasa de **29 a 19**, que es lo que el informe describe en palabras.

### Modelos de las sondas (solo en las variantes del panel)

Una auditoría GEO mide **lo que obtiene un usuario real**, así que las sondas usan los modelos que sirve hoy la versión gratuita de cada producto:

| Sonda | Público | Variantes del panel |
|---|---|---|
| ChatGPT | `gpt-5.4-mini` | **`gpt-5.6-luna`** (por defecto para cuentas Free desde 08/2026) |
| Gemini | `gemini-2.5-flash` | **`gemini-3.5-flash`** (por defecto en la app desde 07/2026) |
| Claude | `claude-sonnet-4-6` / `claude-haiku-4-5` | sin cambios |
| Perplexity | `sonar` | sin cambios |

> **Gemini 3.x cambió el control de razonamiento.** `thinkingBudget` está deprecado y su sustituto es `thinking_level` (`minimal`/`low`/`medium`/`high`). **Enviar los dos devuelve un 400**, así que el builder *sustituye*, nunca añade. No hay equivalente exacto a `thinkingBudget: 0`: `minimal` es lo más cercano y **no garantiza** que el modelo no razone, que era el motivo original del budget 0 (Gemini gastaba los tokens pensando y cortaba la respuesta). Si vuelven a aparecer respuestas truncadas de Gemini, sube `maxOutputTokens` antes que cualquier otra cosa.

**Solo cambian las sondas.** Los agentes que también llaman a OpenAI (`Informe ChatGPT`, `Agente 5 - Huella Digital`, `Descubrir Directorios`) son el motor de la auditoría, no lo que ve un usuario; además dos usan la Responses API, donde cambiar de modelo es más arriesgado. Se quedan en `gpt-5.4-mini`.

### Detección de encabezados con parser real (no regex)

El workflow buscaba encabezados con `/<h([1-3])[^>]*>([\s\S]*?)<\/h\1>/gi` sobre el HTML **completo**, sin distinguir markup real de texto dentro de `<style>`, `<script>` o comentarios.

Medido en una home real: un comentario CSS que mencionaba `<h2>` en prosa fue interpretado como etiqueta, y su captura perezosa **se tragó 4.237 caracteres** hasta el siguiente `</h2>` — con el `<h1>` de verdad dentro. El informe decía "la home no tiene ningún H1" habiéndolo. Afecta a cualquier web con `<h2>` dentro de un comentario, un script de tracking o un CSS inline, así que se veía en todas las auditorías.

Las variantes del panel usan ahora un parser: **cheerio** si la instancia de n8n permite módulos externos (`NODE_FUNCTION_ALLOW_EXTERNAL`), y si no, un **tokenizador propio sin dependencias** que salta comentarios y elementos de texto crudo. Así el arreglo funciona con o sin esa variable de entorno, en vez de romperse en ejecución y desperdiciar una auditoría de pago.

> **Solo cambia la detección.** La forma de salida (`{nivel, texto}`) es idéntica, así que el análisis y la puntuación no se tocan.

> En un nodo Code de n8n **no se puede llamar `$` a la instancia de cheerio**: ese símbolo está reservado para las referencias entre nodos. El builder usa `__q`.

Nodos parcheados: `Parsear Home` (LITE), `Consolidar Señales Web` y `Analizar Landings` (COMPLETO). Verificado ejecutando el JS generado contra un HTML real: 1 H1 detectado, 0 encabezados fantasma, y 12 casos límite en verde.

### Temperatura de los agentes de análisis

Los 9 agentes de análisis del COMPLETO pasan de `temperature: 1` a **`0.2`** en la variante del panel, para reducir la varianza entre ejecuciones — lo que interesa en una auditoría que se repite y se compara consigo misma.

> `docs/04` afirma que `gpt-5.4-mini` rechaza `temperature` con un 400. **Esa nota está desfasada**: se comprobó a mano que sí la acepta. Si alguna ejecución empezara a fallar con un 400 en los agentes, `TEMPERATURA_ANALISIS` en `workflows/panel_common.py` es el primer sitio donde mirar.
>
> Ojo con la expectativa: bajar la temperatura reduce la **varianza**, no la **invención**. Las alucinaciones de las sondas se combaten con *grounding* (por eso Perplexity es el único que describe bien la marca), y el workflow ya las **detecta** en `verificacion_factual` en vez de esconderlas.

### El ruido del mapa competitivo se filtra al mostrar, no al guardar

Un informe real trajo **82 competidores, de los cuales 58 tenían UNA sola mención** (citas sueltas de un único modelo, incluidas entradas que ni son empresas). El filtrado se hace **en el render** (se muestran los de ≥2 menciones y se indica cuántos se omiten), no en el workflow: el dato crudo es la evidencia de la auditoría y se conserva íntegro en `informes`. El mapa no alimenta la nota, así que el ruido era solo un problema de presentación.

## Cambiar el esquema

1. Edita `src/server/db/schema.ts`.
2. `npm run db:generate` → escribe el SQL nuevo en `src/server/db/migrations/`.
3. `python workflows/build_panel_db.py` → reempaqueta el SQL en el workflow.
4. Reimporta el workflow en n8n y lanza la operación de migración.

No edites el SQL generado a mano, y no edites el JSON del workflow a mano: se pierde en la siguiente regeneración (`docs/04`).

## Verificar el render sin gastar una ejecución

Los dos informes se pueden previsualizar contra sus fixtures, sin llamar a n8n:

- http://localhost:3000/preview-informe — informe **LITE**
- http://localhost:3000/preview-informe?tipo=completo — informe **COMPLETO**

Los fixtures viven en `docs/ejemplo-informe-lite.json` y `docs/ejemplo-informe-completo.json`.

> El fixture del completo está **derivado del propio workflow** (los esquemas JSON que los agentes tienen obligación de devolver y los `return` de los nodos Code), no inventado. Aun así, **no procede de una ejecución real**: cuando se lance la primera auditoría completa hay que contrastar el render con el payload de verdad y corregir lo que baile.

El detalle de una ejecución elige el render **por la forma del informe** (`score.global` ⇒ completo, `nota` ⇒ lite), no por la columna `tipo`: si una fila se guardó con el tipo equivocado, manda el dato real.

## Comprobaciones que no necesitan ni n8n ni servidor

El proyecto no tiene runner de tests. Estas dos son las que cubren lo que un typecheck no ve, y se ejecutan en segundos:

```bash
npm run check
```

- `scripts/verificar_panel_db.mjs` — extrae el jsCode **real** del workflow generado y comprueba que cada operación devuelve tantos parámetros como placeholders `$N` tiene su SQL (un desajuste ahí no lo detecta ni TypeScript ni el validador: revienta en producción), que los emails y roles se normalizan, que `migrate` sigue partiéndose en una sentencia por item, y que los intentos de inyección y los UUID inválidos se rechazan.
- `scripts/verificar_auth.mjs` — compila los módulos de auth y comprueba el hash de contraseñas (formato, salt, coste real, hashes corruptos) y la cookie de sesión (ida y vuelta, firma manipulada, payload alterado, secreto rotado, `AUTH_SECRET` ausente).

## Estructura

```
src/
  middleware.ts               puerta de entrada (runtime EDGE: solo verifica la cookie)
  app/
    api/health/route.ts       GET /api/health (panel → n8n → Postgres). Única ruta pública
    api/auth/                 login · logout · bootstrap (primera cuenta)
    api/runs/ · api/usuarios/ ejecuciones y cuentas
    login/ · usuarios/        pantalla de entrada y gestión de cuentas
    layout.tsx · page.tsx     shell del panel
  lib/report/                 render de los informes (portado del frontend público)
    InformeLiteView.tsx       informe LITE
    InformeCompletoView.tsx   informe COMPLETO (4 dimensiones, factual, plan, KPIs)
    primitivas.tsx            piezas comunes a los dos
  lib/shared/                 tipos usados por cliente Y servidor
    status.ts                 estados y tipos de ejecución
    dto.ts                    contratos de la API
    auth.ts                   roles y contratos de sesión (sin nada secreto)
    report.ts                 esquema del informe LITE
    report-completo.ts        esquema del informe COMPLETO
  server/
    n8n/client.ts             capa de datos: llama al workflow panel-db
    auth/password.ts          scrypt — SOLO runtime Node
    auth/session.ts           firma/verifica la cookie — Edge y Node
    auth/guard.ts             leerSesion · exigirSesion · exigirAdmin
    users/repo.ts             cuentas, a través de panel-db
    db/schema.ts              tablas runs · informes · users (esquema como código)
    db/migrations/            SQL versionado, generado por drizzle-kit
workflows/
  build_panel_db.py           genera el workflow de la capa de datos
  validate_workflow.py        validador que pide docs/04
  build_lite2.py · build_workflow_v10.py    builders de los análisis
scripts/
  verificar_panel_db.mjs      ejerce el jsCode real del workflow panel-db
  verificar_auth.mjs          hash de contraseñas y cookie de sesión
  reset_password.mjs          salida de emergencia si el único admin queda fuera
  portar_css_informe.py       regenera el CSS del informe COMPLETO
docs/                         contexto del proyecto (00 → 05)
```

## Las tres reglas que no se negocian

1. **Cambios pequeños y verificables.** Nada de reescrituras cuando basta un ajuste.
2. **Honestidad técnica y de datos.** Los `avisos` y los estados `no_verificable` se muestran tal cual; nunca se convierten en un 0 inventado.
3. **La lógica GEO vive en n8n.** El panel orquesta y almacena. Si el análisis cambia, se cambia el builder del workflow, no el panel.

## Documentación

`docs/` contiene el contexto completo: 00 proyecto · 01 arquitectura · 02 contrato de workflows (esquema del informe) · 03 modelo de datos · 04 gestión de workflows · 05 fases. Más `docs/ejemplo-informe-lite.json`, el fixture con el que se verifica el render.

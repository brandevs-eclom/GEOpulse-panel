# CLAUDE.md — GEOpulse Panel

Este fichero lo lee Claude Code en cada sesión. Resume las reglas del proyecto. El contexto completo está en `docs/`.

## Qué es esto

Panel de control interno de la agencia **BranDevs** para **GEOpulse**, una herramienta de auditoría GEO (mide si la IA —ChatGPT, Claude, Gemini, Perplexity— recomienda una marca en su sector) que ya existe y corre sobre **n8n**. El panel permite ver las ejecuciones, lanzar análisis por detrás y ver el detalle de cada informe. **Lee `docs/` antes de programar.**

## Arquitectura en una frase

El panel hace `POST` a los **webhooks de n8n existentes** (que son el motor de análisis), guarda ejecuciones e informes en **PostgreSQL**, y muestra todo en una UI. El frontend/stack lo propones tú y lo justificas (ver `docs/01`).

## Reglas de trabajo (importantes)

- **Cambios pequeños y verificables.** Nada de reescrituras completas cuando basta un ajuste. Este principio viene del proyecto original y se mantiene.
- **Verifica lo que construyes.** Backend con datos de prueba; render con `docs/ejemplo-informe-lite.json` (un informe real con los 4 modelos).
- **Honestidad técnica.** Si algo tiene coste, riesgo o límite, dilo antes de darlo por bueno. No prometas de más.
- **No reimplementes la lógica GEO** en el backend. El análisis vive en los workflows de n8n. Si el análisis cambia, se cambia el builder del workflow (`workflows/*.py`), no el panel.
- **Respeta la honestidad de los datos del informe**: muestra los `avisos` y los estados `no_verificable` tal cual; no los escondas ni los maquilles.
- **No toques los pesos de puntuación ni las claves de modelo.** La nota debe seguir siendo comparable entre lite y completo y con auditorías previas.
- **Auth: respeta la frontera Node/Edge.** El hash y la verificación de contraseñas (`src/server/auth/password.ts`, scrypt) son **runtime Node**. El middleware corre en **Edge** y solo verifica la firma de la cookie: no consulta la base de datos y no puede importar nada que use `node:crypto`. Si `npm run build` se queja de un módulo no soportado, es que se ha colado un import de Node en el middleware.
- **Las operaciones sobre `users` normalizan el email a minúsculas** dentro del workflow `panel-db`. El `unique` de Postgres no es case-insensitive, así que saltarse eso hace convivir dos cuentas con el mismo email y vuelve ambiguo el login.

## El detalle que más se olvida

Los webhooks responden **síncronos y tardan** (lite 1-2 min, completo 3-5 min). El panel debe ser **asíncrono con polling**: crear la ejecución, responder un id, disparar el POST a n8n en 2º plano, y que el navegador consulte el estado. Ver `docs/01` (sección "el reto de la llamada síncrona").

## Estructura

- `docs/` — contexto: 00 proyecto · 01 arquitectura · 02 contrato de workflows (esquema del informe) · 03 modelo de datos · 04 gestión de workflows · 05 fases. Más `ejemplo-informe-lite.json` (fixture de render).
- `workflows/` — los builders de Python de los workflows de n8n (`build_lite2.py`, `build_workflow_v10.py`), los JSON generados, y dos frontends HTML de referencia (`geopulse-lite2.html`, `geopulse-frontend-brandevs.html`) de los que puedes portar la lógica de render.
- El resto de la estructura la propones tú en la fase 0.

## Empezar

Sigue `docs/05-FASES.md`. Fase 0: proponer stack + estructura, levantar esqueleto con Postgres y `/api/health`. No generes código de producto hasta acordar el stack.

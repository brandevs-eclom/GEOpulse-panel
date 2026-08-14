# 05 · Plan por fases

Construir por fases. Cada fase debe dejar algo **funcionando y verificable** antes de pasar a la siguiente. No intentes hacerlo todo de golpe.

## Fase 0 — Cimientos y acuerdo (sin código de producto todavía)

- Proponer el stack (frontend, backend, ORM, cómo se ejecuta el trabajo en 2º plano) con justificación breve de cada pieza.
- Proponer la estructura de carpetas del repo.
- Levantar el esqueleto: proyecto vacío que arranca, conexión a Postgres, primera migración con las tablas `runs` e `informes`, variables de entorno (`.env.example`) documentadas.
- Un endpoint de salud (`GET /api/health`) que confirme que el backend vive y habla con Postgres.

**Hecho cuando**: el proyecto arranca, la migración crea las tablas, `/api/health` responde ok.

## Fase 1 — Lanzar y ver (el núcleo)

El objetivo es el flujo completo de una ejecución de punta a punta, empezando por el **LITE** (más rápido y barato de probar).

- `POST /api/runs`: valida marca/dominio/sector, crea la fila en `runs` (estado `pendiente`), responde con el `id`, y dispara el trabajo en 2º plano que hace el POST al webhook de n8n.
- El worker/proceso: marca `en_curso`, llama a n8n con timeout generoso, al recibir el informe lo guarda en `informes`, extrae `nota`/`veredicto`/`sov`/`sondeos`/`tiene_avisos` a `runs` y marca `completado`. Si falla, `error` con el mensaje.
- `GET /api/runs` (listado paginado) y `GET /api/runs/:id` (detalle con el informe).
- **Frontend mínimo**:
  - Formulario de lanzamiento (marca, dominio, sector, país, región; toggle lite/completo).
  - Tabla de ejecuciones con estado en vivo (polling): fecha, marca, dominio, tipo, estado, nota, chip de "avisos" si los hay.
  - Página de detalle que **renderice el informe**: al menos las áreas (`por_area`), el GEO Score, el resumen, los avisos, la matriz de aparición de los 4 modelos, y el mapa competitivo. Reutiliza la lógica de los frontends actuales (ver `docs/02` para el esquema y los HTML de referencia).
- Límite de concurrencia configurable (máx. N análisis a la vez).

**Hecho cuando**: puedo lanzar un análisis LITE desde el panel, verlo pasar de pendiente a completado sin recargar, y abrir su detalle con el informe pintado.

## Fase 2 — El informe completo y el detalle rico

- Soportar el webhook `geopulse-audit` (completo) con su duración larga y su timeout mayor.
- Render de las secciones extra del completo: las 4 dimensiones (descubrimiento, competitivo, conocimiento, reputación), verificación factual, huella por canal, plan de acción, KPIs, citas destacadas.
- En el detalle técnico: mostrar el `payload` enviado, tiempos, `_diag`, y (plegado) el JSON crudo para depurar.
- Reintento manual de una ejecución en error (reusar el `payload` guardado, sin duplicar historial de forma confusa).

**Hecho cuando**: una auditoría completa se lanza, sobrevive los ~5 min, y su detalle muestra todo el informe profesional.

## Fase 3 — Vista de agencia (histórico y métricas)

- **Evolución por dominio**: como un mismo dominio se audita varias veces, una vista que muestre la progresión del GEO Score y de la visibilidad (sov) en el tiempo para un dominio.
- Dashboard con métricas: nº de análisis, reparto de veredictos, nota media por sector, dominios peor/mejor posicionados.
- Filtros y búsqueda en el listado (por dominio, sector, rango de fechas, estado, tipo).
- Export (CSV/PDF) de una ejecución o de un listado, si se necesita para clientes.

**Hecho cuando**: puedo seguir la evolución de un cliente a lo largo de varias auditorías y sacar una foto agregada del conjunto.

## Fase 4 (opcional) — Automatización y operación

- Programar auditorías recurrentes (p. ej. re-auditar un dominio cada mes) con un scheduler.
- Despliegue de workflows a n8n vía su API REST desde el repo (ver `docs/04`), con salvaguardas para no pisar producción.
- Auth de usuarios más fina (roles: quién puede lanzar completos —que cuestan— vs. quién solo ve).
- Alertas: avisar si la visibilidad de un cliente cae entre dos auditorías.

## Cómo trabajar dentro de cada fase

- Cambios pequeños y verificables. Nada de reescrituras cuando basta un ajuste.
- Verifica lo que construyes: si es lógica de backend, con datos de prueba; si es render, con un informe de ejemplo (puedes generar uno guardando la salida real de un webhook, o construir un fixture a partir del esquema de `docs/02`).
- Honestidad técnica: si algo tiene un coste, un riesgo o una limitación, dilo antes de dar por buena una decisión.

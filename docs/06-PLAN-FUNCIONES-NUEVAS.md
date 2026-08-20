# 06 · Plan de implementación de las funciones nuevas

Plan por fases para llevar GEOpulse al siguiente nivel a partir de `GEOPULSE-FUNCIONES-NUEVAS.md`.
**No es una reconstrucción**: es una secuencia para *añadir* capacidades sobre lo que ya existe, ordenada
por valor/esfuerzo y por dependencias reales, no por el orden del catálogo.

Cada función del catálogo se auditó contra el código real y se clasificó `KEEP / REFACTOR / REPLACE / NEW`.

## El hallazgo que cambia el plan

**El motor ya hace mucho más de lo que el catálogo asume.** De las 35 funciones auditadas: **13 son REFACTOR**
(ampliar algo que ya existe), **21 NEW**, **1 REPLACE**. Casi todo el Bloque A-E es *ampliar*, no *crear*:

- Estados por métrica (`ok|warning|error|no_verificable`), verificación factual por afirmación, alucinaciones
  con gravedad → la **honestidad del dato ya está**, en forma cualitativa. A1 solo la vuelve numérica.
- **Posición en ranking, `tasa_aparicion`, `share_of_voice`, mapa competitivo** ya se calculan (evaluadores
  D1/D2). A3/A4 son ampliar prompts, no construir.
- **Fuentes citadas clasificadas por tipo + "dónde ya estás / dónde colocarte"** ya existe (`CODE_RECO`). A5 es
  añadir dos flags.
- **Geolocalización parametrizada (17 países)** ya está; A6 es meterla en un bucle.
- El informe **ya se persiste entero** (`informes.informe` jsonb) y los escalares comparables ya van a columnas
  de `runs` (`nota`, `sov`, `veredicto`). El Bloque F (histórico) necesita sobre todo **una op de lectura de
  serie por dominio**, no un rediseño de datos.

**Lo que de verdad no existe:** par numérico `confidence+source` por dato (A1), universo de consultas
persistente (A2), KPIs GEO finos (A3/A4 como campos), modelo determinista de valor/prioridad (D3/D4),
observabilidad de coste/tokens (E1), versionado (E2), toda la capa histórica/monitorización (F) y la de
plataforma (G).

## Restricciones duras que ordenan todo

1. **Los pesos del score están congelados.** `CODE_SCORE` usa `pesos = {seo_tecnico:0.25, contenido:0.15,
   sov:0.35, huella:0.25}`, fijos por diseño: la nota tiene que ser comparable entre LITE y COMPLETO y con
   auditorías previas (CLAUDE.md). → **D2 (pesos dinámicos) rompe esa comparabilidad**: es una decisión de
   producto, no una tarea, y va aparte. **Todo KPI nuevo (A3/A4) debe ser informativo, nunca alimentar la nota.**
2. **El coste manda el orden.** A2 y A6 multiplican los sondeos de pago (A6 = 48 sondeos por *locale* en el
   COMPLETO). Por eso **medir el coste (E1) y cachear (E4) van ANTES** que multiplicarlo.
3. **Dato inferido ≠ dato medido.** Es el corazón del producto (y de A1). Cualquier `confidence`, autoridad de
   fuente (A5), NAP (B3) o causa (D1) que **produzca el LLM** debe marcarse como inferencia, o repetimos el bug
   `es_marca` (el LLM marcaba competidores como "tu marca" e inflaba la cuota).
4. **Los workflows se tocan solo desde su builder de Python.** Nunca el JSON exportado (`GEOpulse.json` está
   drifteado). Y el mecanismo de migraciones **no es idempotente** (docs/03): E1, E2, A2, E4 y F1 añaden
   columnas y hay que arreglar `leer_migraciones()`/`migrate` antes de la primera migración `0001`.

---

## Las 9 fases

Cada fase es un lote entregable y verificable por sí solo. El orden respeta dependencias reales, no el catálogo.

### Fase 1 · Trazabilidad y honestidad transversal — `E2 · E1 · E3` — ✅ HECHA (2026-08-19)
**Objetivo:** instrumentar versión, coste y estado por módulo **sin tocar la nota**. Son baratos y habilitan
medir todo lo demás.
- **E2 · Versionado** (NEW, trivial): ✅ constantes `analysis_version`/`scoring_version`/`prompt_version` en
  ambos builders → `meta` del informe (`completo-v10`/`lite-v2`, `score-v1`, `prompt-v1`). Se sella en el nodo
  final (`Ensamblar Reporte` / `Ensamblar LITE2`) para que todo informe lo lleve. **Nota:** se guarda en
  `informe.meta` (jsonb), **no** en columnas de `runs` — las migraciones no son idempotentes (ver riesgos).
- **E1 · Coste por run** (REFACTOR, alto): ✅ tokens **medidos** del `usage` real de cada API (4 formas
  distintas normalizadas) + `estimated_cost_usd` desde una **tabla de tarifas editable** en el builder,
  marcada como estimación; un modelo sin precio no se inventa (`sin_precio[]`, `completo:false`, el total es un
  suelo). Se emite `informe.coste` + resumen en `meta`. En el COMPLETO los 8 agentes langchain **no exponen
  usage** → se declaran en `coste.no_medido` en vez de fingir tokens. En LITE todas las llamadas son HTTP
  crudo, así que no hay hueco.
- **E3 · Estados por módulo** (REFACTOR, medio): ✅ COMPLETO (`informe.estados_modulos`, 11 módulos) **y LITE**
  (4 módulos: seo_tecnico, huella_digital, visibilidad, informe) con `completed|partial|failed` por bloque +
  aviso en ambos renders que distingue "no se pudo" de "medido a medias". El módulo `informe` de LITE saca a la
  superficie el fallo silencioso del agente (JSON no parseable → `A={}`), que ningún aviso capturaba.

**Extra de honestidad (E1) hecho aquí:** el coste ahora deriva el **modelo real** de la respuesta de la API
(`body.model`/`modelVersion`) porque `panel_common.py` cambia las sondas del panel a modelos del tier gratuito
(ChatGPT→`gpt-5.6-luna`, Gemini→`gemini-3.5-flash`); antes el coste los etiquetaba/tarifaba como los base. Tarifa
por prefijo (absorbe sufijos de versión) y tabla de precios ampliada.

**Verificación:** ✅ `scripts/verificar_ensamblar.mjs` (COMPLETO) y `scripts/verificar_lite.mjs` (LITE) —ambos
en `npm run check`— ejercen el jsCode real contra fixture: normalización de coste por proveedor, agregación con
modelo sin precio, y estados por módulo (real todo `completed`; simulados `partial`/`failed`).

### Fase 2 · Entregables rápidos sin riesgo — `G12 · B2 · C2` — ✅ HECHA (2026-08-19)
**Objetivo:** valor visible de bajo riesgo mientras asientan los cimientos.
- **G12 · Exports** (REFACTOR, medio): ✅ helpers puros `src/lib/report/export.ts` (JSON crudo + fila CSV de 30
  escalares, tolerante LITE/COMPLETO vía forma, `null`→celda vacía nunca 0) + botones JSON/CSV/Imprimir en
  `runs/[id]` (descarga 100% cliente, sin endpoint) + `@media print` (COMPLETO ya lo tenía; añadido el del LITE
  —abrir acordeón— y ocultar el chrome del panel con `.gp-no-print` en `globals.css`).
- **B2 · Answer-first / intent** (REFACTOR, bajo): ✅ el Agente 3 del COMPLETO añade `answer_first` (posición de
  la respuesta) e `intent_mismatch` (tipo-keyword vs tipo-página), **desglose** de `intent_match`, no duplicado.
  Informativos e **inferidos**: se marcan "(inferido por IA)" en el render del panel y del email, y **no entran
  en `score_cont`** (pesos congelados). `prompt_version` → `prompt-v2`.
- **C2 · Variantes de marca** (REFACTOR, medio): ✅ el agente LITE devuelve `variantes_marca`; el ensamblado
  separa **medido** (`deteccion`, tokens deterministas) de **inferido** (`observadas`, grafías del LLM), estas
  filtradas con `pareceMarca` (mismo criterio que el parche es_marca) para que un competidor no se cuele. No
  tocan menciones ni SoV. Render con chips `.tag-inferido`. `prompt_version` LITE → `prompt-v2`.

**Verificación:** ✅ `scripts/verificar_export.mjs` (nuevo, en `npm run check`) ejerce los helpers contra ambos
fixtures (round-trip JSON, escalares por forma, honestidad null→vacío, escapado CSV). B2 y C2 cubiertos por
`verificar_ensamblar.mjs` y `verificar_lite.mjs` (esquema del agente, `Calcular Score` no usa los campos, filtro
`pareceMarca` no acepta competidores, variantes tras el mapa). Render confirmado en el preview.

### Fase 3 · Capa de honestidad del dato — `A1`
**Objetivo:** anotar cada dato con `confidence` (0-1) y un `source` enum determinista
(`crawler | validador_schema | sondeo_llm | inferencia_llm`).
- **A1** (REFACTOR, alto): va sola en su fase porque toca el esquema de casi todos los agentes de ambos
  builders y el render. Empezar por el `source` **determinista** (lo sabe el nodo que produce el dato, no el
  LLM) y dejar el `confidence` numérico para donde tenga sentido; un valor inferido se marca, no se presenta
  como medido.

**Verificación:** toda métrica trae `confidence` y `source`; `no_verificable` ⇒ confianza baja; ningún dato del
crawler queda marcado como inferencia y viceversa.

### Fase 4 · Métricas finas de visibilidad y competencia — `A3 · A4 · A5`
**Objetivo:** ampliar los evaluadores, **todo informativo** (no entra en la nota).
- **A3 · Prominencia** (REFACTOR, medio): D1 ya da `posicion`/`total_listadas`; añadir *primera mención* (orden
  en el texto) y *prominencia vs competidores*.
- **A4 · Mención/recomendación/inclusión** (REFACTOR, medio): hoy solo se cuenta "aparece"; separar los tres
  niveles → `Brand Mention Rate`, `Recommendation Rate`, `Answer Inclusion`.
- **A5 · Mapa de autoridad de fuentes** (REFACTOR, medio): `CODE_RECO` ya clasifica por tipo y calcula "dónde
  colocarte"; añadir dos flags — autoridad aproximada y **si el dominio es de un competidor** (cruzar contra
  `mapa_competitivo`).

> **Dependencia crítica:** A3/A4 se apoyan en el conteo de menciones, que arrastra el bug `es_marca`. **Arreglar
> la detección de marca antes** o los KPIs nuevos heredan el sesgo.

**Verificación:** primera-vs-última mención dan prominencia distinta; "cita como ejemplo pero recomienda a otro"
⇒ mención=sí, recomendación=no; las fuentes de competidor quedan como "no colocables".

### Fase 5 · Extractabilidad y accionables on-page — `B1 · B3`
**Objetivo:** análisis por página y generación de schema pegable.
- **B1 · Extractability score** (REFACTOR, alto): el Agente 3 ya evalúa señales cercanas
  (`estructura_extraccion`, `indice_autoridad`); ampliar a un `extractability_score` **por página** explicado
  por señales (respuestas directas, datos/tablas, headings-pregunta, fragmentos autocontenidos).
- **B3 · Generador de schema** (NEW, medio): hoy solo se *detecta* schema (`analizarOrg`); **generar** el
  JSON-LD recomendado para los huecos (FAQPage, Service, LocalBusiness) listo para pegar.

**Verificación:** una página con FAQ+datos puntúa más y enumera por qué; el JSON-LD generado valida en el
validador oficial y corresponde a contenido real (Google lo exige).

### Fase 6 · Diagnóstico probabilístico y priorización determinista — `D1 · D3 · D4`
**Objetivo:** pasar de auditoría a analista.
- **D1 · Causa raíz con probabilidad** (REFACTOR, medio): el Analista ya da `gaps_criticos`; añadir
  `root_causes[]` cada una con `confidence` y evidencia real.
- **D3 · Valor de negocio** (NEW, medio): ponderar oportunidades por valor comercial, no solo por volumen
  (entrada del proyecto: servicios/productos prioritarios).
- **D4 · Prioridad con fórmula** (REPLACE, alto): hoy la prioridad `alta|media|baja` la pone el LLM; sustituir
  por `Impacto × Valor × Confianza × Oportunidad ÷ Esfuerzo`, con los factores visibles. Depende de D1/D3 y de
  A1 (la `confianza` de la fórmula sale de ahí).

**Verificación:** las causas traen evidencia real, no inventada; cambiar un factor reordena el plan de forma
coherente.

### Fase 7 · Histórico y monitorización — `F1 · F2 · F4 · F3`
**Objetivo:** medir evolución. **Depende de A2** para comparar peras con peras (mismas consultas), aunque F1/F2
sobre los escalares que ya se guardan puede arrancar antes en modo "mejor esfuerzo".
- **F1 · Snapshots** (NEW, alto): evolución `hoy/7d/30d/90d` con delta y tendencia. Los escalares (`nota`,
  `sov`) ya están en `runs`; falta **una op de lectura de serie por dominio** en `panel-db` y la vista.
- **F2 · Diff de respuestas** (NEW, alto): comparar run actual vs anterior (¿dejó de mencionarte un modelo?,
  ¿competidor nuevo?). La materia prima ya está en `informes.informe`.
- **F4 · Cambios de competidores** (NEW, alto): mismo sustrato que F1/F2.
- **F3 · Alertas** (NEW, alto): caída de visibilidad/citación, ganancia de competidor. Vía **cron de n8n** (su
  fuerte). Requiere primero un `vercel.json`/cron que hoy no existe.

**Verificación:** varias ejecuciones dibujan la serie; un cambio real de mención se resalta; forzar una caída
dispara la alerta.

### Fase 8 · Coste, caché y escala del análisis — `E4 · A2 · A6`
**Objetivo:** frenar el coste **antes** de multiplicarlo.
- **E4 · Caché incremental** (NEW, alto): hash del HTML/inputs; si nada cambió, reutilizar deterministas y no
  relanzar el LLM. Ahorro directo.
- **A2 · Universo de consultas persistente** (NEW, alto): tabla `ai_queries` + concepto de proyecto; el builder
  **recibe** el set en vez de regenerarlo. Es la base real del histórico comparable (Fase 7).
- **A6 · Multi-locale** (REFACTOR, alto): meter la geo ya parametrizada en un bucle por locale. **Multiplica el
  coste** → va después de E4 y con tope de gasto.

**Verificación:** re-lanzar sin cambios no repite las llamadas caras; dos runs del mismo proyecto usan el mismo
set base; dos ubicaciones se muestran lado a lado.

### Fase 9 · Plataforma / Search Intelligence — `G11 · C1 · G1-G10`
**Objetivo:** solo si se decide competir en SEO tradicional. **Meses + presupuesto de APIs de pago + crawler
headless.** Casi todo NEW y riesgo alto.
- Entrada sensata y **gratuita**: **G11 · GSC/GA4** (alto valor, sin coste de API).
- **C1 · Grafo de entidad + NAP** (REFACTOR, alto): la extracción de entidades ya existe (plana); el grafo y la
  consistencia NAP necesitan una fuente de directorios estructurados que el pipeline no recoge hoy.
- El resto (G1 crawler, G4/G5/G8 APIs de pago, G10 search graph) es la plataforma tipo Semrush: decisión de
  negocio, no trabajo inmediato.

---

## Riesgos transversales

| Riesgo | Mitigación |
|---|---|
| **D2 rompe la comparabilidad de la nota** entre LITE/COMPLETO y con auditorías previas. | Sacarlo del plan técnico: es decisión de producto (¿versión de scoring v4 + histórico re-scoreado?). Mientras, todo KPI nuevo es informativo. |
| **El bug `es_marca`** infla la cuota y sostiene el conteo de menciones sobre el que se apoyan A3/A4/A5. | Arreglar la detección de marca **antes** de la Fase 4. |
| **Presentar inferencia del LLM como dato medido** (confidence de A1, autoridad de A5, causa de D1, NAP de B3). | A1 primero: el `source` deja explícito qué es medido y qué inferido. |
| **Migraciones no idempotentes** (docs/03). E1, E2, A2, E4, F1 añaden columnas. | Arreglar `migrate`/`leer_migraciones()` antes de la primera `0001`. |
| **A2 y A6 multiplican los sondeos de pago.** | E1 (medir) y E4 (cachear) van antes; tope de gasto por proyecto. |
| **Editar el JSON exportado en vez del builder.** | Regla del proyecto: solo desde `build_*.py`; validar y reimportar. |

## Decisiones que son tuyas (no técnicas)

1. **D2 · pesos dinámicos:** ¿rompemos la comparabilidad del score (nueva versión, histórico segmentado) o los
   mantenemos congelados y D2 no se hace?
2. **A6 · multi-locale:** multiplica el coste por cada locale (48 sondeos/locale en COMPLETO). ¿Apruebas el
   modelo de coste y un tope?
3. **Bloque G · plataforma:** ¿se compromete presupuesto de APIs de pago (SERP/keywords/backlinks) e infra de
   crawler, o se limita el alcance a la capa GEO + G11 gratis?
4. **C1/B3 · NAP y directorios:** necesitan una fuente estructurada de NAP que el pipeline no recoge. ¿De dónde
   sale (entrada manual del proyecto, API, scraping)?

## Orden corto recomendado

**Ahora:** Fase 1 (E2+E1+E3) → Fase 2 (G12+B2+C2) → Fase 3 (A1) → Fase 4 (A3+A4+A5).
**Después:** Fase 5 (B1+B3) → Fase 6 (D1+D3+D4) → Fase 7 (histórico) → Fase 8 (coste/caché/escala).
**Solo si se va a plataforma:** Fase 9, empezando por G11 (GSC/GA4).

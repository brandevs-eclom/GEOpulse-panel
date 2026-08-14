# 02 · Contrato de los workflows de n8n

Este es el contrato que el panel debe respetar al hablar con n8n. **Es la interfaz entre el panel y el motor de análisis.** No lo cambies desde el panel; si algo tiene que cambiar aquí, se cambia en el workflow (ver `docs/04`).

## Endpoints

Ambos son `POST`, responden de forma **síncrona** (la conexión queda abierta hasta que el análisis termina) y devuelven `Content-Type: application/json`. El nodo final añade `Access-Control-Allow-Origin: *`.

| Informe | Path del webhook | Nodos | Duración típica | Coste aprox. |
|---|---|---|---|---|
| LITE v2 (muestra) | `/webhook/geopulse-lite2` | 24 | 1–2 min | bajo (~13 llamadas LLM) |
| Completo (profesional) | `/webhook/geopulse-audit` | 71 | 3–5 min | ~64 sondeos + 4 agentes + informe |

La URL base de n8n va en variable de entorno (p. ej. `N8N_BASE_URL=https://api.brandevs.com`). La URL final sería `${N8N_BASE_URL}/webhook/geopulse-lite2`.

> Nota: en producción los webhooks usan la ruta `/webhook/...`. En pruebas dentro del editor de n8n la ruta es `/webhook-test/...` y solo responde una vez con el editor abierto. El panel debe apuntar a `/webhook/...`.

## Entrada (body del POST) — igual para ambos

```json
{
  "brand":   "BranDevs",                      // obligatorio
  "domain":  "brandevs.com",                  // obligatorio (con o sin http/https; el workflow lo normaliza)
  "keyword": "agencia de marketing digital",  // obligatorio (el sector/término)
  "pais":    "ES",                            // opcional, ISO-3166 alpha-2. Por defecto "ES"
  "region":  "Madrid"                         // opcional (ciudad o región; afina la geolocalización de los sondeos)
}
```

Validación que hace el propio workflow (nodo `Normalizar Input`): si falta `brand`, `domain` o `keyword`, lanza error. Normaliza el dominio a origin (`https://host`, sin `www`, sin barra final). Mapea `pais` a nombre y compone `mercado = "region, país"`.

**El panel debe validar estos tres campos antes de disparar**, para no gastar una llamada en un 400.

Países soportados en el mapeo actual: ES, MX, AR, CO, CL, PE, US, GB, FR, DE, IT, PT. Otros códigos se aceptan pero se usan tal cual.

## Salida — esquema del informe

La respuesta es el objeto informe (en el completo puede venir envuelto según el nodo final; **el panel debe tolerar recibir el objeto directamente o dentro de un array `[{...}]`** y quedarse con el primero). Este es el esquema del **LITE**; el completo es un superconjunto (mismas claves de cabecera, más secciones).

```jsonc
{
  "meta": {
    "brand": "…", "domain": "https://…", "host": "…",
    "keyword": "…", "mercado": "Madrid, España",
    "version": "lite2",                 // o "completo"
    "fecha": "2026-07-22T…Z",
    "modelos": ["ChatGPT","Claude","Gemini","Perplexity"],
    "preguntas_lanzadas": 3,
    "sondeos": 12                       // sondeos que devolvieron respuesta (puede ser < máximo)
  },

  "nota": 73,                           // GEO Score 0-100. Puede ser null si no hubo datos suficientes.

  "por_area": {                         // las estadísticas de cabecera (0-100 o null)
    "seo_tecnico": 80,
    "contenido": 90,
    "sov": 58,                          // "share of voice" = visibilidad en IA
    "huella": 56
    // (nota: infraestructura se fusionó dentro de seo_tecnico; ya NO es un área propia)
  },

  "resumen_hallazgos": "Texto de 2-3 frases redactado por el agente.",

  "posicionamiento": { "veredicto": "parcial" },  // visible | parcial | invisible | sin_datos

  "avisos": [                           // ← IMPORTANTE: mostrarlos. Vacío si todo se pudo medir.
    "No hemos podido leer el contenido de tu home (respuesta 403)…"
  ],

  "seo_tecnico": {
    "puntos": [                         // cada punto: estado ok|warning|error|no_verificable
      { "clave": "rastreo_bots_ia",   "titulo": "Acceso de los bots de IA", "estado": "ok",
        "valor": "sin bloqueos críticos", "detalle": "…",
        "bloqueados_por_categoria": { "retrieval": [], "user_fetch": [], "training": ["GPTBot"] },
        "waf": { "bloquea": false, "status": 200, "challenge": false } },
      { "clave": "jerarquia_contenido", "titulo": "Jerarquía de encabezados", "estado": "warning", "valor": "2 H1 · 8 encabezados", "detalle": "…" },
      { "clave": "schema", "titulo": "Datos estructurados (Schema.org)", "estado": "ok",
        "valor": "4 tipos", "detalle": "…", "tipos_detectados": ["Organization","WebSite","…"],
        "campos_ausentes": [], "validador": { "disponible": true, "errores": 0, "warnings": 0 } },
      { "clave": "indice_autoridad", "titulo": "Índice de autoridad", "estado": "warning", "valor": null, "detalle": "…" },
      { "clave": "semantica", "titulo": "Cómo lee la IA tu web", "estado": "ok", "valor": "82 / 100", "detalle": null,
        "entidades": ["telecomunicaciones","Murcia","fibra óptica","…"] }
    ],
    "bloqueados": 4                     // nº de comprobaciones extra que solo trae el informe completo
  },

  "huella_digital": {
    "enlaces": [ { "dominio": "economia3.com", "url": "https://…" }, … ],  // presencia externa
    "dominio_propio_citado": true,
    "eeatc": { "experiencia": 78, "expertise": 70, "autoridad": 60, "confianza": 72, "citabilidad": 55, "puntuacion_global": 67 },
    "bloqueados": 3
  },

  "preguntas": [                        // el detalle de cada pregunta × 4 modelos
    { "pregunta": "¿Cuáles son las mejores opciones de … en Madrid, España?",
      "respuestas": [
        { "modelo": "ChatGPT",    "clave": "chatgpt",    "respondio": true, "aparece": true,  "respuesta": "texto literal…" },
        { "modelo": "Claude",     "clave": "claude",     "respondio": true, "aparece": true,  "respuesta": "…" },
        { "modelo": "Gemini",     "clave": "gemini",     "respondio": true, "aparece": false, "respuesta": "…" },
        { "modelo": "Perplexity", "clave": "perplexity", "respondio": true, "aparece": false, "respuesta": "…" }
      ] }
  ],

  "aparicion": {                        // la matriz de visibilidad
    "por_modelo": [
      { "modelo": "ChatGPT", "clave": "chatgpt", "apariciones": 2, "preguntas_validas": 3, "tasa": 67,
        "celdas": [ { "respondio": true, "aparece": true }, … ] },
      … (una entrada por modelo: 4 en total)
    ],
    "tasa_global": 58, "total_hits": 7, "total_validas": 12
  },

  "mapa_competitivo": [                 // quién ocupa el espacio; la marca SIEMPRE está, aunque con 0
    { "empresa": "Competidora Uno", "es_marca": false, "menciones": 5,
      "por_modelo": { "chatgpt": 1, "claude": 1, "gemini": 1, "perplexity": 2 } },
    { "empresa": "BranDevs", "es_marca": true, "menciones": 6,
      "por_modelo": { "chatgpt": 2, "claude": 2, "gemini": 2, "perplexity": 0 } }
  ],

  "_diag": {                            // diagnóstico técnico para depurar (guardar, útil en el detalle)
    "home_status": 200, "robots_status": 200, "sitemap_status": 200,
    "html_bytes": 148234, "palabras": 620, "home_legible": true,
    "csr": false, "spa": [], "encabezados": 8, "jsonld_bloques": 3,
    "robots_grupos": 3, "sitemap_urls": 40, "validador_schema": "ok"
  }
}
```

### Diferencias del informe COMPLETO

El completo devuelve el mismo bloque de cabecera (`meta`, `nota`, `por_area`, `resumen_hallazgos`, `posicionamiento`) y añade secciones más ricas: las 4 dimensiones del análisis de IA (descubrimiento, competitivo, conocimiento, reputación), verificación factual de lo que la IA afirma, huella investigada canal a canal, un plan de acción priorizado, KPIs y citas destacadas. El panel puede, en fase 1, renderizar el bloque común y guardar el JSON íntegro; el render fino del completo puede ser una fase posterior.

## Modelos y sus claves

Cuatro modelos, clave estable en minúscula (útil para columnas de tabla y agregados):

| clave | etiqueta | modelo real | tipo |
|---|---|---|---|
| `chatgpt` | ChatGPT | `gpt-5.4-mini` | paramétrico |
| `claude` | Claude | `claude-haiku-4-5` (lite) / `claude-sonnet-4-6` (completo) | paramétrico |
| `gemini` | Gemini | `gemini-2.5-flash` (con `thinkingBudget: 0`) | paramétrico |
| `perplexity` | Perplexity | `sonar` | grounded (busca en web) |

## Errores

Con `neverError`/`onError: continueRegularOutput`, los workflows tienden a **no** tumbarse: si un modelo o la web fallan, el informe llega igual con avisos y estados `no_verificable`. Aun así, el panel debe manejar:
- **Timeout** del POST (n8n no responde a tiempo) → marcar la ejecución como `error`.
- **Respuesta no-JSON o vacía** → marcar como `error`, guardar el cuerpo crudo para depurar.
- **HTTP 4xx/5xx** del webhook → `error` con el status.

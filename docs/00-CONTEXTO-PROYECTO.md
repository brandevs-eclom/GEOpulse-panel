# 00 · Contexto del proyecto

## Qué es GEOpulse

GEOpulse es una herramienta de auditoría **GEO** (Generative Engine Optimization) desarrollada por **BranDevs** (agencia web/IA/marketing, brandevs.com / gptads.es). Mide si la inteligencia artificial —ChatGPT, Claude, Gemini y Perplexity— recomienda una marca cuando un usuario pregunta por su sector, y audita los factores que determinan esa visibilidad.

En una frase: **lanza preguntas reales de cliente a los cuatro grandes motores de IA, geolocalizadas en el mercado del cliente, mide si aparece la marca o su competencia, y lo resume en una nota de 0 a 100 (el "GEO Score")**.

La herramienta ya existe y está en producción. Consta de:

- **Dos workflows de n8n** que hacen todo el análisis (leer la web, sondear los 4 modelos, consolidar y puntuar). Se invocan por webhook y devuelven un JSON con el informe completo.
  - **Informe completo** (`geopulse-audit`, 71 nodos): 16 preguntas × 4 modelos en 4 dimensiones, huella digital investigada, plan de acción. Es el producto profesional.
  - **Informe LITE v2** (`geopulse-lite2`, 24 nodos): 3 preguntas × 4 modelos + sonda de huella. Es la muestra gratuita embebida en la web.
- **Frontends HTML** (widgets embebidos en WordPress/Elementor con Shadow DOM) que pintan el informe que devuelve cada workflow. Estos frontends son de cara al cliente y **no forman parte de este proyecto**, aunque el panel reutilizará su lógica de render.

## Qué vamos a construir: GEOpulse Panel

Un **panel de control interno** (uso de la agencia, no del cliente final) que permita:

1. **Ver todas las ejecuciones** de análisis en una tabla/listado: qué marca, qué dominio, qué tipo de informe (lite/completo), cuándo, estado (en curso / terminado / error) y la nota resultante.
2. **Lanzar análisis "por detrás"**: desde el panel, rellenar los datos (marca, dominio, sector, país/región) y disparar el workflow correspondiente, sin pasar por el widget público.
3. **Ver el detalle de cada ejecución**: el informe completo renderizado (las 4-5 áreas, la matriz de aparición de los 4 modelos, el mapa competitivo, la huella, los avisos de fiabilidad, las respuestas literales de cada modelo, etc.), además de los metadatos técnicos de la ejecución (payload enviado, tiempos, errores).
4. **Gestionar los workflows de n8n desde el propio repositorio**: los workflows se generan con scripts de Python (ver `docs/04`). Traer esos scripts a este proyecto permite que estén en el contexto y evolucionen junto al panel.

## Qué NO es (de momento)

- No es una reescritura de los workflows. Los workflows de n8n **siguen siendo la fuente de verdad del análisis**; el panel los orquesta y almacena resultados, no reimplementa la lógica GEO.
- No es un producto SaaS multi-cliente con billing. Es una herramienta interna de la agencia. (Puede diseñarse con multi-tenant en mente, pero no es requisito de la fase 1.)
- No sustituye a los widgets públicos de la web.

## Principios de producto que hay que respetar

- **Honestidad de los datos.** El informe ya distingue lo que se pudo medir de lo que no (estados `no_verificable`, array de `avisos`). El panel debe mostrar eso tal cual, no esconderlo.
- **La nota es comparable entre lite y completo.** Ambos informes usan los mismos criterios de puntuación y pesos. No los toques desde el panel.
- **Trabajo iterativo.** Cambios pequeños, verificables, sin reescrituras innecesarias.

## Glosario rápido

- **GEO / GEO Score**: optimización para motores generativos / la nota 0-100 del informe.
- **Sondeo**: una pregunta lanzada a un modelo. El lite hace 12 (3×4); el completo, 64 (16×4).
- **Los 4 modelos**: ChatGPT (`gpt-5.4-mini`), Claude (`claude-*`), Gemini (`gemini-2.5-flash`), Perplexity (`sonar`, el único "grounded"/con búsqueda web).
- **E-E-A-T-C**: experiencia, expertise, autoridad, confianza y citabilidad (métricas de huella).
- **Huella digital**: menciones de la marca fuera de su propia web.

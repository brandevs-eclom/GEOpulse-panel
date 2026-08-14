# 04 · Gestión de los workflows de n8n desde este repo

Uno de los objetivos es que **los workflows de n8n vivan en el contexto de este proyecto**, para que evolucionen junto al panel y no queden como una caja negra externa.

## Cómo están hechos los workflows (importante)

Los workflows **NO se editan a mano en el editor de n8n**. Se **generan con scripts de Python** que construyen el JSON de nodos y conexiones. Este patrón es deliberado y hay que mantenerlo: permite cambios controlados, revisables en git y reproducibles.

En `workflows/` de este repo tienes:

- `build_lite2.py` → genera `geopulse-lite2-workflow.json` (el informe LITE, 24 nodos).
- `build_workflow_v10.py` → genera `geopulse-workflow.json` (el informe COMPLETO, 71 nodos). *(El nombre del fichero de salida se mantiene aunque el builder sea v10; en producción el JSON se importa como `geopulse-workflow-v3.json`.)*
- Los dos JSON ya generados, para referencia.

### Flujo de trabajo para tocar un workflow

```
1. Editar el builder .py (nunca el JSON directamente)
2. Ejecutar:  python3 workflows/build_lite2.py   (o build_workflow_v10.py)
3. Se regenera el .json
4. Validar (ver más abajo)
5. Importar el .json en n8n (manual, por ahora) y activar
```

### Reglas de oro aprendidas construyendo estos workflows

Estas están grabadas a fuego por bugs reales de producción. Respétalas si tocas los builders:

- **Peticiones HTTP GET** (leer la web del cliente): obligatorio `fullResponse: true` + `responseFormat: "text"` + `outputPropertyName: "body"` + `neverError: true`, **y un User-Agent de navegador**. Sin el User-Agent, los WAF/Cloudflare devuelven 403 y todo el análisis técnico sale vacío.
- **Lectura de respuestas de los LLM tras un merge**: usar arquitectura de items (un nodo `Sondas` emite N items, cada nodo de modelo corre N veces) y leer con `$('Nodo').all()[idx]` + la función `pick()`. NUNCA `.first()` sobre nodos que corren varias veces. Con `fullResponse`, la respuesta viene en `.body`.
- **`pick()` debe entender los 4 formatos de respuesta**: OpenAI (`choices[].message.content`), Anthropic (`content[].text`), **Gemini (`candidates[].content.parts[].text`)** y Perplexity. Ya está resuelto; no lo rompas.
- **Gemini es un modelo de razonamiento**: hay que enviarle `generationConfig.thinkingConfig.thinkingBudget = 0`, si no gasta casi todos los tokens "pensando" y devuelve la respuesta cortada (bug real: las listas de empresas salían a medias).
- **Anthropic** exige el header `anthropic-version: 2023-06-01`.
- **OpenAI `gpt-5.4-mini` es de razonamiento**: SIN `temperature` ni `max_tokens` (los rechaza con 400).
- **Perplexity y Gemini** usan **Header Auth genérica** en n8n, no credencial predefinida. Gemini con el header `x-goog-api-key`.
- **Expresiones `={{ }}` de n8n**: nunca `}}` dentro (rompe el parseo). Los prompts con esquemas JSON que contienen `}}` se construyen en un nodo Code, no en la expresión del HTTP.
- **Detección de marca en las respuestas**: no exigir el nombre completo literal (una empresa citada solo por su palabra distintiva cuenta para su nombre completo), pero sin dar por buena una palabra genérica del sector. Ya resuelto en el nodo de consolidación.
- **Honestidad**: si algo no se puede medir, el informe emite `avisos` y pone `no_verificable`, nunca un 0 inventado.

### Validación de un workflow tras generarlo

Antes de importar, conviene comprobar por script (Python/Node) que: los nombres de nodo son únicos, todas las referencias `$('Nodo')` existen, no hay `}}` dentro de expresiones, los GET llevan User-Agent + outputPropertyName, los merges tienen el número correcto de entradas, y los nodos LLM llevan `fullResponse`. En el proyecto original esto se hacía con un pequeño validador; **replícalo o mejóralo dentro de este repo** para que el pipeline sea seguro.

## Qué puede hacer el panel con los workflows (roadmap)

- **Fase 1**: los workflows solo se referencian (el panel llama a sus webhooks). Los builders viven en `workflows/` para tenerlos en contexto y poder regenerarlos desde este repo.
- **Fase futura (opcional)**: automatizar el despliegue. n8n tiene una **API REST** (`/api/v1/workflows`) que permite crear/actualizar workflows y activarlos con un token. Se podría añadir un comando que genere el JSON y lo suba a n8n sin pasar por la importación manual. Evalúalo cuando lleguemos ahí; requiere un `N8N_API_KEY` y cuidado con no pisar workflows en producción.

## Lo que NO debe pasar

- El panel **no reimplementa** la lógica GEO en su backend. Si el análisis tiene que cambiar, se cambia en el builder del workflow.
- No editar el JSON generado a mano: se pierde en la siguiente regeneración.
- No mover las claves de modelo ni los pesos de puntuación desde el panel: la nota debe seguir siendo comparable entre lite y completo, y con auditorías anteriores.

#!/usr/bin/env python3
"""GEOpulse v3: 4 agentes de sondeo LLM en ramas paralelas + agente de informe detallado.
Datos de repositorios reales (HTTP, KG, Wikidata, validator, citations) contrastados con lo que afirman los modelos."""
import json
import os

UA_CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

# ============================================================
# PROMPTS — CAPA TÉCNICA (heredados de v2)
# ============================================================

PROMPT_A1_INFRA = """Eres un auditor técnico especializado en infraestructura GEO (Generative Engine Optimization). Evalúas los cimientos técnicos que permiten a los motores generativos descubrir y entender un sitio web. Todos tus datos de entrada provienen de verificaciones reales (peticiones HTTP y el validador oficial de schema.org), no de suposiciones.

ENTRADA: JSON con: domain, home_url (la RAÍZ del dominio, que es lo que se ha analizado como "la home"), pagina_indicada (si no es null, una URL con path que el cliente pidió analizar además de la home), llms_txt (status HTTP, exists, parece_html, contenido), schema_existe (booleano determinista), jsonld (bloques de la home), schema_org_home y schema_org_sitio (comprobación DETERMINISTA de Organization/LocalBusiness, ver abajo), schema_landings (tipos de JSON-LD y comprobación org de cada página interna), validacion_schema_org ({disponible, num_errores, num_warnings, errores, warnings}; si disponible=false ignóralo sin penalizar) y sitemap_xml (status, exists, lastmod_mas_reciente).

EVALÚA:
1. llms_txt → "ok" si existe con formato correcto (Markdown: H1, blockquote resumen, secciones con enlaces). "warning" si existe pero pobre. "error" si no existe o parece_html=true (soft-404). IMPORTANTE: indica siempre en el detalle que llms.txt es una señal de adopción temprana sin efecto confirmado por los motores en 2026: recomendable por coste cero, pero no crítica.
2. schema → DOS PASOS obligatorios:
   PASO 1 (existencia): usa schema_existe tal cual. Si es false → existe: false, estado "error", campos vacíos, y NO continúes.
   PASO 2 (calidad, solo si existe): a) CAMPOS DE Organization/LocalBusiness — NO los juzgues tú, ya vienen comprobados en código. Copia `campos_ausentes` EXACTAMENTE de `schema_org_home.ausentes` (lista de nombres de campo tal cual: "sameAs", "telephone"...). Tienes PROHIBIDO añadir a esa lista un campo que aparezca en `schema_org_home.presentes`, y prohibido reformularlos en prosa ("Organization en la home con name" NO es un nombre de campo). Si `schema_org_home.encontrado` es false pero `schema_org_sitio.encontrado` es true, dilo así en el detalle: el marcado existe en el sitio (cita `schema_org_sitio.mejor_en`) pero no en la home, que es donde más pesa. "ok" solo si `schema_org_home.ausentes` está vacío. b) VOCABULARIO: marca en propiedades_invalidas tipos o propiedades que no existen en schema.org o con erratas (schema.org es case-sensitive); si hay alguna, el estado no puede ser "ok". c) VALIDADOR OFICIAL: si disponible, num_errores > 0 → mínimo "warning" citando los errores. d) COBERTURA: usa schema_landings para valorar si el marcado vive solo en la home o también en las páginas de servicio. Si una landing trae es_fallback_home=true significa que no se pudieron muestrear páginas internas y se usó la home como respaldo: evalúala igualmente, pero indica en el detalle que la cobertura en páginas internas queda sin verificar (no la penalices como ausente).
3. sitemap → "ok" si status 200 Y lastmod_mas_reciente dentro de los últimos 6 meses; "warning" si existe pero el lastmod es antiguo o no hay (los crawlers de IA priorizan contenido fresco); "error" si no responde.

REGLAS: evalúa EXCLUSIVAMENTE los datos de entrada; "no_verificable" cuando falte el dato; sé concreto (campos y tipos exactos).

Responde ÚNICAMENTE con un objeto JSON válido con esta estructura exacta:
{"llms_txt":{"estado":"ok|warning|error|no_verificable","detalle":"string"},"schema":{"existe":true,"estado":"ok|warning|error|no_verificable","tipos_detectados":["string"],"campos_ausentes":["string"],"propiedades_invalidas":["string"],"cobertura_landings":"string","detalle":"string"},"validador_oficial":{"disponible":true,"num_errores":0,"num_warnings":0},"sitemap":{"estado":"ok|warning|error|no_verificable","detalle":"string"},"acciones":[{"prioridad":"alta|media|baja","accion":"string"}]}"""

PROMPT_A2_SEO = """Eres un auditor de SEO técnico especializado en rastreabilidad para crawlers de IA. Trabajas SOLO con verificaciones reales: el robots.txt descargado, las respuestas reales del servidor a peticiones hechas con los User-Agents de los bots de IA, los headers HTTP y el HTML crudo.

ENTRADA: JSON con: robots_txt (status, contenido, bots detectados por categoría), acceso_edge (resultado REAL de pedir la home identificándose como GPTBot, ClaudeBot, OAI-SearchBot, PerplexityBot, ChatGPT-User y Claude-User frente al baseline de navegador; incluye `veredicto`, `motivo`, `baseline_valido` y `bloqueados_por_categoria` YA CALCULADOS en código), home (status, url, meta_robots, x_robots_tag, canonical, headings, render, response_time_ms, word_count) y landings.

CONTEXTO 2026 — categorías de bots (puntúa por categoría, NO por bot suelto):
- TRAINING (GPTBot, ClaudeBot, CCBot, Bytespider, Meta-ExternalAgent, Amazonbot; tokens Google-Extended y Applebot-Extended): bloquearlos es una decisión legítima de derechos SIN coste en citaciones. NO baja el estado; repórtalo como informativo.
- RETRIEVAL/SEARCH (OAI-SearchBot, Claude-SearchBot, PerplexityBot, DuckAssistBot, YouBot): alimentan los índices que los motores citan. Bloqueo total de cualquiera → "error": borra al sitio de las respuestas de ese motor.
- USER-FETCH (ChatGPT-User, Claude-User, Perplexity-User, MistralAI-User): visitas pedidas en directo por un usuario. Bloqueo → "warning".
- DEPRECADOS (Claude-Web, anthropic-ai): sin efecto; si aparecen, menciónalo como regla obsoleta.
- "User-agent: *" con "Disallow: /" bloquea todo → "error".

EVALÚA:
1. rastreo_bots_ia → aplica las categorías al robots.txt real; cita las líneas exactas.
2. acceso_edge → el estado te viene DADO: copia `acceso_edge.veredicto` tal cual en el campo `estado`. NO lo recalcules ni lo empeores porque "suene grave". El razonamiento está en `acceso_edge.motivo`: úsalo como base del detalle, con estas reglas de redacción. a) Si el veredicto es "ok" porque solo hay bloqueados de TRAINING, dilo sin dramatizar: es una decisión legítima del cliente, probablemente un ajuste del hosting o de un plugin, y NO le cuesta citaciones; nómbralos y di explícitamente que los bots que deciden si le citan sí acceden. b) Si es "error", explica que el bloqueo es a nivel de servidor/CDN aunque el robots.txt lo permita, y qué motor concreto deja de poder citarle. c) Si es "no_verificable" (baseline_valido=false), NO afirmes nada sobre bloqueos: di que la comprobación no es concluyente porque la propia petición de referencia no pasó, y que eso suele ser el WAF filtrando por reputación de IP, no el cliente bloqueando bots. d) Un `posible_rate_limit` (429) NO es una política contra ese bot: menciónalo como límite de peticiones, nunca como bloqueo de IA. En `bots_bloqueados_edge` lista SOLO los que tengan bloqueado_edge=true.
3. indexabilidad → "error" si meta_robots O x_robots_tag contienen noindex (el header cuenta igual que el meta). Menciona canonical cross-domain.
4. renderizado → si sospecha_csr=true o hay spa_markers con ratio_texto_html muy bajo, "error"/"warning": el contenido depende de JavaScript y la mayoría de crawlers de IA no lo ejecutan, así que leen una página vacía.
5. rendimiento → "ok" < 800 ms, "warning" 800-1500, "error" > 1500; null → "no_verificable".
6. jerarquia_contenido → home y CADA landing, página por página: un único h1 descriptivo, h2/h3 sin saltos, headings comprensibles para un LLM. por_pagina con estado global = el peor. Si una landing trae es_fallback_home=true, es la propia home usada como respaldo porque no se pudieron muestrear páginas internas: evalúala con normalidad e indícalo en el detalle, sin penalizar por ello.

REGLAS: solo la entrada; nada inventado; cita valores reales.

Responde ÚNICAMENTE con un objeto JSON válido con esta estructura exacta:
{"rastreo_bots_ia":{"estado":"ok|warning|error|no_verificable","bloqueados_por_categoria":{"training":["string"],"retrieval":["string"],"user_fetch":["string"]},"reglas_obsoletas":["string"],"detalle":"string"},"acceso_edge":{"estado":"ok|warning|error|no_verificable","bots_bloqueados_edge":["string"],"detalle":"string"},"indexabilidad":{"estado":"ok|warning|error|no_verificable","detalle":"string"},"renderizado":{"estado":"ok|warning|error|no_verificable","detalle":"string"},"rendimiento":{"estado":"ok|warning|error|no_verificable","valor_ms":0,"detalle":"string"},"jerarquia_contenido":{"estado":"ok|warning|error|no_verificable","detalle":"string","por_pagina":[{"url":"string","estado":"ok|warning|error","detalle":"string"}]},"acciones":[{"prioridad":"alta|media|baja","accion":"string"}]}"""

PROMPT_A3_CONTENIDO = """Eres un analista de contenido especializado en GEO. Evalúas si el contenido de una web está optimizado para ser citado por motores generativos, aplicando los criterios con mayor correlación medida con la citación: claridad answer-first, señales E-E-A-T y formato pregunta-respuesta.

ENTRADA: JSON con: keyword, title, meta_description, headings, texto_extracto (texto plano de la home) y word_count.

EVALÚA:
1. indice_autoridad → datos concretos, cifras, años, certificaciones, casos con atribución específica que un LLM pueda citar. "ok" abundantes, "warning" escasos, "error" ninguno.
2. intent_match → ¿responde directamente a la intención de la keyword con estilo ANSWER-FIRST (la respuesta en las primeras 1-2 frases de cada sección)? ¿Hay formato pregunta-respuesta o FAQs? Valora ambos criterios por nombre.
3. estructura_extraccion → CHUNKS AUTOCONTENIDOS: los motores RAG recuperan fragmentos, no páginas; cada sección debe responder su pregunta completa sin depender del contexto anterior. Evalúa eso, además de listas/tablas/párrafos cortos.
4. tono → 2-4 palabras.
5. entidades → 5-10 entidades núcleo realmente presentes.
6. claridad_nucleo → 0-100: ¿un LLM entendería sin ambigüedad qué hace el negocio, para quién y dónde?

REGLAS: solo el texto recibido; acciones concretas (máximo 5).

Responde ÚNICAMENTE con un objeto JSON válido con esta estructura exacta:
{"indice_autoridad":{"estado":"ok|warning|error","detalle":"string"},"intent_match":{"estado":"ok|warning|error","detalle":"string"},"estructura_extraccion":{"estado":"ok|warning|error","detalle":"string"},"tono":"string","entidades":["string"],"claridad_nucleo":0,"acciones":[{"prioridad":"alta|media|baja","accion":"string"}]}"""

PROMPT_DIRECTORIOS_JS = (
    "Eres un consultor de link building y presencia digital para el sector \"__KEYWORD__\". Tu tarea: descubrir con busquedas web reales los directorios, listados sectoriales, medios especializados, comunidades profesionales y rankings \"mejores de\" donde una empresa de este sector DEBERIA aparecer para ganar autoridad y citaciones en motores de IA.\\n\\n"
    "MERCADO: la empresa opera en __PAIS__. Incluye TANTO directorios y medios nacionales/locales de ese mercado COMO internacionales de alta autoridad del sector. No te limites a los cuatro directorios genericos de siempre (esos ya se detectan por otra via): el valor de tu respuesta esta en descubrir sitios ESPECIFICOS y de NICHO del sector que sorprendan y de verdad muevan la aguja.\\n\\n"
    "YA PRESENTE (NO los recomiendes, la marca ya esta o ya se han detectado): __YA_PRESENTE__\\n\\n"
    "REGLAS ESTRICTAS:\\n"
    "- Haz varias busquedas especificas del sector (p.ej. \"mejores directorios [sector]\", \"[sector] directorio empresas\", \"donde aparecer [sector] [pais]\", \"asociaciones [sector]\", \"medios [sector]\").\\n"
    "- Cada sitio que recomiendes DEBE salir de un resultado de busqueda real e incluir su URL. Si no lo has visto en una busqueda, NO lo inventes.\\n"
    "- EXCLUYE cualquier dominio de la lista YA PRESENTE y EXCLUYE ruido generico (Google, redes sociales, Wikipedia, YouTube, Amazon).\\n"
    "- Prioriza por relevancia y autoridad para el sector: \"alta\" para directorios/medios muy relevantes y con autoridad, \"media\" para relevantes, \"baja\" para complementarios.\\n"
    "- categoria: directorio (o nicho para directorios muy especializados), medio, lista (rankings/comparativas), comunidad (foros/asociaciones/grupos).\\n"
    "- por_que: explica en una frase POR QUE ese sitio importa para este sector concreto y que aporta aparecer alli.\\n"
    "- Maximo 6 por categoria. Calidad sobre cantidad: mejor 8 sitios certeros y sorprendentes que 25 genericos.\\n\\n"
    "Responde UNICAMENTE con un objeto JSON valido, sin markdown, con esta estructura exacta:\\n"
    "{\"recomendaciones\":[{\"sitio\":\"nombre\",\"url\":\"https://...\",\"categoria\":\"directorio|nicho|medio|lista|comunidad\",\"por_que\":\"string\",\"prioridad\":\"alta|media|baja\"}],\"resumen\":\"string\"}"
)

PROMPT_A5_HUELLA_JS = (
    "Eres un investigador de reputacion y huella digital. Investiga con busquedas web reales la presencia externa de la empresa \"__BRAND__\" (web: __DOMAIN__), del sector \"__KEYWORD__\".\\n\\n"
    "ALCANCE: la investigacion es ORGANICA Y GLOBAL. NO filtres ni priorices por pais ni por region: las menciones cuentan vengan de donde vengan, y una mencion internacional vale tanto como una local. Para no confundir la empresa con homonimas, verifica la identidad por el DOMINIO (__DOMAIN__) y por el sector, NUNCA por ubicacion.\\n\\n"
    "Busca y evalua:\\n"
    "1. presencia_foros: menciones en Reddit, Quora, foros y comunidades del sector.\\n"
    "2. medios: apariciones en prensa, medios digitales o notas de prensa.\\n"
    "3. directorios: presencia en directorios y plataformas de resenas relevantes para su sector (agencias: Clutch, GoodFirms, Sortlist; SaaS: G2, Capterra; hosteleria: TripAdvisor; general: Google, Trustpilot).\\n"
    "4. listas_sector: MUY IMPORTANTE: busca los articulos y rankings tipo \"mejores __KEYWORD__\" que existan y comprueba si la empresa aparece en ellos; los motores generativos se nutren de esas listas. Nombra las listas encontradas y si la marca esta o no.\\n\\n"
    "CRITERIOS DE CALIDAD (campo calidad en cada categoria):\\n"
    "- La auto-mencion NO es huella externa: cobertura procedente del propio dominio (__DOMAIN__: su pagina de prensa o su blog) o notas de prensa autopublicadas -> maximo \"warning\", calidad \"autopublicada\".\\n"
    "- La presencia hueca puntua poco: fichas de directorio vacias (sin resenas ni actividad) e hilos donde solo aparece el nombre sin conversacion -> maximo \"warning\", calidad \"superficial\". Reserva \"ok\" y \"sustancial\" para resenas reales, cobertura de terceros e hilos con conversacion.\\n\\n"
    "E-E-A-T-C: puntua de 0 a 100 cinco componentes, cada uno justificado con lo que hayas encontrado:\\n"
    "- experiencia: pruebas de trabajo real (casos, proyectos, trayectoria) mencionadas por TERCEROS.\\n"
    "- expertise: reconocimiento externo de conocimiento especializado.\\n"
    "- autoridad: quien habla de la marca y con cuanto peso (medios reales, directorios con resenas, listas del sector).\\n"
    "- confianza: resenas y valoraciones de clientes; senales negativas si las hay.\\n"
    "- citabilidad: DATO DURO, no impresion. Estas son las fuentes que el motor de busqueda cito REALMENTE al responder preguntas del sector de esta empresa: __CITACIONES__. Si cliente_citado es false, el dominio NO aparece entre las fuentes que el motor consulta para su sector: la citabilidad es baja por definicion, dilo sin rodeos y nombra los dominios que si aparecen.\\n"
    "puntuacion_global: media de los cinco. carencias: que falta para subir cada componente bajo.\\n\\n"
    "REGLAS ESTRICTAS: cada afirmacion debe salir de un resultado de busqueda real e incluir su URL en fuentes. Si en una categoria no encuentras nada: estado \"error\", presencia false, calidad \"inexistente\" (hallazgo valido, NO lo rellenes con suposiciones).\\n\\n"
    "Responde UNICAMENTE con un objeto JSON valido, sin markdown, con esta estructura exacta:\\n"
    "{\"presencia_foros\":{\"estado\":\"ok|warning|error\",\"presencia\":false,\"calidad\":\"sustancial|superficial|autopublicada|inexistente\",\"detalle\":\"string\",\"fuentes\":[\"url\"]},\"medios\":{\"estado\":\"ok|warning|error\",\"presencia\":false,\"calidad\":\"string\",\"detalle\":\"string\",\"fuentes\":[\"url\"]},\"directorios\":{\"estado\":\"ok|warning|error\",\"presencia\":false,\"calidad\":\"string\",\"detalle\":\"string\",\"fuentes\":[\"url\"]},\"listas_sector\":{\"estado\":\"ok|warning|error\",\"presencia\":false,\"calidad\":\"string\",\"listas_encontradas\":[\"string\"],\"detalle\":\"string\",\"fuentes\":[\"url\"]},\"eeatc\":{\"experiencia\":{\"puntuacion\":0,\"detalle\":\"string\"},\"expertise\":{\"puntuacion\":0,\"detalle\":\"string\"},\"autoridad\":{\"puntuacion\":0,\"detalle\":\"string\"},\"confianza\":{\"puntuacion\":0,\"detalle\":\"string\"},\"citabilidad\":{\"puntuacion\":0,\"citado_por_motores\":false,\"detalle\":\"string\"},\"puntuacion_global\":0,\"carencias\":[\"string\"]},\"resumen\":\"string\"}"
)

# ============================================================
# PROMPTS — LOS 4 AGENTES DE SONDEO (evaluadores)
# ============================================================

BASE_EVAL = """CONTEXTO GEOGRÁFICO: la empresa auditada opera en el mercado que se indica en el campo geo. Todas las preguntas se lanzaron ancladas a ese mercado.

CONFUSIÓN DE ENTIDAD (regla crítica): si un modelo describe una empresa HOMÓNIMA de otro país o de otro sector, NO la cuentes como mención de la marca auditada. Márcala como confusión de entidad y repórtala: significa que el nombre de la marca no está anclado a su entidad real en el conocimiento del modelo, lo cual es un hallazgo de primer orden (y a menudo peor que no aparecer, porque el usuario recibe información de otra empresa creyendo que es esta).

Trabajas SOLO con el texto de las respuestas recibidas. Nunca inventes menciones, empresas, atributos ni citas. El matching del nombre de la marca es tolerante a mayúsculas y variantes obvias, pero NUNCA cuentes coincidencias ambiguas de palabras genéricas. Si un modelo devolvió respuesta vacía, márcalo como no evaluable en lugar de suponer. Si la marca no aparece, dilo sin suavizarlo: una ausencia bien documentada es el hallazgo más valioso de esta auditoría.

Contexto de los modelos: chatgpt, claude y gemini responden de forma PARAMÉTRICA (con lo que "recuerdan" de su entrenamiento); perplexity responde GROUNDED (buscando en la web en tiempo real). Divergencias entre ambos tipos son señal, no ruido: si la marca sale en el grounded pero no en los paramétricos, es una marca reciente o poco consolidada en el conocimiento de los modelos; si sale en los paramétricos pero no en el grounded, su presencia web actual es débil."""

PROMPT_EVAL_D1 = """Eres el Agente de DESCUBRIMIENTO de una auditoría de visibilidad en motores generativos. Mides si la marca EMERGE ESPONTÁNEAMENTE cuando un usuario pide recomendaciones del sector sin nombrarla.

""" + BASE_EVAL + """

ENTRADA: JSON con brand, keyword y sondas: [{pregunta, respuestas: {chatgpt, claude, gemini, perplexity}}]. Ninguna pregunta nombra a la marca: son consultas de descubrimiento puro.

EVALÚA, por cada pregunta y cada modelo: si la marca aparece (mencionada), su posición en la lista (posicion, null si no hay ranking), cuántas empresas lista el modelo en total (total_listadas) y una cita textual breve como evidencia (máximo 20 palabras).

AGREGA por modelo: apariciones (nº de preguntas donde aparece), total_preguntas, tasa_aparicion (0-100), posicion_media (null si nunca aparece).
AGREGA global: share_of_voice_global (presencia de la marca frente al total de menciones de empresas en todas las respuestas, 0-100) y empresas_recomendadas (qué empresas recomiendan los modelos: es el mapa real de quién ocupa el espacio que la marca quiere). Por cada empresa da veces (total de menciones), modelos (en cuáles aparece) y menciones_por_modelo: el desglose EXACTO de cuántas veces la menciona cada modelo (chatgpt, claude, gemini, perplexity). Los cuatro números de menciones_por_modelo deben sumar exactamente veces. Incluye también a la marca auditada en esta lista si aparece.
Escribe un veredicto directo y 3-5 hallazgos concretos con evidencia.

Responde ÚNICAMENTE con un objeto JSON válido con esta estructura exacta:
{"detalle_preguntas":[{"pregunta":"string","resultados":{"chatgpt":{"mencionada":false,"posicion":null,"total_listadas":0,"evidencia":"string"},"claude":{"mencionada":false,"posicion":null,"total_listadas":0,"evidencia":"string"},"gemini":{"mencionada":false,"posicion":null,"total_listadas":0,"evidencia":"string"},"perplexity":{"mencionada":false,"posicion":null,"total_listadas":0,"evidencia":"string"}}}],"por_modelo":{"chatgpt":{"apariciones":0,"total_preguntas":0,"tasa_aparicion":0,"posicion_media":null},"claude":{"apariciones":0,"total_preguntas":0,"tasa_aparicion":0,"posicion_media":null},"gemini":{"apariciones":0,"total_preguntas":0,"tasa_aparicion":0,"posicion_media":null},"perplexity":{"apariciones":0,"total_preguntas":0,"tasa_aparicion":0,"posicion_media":null}},"share_of_voice_global":0,"empresas_recomendadas":[{"empresa":"string","veces":0,"modelos":["string"],"menciones_por_modelo":{"chatgpt":0,"claude":0,"gemini":0,"perplexity":0}}],"confusion_entidad":{"detectada":false,"detalle":"string"},"veredicto":"string","hallazgos":["string"]}"""

PROMPT_EVAL_D2 = """Eres el Agente COMPETITIVO de una auditoría de visibilidad en motores generativos. Mides cómo posicionan los modelos a la marca FRENTE A SUS RIVALES y qué atributos asigna la IA a cada uno.

""" + BASE_EVAL + """

ENTRADA: JSON con brand, keyword, competitors (puede estar vacío) y sondas: [{pregunta, respuestas: {chatgpt, claude, gemini, perplexity}}]. Las preguntas incluyen comparativas y una consulta clave: "¿cuáles son las alternativas a la marca?", cuya respuesta revela el conjunto competitivo TAL Y COMO LO VE EL MODELO (puede no coincidir con los competidores que el cliente cree tener: si es así, dilo, es un hallazgo de primer orden).

EVALÚA:
- conjunto_competitivo: cada empresa mencionada como rival, con menciones (nº total de veces), menciones_por_modelo (desglose EXACTO por chatgpt, claude, gemini y perplexity; los cuatro deben sumar menciones), en qué modelos aparece, posicion_media si hay rankings, y los atributos que los modelos le asignan (textuales).
- posicion_marca: en qué modelos se la menciona, posición media y cómo se la describe frente a los rivales.
- atributos_marca: conceptos que los modelos asocian a la marca (textuales).
- gaps_atributos: atributos que la IA asigna a competidores y NO a la marca (esto es lo que hay que ganar en el discurso público).
- ventajas_percibidas: atributos donde la marca gana según los modelos.
- competidores_inesperados: rivales que los modelos citan y que el cliente no listó.
Veredicto directo y 3-5 hallazgos con evidencia.

Responde ÚNICAMENTE con un objeto JSON válido con esta estructura exacta:
{"conjunto_competitivo":[{"empresa":"string","menciones":0,"menciones_por_modelo":{"chatgpt":0,"claude":0,"gemini":0,"perplexity":0},"modelos":["string"],"posicion_media":null,"atributos":["string"]}],"posicion_marca":{"mencionada_en":["string"],"posicion_media":null,"detalle":"string"},"atributos_marca":["string"],"gaps_atributos":["string"],"ventajas_percibidas":["string"],"competidores_inesperados":["string"],"veredicto":"string","hallazgos":["string"]}"""

PROMPT_EVAL_D3 = """Eres el Agente de CONOCIMIENTO Y PRECISIÓN de una auditoría de visibilidad en motores generativos. Mides QUÉ SABEN los modelos de la marca y, sobre todo, SI LO QUE DICEN ES CIERTO, contrastándolo contra fuentes reales verificadas.

""" + BASE_EVAL + """

ENTRADA: JSON con brand, keyword, sondas: [{pregunta, respuestas: {chatgpt, claude, gemini, perplexity}}] y datos_verificados: {texto_web (contenido REAL extraído de la web de la empresa), title, meta_description}. Las preguntas piden a qué se dedica, qué servicios ofrece, dónde está / cuándo se fundó / quién la dirige, y qué clientes o casos de éxito tiene (estas dos últimas son las de mayor propensión a la alucinación).

EVALÚA:
- nivel_conocimiento por modelo: "alto" (la describe con precisión y detalle), "medio" (idea general correcta pero vaga), "bajo" (apenas la ubica o la confunde), "nulo" (dice no conocerla). Que un modelo admita no conocerla es un resultado LIMPIO y preferible a que invente: refléjalo así.
- descripcion_percibida por modelo: cómo describe cada uno a la empresa, en una frase.
- verificacion_factual: OBLIGATORIO. Toma CADA afirmación factual concreta (sector, servicios, sede, año, fundadores, clientes, premios, tamaño) y contrástala contra datos_verificados. Veredicto por afirmación: "verificada" (coincide con el contenido real de la web), "contradicha" (la fuente real dice otra cosa: indica exactamente qué dice), "no_contrastable" (los datos verificados no cubren ese punto). Indica siempre el modelo que la hizo y cita la fuente real usada.
- alucinaciones: afirmaciones contradichas o inventadas con aspecto de dato duro (clientes o premios que no existen), con gravedad.
- contradicciones_entre_modelos: datos incompatibles entre modelos (si dos se contradicen, al menos uno alucina).
- servicios_correctos / servicios_erroneos / servicios_ausentes: comparando lo que dicen los modelos con los servicios que realmente aparecen en la web (los ausentes son los que la empresa ofrece y la IA no sabe que ofrece: puro gap de comunicación).
- riesgo_alucinacion: nivel "bajo|medio|alto" según cantidad y gravedad de lo contradicho.
Veredicto directo y 3-5 hallazgos con evidencia.

Responde ÚNICAMENTE con un objeto JSON válido con esta estructura exacta:
{"nivel_conocimiento":{"chatgpt":"alto|medio|bajo|nulo","claude":"alto|medio|bajo|nulo","gemini":"alto|medio|bajo|nulo","perplexity":"alto|medio|bajo|nulo"},"descripcion_percibida":{"chatgpt":"string","claude":"string","gemini":"string","perplexity":"string"},"verificacion_factual":[{"afirmacion":"string","modelo":"string","veredicto":"verificada|contradicha|no_contrastable","fuente_real":"string","evidencia":"string"}],"alucinaciones":[{"modelo":"string","afirmacion":"string","gravedad":"alta|media|baja"}],"contradicciones_entre_modelos":["string"],"servicios_correctos":["string"],"servicios_erroneos":["string"],"servicios_ausentes":["string"],"riesgo_alucinacion":{"nivel":"bajo|medio|alto","detalle":"string"},"confusion_entidad":{"detectada":false,"detalle":"string"},"veredicto":"string","hallazgos":["string"]}"""

PROMPT_EVAL_D4 = """Eres el Agente de REPUTACIÓN Y OBJECIONES de una auditoría de visibilidad en motores generativos. Mides QUÉ LE DICE LA IA a un cliente potencial que duda, que es el momento en que una recomendación se gana o se pierde.

""" + BASE_EVAL + """

ENTRADA: JSON con brand, keyword, sondas: [{pregunta, respuestas: {chatgpt, claude, gemini, perplexity}, citations_perplexity: [urls reales que el motor grounded consultó]}]. Las preguntas simulan a un usuario receloso: fiabilidad y puntos débiles, opiniones negativas, si merece la pena el precio, y riesgos de trabajar con la marca.

EVALÚA:
- sentimiento_por_modelo: polaridad (-1 a 1) y tono en una frase.
- polaridad_global: media sobre menciones reales.
- objeciones_detectadas: cada pega concreta que un modelo pone a la marca, con el modelo, la evidencia textual y, si viene del grounded, la URL de la fuente en la que se apoya (mira citations_perplexity). Una objeción respaldada por una fuente real es un problema de reputación REAL y accionable; una objeción sin fuente puede ser una alucinación negativa, que es un problema DISTINTO (y se corrige con presencia, no con servicio).
- defensa_de_marca: cuando el usuario duda, ¿el modelo defiende a la marca, se muestra neutro, o la hunde y empuja hacia un competidor? Indica hacia qué competidor deriva si lo hace. Estado "ok" (defiende), "warning" (neutro o evasivo / dice no conocerla), "error" (la desaconseja o deriva a la competencia).
- riesgos_reputacionales y atributos_negativos.
- fuentes_negativas: URLs reales citadas que sostienen lo negativo.
Veredicto directo y 3-5 hallazgos con evidencia.

Responde ÚNICAMENTE con un objeto JSON válido con esta estructura exacta:
{"sentimiento_por_modelo":{"chatgpt":{"polaridad":0,"tono":"string"},"claude":{"polaridad":0,"tono":"string"},"gemini":{"polaridad":0,"tono":"string"},"perplexity":{"polaridad":0,"tono":"string"}},"polaridad_global":0,"objeciones_detectadas":[{"objecion":"string","modelo":"string","evidencia":"string","fuente":null,"respaldada_por_fuente":false}],"defensa_de_marca":{"estado":"ok|warning|error","deriva_a_competidor":null,"detalle":"string"},"riesgos_reputacionales":["string"],"atributos_negativos":["string"],"fuentes_negativas":["string"],"veredicto":"string","hallazgos":["string"]}"""

# ============================================================
# PROMPT — AGENTE DE INFORME (el 5º)
# ============================================================

PROMPT_INFORME = """Eres el analista senior que redacta el INFORME DE VISIBILIDAD EN MOTORES GENERATIVOS de una empresa. Recibes el trabajo ya evaluado de cuatro agentes especializados que han sondeado tres modelos de IA (chatgpt y claude, paramétricos; perplexity, grounded con búsqueda web real) con 16 preguntas formuladas como las haría un usuario real.

ENTRADA: JSON con meta (marca, dominio, keyword, competidores y geo: el mercado geográfico al que se ancló toda la auditoría; menciónalo en el resumen ejecutivo, porque los resultados solo son válidos para ese mercado), bloques: {descubrimiento, competitivo, conocimiento, reputacion} (la evaluación estructurada de cada agente) y fuentes_sector (los dominios que el motor grounded citó REALMENTE al responder las preguntas del sector, con cuántas veces, y si el dominio del cliente está entre ellos).

TU TRABAJO es producir un informe COMPLETO, específico y honesto. Rellena TODAS las secciones:

1. resumen_ejecutivo: 5-8 frases para un decisor no técnico. Qué visibilidad tiene la marca hoy en las IA EN SU MERCADO (nómbralo), qué es lo más grave, qué es lo más aprovechable, y qué pasaría si no se hace nada. Sin jerga y sin adornos. Si algún agente detectó confusión de entidad (el modelo habla de otra empresa homónima), eso va en las primeras frases: es más grave que la ausencia.
2. veredicto_visibilidad: nivel ("invisible": no emerge en descubrimiento y los modelos apenas la conocen; "emergente": aparece de forma esporádica o solo en un motor; "competitiva": aparece con regularidad pero no lidera; "dominante": aparece de forma consistente y en cabeza) + justificacion basada en las tasas de aparición reales.
3. tabla_visibilidad: una fila por modelo (chatgpt, claude, gemini, perplexity) con: aparece_descubrimiento (tasa), conoce_marca (nivel), sentimiento, y una observacion diferencial de ese modelo.
4. analisis_por_dimension: para descubrimiento, competitivo, conocimiento y reputacion → resumen (qué se ha encontrado, con datos) e implicacion_negocio (qué significa eso en clientes, oportunidades perdidas o riesgo). Sé concreto: cita cifras y evidencias de los bloques.
5. divergencia_parametrico_grounded: compara lo que los modelos "recuerdan" (chatgpt/claude/gemini) con lo que la web dice hoy (perplexity) y explica qué significa esa diferencia para esta marca en concreto.
6. conjunto_competitivo_consolidado: fusiona los rivales detectados por los agentes de descubrimiento y competitivo, e INCLUYE SIEMPRE a la marca auditada como una entrada más con es_marca: true, aunque tenga CERO menciones. Por empresa: menciones (total), menciones_por_modelo (desglose por chatgpt, claude, gemini y perplexity), modelos en los que aparece, y amenaza (alta si domina el descubrimiento donde la marca no aparece). Ordena de más a menos menciones. Nota: el sistema ya calcula este mapa por su cuenta a partir de los datos de los agentes; tu versión sirve de contraste y de contexto narrativo, así que céntrate en explicar QUIÉN es cada rival y POR QUÉ amenaza, no solo en repetir cifras.
7. gaps_criticos: los agujeros que explican la falta de visibilidad, cada uno con su evidencia concreta y su impacto. USA fuentes_sector: si el motor grounded cita dominios donde la marca no está, eso ES un gap y hay que nombrar esos dominios.
8. oportunidades: ángulos aprovechables (atributos donde la marca ya gana, nichos que los rivales no cubren, modelos donde ya tiene tracción).
9. plan_accion_llm: hasta 8 acciones ordenadas por impacto. Cada una: prioridad, accion (verbo primero, específica), por_que (el hallazgo que la motiva), evidencia (dato o cita del informe), esfuerzo y impacto_esperado. Prohibido lo genérico: cada acción debe responder a algo REAL de este informe. Si el motor cita listas, medios o foros concretos donde la marca no está, la acción es conseguir presencia AHÍ, con el dominio nombrado.
10. kpis_seguimiento: métricas medibles para la próxima auditoría, con su valor actual (sacado de este informe) y un objetivo realista.
11. citas_destacadas: 3-5 citas textuales literales de las respuestas de los modelos que un cliente debe leer sí o sí (las más reveladoras, positivas o negativas). Máximo 25 palabras cada una, con su modelo y la pregunta que las provocó.

REGLAS: básate EXCLUSIVAMENTE en los bloques recibidos; no inventes datos, empresas ni citas; si un bloque está vacío o un modelo no respondió, dilo en lugar de rellenar. No exageres ni suavices: si la marca es invisible en las IA, el informe debe decirlo con claridad en la primera frase. Español claro y profesional.

Responde ÚNICAMENTE con un objeto JSON válido con esta estructura exacta:
{"resumen_ejecutivo":"string","veredicto_visibilidad":{"nivel":"invisible|emergente|competitiva|dominante","justificacion":"string"},"tabla_visibilidad":[{"modelo":"string","aparece_descubrimiento":"string","conoce_marca":"string","sentimiento":"string","observacion":"string"}],"analisis_por_dimension":{"descubrimiento":{"resumen":"string","implicacion_negocio":"string"},"competitivo":{"resumen":"string","implicacion_negocio":"string"},"conocimiento":{"resumen":"string","implicacion_negocio":"string"},"reputacion":{"resumen":"string","implicacion_negocio":"string"}},"divergencia_parametrico_grounded":"string","conjunto_competitivo_consolidado":[{"empresa":"string","es_marca":false,"menciones":0,"menciones_por_modelo":{"chatgpt":0,"claude":0,"gemini":0,"perplexity":0},"modelos":["string"],"amenaza":"alta|media|baja"}],"gaps_criticos":[{"gap":"string","evidencia":"string","impacto":"string"}],"oportunidades":["string"],"plan_accion_llm":[{"prioridad":"alta|media|baja","accion":"string","por_que":"string","evidencia":"string","esfuerzo":"bajo|medio|alto","impacto_esperado":"string"}],"kpis_seguimiento":[{"kpi":"string","valor_actual":"string","objetivo":"string"}],"citas_destacadas":[{"modelo":"string","pregunta":"string","cita":"string"}]}"""

PROMPT_A6_DIRECTOR = """Eres el director de una auditoría GEO/SEO completa. Recibes: el score global y por área (determinista, NO lo recalcules), los hallazgos técnicos (infraestructura, SEO técnico, contenido), la huella digital externa, y el INFORME DE VISIBILIDAD EN LLMs ya redactado por el analista.

TU TRABAJO es la síntesis GLOBAL que une lo técnico con lo de visibilidad. NO repitas el informe de LLMs: úsalo como insumo.
1. diagnostico_ejecutivo: 4-6 frases. Cómo se conectan las causas técnicas y de huella con el resultado de visibilidad observado en las IA (ejemplo: si los bots de retrieval están bloqueados o la web no tiene huella externa, esa es la CAUSA de la invisibilidad que el informe describe). Esa relación causa-efecto es lo que el cliente debe entender.
2. plan_accion: máximo 7 acciones GLOBALES ordenadas por impacto (prioridad, area, accion con verbo primero, impacto_esperado). Prioriza las que desbloquean varias áreas a la vez. No dupliques literalmente el plan del informe de LLMs: integra.
3. quick_wins: máximo 3 acciones ejecutables en menos de un día.

REGLAS: solo el informe recibido; no inventes trabajo si un área está bien; español claro.

Responde ÚNICAMENTE con un objeto JSON válido con esta estructura exacta:
{"diagnostico_ejecutivo":"string","plan_accion":[{"prioridad":"alta|media|baja","area":"string","accion":"string","impacto_esperado":"string"}],"quick_wins":["string"]}"""

# ============================================================
# CODE NODES — CAPA TÉCNICA (heredados de v2)
# ============================================================

CODE_NORMALIZAR = r"""// Normaliza y valida el input del webhook (incluye geolocalización del mercado y email)
const b = $json.body || $json;
for (const f of ['brand', 'domain', 'keyword']) {
  if (!b[f] || !String(b[f]).trim()) throw new Error('Falta el campo obligatorio: ' + f);
}
let d = String(b.domain).trim();
if (!/^https?:\/\//i.test(d)) d = 'https://' + d;
d = d.replace(/\/+$/, '');
const m = d.match(/^(https?:\/\/[^\/]+)/i);
if (!m) throw new Error('Dominio no válido: ' + b.domain);
const origin = m[1].toLowerCase();
const competitors = String(b.competitors || '').split(',').map(s => s.trim()).filter(Boolean);

// --- Geolocalización del mercado ---
const PAISES = {
  ES: { es: 'España', en: 'Spain', idioma: 'es' },
  MX: { es: 'México', en: 'Mexico', idioma: 'es' },
  AR: { es: 'Argentina', en: 'Argentina', idioma: 'es' },
  CO: { es: 'Colombia', en: 'Colombia', idioma: 'es' },
  CL: { es: 'Chile', en: 'Chile', idioma: 'es' },
  PE: { es: 'Perú', en: 'Peru', idioma: 'es' },
  US: { es: 'Estados Unidos', en: 'the United States', idioma: 'en' },
  GB: { es: 'Reino Unido', en: 'the United Kingdom', idioma: 'en' },
  IE: { es: 'Irlanda', en: 'Ireland', idioma: 'en' },
  CA: { es: 'Canadá', en: 'Canada', idioma: 'en' },
  AU: { es: 'Australia', en: 'Australia', idioma: 'en' },
  FR: { es: 'Francia', en: 'France', idioma: 'en' },
  DE: { es: 'Alemania', en: 'Germany', idioma: 'en' },
  IT: { es: 'Italia', en: 'Italy', idioma: 'en' },
  PT: { es: 'Portugal', en: 'Portugal', idioma: 'en' },
  BR: { es: 'Brasil', en: 'Brazil', idioma: 'en' },
  NL: { es: 'Países Bajos', en: 'the Netherlands', idioma: 'en' }
};
const pais = String(b.pais || 'ES').trim().toUpperCase().slice(0, 2);
const info = PAISES[pais] || { es: pais, en: pais, idioma: 'en' };
const region = String(b.region || '').trim();
// Idioma de las PREGUNTAS a los modelos (el informe siempre se redacta en español)
const idioma = (b.idioma === 'es' || b.idioma === 'en') ? b.idioma : info.idioma;

const geo = {
  pais,
  pais_nombre: info.es,
  pais_nombre_en: info.en,
  region,
  idioma,
  texto: region ? region + ', ' + info.es : info.es,
  texto_en: region ? region + ', ' + info.en : info.en,
  // Parámetros nativos de localización de las APIs (contrato verificado)
  user_location: region ? { country: pais, region: region } : { country: pais },
  user_location_openai: region
    ? { type: 'approximate', country: pais, region: region }
    : { type: 'approximate', country: pais }
};

// --- Email de destino (se captura y viaja en el informe; el envío se activa aparte) ---
const email = String(b.email || '').trim().toLowerCase();
const email_valido = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

return [{ json: {
  brand: String(b.brand).trim(),
  keyword: String(b.keyword).trim(),
  competitors,
  domain: origin,
  // La home DE VERDAD, siempre la raiz.
  //
  // BUG REAL (medido en la auditoria de BranDevs, 2026-08): esto era 'd', o sea
  // el dominio TAL CUAL lo escribia el cliente, con path incluido. Si escribia
  // 'midominio.com/una-landing', todo el analisis de "la home" —schema, validador
  // oficial de schema.org, title, encabezados— se hacia sobre esa pagina interna,
  // pero el informe seguia hablando de "la home" y meta.domain mostraba la raiz.
  // Resultado: se acusaba al cliente de no tener Organization/LocalBusiness
  // cuando si lo tenia, solo que en la home, que nunca se llego a descargar.
  home_url: origin + '/',
  // La URL que escribio el cliente. Si trae path, se analiza TAMBIEN (entra como
  // landing, ver 'Seleccionar Landings'), pero ya no se confunde con la home.
  pagina_url: d,
  pagina_es_home: d.replace(/\/+$/, '') === origin,
  geo,
  email,
  email_valido,
  urls: { llms_txt: origin + '/llms.txt', robots_txt: origin + '/robots.txt', sitemap: origin + '/sitemap.xml' },
  fecha: new Date().toISOString()
}}];"""

CODE_PREPARAR_BOTS = r"""// UAs reales de los bots de IA para comprobar bloqueos a nivel CDN/WAF.
//
// La CATEGORIA es lo que decide si un bloqueo importa, y es la misma taxonomia
// que ya se aplica al robots.txt:
//   training   → rastrean para ENTRENAR modelos. Bloquearlos es una decision
//                legitima del cliente y NO cuesta citaciones. Muchos hostings y
//                plugins lo activan por defecto.
//   retrieval  → buscan en vivo para responder. Si estos no pasan, no te citan.
//   user_fetch → abren una URL porque un usuario la ha pedido en el chat.
// Antes solo se probaban 2 de training y 1 de retrieval, asi que un bloqueo de
// entrenamiento (inofensivo) hundia el bloque entero.
const bots = [
  { ua_name: 'GPTBot', categoria: 'training', ua: 'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.2; +https://openai.com/gptbot' },
  { ua_name: 'ClaudeBot', categoria: 'training', ua: 'Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)' },
  { ua_name: 'OAI-SearchBot', categoria: 'retrieval', ua: 'Mozilla/5.0 (compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)' },
  { ua_name: 'PerplexityBot', categoria: 'retrieval', ua: 'Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://docs.perplexity.ai/docs/perplexitybot)' },
  { ua_name: 'ChatGPT-User', categoria: 'user_fetch', ua: 'Mozilla/5.0 (compatible; ChatGPT-User/1.0; +https://openai.com/bot)' },
  { ua_name: 'Claude-User', categoria: 'user_fetch', ua: 'Mozilla/5.0 (compatible; Claude-User/1.0; +Claude-User@anthropic.com)' }
];
return bots.map(b => ({ json: b }));"""

CODE_ANALIZAR_EDGE = r"""// Compara el acceso real de cada UA de bot contra el baseline de navegador
const baseline = $('GET Home').first().json;
const bots = $('Preparar Fetch Bots').all().map(i => i.json);
const resps = $input.all().map(i => i.json);
const baseStatus = baseline.statusCode ?? null;
const baseRaw = baseline.body ?? baseline.data;
const baseLen = typeof baseRaw === 'string' ? baseRaw.length : 0;
const challenge = (b) => /just a moment|attention required|cf-browser-verification|checking your browser|access denied|enable javascript and cookies/i.test(b || '');

// BASELINE BLINDADO: si la peticion de navegador no devolvio 200, no hay con que
// comparar y NADA de lo que salga aqui es concluyente. Pasa de verdad: hay WAFs
// que devuelven 403 a un User-Agent de navegador que llega desde una IP de
// datacenter (heuristica antiscraping) mientras dejan pasar a los bots
// declarados. Sin este corte, el informe acusaria al cliente de bloquear bots
// basandose en una comparacion contra un baseline roto.
const baselineValido = baseStatus === 200;

const resultados = bots.map((b, i) => {
  const r = resps[i] || {};
  const status = r.statusCode ?? null;
  const raw = r.body ?? r.data;
  const body = typeof raw === 'string' ? raw : '';
  const bloqueado = status === null || status === 403 || status === 503 || status === 429 || (status === 200 && challenge(body));
  return {
    bot: b.ua_name,
    categoria: b.categoria || 'training',
    status,
    // null (no false) cuando no se puede saber: ausencia de dato, no ausencia de bloqueo.
    bloqueado_edge: baselineValido ? !!bloqueado : null,
    // 429 es rate limit, no una politica contra ese bot: se marca aparte para no
    // venderlo como "te bloquean los bots de IA".
    posible_rate_limit: status === 429,
    ratio_vs_baseline: baseLen && body.length ? Math.round((body.length / baseLen) * 100) / 100 : null,
    challenge_detectado: challenge(body)
  };
});

// --- Veredicto DETERMINISTA, por categoria ---
const porCategoria = { training: [], retrieval: [], user_fetch: [] };
for (const r of resultados) {
  if (r.bloqueado_edge === true) (porCategoria[r.categoria] || porCategoria.training).push(r.bot);
}
const criticos = porCategoria.retrieval.concat(porCategoria.user_fetch);

let veredicto, motivo;
if (!baselineValido) {
  veredicto = 'no_verificable';
  motivo = 'El baseline de navegador devolvio ' + (baseStatus === null ? 'sin respuesta' : baseStatus) +
    ' en vez de 200, asi que no hay contra que comparar. Puede ser el WAF filtrando por reputacion de IP: ' +
    'no se puede concluir nada sobre el acceso de los bots.';
} else if (criticos.length) {
  veredicto = 'error';
  motivo = 'Bloqueados bots de retrieval/user-fetch (' + criticos.join(', ') + '). ' +
    'Estos son los que deciden si un motor te cita: si no pueden leer la web, no apareces.';
} else if (porCategoria.training.length) {
  veredicto = 'ok';
  motivo = 'Solo se bloquean rastreadores de ENTRENAMIENTO (' + porCategoria.training.join(', ') + '). ' +
    'Suele ser un ajuste deliberado del hosting o de un plugin, es una decision legitima y NO cuesta ' +
    'citaciones: los bots que deciden si te citan (' +
    resultados.filter(r => r.categoria !== 'training' && r.bloqueado_edge === false).map(r => r.bot).join(', ') +
    ') acceden con normalidad.';
} else {
  veredicto = 'ok';
  motivo = 'Todos los bots de IA probados acceden igual que un navegador.';
}

return [{ json: {
  baseline_status: baseStatus,
  baseline_valido: baselineValido,
  resultados,
  bloqueados_por_categoria: porCategoria,
  veredicto,
  motivo
} }];"""

CODE_PARSEAR_VALIDACION = r"""// Parsea la respuesta de validator.schema.org (endpoint no documentado: extracción defensiva)
const j = $input.first().json;
let out = { disponible: false, motivo: 'sin respuesta del validador' };
try {
  const rawV = j.body ?? j.data;
  let body = typeof rawV === 'string' ? rawV : JSON.stringify(rawV || '');
  if ((j.statusCode ?? 0) === 200 && body) {
    body = body.replace(/^\)\]\}'?\s*/, '').trim();
    const data = JSON.parse(body);
    const errores = [], warnings = [];
    const push = (e, propiedad) => {
      const item = { propiedad: propiedad || null, tipo: e.errorType || e.type || 'error',
        detalle: [propiedad, e.errorType || e.type, ...(Array.isArray(e.args) ? e.args : [])].filter(Boolean).join(' ') };
      (e.warning || e.isWarning ? warnings : errores).push(item);
    };
    for (const gTri of data.tripleGroups || []) {
      for (const n of gTri.nodes || []) {
        for (const e of n.errors || []) push(e, null);
        for (const p of n.properties || []) { for (const e of p.errors || []) push(e, p.pred || null); }
      }
    }
    out = { disponible: true,
      num_errores: typeof data.totalNumErrors === 'number' ? data.totalNumErrors : errores.length,
      num_warnings: typeof data.totalNumWarnings === 'number' ? data.totalNumWarnings : warnings.length,
      errores: errores.slice(0, 15), warnings: warnings.slice(0, 15) };
  } else { out.motivo = 'status ' + (j.statusCode ?? 'desconocido'); }
} catch (e) { out = { disponible: false, motivo: 'respuesta no parseable' }; }
return [{ json: out }];"""

CODE_ELEGIR_SITEMAP = r"""// Resuelve el sitemap real en 3 pasos:
// 1) si /sitemap.xml es un indice (Yoast/RankMath) -> elegir el sub-sitemap de paginas
// 2) si /sitemap.xml no existe -> usar la ruta declarada en el robots.txt (linea "Sitemap:")
// 3) ultimo recurso: /sitemap.xml (Seleccionar Landings caera a los enlaces de la home)
const j = $('GET sitemap.xml').first().json;
const rawSm = j.body ?? j.data;
const body = typeof rawSm === 'string' ? rawSm : '';
const urlsCfg = $('Normalizar Input').first().json.urls;

const rob = $('GET robots.txt').first().json;
const rawRob = rob.body ?? rob.data;
const robotsBody = typeof rawRob === 'string' ? rawRob : '';
const smMatch = robotsBody.match(/^[ \t]*sitemap:[ \t]*(\S+)/im);
const smRobots = smMatch ? smMatch[1] : null;

const locs = [...body.matchAll(/<loc>\s*([^<\s]+)\s*<\/loc>/gi)].map(x => x[1]);
const xmlLocs = locs.filter(u => /\.xml(\?|$)/i.test(u));

let sitemap_url;
if (xmlLocs.length) {
  sitemap_url = xmlLocs.find(u => /page/i.test(u)) || xmlLocs.find(u => /post/i.test(u)) || xmlLocs[0];
} else if (locs.length) {
  sitemap_url = urlsCfg.sitemap;
} else if (smRobots) {
  sitemap_url = smRobots;
} else {
  sitemap_url = urlsCfg.sitemap;
}
return [{ json: { sitemap_url, declarado_en_robots: smRobots } }];"""

CODE_SELECCIONAR_LANDINGS = r"""// Mapea TODAS las URLs del sitemap y selecciona las que COINCIDEN con el termino de busqueda.
// La home (o la URL indicada en dominio) va siempre. Ya NO coge "las 3 primeras" a ciegas.
// Pertenencia al sitio por HOST NORMALIZADO (sin esquema, sin www): arregla dominio.com vs www.dominio.com.
const norm = $('Normalizar Input').first().json;
const MAX_LANDINGS = 12;   // tope de seguridad para acotar el fan-out HTTP y el coste

const hostOf = (u) => { const m = String(u).trim().match(/^https?:\/\/([^\/:?#]+)/i); return m ? m[1].toLowerCase().replace(/^www\./, '') : null; };
const pathOf = (u) => { const m = String(u).match(/^https?:\/\/[^\/]+(\/[^?#]*)?/i); return ((m && m[1]) || '/').replace(/\/+$/, '') || '/'; };
const baseHost = hostOf(norm.domain);

// --- 1. Recoger TODAS las URLs del sitemap (o enlaces de la home como fallback) ---
const smJson = $('GET Sitemap Páginas').first().json;
const smRaw = smJson.body ?? smJson.data;
const smBody = typeof smRaw === 'string' ? smRaw : '';
let urls = [...smBody.matchAll(/<loc>\s*([^<\s]+)\s*<\/loc>/gi)].map(x => x[1]).filter(u => !/\.xml(\?|$)/i.test(u));
let fuente = 'sitemap';
if (!urls.length) {
  fuente = 'enlaces_home';
  const homeJson = $('GET Home').first().json;
  const rawHome = homeJson.body ?? homeJson.data;
  const html = typeof rawHome === 'string' ? rawHome : '';
  urls = [...html.matchAll(/<a[^>]+href=["']([^"'#\s]+)["']/gi)].map(x => x[1]).map(h => {
    if (/^https?:\/\//i.test(h)) return h;
    if (h.startsWith('//')) return 'https:' + h;
    if (h.startsWith('/')) return norm.domain + h;
    return null;
  }).filter(Boolean);
}

// Excluir ruido (legal, carrito, assets...). NO excluye por "primeras N".
const EXCLUDE = /(aviso-?legal|privacidad|privacy|cookie|terminos|condiciones|politica-|\/politica|\/login|\/carrito|\/cart|\/checkout|\/wp-|\/feed\/?$|\.(jpg|jpeg|png|gif|svg|webp|pdf|css|js|ico|mp4|zip|xml)(\?|$)|mailto:|tel:)/i;

// --- 2. Matching contra el termino de busqueda ---
// Tokeniza el keyword (quita stopwords y acentos) y puntua coincidencias en el slug de cada URL.
const STOP = new Set(['de','la','el','los','las','en','y','a','para','con','del','por','un','una','o','the','of','in','and','for','to']);
const limpiar = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9\s]/g, ' ');
const tokens = [...new Set(limpiar(norm.keyword).split(/\s+/).filter(t => t.length > 2 && !STOP.has(t)))];

function puntuar(path){
  const slug = limpiar(path.replace(/[\/\-_]+/g, ' '));
  let score = 0;
  for (const t of tokens) if (slug.includes(t)) score += 2;
  const prof = (path.match(/\//g) || []).length;
  if (prof >= 4) score -= 1;   // rutas muy profundas, menos representativas
  return score;
}

// --- 3. Construir lista: dedup + puntuar ---
const debug = { fuente, candidatas: urls.length, tokens, descartes: { otro_host: 0, home: 0, excluidas: 0, duplicadas: 0 } };
const seen = new Set();
const homeUrl = (norm.home_url || norm.domain).replace(/\/+$/, '');

// Paginas que entran SI O SI, antes que ninguna otra: la home, y ademas la URL
// que escribio el cliente si traia path (para eso la escribio). Se meten en
// 'seen' ANTES del bucle para que no vuelvan a salir del sitemap: esa era la
// causa de que la primera landing apareciese duplicada en el informe.
const fijas = [homeUrl];
const paginaUrl = String(norm.pagina_url || '').trim().replace(/\/+$/, '');
if (paginaUrl && paginaUrl !== homeUrl && hostOf(paginaUrl) === baseHost) fijas.push(paginaUrl);
for (const f of fijas) seen.add(hostOf(f) + pathOf(f));

let candidatos = [];
for (const u of urls) {
  const clean = String(u).trim().replace(/\/+$/, '');
  const h = hostOf(clean);
  if (!h || h !== baseHost) { debug.descartes.otro_host++; continue; }
  const path = pathOf(clean);
  if (path === '/') { debug.descartes.home++; continue; }   // la home se añade aparte, siempre
  if (EXCLUDE.test(clean)) { debug.descartes.excluidas++; continue; }
  const key = h + path;
  if (seen.has(key)) { debug.descartes.duplicadas++; continue; }
  seen.add(key);
  candidatos.push({ url: clean, score: puntuar(path) });
}

// Coincidencias con el keyword = algun token en el slug. Si no hay coincidencias (o keyword raro),
// cae a las primeras candidatas validas para no quedarse sin paginas internas.
const conMatch = candidatos.filter(c => tokens.some(t => limpiar(c.url).includes(t)));
let elegidas = (conMatch.length ? conMatch.sort((a, b) => b.score - a.score) : candidatos).slice(0, MAX_LANDINGS);
debug.con_match_keyword = conMatch.length;
debug.total_candidatas_validas = candidatos.length;
debug.seleccionadas = elegidas.length;
debug.criterio = conMatch.length ? 'coincidencia con termino de busqueda' : 'sin coincidencias: primeras paginas validas';

// --- 4. Primero las fijas (home + la URL indicada), luego las elegidas ---
debug.fijas = fijas;
const items = fijas.map((u, i) => ({
  json: { url: u, skip: false, es_home: i === 0, ...(i === 0 ? { _debug: debug } : {}) }
}));
if (!elegidas.length) {
  items[0].json.es_fallback_home = true;
  return items;
}
for (const c of elegidas.slice(0, Math.max(0, MAX_LANDINGS - items.length + 1))) {
  items.push({ json: { url: c.url, skip: false } });
}
return items;
"""

# ============================================================
# Deteccion DETERMINISTA de Organization/LocalBusiness en JSON-LD
# ============================================================
# POR QUE EXISTE
# 'campos_ausentes' lo redactaba el LLM en prosa libre a partir de los bloques
# JSON-LD. En la auditoria real de BranDevs listo como ausentes los siete campos
# (name, url, logo, description, sameAs, address, telephone) cuando los siete
# estaban en la home. El LITE ya lo calculaba en codigo; el COMPLETO no.
#
# Ahora se calcula aqui y el agente recibe el resultado ya hecho (ver el prompt
# del Agente 1, que tiene prohibido contradecirlo).
#
# Se inyecta en DOS nodos Code (la home y las landings) porque en n8n los nodos
# no comparten codigo. Definirlo aqui una sola vez evita que se desincronicen.
JS_SCHEMA_ORG = r"""
// --- Deteccion determinista de Organization/LocalBusiness ---
const CAMPOS_ORG = ['name', 'url', 'logo', 'description', 'sameAs', 'address', 'telephone'];
// LocalBusiness tiene decenas de subtipos (ProfessionalService, Store, Dentist...).
// Se aceptan los mas comunes y, como red, cualquier tipo que termine en Business
// u Organization. OJO: 'Service' a secas NO es una organizacion, es una oferta.
const RE_ORG = /^(organization|corporation|ngo|localbusiness|professionalservice|store|onlinestore|restaurant|hotel|medicalbusiness|legalservice|homeandconstructionbusiness|automotivebusiness|financialservice|foodestablishment|healthandbeautybusiness|lodgingbusiness|sportsactivitylocation|entertainmentbusiness|educationalorganization|governmentorganization|sportsorganization|newsmediaorganization|travelagency|realestateagent|dentist|physician|attorney|emergencyservice|childcare|selfstorage|shoppingcenter|touristinformationcenter|[a-z]*business|[a-z]*organization)$/i;

const tiposDe = (n) => {
  const t = n && n['@type'];
  return (Array.isArray(t) ? t : [t]).filter(x => typeof x === 'string');
};
const esOrg = (n) => tiposDe(n).some(t => RE_ORG.test(t.replace(/^https?:\/\/schema\.org\//i, '')));

// Recorre TODO: @graph, arrays de raiz y objetos anidados dentro de propiedades.
// Un Organization dentro de publisher/provider tambien cuenta: existe igual.
function aplanarLd(v, out, prof) {
  if (!v || prof > 6) return out;
  if (Array.isArray(v)) { for (const x of v) aplanarLd(x, out, prof + 1); return out; }
  if (typeof v !== 'object') return out;
  if (v['@type']) out.push(v);
  for (const k of Object.keys(v)) {
    if (k === '@context') continue;
    if (v[k] && typeof v[k] === 'object') aplanarLd(v[k], out, prof + 1);
  }
  return out;
}

// Un campo cuenta como presente si tiene contenido de verdad: '' , [] y {} no valen.
const tieneValor = (v) => {
  if (v === null || v === undefined) return false;
  if (typeof v === 'string') return v.trim() !== '';
  if (Array.isArray(v)) return v.length > 0;
  if (typeof v === 'object') return Object.keys(v).length > 0;
  return true;
};

// Se queda con el nodo de organizacion MAS COMPLETO: una web puede declarar un
// Organization escueto en una pagina y el bueno en otra.
function analizarOrg(nodos) {
  const orgs = (nodos || []).filter(esOrg);
  if (!orgs.length) {
    return { encontrado: false, tipo: null, presentes: [], ausentes: CAMPOS_ORG.slice() };
  }
  let mejor = null;
  for (const o of orgs) {
    const presentes = CAMPOS_ORG.filter(c => tieneValor(o[c]));
    if (!mejor || presentes.length > mejor.presentes.length) {
      mejor = {
        encontrado: true,
        tipo: tiposDe(o).join('+'),
        presentes,
        ausentes: CAMPOS_ORG.filter(c => !tieneValor(o[c]))
      };
    }
  }
  return mejor;
}
"""

CODE_ANALIZAR_LANDINGS = JS_SCHEMA_ORG + r"""
// Extrae title, headings y tipos de Schema de cada landing descargada.
// Defensivo: NUNCA emite vacio. Pase lo que pase aguas arriba, siempre devuelve 1 item {landings, _debug}.
let reqs = [], resps = [];
try { reqs = $('Seleccionar Landings').all().map(i => i.json); } catch (e) { reqs = []; }
try { resps = $input.all().map(i => i.json); } catch (e) { resps = []; }

const stripTags = (h) => String(h).replace(/<[^>]+>/g, ' ').replace(/&nbsp;|&amp;|&quot;|&#\d+;|&[a-z]+;/gi, ' ').replace(/\s+/g, ' ').trim();
const landings = [];
reqs.forEach((r, idx) => {
  if (!r || r.skip) return;
  const resp = resps[idx] || {};
  const rawL = resp.body ?? resp.data;
  const html = typeof rawL === 'string' ? rawL.slice(0, 300000) : '';
  const tm = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  const title = tm ? stripTags(tm[1]).slice(0, 150) : null;
  const headings = [];
  const reH = /<h([1-6])[^>]*>([\s\S]*?)<\/h\1>/gi;
  let m;
  while ((m = reH.exec(html)) !== null && headings.length < 30) {
    headings.push({ nivel: 'h' + m[1], texto: stripTags(m[2]).slice(0, 120) });
  }
  const tipos = new Set();
  let nodos = [];
  let malformados = 0;
  const reLd = /<script[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
  while ((m = reLd.exec(html)) !== null) {
    try {
      const parsed = JSON.parse(m[1].trim());
      // aplanarLd baja tambien a @graph, arrays y objetos anidados: antes solo se
      // miraba el primer nivel y un Organization dentro de publisher no contaba.
      nodos = aplanarLd(parsed, nodos, 0);
    } catch (e) { malformados++; }
  }
  for (const b of nodos) for (const t of tiposDe(b)) tipos.add(t);
  landings.push({
    url: r.url,
    status: resp.statusCode ?? null,
    title,
    headings,
    schema_tipos: [...tipos],
    // Campos de Organization/LocalBusiness comprobados EN CODIGO, no por el LLM.
    schema_org: analizarOrg(nodos),
    schema_bloques_malformados: malformados,
    es_home: !!r.es_home,
    es_fallback_home: !!r.es_fallback_home
  });
});

const _debug = (reqs[0] && reqs[0]._debug) || (reqs.length === 0 ? { motivo: 'sin items de entrada desde GET Landing' } : null);
return [{ json: { landings, _debug } }];
"""

CODE_CONSOLIDAR = JS_SCHEMA_ORG + r"""
// Consolida todas las señales verificadas (repositorios reales, sin LLM)
const input = $('Normalizar Input').first().json;
const llms = $('GET llms.txt').first().json;
const robots = $('GET robots.txt').first().json;
const sitemap = $('GET sitemap.xml').first().json;
const home = $('GET Home').first().json;
const smPaginas = $('GET Sitemap Páginas').first().json;
let landings = [];
let landings_debug = null;
try {
  const aj = $('Analizar Landings').first().json;
  landings = aj.landings || [];
  landings_debug = aj._debug || null;
} catch (e) { landings = []; landings_debug = { motivo: 'Analizar Landings sin output (0 items)' }; }
const acceso_edge = $('Analizar Acceso Edge').first().json;

const asText = (r) => { const b = r.body ?? r.data; return typeof b === 'string' ? b : JSON.stringify(b || ''); };
const stripTags = (h) => h
  .replace(/<script[\s\S]*?<\/script>/gi, ' ').replace(/<style[\s\S]*?<\/style>/gi, ' ')
  .replace(/<noscript[\s\S]*?<\/noscript>/gi, ' ').replace(/<[^>]+>/g, ' ')
  .replace(/&nbsp;|&amp;|&quot;|&#\d+;|&[a-z]+;/gi, ' ').replace(/\s+/g, ' ').trim();

const llmsBody = asText(llms).slice(0, 4000);
const llmsIsHtml = /<html|<!doctype/i.test(llmsBody);
const llms_txt = { status: llms.statusCode ?? null,
  exists: llms.statusCode === 200 && !llmsIsHtml && llmsBody.trim().length > 0,
  parece_html: llmsIsHtml, contenido: llmsBody.slice(0, 2500) };

const robotsBody = asText(robots).slice(0, 6000);
const CATS = {
  training: ['GPTBot','ClaudeBot','CCBot','Bytespider','Meta-ExternalAgent','meta-externalagent','Amazonbot','Google-Extended','Applebot-Extended'],
  retrieval: ['OAI-SearchBot','Claude-SearchBot','PerplexityBot','DuckAssistBot','YouBot'],
  user_fetch: ['ChatGPT-User','Claude-User','Perplexity-User','MistralAI-User'],
  deprecados: ['Claude-Web','anthropic-ai']
};
const detectados = {};
for (const [cat, list] of Object.entries(CATS)) {
  detectados[cat] = list.filter(bt => new RegExp(bt.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&'), 'i').test(robotsBody));
}
const robots_txt = { status: robots.statusCode ?? null, exists: robots.statusCode === 200,
  bots_detectados_por_categoria: detectados, contenido: robotsBody };

const smBody = asText(smPaginas);
const lastmods = [...smBody.matchAll(/<lastmod>\s*([^<\s]+)\s*<\/lastmod>/gi)].map(x => x[1]).sort();
const sitemap_xml = { status: sitemap.statusCode ?? null, exists: sitemap.statusCode === 200,
  lastmod_mas_reciente: lastmods.length ? lastmods[lastmods.length - 1] : null };

const html = asText(home).slice(0, 400000);
const pick = (re) => { const m = html.match(re); return m ? m[1].trim() : null; };
const title = pick(/<title[^>]*>([\s\S]*?)<\/title>/i);
const meta_description = pick(/<meta[^>]+name=["']description["'][^>]*content=["']([^"']*)["']/i) || pick(/<meta[^>]+content=["']([^"']*)["'][^>]*name=["']description["']/i);
const meta_robots = pick(/<meta[^>]+name=["']robots["'][^>]*content=["']([^"']*)["']/i) || pick(/<meta[^>]+content=["']([^"']*)["'][^>]*name=["']robots["']/i);
const canonical = pick(/<link[^>]+rel=["']canonical["'][^>]*href=["']([^"']*)["']/i);
const hdrs = home.headers || {};
const x_robots_tag = hdrs['x-robots-tag'] || hdrs['X-Robots-Tag'] || null;

const jsonld = [];
let nodosLd = [];
const reLd = /<script[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
let m;
while ((m = reLd.exec(html)) !== null) {
  try {
    const parsed = JSON.parse(m[1].trim());
    if (parsed['@graph']) jsonld.push(...parsed['@graph']);
    else if (Array.isArray(parsed)) jsonld.push(...parsed);
    else jsonld.push(parsed);
    // Ademas del aplanado de arriba (que solo baja un nivel), se recorre en
    // profundidad para la comprobacion determinista de campos.
    nodosLd = aplanarLd(parsed, nodosLd, 0);
  } catch (e) { jsonld.push({ _error: 'Bloque JSON-LD malformado (no parseable)' }); }
}
const schema_existe = jsonld.some(b => !b._error);

// Campos de Organization/LocalBusiness EN LA HOME, comprobados en codigo.
// El Agente 1 recibe esto ya resuelto y tiene prohibido contradecirlo.
const schema_org_home = analizarOrg(nodosLd);
// Y si la home no lo trae, puede estar en otra pagina: se mira el sitio entero
// para poder decir "no esta en la home pero si en /contacto" en vez de "no hay".
const schema_org_sitio = (() => {
  const conOrg = (landings || []).filter(l => l && l.schema_org && l.schema_org.encontrado);
  if (!conOrg.length) return { encontrado: false, paginas: [] };
  const mejor = conOrg.reduce((a, b) =>
    b.schema_org.presentes.length > a.schema_org.presentes.length ? b : a);
  return {
    encontrado: true,
    paginas: conOrg.map(l => l.url).slice(0, 5),
    mejor_en: mejor.url,
    tipo: mejor.schema_org.tipo,
    presentes: mejor.schema_org.presentes,
    ausentes: mejor.schema_org.ausentes
  };
})();

const headings = [];
const reH = /<h([1-3])[^>]*>([\s\S]*?)<\/h\1>/gi;
while ((m = reH.exec(html)) !== null && headings.length < 40) {
  headings.push({ nivel: 'h' + m[1], texto: stripTags(m[2]).slice(0, 120) });
}

const texto = stripTags(html);
const word_count = texto ? texto.split(' ').length : 0;

const spa_markers = [];
if (/__NEXT_DATA__/.test(html)) spa_markers.push('Next.js');
if (/window\.__NUXT__/.test(html)) spa_markers.push('Nuxt');
if (/ng-version=/.test(html)) spa_markers.push('Angular');
if (/<div[^>]+id=["'](root|app)["'][^>]*>\s*<\/div>/i.test(html)) spa_markers.push('root/app vacío');
const ratio_texto_html = html.length ? Math.round((texto.length / html.length) * 1000) / 1000 : null;
const sospecha_csr = (word_count < 150 && html.length > 50000) || spa_markers.includes('root/app vacío');

let response_time_ms = null;
if (typeof fetch === 'function') {
  try {
    const t0 = Date.now();
    await fetch(input.home_url, { redirect: 'follow' });
    response_time_ms = Date.now() - t0;
  } catch (e) { response_time_ms = null; }
}

// RESPALDO: si no hay landings, la home entra como pagina unica de analisis.
// Garantiza que jerarquia de encabezados, cobertura de schema y todo lo dependiente
// SIEMPRE tenga al menos una pagina real que evaluar (se acabo el 0 en cadena).
if (!landings.length) {
  const tiposHome = [...new Set(jsonld.filter(b => !b._error).flatMap(b => {
    const t = b['@type'];
    return typeof t === 'string' ? [t] : (Array.isArray(t) ? t : []);
  }))];
  landings = [{
    url: input.home_url,
    status: home.statusCode ?? null,
    title,
    headings,
    schema_tipos: tiposHome,
    es_fallback_home: true
  }];
}

return [{ json: { ...input, llms_txt, robots_txt, sitemap_xml, schema_existe, landings, landings_debug, acceso_edge,
  schema_org_home, schema_org_sitio,
  home: { status: home.statusCode ?? null, url: input.home_url, title, meta_description, meta_robots, x_robots_tag,
    canonical, headings, jsonld, render: { ratio_texto_html, spa_markers, sospecha_csr },
    texto_extracto: texto.slice(0, 6000), word_count, response_time_ms } } }];"""

CODE_EXTRAER_HUELLA = r"""// Parsea la respuesta de la Responses API (web_search) a JSON
const j = $input.first().json;
let texto = '';
if (Array.isArray(j.output)) {
  const msg = j.output.find(o => o.type === 'message');
  if (msg && Array.isArray(msg.content)) {
    texto = msg.content.filter(c => c.type === 'output_text').map(c => c.text).join('\n');
  }
}
if (!texto && typeof j.output_text === 'string') texto = j.output_text;
let parsed = null;
try {
  parsed = JSON.parse(texto.replace(/^```json\s*/i, '').replace(/^```\s*/, '').replace(/```\s*$/, '').trim());
} catch (e) {}
return [{ json: parsed || { _raw: texto || JSON.stringify(j).slice(0, 2000), _error: 'Respuesta no parseable como JSON' } }];"""

# ============================================================
# CODE NODES — LOS 4 AGENTES DE SONDEO
# ============================================================

SONDAS = {
    "D1": ("descubrimiento", r"""// Batería de DESCUBRIMIENTO: ninguna pregunta nombra a la marca (visibilidad espontánea)
// Todas se anclan al mercado geográfico para no medir visibilidad en un mercado indefinido.
const { keyword, geo } = $('Normalizar Input').first().json;
const Z = geo.idioma === 'en' ? geo.texto_en : geo.texto;
const preguntas = geo.idioma === 'en' ? [
  `I'm in ${Z}. I'm looking for ${keyword}. Which companies or providers do you recommend? Give me a top 5 with a brief reason for each.`,
  `What are the best options for ${keyword} in ${Z} right now? Name them and explain why they stand out.`,
  `I run a small business in ${Z} and I need to hire ${keyword}. Which specific companies should I ask for a quote?`,
  `Which ${keyword} providers operating in ${Z} have the best reputation and provable experience? Name them.`
] : [
  `Estoy en ${Z}. Busco ${keyword}. ¿Qué empresas o proveedores me recomiendas? Dame un top 5 con una breve razón para cada uno.`,
  `¿Cuáles son las mejores opciones de ${keyword} en ${Z} ahora mismo? Nómbralas y explica por qué destacan.`,
  `Soy una pyme en ${Z} y necesito contratar ${keyword}. ¿A qué empresas concretas debería pedir presupuesto?`,
  `¿Qué proveedores de ${keyword} que operen en ${Z} tienen mejor reputación y experiencia demostrable? Nómbralos.`
];
return preguntas.map((p, i) => ({ json: { bloque: 'descubrimiento', pregunta_id: i + 1, prompt: p } }));"""),

    "D2": ("competitivo", r"""// Batería COMPETITIVA: posicionamiento frente a rivales y conjunto competitivo percibido
const { brand, keyword, competitors, geo } = $('Normalizar Input').first().json;
const Z = geo.idioma === 'en' ? geo.texto_en : geo.texto;
const comp = competitors.length ? competitors.join(', ') : null;
const preguntas = geo.idioma === 'en' ? [
  comp ? `For ${keyword} in ${Z}, compare ${brand} with ${comp}. Which one would you choose and why?`
       : `Which are the main companies competing in ${keyword} in ${Z}? Compare them.`,
  `What are the alternatives to ${brand} (${Z})? Name them and explain how they differ.`,
  `Between ${brand} and its competitors in ${keyword} in ${Z}, which offers the best service and why?`,
  `How does ${brand} differ from other ${keyword} companies in ${Z}? What are its strengths against the competition?`
] : [
  comp ? `Para ${keyword} en ${Z}, compara ${brand} con ${comp}. ¿Cuál elegirías y por qué?`
       : `¿Cuáles son las principales empresas que compiten en ${keyword} en ${Z}? Compáralas entre sí.`,
  `¿Cuáles son las alternativas a ${brand} (${Z})? Nómbralas y di en qué se diferencian.`,
  `Entre ${brand} y sus competidores en ${keyword} en ${Z}, ¿cuál ofrece mejor servicio y por qué?`,
  `¿En qué se diferencia ${brand} de otras empresas de ${keyword} en ${Z}? ¿Cuáles son sus puntos fuertes frente a la competencia?`
];
return preguntas.map((p, i) => ({ json: { bloque: 'competitivo', pregunta_id: i + 1, prompt: p } }));"""),

    "D3": ("conocimiento", r"""// Batería de CONOCIMIENTO Y PRECISIÓN: qué sabe el modelo y si es cierto (contrastable)
// La ubicación desambigua homónimos: sin ella, el modelo puede describir otra empresa del mismo nombre.
const { brand, geo } = $('Normalizar Input').first().json;
const Z = geo.idioma === 'en' ? geo.texto_en : geo.texto;
const preguntas = geo.idioma === 'en' ? [
  `What do you know about the company ${brand}, based in ${Z}? What exactly does it do?`,
  `What services does ${brand} (${Z}) offer and what kind of client does it target?`,
  `Where is ${brand} (${Z}) headquartered, when was it founded and who runs it?`,
  `What clients, case studies or notable projects does ${brand} (${Z}) have?`
] : [
  `¿Qué sabes de la empresa ${brand}, de ${Z}? ¿A qué se dedica exactamente?`,
  `¿Qué servicios ofrece ${brand} (${Z}) y a qué tipo de cliente se dirige?`,
  `¿Dónde tiene su sede ${brand} (${Z}), cuándo se fundó y quién la dirige?`,
  `¿Qué clientes, casos de éxito o proyectos destacados tiene ${brand} (${Z})?`
];
return preguntas.map((p, i) => ({ json: { bloque: 'conocimiento', pregunta_id: i + 1, prompt: p } }));"""),

    "D4": ("reputacion", r"""// Batería de REPUTACIÓN Y OBJECIONES: qué le dice la IA a un cliente que duda
const { brand, keyword, geo } = $('Normalizar Input').first().json;
const Z = geo.idioma === 'en' ? geo.texto_en : geo.texto;
const preguntas = geo.idioma === 'en' ? [
  `I'm in ${Z} and I'm hesitating about hiring ${brand}. Is it trustworthy? What are its weak points?`,
  `What negative reviews, complaints or criticism are there about ${brand} (${Z})?`,
  `Is ${brand} worth what it charges compared to cheaper ${keyword} alternatives in ${Z}?`,
  `What risks should I consider before working with ${brand} (${Z})?`
] : [
  `Estoy en ${Z} y dudo si contratar a ${brand}. ¿Es fiable? ¿Qué puntos débiles tiene?`,
  `¿Qué opiniones, quejas o críticas negativas hay sobre ${brand} (${Z})?`,
  `¿Merece la pena lo que cobra ${brand} frente a alternativas más baratas de ${keyword} en ${Z}?`,
  `¿Qué riesgos debería tener en cuenta antes de trabajar con ${brand} (${Z})?`
];
return preguntas.map((p, i) => ({ json: { bloque: 'reputacion', pregunta_id: i + 1, prompt: p } }));"""),
}

def code_unir(dx, bloque):
    return (r"""// Une cada pregunta con la respuesta de los 4 modelos + citations del grounded
const preguntas = $('Sondas %s').all().map(i => i.json);
const gpt = $('%s - ChatGPT').all().map(i => i.json);
const cla = $('%s - Claude').all().map(i => i.json);
const gem = $('%s - Gemini').all().map(i => i.json);
const per = $('%s - Perplexity').all().map(i => i.json);

const pick = (arr, idx) => {
  const j = arr[idx] || {};
  const rawB = j.body ?? j.data;
  const body = rawB && typeof rawB === 'object' ? rawB : j;
  return String(
    body.choices?.[0]?.message?.content
    ?? (Array.isArray(body.content) ? body.content.map(c => c.text || '').join('\n') : null)
    ?? (Array.isArray(body.candidates?.[0]?.content?.parts) ? body.candidates[0].content.parts.map(p => p.text || '').join('') : null)
    ?? body.message?.content ?? body.output ?? body.text ?? ''
  );
};
const pickCitations = (arr, idx) => {
  const j = arr[idx] || {};
  const rawB = j.body ?? j.data;
  const body = rawB && typeof rawB === 'object' ? rawB : j;
  if (Array.isArray(body.citations)) return body.citations;
  if (Array.isArray(body.search_results)) return body.search_results.map(s => s.url).filter(Boolean);
  return [];
};

const sondas = preguntas.map((p, idx) => ({
  pregunta: p.prompt,
  respuestas: { chatgpt: pick(gpt, idx), claude: pick(cla, idx), gemini: pick(gem, idx), perplexity: pick(per, idx) },
  citations_perplexity: pickCitations(per, idx)
}));
return [{ json: { bloque: '%s', sondas } }];""" % (dx, dx, dx, dx, dx, bloque))

CODE_CONSOLIDAR_SONDEOS = r"""// Reúne los 4 bloques evaluados + agrega las fuentes REALES que citó el motor grounded
const out = (n) => { const j = $(n).first().json; return j.message?.content ?? j; };
const bloques = {
  descubrimiento: out('Evaluador D1 - Descubrimiento'),
  competitivo: out('Evaluador D2 - Competitivo'),
  conocimiento: out('Evaluador D3 - Conocimiento'),
  reputacion: out('Evaluador D4 - Reputacion')
};

const norm = $('Normalizar Input').first().json;

// --- Las 16 preguntas EXACTAS lanzadas a los modelos, clasificadas por bloque ---
// Salen de los nodos Unir (dato duro), no de ningun LLM: el informe puede mostrarlas tal cual.
const preguntas = {};
for (const [bloque, nodo] of [['descubrimiento','D1 - Unir'], ['competitivo','D2 - Unir'],
                              ['conocimiento','D3 - Unir'], ['reputacion','D4 - Unir']]) {
  try { preguntas[bloque] = ($(nodo).first().json.sondas || []).map(s => s.pregunta).filter(Boolean); }
  catch (e) { preguntas[bloque] = []; }
}

const domain = norm.domain.replace(/^https?:\/\//, '').replace(/^www\./, '');
const conteo = {};
const urlsCliente = [];
let total = 0;
for (const nodo of ['D1 - Perplexity', 'D2 - Perplexity', 'D3 - Perplexity', 'D4 - Perplexity']) {
  let items = [];
  try { items = $(nodo).all(); } catch (e) { items = []; }
  for (const it of items) {
    const j = it.json || {};
    const rawB = j.body ?? j.data;
  const body = rawB && typeof rawB === 'object' ? rawB : j;
    const cits = Array.isArray(body.citations) ? body.citations
      : (Array.isArray(body.search_results) ? body.search_results.map(s => s.url).filter(Boolean) : []);
    for (const u of cits) {
      if (typeof u !== 'string') continue;
      const m = u.match(/^https?:\/\/([^\/]+)/i);
      if (!m) continue;
      const d = m[1].toLowerCase().replace(/^www\./, '');
      conteo[d] = (conteo[d] || 0) + 1;
      total++;
      if (d === domain) urlsCliente.push(u);
    }
  }
}
const dominios_citados = Object.entries(conteo)
  .map(([dominio, veces]) => ({ dominio, veces }))
  .sort((a, b) => b.veces - a.veces)
  .slice(0, 25);

// --- MAPA COMPETITIVO DETERMINISTA (fusiona D1 + D2) ---
// Alimenta los graficos: NO depende de que el agente de informe rellene su campo.
const MOD = ['chatgpt', 'claude', 'gemini', 'perplexity'];
const key = (s) => String(s || '').trim().toLowerCase().replace(/[^a-z0-9]/g, '');
const brandKey = key(bloques.descubrimiento && norm.brand);
const mapa = new Map();

const acumular = (nombre, total, porModelo, modelos) => {
  const k = key(nombre);
  if (!k) return;
  if (!mapa.has(k)) mapa.set(k, {
    empresa: String(nombre).trim(), es_marca: k === brandKey, menciones: 0,
    menciones_por_modelo: { chatgpt: 0, claude: 0, gemini: 0, perplexity: 0 }, modelos: new Set()
  });
  const e = mapa.get(k);
  let suma = 0;
  const pm = (porModelo && typeof porModelo === 'object') ? porModelo : null;
  if (pm) {
    for (const m of MOD) {
      const v = typeof pm[m] === 'number' ? pm[m] : 0;
      e.menciones_por_modelo[m] += v;
      suma += v;
      if (v > 0) e.modelos.add(m);
    }
  } else if (Array.isArray(modelos)) {
    // Fallback si el evaluador no devolvio el desglose: 1 mencion por modelo declarado
    for (const m of modelos.map(x => String(x).toLowerCase())) {
      if (MOD.includes(m)) { e.menciones_por_modelo[m] += 1; suma += 1; e.modelos.add(m); }
    }
  }
  e.menciones += suma || (typeof total === 'number' ? total : 0);
};

(bloques.descubrimiento?.empresas_recomendadas || []).forEach(x =>
  acumular(x.empresa, x.veces, x.menciones_por_modelo, x.modelos));
(bloques.competitivo?.conjunto_competitivo || []).forEach(x =>
  acumular(x.empresa, x.menciones, x.menciones_por_modelo, x.modelos));

// La marca SIEMPRE en el mapa, aunque sea con cero: ese cero es el dato del grafico.
if (!mapa.has(brandKey)) mapa.set(brandKey, {
  empresa: norm.brand, es_marca: true, menciones: 0,
  menciones_por_modelo: { chatgpt: 0, claude: 0, gemini: 0, perplexity: 0 }, modelos: new Set()
});

const marca = mapa.get(brandKey);
const mMarca = marca ? marca.menciones : 0;
const mapa_competitivo = [...mapa.values()].map(e => ({
  empresa: e.empresa,
  es_marca: e.es_marca,
  menciones: e.menciones,
  menciones_por_modelo: e.menciones_por_modelo,
  modelos: [...e.modelos],
  amenaza: e.es_marca ? null
    : (e.menciones > 0 && (mMarca === 0 || e.menciones >= mMarca * 2)) ? 'alta'
    : (e.menciones > mMarca) ? 'media' : 'baja'
})).sort((a, b) => b.menciones - a.menciones);

return [{ json: {
  preguntas,
  mapa_competitivo,
  meta: { brand: norm.brand, domain: norm.domain, keyword: norm.keyword,
    competitors: norm.competitors, geo: norm.geo.texto, pais: norm.geo.pais, idioma_sondeo: norm.geo.idioma },
  bloques,
  fuentes_sector: {
    disponible: total > 0,
    total_citas: total,
    dominios_citados,
    cliente_citado: urlsCliente.length > 0,
    urls_cliente: urlsCliente.slice(0, 5)
  }
} }];"""

CODE_SCORE = r"""// Score global determinista (pesos por evidencia). El SoV sale de los 4 bloques evaluados.
const out = (n) => { const j = $(n).first().json; return j.message?.content ?? j; };
const base = $('Consolidar Señales Web').first().json;
const sondeo = $('Consolidar Sondeos').first().json;
const infra = out('Agente 1 - Infraestructura GEO');
const seo = out('Agente 2 - SEO Técnico');
const contenido = out('Agente 3 - Contenido y Entidades');
const informe = out('Agente Informe LLM');
const huella = $('Extraer Huella').first().json;

const val = (e) => e === 'ok' ? 100 : e === 'warning' ? 50 : e === 'error' ? 0 : null;
const avg = (arr) => { const v = arr.filter(x => x !== null && x !== undefined && !Number.isNaN(x)); return v.length ? Math.round(v.reduce((a, b) => a + b, 0) / v.length) : null; };
const wavg = (pairs) => { let s = 0, w = 0; for (const [v, p] of pairs) { if (v !== null && v !== undefined && !Number.isNaN(v)) { s += v * p; w += p; } } return w ? Math.round(s / w) : null; };

// --- Infraestructura (el schema puntua ahora en SEO tecnico; quedan sitemap y llms.txt) ---
const score_infra = wavg([
  [val(infra.sitemap?.estado), 0.65],
  [val(infra.llms_txt?.estado), 0.35]
]);

// --- SEO tecnico con pesos por gravedad (criterio 2026): la jerarquia y el schema son
// los fallos que mas penalizan la lectura por IA; una media simple los diluia y una web
// con 2 H1 se iba a 90. Jerarquia 40% + schema 35% + resto de comprobaciones 25%
// (el resto incluye la infraestructura, que desde 2026 se integra en SEO tecnico).
const score_seo = wavg([
  [val(seo.jerarquia_contenido?.estado), 0.40],
  [val(infra.schema?.estado), 0.35],
  [avg([
    val(seo.rastreo_bots_ia?.estado), val(seo.acceso_edge?.estado), val(seo.indexabilidad?.estado),
    val(seo.renderizado?.estado), val(seo.rendimiento?.estado), score_infra
  ]), 0.25]
]);

const score_cont = avg([
  val(contenido.indice_autoridad?.estado), val(contenido.intent_match?.estado),
  val(contenido.estructura_extraccion?.estado),
  typeof contenido.claridad_nucleo === 'number' ? contenido.claridad_nucleo : null
]);

// --- SoV a partir de los 4 bloques (determinista) ---
const b = sondeo.bloques || {};
const d1 = b.descubrimiento || {}, d2 = b.competitivo || {}, d3 = b.conocimiento || {}, d4 = b.reputacion || {};

// Descubrimiento: media de la tasa de aparición de los 3 modelos
const tasas = ['chatgpt', 'claude', 'gemini', 'perplexity']
  .map(k => d1.por_modelo?.[k]?.tasa_aparicion)
  .filter(x => typeof x === 'number');
const s_desc = tasas.length ? avg(tasas) : null;

// Competitivo: presencia y posición frente a rivales
const mods = (d2.posicion_marca?.mencionada_en || []).length;
const pm = d2.posicion_marca?.posicion_media;
const s_comp = mods === 0 ? 0 : (typeof pm === 'number' && pm <= 3 ? 100 : (mods >= 2 ? 70 : 50));

// Conocimiento: nivel por modelo, penalizado por alucinaciones contradichas
const NIV = { alto: 100, medio: 60, bajo: 30, nulo: 0 };
const nivs = ['chatgpt', 'claude', 'gemini', 'perplexity']
  .map(k => NIV[d3.nivel_conocimiento?.[k]])
  .filter(x => typeof x === 'number');
let s_conoc = nivs.length ? avg(nivs) : null;
const contradichas = (d3.verificacion_factual || []).filter(v => v.veredicto === 'contradicha').length;
if (s_conoc !== null && contradichas) s_conoc = Math.max(0, s_conoc - contradichas * 10);

// Reputación: polaridad global + defensa de marca ante objeción
const pol = typeof d4.polaridad_global === 'number' ? d4.polaridad_global : null;
const s_pol = pol === null ? null : Math.round(((pol + 1) / 2) * 100);
const s_def = val(d4.defensa_de_marca?.estado);
const s_rep = avg([s_pol, s_def]);

const score_sov = wavg([[s_desc, 0.45], [s_comp, 0.20], [s_conoc, 0.20], [s_rep, 0.15]]);

// --- Huella con pesos (criterio 2026): E-E-A-T-C 40% + presencia externa 35% +
// visibilidad del dominio entre las fuentes citadas de verdad por los motores 25%.
const eKeys = ['presencia_foros', 'medios', 'directorios', 'listas_sector'];
const fsec = sondeo.fuentes_sector || {};
const s_vis_dominio = fsec.disponible ? (fsec.cliente_citado ? 100 : 0) : null;
const score_huella = huella._error ? null : wavg([
  [typeof huella.eeatc?.puntuacion_global === 'number' ? huella.eeatc.puntuacion_global : null, 0.40],
  [avg(eKeys.map(k => val(huella[k]?.estado))), 0.35],
  [s_vis_dominio, 0.25]
]);

// Pesos globales v3.1 (criterio 2026): la infraestructura se FUSIONA en SEO tecnico
// (es SEO en esencia) y este pasa a valer 25% (20 + 5). Quedan 4 areas.
const pesos = { seo_tecnico: 0.25, contenido: 0.15, sov: 0.35, huella: 0.25 };
const areas = { seo_tecnico: score_seo, contenido: score_cont, sov: score_sov, huella: score_huella };
let totalPeso = 0, suma = 0;
for (const [k, v] of Object.entries(areas)) {
  if (v !== null) { suma += v * pesos[k]; totalPeso += pesos[k]; }
}
const score_global = totalPeso ? Math.round(suma / totalPeso) : null;

return [{ json: {
  meta: {
    brand: base.brand, domain: base.domain, keyword: base.keyword, competitors: base.competitors, fecha: base.fecha,
    geo: base.geo,
    email: base.email || null,
    email_valido: !!base.email_valido,
    modelos_sondeados: ['gpt-5.4-mini', 'claude-sonnet-4-6', 'gemini-2.5-flash', 'sonar (grounded)'],
    preguntas_lanzadas: 16, sondeos_totales: 48,
    landings_analizadas: (base.landings || []).map(l => l.url)
  },
  score: { global: score_global, por_area: areas, desglose_sov: { descubrimiento: s_desc, competitivo: s_comp, conocimiento: s_conoc, reputacion: s_rep }, pesos },
  infraestructura_geo: infra,
  seo_tecnico: seo,
  contenido_geo: contenido,
  sondeo_llm: sondeo.bloques,
  preguntas: sondeo.preguntas,
  mapa_competitivo: sondeo.mapa_competitivo,
  fuentes_sector: sondeo.fuentes_sector,
  informe_llm: informe,
  huella_digital: huella
} }];"""

CODE_ENSAMBLAR = r"""// Añade la síntesis global del Director y devuelve el JSON final
// Lee el reporte de Fusionar Recomendaciones (último nodo que lo arrastra completo, YA con
// recomendaciones_huella), NO de Calcular Score, que es una foto anterior a las recomendaciones.
let informe;
try { informe = $('Fusionar Recomendaciones').first().json; }
catch (e) { informe = $('Calcular Score').first().json; }   // respaldo defensivo
const d = $input.first().json;
const director = d.message?.content ?? d;
return [{ json: { ...informe, sintesis: director } }];"""

CODE_EMAIL = r"""// Informe completo en HTML apto para email. CERO LLM: plantilla + datos del propio reporte.
// Tablas + estilos inline + colores de fondo: se ve igual en Gmail, Outlook, Apple Mail y moviles.
const r = $input.first().json;
const meta = r.meta || {};
if (!meta.email || !meta.email_valido) return [];   // sin destinatario valido, no se envia nada

const C = {
  bg:'#F6F5F2', surf:'#FFFFFF', dark:'#262523', darkSoft:'#3D3B37',
  border:'#E7E4DE', borderStrong:'#D6D2C9', text:'#121212', muted:'#6E6B66', mutedL:'#9C9791',
  onDarkMuted:'#B4B0A9',
  accent:'#EF3B2D', accentSoft:'#FDECEA',
  ok:'#17915B', okSoft:'#E8F4EE', warn:'#C07600', warnSoft:'#FBF0DE', err:'#B42318', errSoft:'#FBEBE9'
};
const PAL = ['#C3BCAE','#9A9284','#B8946F','#7A8A90','#D6CFC2','#A19889','#68757B','#8C8478'];
const OTROS = '#5C5952';
const F = "-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif";
const MODELOS = [['chatgpt','ChatGPT'],['claude','Claude'],['gemini','Gemini'],['perplexity','Perplexity']];

const esc = (s) => String(s == null ? '' : s)
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const g = (o,p) => p.split('.').reduce((x,k)=>(x && x[k]!==undefined && x[k]!==null)?x[k]:null, o);
const tono = (v) => (v===null||v===undefined) ? C.mutedL : v>=75 ? C.ok : v>=50 ? C.warn : C.err;
const colEstado = (e) => e==='ok'?C.ok : e==='warning'?C.warn : e==='error'?C.err : C.mutedL;
const icono = (e) => e==='ok'?'&#10003;' : e==='warning'?'!' : e==='error'?'&#10007;' : '&ndash;';
const peor = (a) => a.includes('error')?'error' : a.includes('warning')?'warning' : a.includes('ok')?'ok' : 'muted';
const T = (inner, style) => '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;' + (style||'') + '">' + inner + '</table>';

function barra(pct, color){
  const p = Math.max(0, Math.min(100, Math.round(pct || 0)));
  return T('<tr>' +
    (p > 0 ? '<td bgcolor="' + color + '" height="5" style="height:5px;font-size:0;line-height:0;background-color:' + color + ';width:' + p + '%">&nbsp;</td>' : '') +
    (p < 100 ? '<td bgcolor="' + C.border + '" height="5" style="height:5px;font-size:0;line-height:0;background-color:' + C.border + ';width:' + (100-p) + '%">&nbsp;</td>' : '') +
    '</tr>', 'height:5px;border-radius:3px;overflow:hidden');
}

// Barra 100% apilada: sustituye al donut (el SVG no se renderiza en Gmail ni en Outlook)
function apilada(segs){
  const total = segs.reduce((a,s)=>a+s.v, 0);
  if (!total) return '<div style="font:400 12px ' + F + ';color:' + C.mutedL + '">Sin datos</div>';
  let tds = '';
  segs.forEach(s => {
    if (!s.v) return;
    const w = ((s.v/total)*100).toFixed(2);
    tds += '<td bgcolor="' + s.c + '" height="16" style="height:16px;font-size:0;line-height:0;background-color:' + s.c + ';width:' + w + '%">&nbsp;</td>';
  });
  return T('<tr>' + tds + '</tr>', 'height:16px;border-radius:4px;overflow:hidden');
}

function tarjeta(eyebrow, titulo, estado, cuerpo){
  return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:separate;background:' + C.surf + ';border:1px solid ' + C.border + ';border-radius:10px;margin:0 0 14px 0"><tr><td style="padding:20px 22px">' +
    '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>' +
      '<td style="font:700 10px ' + F + ';letter-spacing:1.4px;text-transform:uppercase;color:' + C.mutedL + '">' + esc(eyebrow) + '</td>' +
      (estado && estado !== 'muted' ? '<td align="right"><span style="display:inline-block;width:9px;height:9px;border-radius:50%;background:' + colEstado(estado) + ';font-size:0;line-height:0">&nbsp;</span></td>' : '') +
    '</tr></table>' +
    '<div style="font:700 17px/1.3 ' + F + ';color:' + C.text + ';margin:6px 0 14px;padding-bottom:12px;border-bottom:1px solid ' + C.border + '">' + esc(titulo) + '</div>' +
    cuerpo + '</td></tr></table>';
}

function metrica(label, estado, valor, detalle, fuentes){
  let h = '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 12px 0"><tr>' +
    '<td style="font:400 13px/1.5 ' + F + ';color:' + C.muted + ';padding-right:10px">' + esc(label) + '</td>' +
    '<td align="right" style="font:600 13px/1.5 ' + F + ';color:' + colEstado(estado) + ';white-space:nowrap">' + icono(estado) + ' ' + esc(valor || '') + '</td>' +
    '</tr></table>';
  if (detalle) h += '<div style="font:400 11px/1.6 ' + F + ';color:' + C.mutedL + ';margin:-6px 0 12px">' + esc(detalle) + '</div>';
  if (Array.isArray(fuentes) && fuentes.length){
    const links = fuentes.slice(0,3).filter(u => typeof u === 'string' && /^https?:\/\//i.test(u));
    if (links.length) h += '<div style="margin:-6px 0 12px">' + links.map(u =>
      '<a href="' + esc(u) + '" style="display:block;font:500 11px/1.6 ' + F + ';color:' + C.accent + ';text-decoration:none;word-break:break-all">' + esc(u.replace(/^https?:\/\//,'').slice(0,58)) + '</a>').join('') + '</div>';
  }
  return h;
}

function seccion(eyebrow, titulo, sub){
  return '<div style="text-align:center;margin:36px 0 22px">' +
    '<div style="font:700 10px ' + F + ';letter-spacing:1.6px;text-transform:uppercase;color:' + C.accent + ';margin-bottom:8px">' + esc(eyebrow) + '</div>' +
    '<div style="font:800 24px/1.2 ' + F + ';color:' + C.text + ';letter-spacing:-0.5px;margin-bottom:8px">' + esc(titulo) + '</div>' +
    (sub ? '<div style="font:400 13px/1.6 ' + F + ';color:' + C.muted + '">' + esc(sub) + '</div>' : '') + '</div>';
}

function panel(eyebrow, titulo, cuerpo){
  return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:separate;background:' + C.surf + ';border:1px solid ' + C.border + ';border-radius:10px;margin:0 0 16px 0"><tr><td style="padding:22px">' +
    (eyebrow ? '<div style="font:700 10px ' + F + ';letter-spacing:1.6px;text-transform:uppercase;color:' + C.accent + ';margin-bottom:6px">' + esc(eyebrow) + '</div>' : '') +
    '<div style="font:800 18px/1.3 ' + F + ';color:' + C.text + ';margin-bottom:12px">' + esc(titulo) + '</div>' +
    cuerpo + '</td></tr></table>';
}

function tablaDatos(heads, rows){
  let h = '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;margin-top:8px"><tr>';
  heads.forEach(x => { h += '<th align="left" style="font:700 9px ' + F + ';letter-spacing:1.2px;text-transform:uppercase;color:' + C.mutedL + ';padding:8px;border-bottom:1px solid ' + C.borderStrong + '">' + esc(x) + '</th>'; });
  h += '</tr>';
  rows.forEach(row => {
    const marca = !!row._brand;
    h += '<tr>';
    (row.cells || row).forEach((c, j) => {
      const col = j === 0 ? (marca ? C.accent : C.text) : C.muted;
      h += '<td' + (marca ? ' bgcolor="' + C.accentSoft + '"' : '') + ' style="font:' + (j===0?600:400) + ' 12px/1.5 ' + F + ';color:' + col + ';padding:10px 8px;border-bottom:1px solid ' + C.border + ';vertical-align:top' + (marca ? ';background-color:' + C.accentSoft : '') + '">' + esc(c) + '</td>';
    });
    h += '</tr>';
  });
  return h + '</table>';
}

function accion(a, i){
  const pr = String(a.prioridad || 'media').toLowerCase();
  const bg = pr === 'alta' ? C.accent : pr === 'baja' ? C.mutedL : C.dark;
  const tag = a.area || (a.esfuerzo ? 'Esfuerzo ' + a.esfuerzo : '');
  return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;border-bottom:1px solid ' + C.border + '"><tr>' +
    '<td width="42" valign="top" style="padding:14px 10px 14px 0">' +
      '<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr><td bgcolor="' + bg + '" width="30" height="30" align="center" style="width:30px;height:30px;background-color:' + bg + ';border-radius:15px;font:800 12px ' + F + ';color:#ffffff">' + (i+1) + '</td></tr></table></td>' +
    '<td valign="top" style="padding:14px 0">' +
      (tag ? '<div style="font:700 9px ' + F + ';letter-spacing:1.2px;text-transform:uppercase;color:' + C.accent + ';margin-bottom:3px">' + esc(tag + ' \u00b7 Prioridad ' + pr) + '</div>' : '') +
      '<div style="font:700 14px/1.45 ' + F + ';color:' + C.text + ';margin-bottom:4px">' + esc(a.accion || '') + '</div>' +
      (a.por_que ? '<div style="font:400 12px/1.6 ' + F + ';color:' + C.muted + '">' + esc(a.por_que) + '</div>' : '') +
      (a.evidencia ? '<div style="font:italic 400 11px/1.6 ' + F + ';color:' + C.mutedL + ';margin-top:3px">&ldquo;' + esc(a.evidencia) + '&rdquo;</div>' : '') +
      (a.impacto_esperado ? '<div style="font:400 12px/1.6 ' + F + ';color:' + C.muted + ';margin-top:3px">&rarr; ' + esc(a.impacto_esperado) + '</div>' : '') +
    '</td></tr></table>';
}

// ---------- Construccion (el nivel de detalle se recorta si el correo se pasa de tamaño) ----------
function construir(opts){
  const MAXC = opts.maxCompetidores;
  const DET = opts.detalles;
  const det = (s) => DET ? s : null;

  const inf = r.informe_llm || {};
  const bl = r.sondeo_llm || {};
  const mapa = Array.isArray(r.mapa_competitivo) ? r.mapa_competitivo : [];
  let B = '';

  B += '<div style="text-align:center;padding:8px 0 26px">' +
    '<div style="font:800 26px/1 ' + F + ';letter-spacing:-1px;color:' + C.text + '">GEO<span style="color:' + C.accent + '">pulse</span></div>' +
    '<div style="font:700 10px ' + F + ';letter-spacing:1.6px;text-transform:uppercase;color:' + C.accent + ';margin-top:8px">Auditor\u00eda de visibilidad en IA</div></div>';

  const linea = [meta.brand, meta.domain, meta.geo ? 'Mercado: ' + meta.geo.texto : null,
    meta.fecha ? new Date(meta.fecha).toLocaleDateString('es-ES') : null,
    meta.sondeos_totales ? meta.sondeos_totales + ' sondeos' : null].filter(Boolean).join('  \u00b7  ');
  B += '<div style="font:400 11px/1.6 ' + F + ';color:' + C.mutedL + ';text-align:right;margin-bottom:14px">' + esc(linea) + '</div>';

  const score = g(r,'score.global');
  const sc = score === null ? 0 : score;
  B += '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:separate;border-radius:12px;margin-bottom:16px"><tr><td bgcolor="' + C.dark + '" style="padding:28px;background-color:' + C.dark + ';border-radius:12px">' +
    '<div style="font:700 10px ' + F + ';letter-spacing:1.6px;text-transform:uppercase;color:' + C.accent + ';margin-bottom:10px">Diagn\u00f3stico global</div>' +
    '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>' +
      '<td width="120" valign="middle" style="padding-right:22px">' +
        '<div style="font:800 46px/1 ' + F + ';color:#ffffff">' + (score === null ? '&ndash;' : score) + '</div>' +
        '<div style="font:700 9px ' + F + ';letter-spacing:1.6px;text-transform:uppercase;color:' + C.onDarkMuted + ';margin:6px 0 10px">GEO Score</div>' +
        T('<tr>' +
          (sc > 0 ? '<td bgcolor="' + tono(score) + '" height="6" style="height:6px;font-size:0;line-height:0;background-color:' + tono(score) + ';width:' + sc + '%">&nbsp;</td>' : '') +
          (sc < 100 ? '<td bgcolor="' + C.darkSoft + '" height="6" style="height:6px;font-size:0;line-height:0;background-color:' + C.darkSoft + ';width:' + (100-sc) + '%">&nbsp;</td>' : '') +
        '</tr>', 'height:6px;border-radius:3px;overflow:hidden') +
      '</td>' +
      '<td valign="middle">' +
        '<div style="font:700 17px/1.35 ' + F + ';color:#ffffff;margin-bottom:8px">As\u00ed te ve hoy la inteligencia artificial</div>' +
        '<div style="font:400 13px/1.75 ' + F + ';color:' + C.onDarkMuted + '">' + esc(g(r,'sintesis.diagnostico_ejecutivo') || 'Auditor\u00eda completada.') + '</div>' +
      '</td></tr></table></td></tr></table>';

  const AREAS = [['seo_tecnico','SEO t\u00e9cnico'],['contenido','Contenido'],['sov','Visibilidad IA'],['huella','Huella externa']];
  const pa = g(r,'score.por_area') || {};
  let ar = '';
  AREAS.forEach(([k,lab]) => {
    const v = typeof pa[k] === 'number' ? pa[k] : null;
    ar += '<tr><td style="padding:9px 0;border-bottom:1px solid ' + C.border + '">' +
      '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>' +
      '<td style="font:600 12px ' + F + ';color:' + C.muted + '">' + esc(lab) + '</td>' +
      '<td align="right" style="font:800 15px ' + F + ';color:' + tono(v) + '">' + (v === null ? '&ndash;' : v) + '</td></tr></table>' +
      barra(v, tono(v)) + '</td></tr>';
  });
  B += panel(null, 'Puntuaci\u00f3n por \u00e1rea', T(ar));

  // ===== SEO TECNICO (reorganizado: rastreo -> lectura -> comprension) =====
  B += seccion('Cimientos', 'SEO T\u00e9cnico',
    'La base t\u00e9cnica que decide si la IA puede encontrarte, leerte y entenderte. Verificado contra fuentes reales: tu servidor y el validador oficial de schema.org.');

  const seo = r.seo_tecnico || {};
  const infra = r.infraestructura_geo || {};

  // Bloque 1 - Rastreo: robots.txt + edge + sitemap
  const bpc = g(seo,'rastreo_bots_ia.bloqueados_por_categoria');
  let bots = '';
  if (bpc){
    const ps = [];
    if ((bpc.retrieval||[]).length) ps.push('Retrieval: ' + bpc.retrieval.join(', '));
    if ((bpc.user_fetch||[]).length) ps.push('User-fetch: ' + bpc.user_fetch.join(', '));
    if ((bpc.training||[]).length) ps.push('Training (sin coste de citaci\u00f3n): ' + bpc.training.join(', '));
    bots = ps.length ? ps.join(' \u00b7 ') : 'Sin bloqueos';
  }
  let cRas = metrica('Bots de IA (robots.txt)', g(seo,'rastreo_bots_ia.estado'), '', det([bots, g(seo,'rastreo_bots_ia.detalle')].filter(Boolean).join(' \u2014 ')));
  if (seo.acceso_edge){
    const bq = (g(seo,'acceso_edge.bots_bloqueados_edge')||[]).join(', ');
    cRas += metrica('Acceso real (CDN/WAF)', g(seo,'acceso_edge.estado'), bq ? 'Bloqueados: ' + bq : '', det(g(seo,'acceso_edge.detalle')));
  }
  cRas += metrica('Sitemap XML', g(infra,'sitemap.estado'), '', det(g(infra,'sitemap.detalle')));
  const robs = g(seo,'rastreo_bots_ia.reglas_obsoletas');
  if (Array.isArray(robs) && robs.length) cRas += metrica('Reglas obsoletas en robots.txt', 'warning', String(robs.length), det(robs.join(' \u00b7 ')));
  B += tarjeta('Rastreo', '\u00bfPueden llegar los bots de IA?', peor([g(seo,'rastreo_bots_ia.estado'), g(seo,'acceso_edge.estado'), g(infra,'sitemap.estado')]), cRas);

  // Bloque 2 - Indexacion y renderizado
  let cIdx = metrica('Indexabilidad', g(seo,'indexabilidad.estado'), '', det(g(seo,'indexabilidad.detalle')));
  if (seo.renderizado) cIdx += metrica('Renderizado sin JS', g(seo,'renderizado.estado'), '', det(g(seo,'renderizado.detalle')));
  cIdx += metrica('Jerarqu\u00eda de encabezados', g(seo,'jerarquia_contenido.estado'), '', det(g(seo,'jerarquia_contenido.detalle')));
  const jpp = g(seo,'jerarquia_contenido.por_pagina');
  if (Array.isArray(jpp) && jpp.length){
    if (DET) cIdx += '<div style="font:400 11px/1.6 ' + F + ';color:' + C.mutedL + ';margin:2px 0 6px">An\u00e1lisis p\u00e1gina por p\u00e1gina:</div>';
    jpp.slice(0,15).forEach(pg => {
      const est = ['ok','warning','error'].includes(pg.estado) ? pg.estado : 'warning';
      const u = String(pg.url || '').replace(/^https?:\/\//,'').replace(/\/$/,'');
      cIdx += metrica(u || 'P\u00e1gina', est, '', det(pg.detalle));
    });
  }
  B += tarjeta('Indexaci\u00f3n', 'Lectura y renderizado', peor([g(seo,'indexabilidad.estado'), g(seo,'renderizado.estado'), g(seo,'jerarquia_contenido.estado')]), cIdx);

  // Bloque 3 - Datos estructurados: schema + validador + llms.txt
  const aus = (g(infra,'schema.campos_ausentes') || []).join(', ');
  let cDat = metrica('Marcado Schema (JSON-LD)', g(infra,'schema.estado'), (g(infra,'schema.tipos_detectados')||[]).join(', '),
    det([g(infra,'schema.detalle'), aus ? 'Campos ausentes: ' + aus : null].filter(Boolean).join(' ')));
  const vo = infra.validador_oficial;
  if (vo && vo.disponible) cDat += metrica('Validador schema.org', (vo.num_errores||0) > 0 ? 'error' : (vo.num_warnings||0) > 0 ? 'warning' : 'ok',
    (vo.num_errores||0) + ' errores \u00b7 ' + (vo.num_warnings||0) + ' avisos', null);
  cDat += metrica('Archivo llms.txt', g(infra,'llms_txt.estado'), '', det(g(infra,'llms_txt.detalle')));
  const cobLand = g(infra,'schema.cobertura_landings');
  if (DET && cobLand && typeof cobLand === 'string') cDat += '<div style="font:400 11px/1.6 ' + F + ';color:' + C.mutedL + ';margin-top:4px">Cobertura en p\u00e1ginas internas: ' + esc(cobLand) + '</div>';
  const cobT = g(infra,'schema.cobertura_por_tipo');
  if (Array.isArray(cobT) && cobT.length){
    const TN = { home:'Home', servicios:'Servicios', producto:'Producto', categoria:'Categor\u00eda', blog_post:'Entradas de blog', blog_index:'\u00cdndice de blog', contacto:'Contacto', sobre_nosotros:'Sobre nosotros', caso_exito:'Casos de \u00e9xito', precios:'Precios', faq:'FAQ', otra:'Otras' };
    cDat += '<div style="font:400 11px/1.6 ' + F + ';color:' + C.mutedL + ';margin:2px 0 8px">Cobertura por tipo de p\u00e1gina (cada tipo necesita su propio marcado):</div>';
    cobT.forEach(t => {
      const con = typeof t.con_schema === 'number' ? t.con_schema : 0;
      const tot = typeof t.paginas === 'number' ? t.paginas : 0;
      const est = tot === 0 ? 'no_verificable' : con === tot ? 'ok' : con > 0 ? 'warning' : 'error';
      const falt = (t.schema_faltante || []).length ? 'falta ' + t.schema_faltante.slice(0,3).join(', ') : '';
      cDat += metrica(TN[t.tipo_pagina] || t.tipo_pagina || 'P\u00e1gina', est, con + '/' + tot + ' con schema', det(falt));
    });
  }
  B += tarjeta('Datos estructurados', 'Se\u00f1ales que la IA interpreta', peor([g(infra,'schema.estado'), g(infra,'llms_txt.estado')]), cDat);

  // Bloque 4 - Contenido optimizado para IA
  const cont = r.contenido_geo || {};
  let cCon = metrica('\u00cdndice de autoridad (datos/citas)', g(cont,'indice_autoridad.estado'), '', det(g(cont,'indice_autoridad.detalle')));
  cCon += metrica('Alineaci\u00f3n con la intenci\u00f3n', g(cont,'intent_match.estado'), '', det(g(cont,'intent_match.detalle')));
  cCon += metrica('Chunks autocontenidos', g(cont,'estructura_extraccion.estado'), '', det(g(cont,'estructura_extraccion.detalle')));
  if (cont.tono) cCon += metrica('Tono percibido', 'ok', cont.tono, null);
  B += tarjeta('Contenido', 'Contenido optimizado para IA', peor([g(cont,'indice_autoridad.estado'), g(cont,'intent_match.estado'), g(cont,'estructura_extraccion.estado')]), cCon);

  // Bloque 5 - Semantica
  const cl = typeof cont.claridad_nucleo === 'number' ? cont.claridad_nucleo : null;
  let cSem = '';
  const ents = (cont.entidades || []).slice(0,10);
  if (ents.length) cSem += '<div style="margin-bottom:10px">' + ents.map((e,i) =>
    '<span style="display:inline-block;margin:0 6px 6px 0;padding:4px 10px;border:1px solid ' + (i<2?'#F6CFCA':C.border) + ';border-radius:99px;background:' + (i<2?C.accentSoft:C.bg) + ';font:500 11px ' + F + ';color:' + (i<2?C.accent:C.muted) + '">' + esc(e) + '</span>').join('') + '</div>';
  if (cl !== null) cSem += metrica('Claridad del n\u00facleo del negocio', cl>=75?'ok' : cl>=50?'warning':'error', cl + ' / 100', null);
  B += tarjeta('Sem\u00e1ntica', 'C\u00f3mo lee la IA tu web', cl===null?'muted' : cl>=75?'ok' : cl>=50?'warning':'error', cSem);

  // ===== HUELLA DIGITAL EXTERNA (off-page) =====
  B += seccion('Off-page', 'Huella digital externa',
    'Tu presencia fuera de tu propia web: d\u00f3nde te mencionan y si la IA te reconoce como autoridad. Investigaci\u00f3n org\u00e1nica y global, sin filtro de pa\u00eds.');

  const hue = r.huella_digital || {};
  const HK = [['presencia_foros','Foros y comunidades'],['medios','Medios y prensa'],['directorios','Directorios y rese\u00f1as'],['listas_sector','Listas y rankings del sector']];
  let c4 = '';
  HK.forEach(([k,lab]) => {
    const o = hue[k];
    if (o) c4 += metrica(lab, o.estado, o.calidad || '', det(o.detalle), o.fuentes);
  });
  B += tarjeta('Off-page', 'Presencia externa', peor(HK.map(([k]) => g(hue, k + '.estado'))), c4);

  const ee = hue.eeatc || {};
  const glob = typeof ee.puntuacion_global === 'number' ? ee.puntuacion_global : null;
  if (glob !== null || ee.experiencia){
    let c5 = '';
    [['experiencia','Experiencia'],['expertise','Expertise'],['autoridad','Autoridad'],['confianza','Confianza'],['citabilidad','Citabilidad']].forEach(([k,lab]) => {
      const o = ee[k];
      if (!o) return;
      const v = typeof o.puntuacion === 'number' ? o.puntuacion : null;
      c5 += '<div style="margin-bottom:14px">' +
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>' +
        '<td style="font:400 13px ' + F + ';color:' + C.muted + '">' + esc(lab) + '</td>' +
        '<td align="right" style="font:600 13px ' + F + ';color:' + tono(v) + '">' + (v === null ? '\u2013' : v + ' / 100') + '</td></tr></table>' +
        barra(v, tono(v)) +
        (DET && o.detalle ? '<div style="font:400 11px/1.6 ' + F + ';color:' + C.mutedL + ';margin-top:5px">' + esc(o.detalle) + '</div>' : '') + '</div>';
    });
    if (glob !== null) c5 += metrica('Puntuaci\u00f3n global', glob>=70?'ok' : glob>=40?'warning':'error', glob + ' / 100', det(hue.resumen));
    const car = (ee.carencias || []).slice(0,4);
    if (car.length) c5 += metrica('Carencias', 'warning', String(car.length), car.join(' \u00b7 '));
    B += tarjeta('Autoridad', 'E-E-A-T-C', glob===null?'muted' : glob>=70?'ok' : glob>=40?'warning':'error', c5);
  }

  if (inf.resumen_ejecutivo || inf.veredicto_visibilidad || mapa.length){
    B += seccion('Motores generativos', 'Tu visibilidad en las respuestas de la IA', '16 preguntas de usuario real lanzadas a ChatGPT, Claude, Gemini y Perplexity.');

    const QB = [['descubrimiento','Descubrimiento','\u00bfEmerges cuando nadie te nombra?'],
                ['competitivo','Competitivo','\u00bfCon qui\u00e9n te compara la IA?'],
                ['conocimiento','Conocimiento','\u00bfQu\u00e9 sabe de ti y es cierto?'],
                ['reputacion','Reputaci\u00f3n','\u00bfQu\u00e9 dice cuando el cliente duda?']];
    const PREG = r.preguntas || {};
    const totalQ = QB.reduce((a,[k]) => a + ((PREG[k]||[]).length), 0);
    if (totalQ){
      let q = '';
      QB.forEach(([k,tit,sub]) => {
        const qs = PREG[k] || [];
        if (!qs.length) return;
        q += '<div style="margin-bottom:16px">' +
          '<div style="font:700 13px ' + F + ';color:' + C.text + '">' + esc(tit) + '</div>' +
          '<div style="font:400 11px ' + F + ';color:' + C.mutedL + ';margin-bottom:7px">' + esc(sub + '  \u00b7  ' + qs.length + ' preguntas') + '</div>' +
          '<ol style="margin:0;padding-left:18px">' + qs.map(x => '<li style="font:400 12px/1.6 ' + F + ';color:' + C.muted + ';margin-bottom:6px">' + esc(x) + '</li>').join('') + '</ol></div>';
      });
      B += panel('Metodolog\u00eda', 'Las ' + totalQ + ' preguntas que hemos lanzado', q);
    }

    const niv = g(inf,'veredicto_visibilidad.nivel');
    if (niv){
      const cbg = niv==='invisible'?C.errSoft : niv==='emergente'?C.warnSoft : niv==='dominante'?C.okSoft : C.accentSoft;
      const cfg = niv==='invisible'?C.err : niv==='emergente'?C.warn : niv==='dominante'?C.ok : C.accent;
      B += '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:separate;background:' + C.surf + ';border:1px solid ' + C.border + ';border-left:4px solid ' + C.accent + ';border-radius:0 10px 10px 0;margin-bottom:16px"><tr><td style="padding:20px 22px">' +
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:10px"><tr><td bgcolor="' + cbg + '" style="background-color:' + cbg + ';border-radius:99px;padding:9px 18px;font:800 13px ' + F + ';letter-spacing:1px;text-transform:uppercase;color:' + cfg + '">' + esc(niv) + '</td></tr></table>' +
        '<div style="font:400 13px/1.7 ' + F + ';color:' + C.muted + '">' + esc(g(inf,'veredicto_visibilidad.justificacion') || '') + '</div></td></tr></table>';
    }
    if (inf.resumen_ejecutivo)
      B += '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:separate;background:' + C.surf + ';border:1px solid ' + C.border + ';border-radius:10px;margin-bottom:16px"><tr><td style="padding:22px;font:400 14px/1.8 ' + F + ';color:' + C.text + '">' + esc(inf.resumen_ejecutivo) + '</td></tr></table>';

    const tv = inf.tabla_visibilidad || [];
    if (tv.length) B += panel(null, 'Modelo por modelo', tablaDatos(['Modelo','Descubrim.','Conoce','Sentimiento'],
      tv.map(t => [t.modelo || '', t.aparece_descubrimiento || '\u2013', t.conoce_marca || '\u2013', t.sentimiento || '\u2013'])));

    const cc = mapa.length ? mapa : (inf.conjunto_competitivo_consolidado || []);
    if (cc.length){
      const bn = (meta.brand || '').trim();
      const emp = cc.map(x => ({
        empresa: x.empresa || '',
        es_marca: !!x.es_marca || (bn && String(x.empresa||'').toLowerCase() === bn.toLowerCase()),
        menciones: typeof x.menciones === 'number' ? x.menciones : 0,
        pm: x.menciones_por_modelo || null,
        modelos: x.modelos || [],
        amenaza: x.amenaza || '\u2013'
      }));
      if (bn && !emp.some(e => e.es_marca)) emp.unshift({empresa:bn, es_marca:true, menciones:0, pm:null, modelos:[], amenaza:'\u2013'});
      const valEn = (e,mk) => (e.pm && typeof e.pm[mk] === 'number') ? e.pm[mk] : ((e.modelos||[]).includes(mk) ? 1 : 0);
      const orden = [...emp].sort((a,b) => (b.es_marca?1:0)-(a.es_marca?1:0) || b.menciones - a.menciones);
      const TOP = 8;
      let ci = 0;
      const color = {};
      orden.slice(0,TOP).forEach(e => { color[e.empresa] = e.es_marca ? C.accent : PAL[ci++ % PAL.length]; });
      const resto = orden.slice(TOP);

      const fila = (titulo, getVal) => {
        const segs = orden.slice(0,TOP).map(e => ({n:e.empresa, marca:e.es_marca, v:getVal(e), c:color[e.empresa]}));
        const vr = resto.reduce((a,e)=>a+getVal(e), 0);
        if (vr > 0) segs.push({n:'Otros', marca:false, v:vr, c:OTROS});
        const total = segs.reduce((a,s)=>a+s.v, 0);
        const m = segs.find(s=>s.marca);
        const pct = total ? Math.round(((m ? m.v : 0)/total)*100) : 0;
        return '<tr><td style="padding:10px 0 14px">' +
          '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:6px"><tr>' +
          '<td style="font:700 11px ' + F + ';letter-spacing:1.2px;text-transform:uppercase;color:' + C.mutedL + '">' + esc(titulo) + '</td>' +
          '<td align="right" style="font:800 14px ' + F + ';color:' + (total ? (pct ? C.accent : C.err) : C.mutedL) + '">' + (total ? pct + '% ' : '') +
            '<span style="font:600 10px ' + F + ';letter-spacing:1px;text-transform:uppercase;color:' + C.mutedL + '">' + (!total ? 'sin datos' : (pct ? 'tu marca' : 'no apareces')) + '</span></td>' +
          '</tr></table>' + apilada(segs) + '</td></tr>';
      };

      let cuerpo = '<div style="font:400 12px/1.6 ' + F + ';color:' + C.muted + ';margin-bottom:8px">Reparto de menciones entre tu marca y sus competidores, motor por motor. Tu marca aparece siempre, aunque su cuota sea cero.</div>';
      cuerpo += T(fila('Total', e=>e.menciones) + MODELOS.map(([mk,ml]) => fila(ml, e=>valEn(e,mk))).join(''));
      cuerpo += '<div style="margin:14px 0 6px;padding-top:14px;border-top:1px solid ' + C.border + '">' +
        orden.slice(0,TOP).map(e => '<span style="display:inline-block;margin:0 14px 6px 0;font:' + (e.es_marca?600:400) + ' 11px ' + F + ';color:' + (e.es_marca?C.text:C.muted) + '">' +
          '<span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:' + color[e.empresa] + ';font-size:0;line-height:0">&nbsp;</span> ' +
          esc(e.empresa + (e.es_marca ? ' (tu marca)' : '')) + '</span>').join('') +
        (resto.length ? '<span style="display:inline-block;font:400 11px ' + F + ';color:' + C.muted + '"><span style="display:inline-block;width:9px;height:9px;border-radius:2px;background:' + OTROS + ';font-size:0;line-height:0">&nbsp;</span> Otros (' + resto.length + ')</span>' : '') + '</div>';

      const filas = orden.slice(0, MAXC).map(e => {
        const cells = [e.empresa + (e.es_marca ? ' \u00b7 tu marca' : ''), String(e.menciones)];
        MODELOS.forEach(([mk]) => cells.push(String(valEn(e,mk))));
        cells.push(e.amenaza);
        return { cells, _brand: e.es_marca };
      });
      cuerpo += tablaDatos(['Empresa','Menc.','GPT','Claude','Pplx','Amenaza'], filas);
      if (orden.length > MAXC) cuerpo += '<div style="font:400 11px ' + F + ';color:' + C.mutedL + ';margin-top:8px">Se muestran las ' + MAXC + ' primeras de ' + orden.length + ' empresas detectadas.</div>';
      B += panel('Cuota de voz', 'Qui\u00e9n ocupa tu espacio en las respuestas de la IA', cuerpo);
    }

    const DIMS = [['descubrimiento','Descubrimiento','Visibilidad espont\u00e1nea'],['competitivo','Competitivo','Posici\u00f3n frente a rivales'],
                  ['conocimiento','Conocimiento','Qu\u00e9 saben y si es cierto'],['reputacion','Reputaci\u00f3n','Qu\u00e9 dicen ante una objeci\u00f3n']];
    DIMS.forEach(([k,eye,tit]) => {
      const dd = g(inf,'analisis_por_dimension.' + k);
      if (!dd) return;
      let c = '';
      if (dd.resumen) c += '<div style="font:400 13px/1.7 ' + F + ';color:' + C.muted + ';margin-bottom:10px">' + esc(dd.resumen) + '</div>';
      if (dd.implicacion_negocio) c += '<div style="font:400 13px/1.7 ' + F + ';color:' + C.muted + ';margin-bottom:10px"><b style="color:' + C.text + '">Qu\u00e9 significa: </b>' + esc(dd.implicacion_negocio) + '</div>';
      if (k === 'descubrimiento' && bl.descubrimiento){
        MODELOS.forEach(([mk,ml]) => {
          const pm = g(bl.descubrimiento,'por_modelo.' + mk);
          if (!pm) return;
          const t = typeof pm.tasa_aparicion === 'number' ? pm.tasa_aparicion : null;
          c += metrica(ml, t===null?'no_verificable' : t>=50?'ok' : t>0?'warning':'error', (t===null?'\u2013':t + '% de aparici\u00f3n'), null);
        });
      }
      if (k === 'conocimiento' && bl.conocimiento){
        MODELOS.forEach(([mk,ml]) => {
          const n = g(bl.conocimiento,'nivel_conocimiento.' + mk);
          if (n) c += metrica(ml, n==='alto'?'ok' : n==='medio'?'warning' : n==='nulo'?'error':'warning', n, null);
        });
        const desc = bl.conocimiento.descripcion_percibida;
        if (DET && desc && typeof desc === 'object') MODELOS.forEach(([mk,ml]) => {
          if (desc[mk]) c += '<div style="font:400 11px/1.6 ' + F + ';color:' + C.mutedL + ';margin:2px 0">' + esc(ml) + ': \u201c' + esc(desc[mk]) + '\u201d</div>';
        });
        const vf = bl.conocimiento.verificacion_factual || [];
        const con = vf.filter(x => x.veredicto === 'contradicha');
        if (vf.length) c += metrica('Contraste con tu web real', con.length?'error':'ok',
          vf.filter(x=>x.veredicto==='verificada').length + ' verificadas \u00b7 ' + con.length + ' contradichas', null);
        const ra = bl.conocimiento.riesgo_alucinacion;
        if (ra && ra.nivel) c += metrica('Riesgo de alucinaci\u00f3n', ra.nivel==='bajo'?'ok' : ra.nivel==='medio'?'warning':'error', ra.nivel, det(ra.detalle));
        const alu = bl.conocimiento.alucinaciones || [];
        if (alu.length){
          c += metrica('Datos inventados por la IA', 'error', String(alu.length), '');
          if (DET) alu.slice(0,4).forEach(x => c += '<div style="font:400 11px/1.6 ' + F + ';color:' + C.mutedL + '">\u2715 ' + (x.modelo?esc(x.modelo)+': ':'') + '\u201c' + esc(x.afirmacion) + '\u201d' + (x.gravedad?' \u00b7 gravedad ' + esc(x.gravedad):'') + '</div>');
        }
        const contr = bl.conocimiento.contradicciones_entre_modelos || [];
        if (DET && contr.length){
          c += '<div style="font:400 11px/1.6 ' + F + ';color:' + C.mutedL + ';margin-top:4px">Contradicciones entre modelos:</div>';
          contr.slice(0,3).forEach(x => c += '<div style="font:400 11px/1.6 ' + F + ';color:' + C.mutedL + '">\u00b7 ' + esc(x) + '</div>');
        }
        const sc = bl.conocimiento.servicios_correctos || [];
        const se = bl.conocimiento.servicios_erroneos || [];
        if (sc.length || se.length){
          c += '<div style="margin:8px 0">' +
            sc.slice(0,6).map(a => '<span style="display:inline-block;margin:0 5px 5px 0;padding:3px 9px;border-radius:99px;background:' + C.okSoft + ';color:' + C.ok + ';font:600 10px ' + F + '">' + esc(a) + '</span>').join('') +
            se.slice(0,6).map(a => '<span style="display:inline-block;margin:0 5px 5px 0;padding:3px 9px;border-radius:99px;background:' + C.errSoft + ';color:' + C.err + ';font:600 10px ' + F + '">' + esc(a) + '</span>').join('') +
            '</div>' + (DET ? '<div style="font:400 10px ' + F + ';color:' + C.mutedL + '">Verde: servicios que la IA te atribuye bien. Rojo: los que te atribuye por error.</div>' : '');
        }
        const sau = bl.conocimiento.servicios_ausentes || [];
        if (sau.length) c += metrica('Servicios que la IA no capta', 'warning', String(sau.length), det(sau.join(' \u00b7 ')));
      }
      if (k === 'reputacion' && bl.reputacion){
        const pol = g(bl.reputacion,'polaridad_global');
        if (typeof pol === 'number') c += metrica('Polaridad global', pol>=0.3?'ok' : pol>=-0.2?'warning':'error', (pol>0?'+':'') + pol.toFixed(2), null);
        const spm = bl.reputacion.sentimiento_por_modelo;
        if (spm && typeof spm === 'object') MODELOS.forEach(([mk,ml]) => {
          const s = spm[mk];
          if (s && typeof s.polaridad === 'number') c += metrica(ml, s.polaridad>=0.3?'ok' : s.polaridad>=-0.2?'warning':'error', (s.polaridad>0?'+':'') + s.polaridad.toFixed(2), det(s.tono));
        });
        const df = bl.reputacion.defensa_de_marca;
        if (df) c += metrica('Defensa ante objeci\u00f3n', df.estado, df.deriva_a_competidor ? 'Deriva a ' + df.deriva_a_competidor : '', det(df.detalle));
        const obj = bl.reputacion.objeciones_detectadas || [];
        if (obj.length){
          c += metrica('Objeciones detectadas', 'warning', String(obj.length), '');
          if (DET) obj.slice(0,5).forEach(x => c += '<div style="font:400 11px/1.6 ' + F + ';color:' + C.mutedL + '">\u00b7 ' + esc(x.objecion) + (x.modelo?' \u2014 ' + esc(x.modelo):'') + (x.respaldada_por_fuente?' (con fuente real)':' (sin fuente)') + '</div>');
        }
        const rr = bl.reputacion.riesgos_reputacionales || [];
        if (DET && rr.length){
          c += '<div style="font:400 11px/1.6 ' + F + ';color:' + C.mutedL + ';margin-top:4px">Riesgos reputacionales:</div>';
          rr.slice(0,5).forEach(x => c += '<div style="font:400 11px/1.6 ' + F + ';color:' + C.mutedL + '">\u00b7 ' + esc(x) + '</div>');
        }
        const neg = bl.reputacion.atributos_negativos || [];
        if (neg.length) c += '<div style="margin:8px 0">' + neg.slice(0,6).map(a => '<span style="display:inline-block;margin:0 5px 5px 0;padding:3px 9px;border-radius:99px;background:' + C.errSoft + ';color:' + C.err + ';font:600 10px ' + F + '">' + esc(a) + '</span>').join('') + '</div>';
        const fn = bl.reputacion.fuentes_negativas || [];
        if (fn.length) c += metrica('Fuentes negativas', 'error', String(fn.length), det([...new Set(fn.map(u => String(u).replace(/^https?:\/\//,'').replace(/^www\./,'').split('/')[0]))].slice(0,5).join(' \u00b7 ')));
      }
      if (k === 'competitivo' && bl.competitivo){
        const ine = bl.competitivo.competidores_inesperados || [];
        if (ine.length) c += metrica('Rivales que no esperabas', 'warning', String(ine.length), ine.join(' \u00b7 '));
      }
      B += tarjeta(eye, tit, null, c);
    });

    if (inf.divergencia_parametrico_grounded)
      B += panel('Memoria vs. web actual', 'Lo que el modelo recuerda no es lo que la web dice hoy',
        '<div style="font:400 13px/1.7 ' + F + ';color:' + C.muted + '">' + esc(inf.divergencia_parametrico_grounded) + '</div>');

    const fs = r.fuentes_sector;
    if (fs && fs.disponible){
      let c = metrica('Tu dominio entre las fuentes citadas', fs.cliente_citado?'ok':'error', fs.cliente_citado?'Citado':'No citado',
        fs.cliente_citado ? null : 'El motor respondi\u00f3 a las preguntas de tu sector sin citar tu web ni una vez. Estos son los dominios donde s\u00ed est\u00e1 buscando.');
      c += '<div>' + (fs.dominios_citados||[]).slice(0,12).map(x =>
        '<span style="display:inline-block;margin:0 6px 6px 0;padding:4px 10px;border:1px solid ' + C.border + ';border-radius:99px;background:' + C.bg + ';font:500 11px ' + F + ';color:' + C.muted + '">' + esc(x.dominio + ' \u00d7' + x.veces) + '</span>').join('') + '</div>';
      B += panel('D\u00f3nde busca el motor', 'Las fuentes que la IA consulta para tu sector', c);
    }

    // ===== DONDE GANAR PRESENCIA (determinista + descubierto por el agente) =====
    const rh = r.recomendaciones_huella;
    if (rh && rh.disponible){
      const RC = [['directorios','Directorios y rese\u00f1as'],['listas_sector','Listas y rankings del sector'],
                  ['medios','Medios y prensa'],['foros','Foros y comunidades'],['otros','Otros portales del sector']];
      let c = '<div style="font:400 13px/1.7 ' + F + ';color:' + C.muted + ';margin-bottom:12px">' + esc(rh.resumen || '') + '</div>';
      RC.forEach(([k, lab]) => {
        const arr = rh[k] || [];
        if (!arr.length) return;
        c += '<div style="font:700 10px ' + F + ';letter-spacing:1.2px;text-transform:uppercase;color:' + C.mutedL + ';margin:14px 0 8px;padding-bottom:6px;border-bottom:1px solid ' + C.border + '">' + esc(lab) + '</div>';
        arr.forEach(x => {
          const pr = String(x.prioridad || 'media').toLowerCase();
          const prBg = pr === 'alta' ? C.accentSoft : pr === 'baja' ? C.bg : C.warnSoft;
          const prFg = pr === 'alta' ? C.accentDark || C.accent : pr === 'baja' ? C.mutedL : C.warn;
          const src = x.fuente === 'citado'
            ? '<span style="display:inline-block;background:' + C.dark + ';color:#fff;font:700 8px ' + F + ';letter-spacing:0.6px;text-transform:uppercase;padding:2px 7px;border-radius:99px;margin-left:8px">La IA ya lo cita</span>'
            : x.fuente === 'descubierto'
            ? '<span style="display:inline-block;background:' + C.accentSoft + ';color:' + C.accent + ';font:700 8px ' + F + ';letter-spacing:0.6px;text-transform:uppercase;padding:2px 7px;border-radius:99px;margin-left:8px">Descubierto</span>' : '';
          const nombre = x.url
            ? '<a href="' + esc(x.url) + '" style="color:' + C.text + ';text-decoration:none;font-weight:700">' + esc(x.sitio) + '</a>'
            : '<span style="font-weight:700;color:' + C.text + '">' + esc(x.sitio) + '</span>';
          c += '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-bottom:1px solid ' + C.border + '"><tr>' +
            '<td style="padding:9px 0;font:400 13px/1.5 ' + F + '">' + nombre + src +
              (x.motivo ? '<div style="font:400 11px/1.6 ' + F + ';color:' + C.mutedL + ';margin-top:2px">' + esc(x.motivo) + '</div>' : '') + '</td>' +
            '<td align="right" valign="top" style="padding:9px 0;white-space:nowrap"><span style="display:inline-block;background:' + prBg + ';color:' + prFg + ';font:700 9px ' + F + ';letter-spacing:0.6px;text-transform:uppercase;padding:4px 10px;border-radius:99px">' + esc(pr) + '</span></td>' +
          '</tr></table>';
        });
      });
      B += panel('Plan de enlaces', 'D\u00f3nde ganar presencia para que la IA te cite', c);
    }

    const gaps = inf.gaps_criticos || [];
    if (gaps.length){
      let c = gaps.map(x => '<div style="padding:11px 0;border-bottom:1px solid ' + C.border + '">' +
        '<div style="font:700 13px/1.45 ' + F + ';color:' + C.err + ';margin-bottom:3px">' + esc(x.gap || '') + '</div>' +
        (x.evidencia ? '<div style="font:400 12px/1.6 ' + F + ';color:' + C.muted + '">Evidencia: ' + esc(x.evidencia) + '</div>' : '') +
        (x.impacto ? '<div style="font:400 12px/1.6 ' + F + ';color:' + C.muted + '">Impacto: ' + esc(x.impacto) + '</div>' : '') + '</div>').join('');
      const op = inf.oportunidades || [];
      if (op.length) c += '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:16px;border-collapse:separate"><tr><td bgcolor="' + C.okSoft + '" style="background-color:' + C.okSoft + ';border:1px solid #CDE6DA;border-radius:8px;padding:16px 18px">' +
        '<div style="font:700 10px ' + F + ';letter-spacing:1.4px;text-transform:uppercase;color:' + C.ok + ';margin-bottom:8px">Oportunidades</div>' +
        '<ul style="margin:0;padding-left:18px">' + op.map(o => '<li style="font:400 12px/1.7 ' + F + ';color:' + C.text + '">' + esc(o) + '</li>').join('') + '</ul></td></tr></table>';
      B += panel('Los agujeros', 'Gaps cr\u00edticos', c);
    }

    const citas = inf.citas_destacadas || [];
    if (citas.length) B += panel('Textual', 'Lo que la IA dice de ti, literalmente', citas.map(x =>
      '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:14px"><tr>' +
      '<td width="3" bgcolor="' + C.accent + '" style="width:3px;background-color:' + C.accent + ';font-size:0;line-height:0">&nbsp;</td>' +
      '<td style="padding-left:14px">' +
        '<div style="font:400 14px/1.6 ' + F + ';color:' + C.text + '">&ldquo;' + esc(x.cita || '') + '&rdquo;</div>' +
        '<div style="font:600 10px ' + F + ';letter-spacing:0.8px;text-transform:uppercase;color:' + C.mutedL + ';margin-top:6px">' + esc([x.modelo, x.pregunta].filter(Boolean).join(' \u00b7 ')) + '</div>' +
      '</td></tr></table>').join(''));

    const plan = inf.plan_accion_llm || [];
    if (plan.length) B += panel('Qu\u00e9 hacer', 'Plan para ganar visibilidad en IA', plan.map((a,i) => accion(a,i)).join(''));

    const kpis = inf.kpis_seguimiento || [];
    if (kpis.length) B += panel('Medici\u00f3n', 'KPIs para la pr\u00f3xima auditor\u00eda',
      tablaDatos(['KPI','Hoy','Objetivo'], kpis.map(k => [k.kpi || '', k.valor_actual || '\u2013', k.objetivo || '\u2013'])));
  }


  const sin = r.sintesis || {};
  const pg = sin.plan_accion || [];
  if (pg.length || (sin.quick_wins || []).length){
    let c6 = pg.map((a,i) => accion(a,i)).join('');
    const qw = sin.quick_wins || [];
    if (qw.length) c6 += '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:18px;border-collapse:separate"><tr><td bgcolor="' + C.okSoft + '" style="background-color:' + C.okSoft + ';border:1px solid #CDE6DA;border-radius:8px;padding:16px 18px">' +
      '<div style="font:700 10px ' + F + ';letter-spacing:1.4px;text-transform:uppercase;color:' + C.ok + ';margin-bottom:8px">Quick wins \u00b7 menos de un d\u00eda</div>' +
      '<ul style="margin:0;padding-left:18px">' + qw.map(x => '<li style="font:400 12px/1.7 ' + F + ';color:' + C.text + '">' + esc(x) + '</li>').join('') + '</ul></td></tr></table>';
    B += panel('Prioridades', 'Plan de acci\u00f3n global', c6);
  }

  B += '<div style="text-align:center;margin-top:34px;padding-top:22px;border-top:1px solid ' + C.border + ';font:400 11px/1.7 ' + F + ';color:' + C.mutedL + '">' +
    '<b style="font:800 13px ' + F + ';color:' + C.text + ';letter-spacing:-0.3px">brandevs</b> \u00b7 GEOpulse<br>' +
    'ChatGPT, Claude y Gemini responden con conocimiento propio; Perplexity busca en la web en tiempo real.<br>' +
    'Los resultados son una muestra puntual: los modelos var\u00edan entre ejecuciones.</div>';

  const pre = 'GEO Score ' + (score === null ? 's/d' : score) + '/100 \u00b7 ' + (g(inf,'veredicto_visibilidad.nivel') || 'auditor\u00eda completada') + ' \u00b7 ' + (meta.brand || '');
  return '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<meta name="x-apple-disable-message-reformatting">' +
    '<title>Informe GEOpulse</title></head>' +
    '<body style="margin:0;padding:0;background:' + C.bg + ';-webkit-text-size-adjust:100%">' +
    '<div style="display:none;max-height:0;overflow:hidden;opacity:0">' + esc(pre) + '</div>' +
    '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="' + C.bg + '" style="background-color:' + C.bg + '"><tr>' +
    '<td align="center" style="padding:28px 12px 44px">' +
    '<table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0" style="width:640px;max-width:100%">' +
    '<tr><td>' + B + '</td></tr></table></td></tr></table></body></html>';
}

// ===== SALIDA PARA PDF: informe COMPLETO, sin recorte de tamaño (lo renderiza Chromium/Gotenberg) =====
// El límite de Gmail ya no aplica: el informe va como PDF adjunto, no como cuerpo del correo.
let htmlPdf = construir({ maxCompetidores: 40, detalles: true });

// Inyectar CSS de impresión (A4, márgenes, evitar cortar tarjetas a mitad de página)
const PRINT_CSS = '<style>'
  + '@page{size:A4;margin:14mm 12mm}'
  + '@media print{'
  +   'table,tr,td{page-break-inside:avoid}'
  +   'a{color:' + C.text + ';text-decoration:none}'
  + '}'
  + 'body{-webkit-print-color-adjust:exact;print-color-adjust:exact}'
  + '</style>';
htmlPdf = htmlPdf.replace('</head>', PRINT_CSS + '</head>');

const inf2 = r.informe_llm || {};
const score2 = g(r,'score.global');
const nombreArchivo = 'Informe-GEOpulse-' + String(meta.brand || 'marca').replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-|-$/g, '') + '.pdf';

// ===== CUERPO DEL EMAIL: mensaje corto de acompañamiento (el detalle va en el PDF adjunto) =====
const bodyEmail = '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">'
  + '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
  + '<body style="margin:0;padding:0;background:' + C.bg + '">'
  + '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="' + C.bg + '"><tr>'
  + '<td align="center" style="padding:32px 16px">'
  + '<table role="presentation" width="520" cellpadding="0" cellspacing="0" border="0" style="width:520px;max-width:100%;background:' + C.surf + ';border:1px solid ' + C.border + ';border-radius:14px">'
  + '<tr><td style="padding:34px 34px 10px">'
  + '<div style="font:800 22px ' + F + ';color:' + C.text + '">GEOpulse</div>'
  + '<div style="font:600 12px ' + F + ';letter-spacing:1px;text-transform:uppercase;color:' + C.accent + ';margin-top:4px">Auditoría de visibilidad en IA</div>'
  + '</td></tr>'
  + '<tr><td style="padding:14px 34px 8px;font:400 15px/1.7 ' + F + ';color:' + C.muted + '">'
  + 'Hola,<br><br>Ya está listo el informe GEOpulse de <b style="color:' + C.text + '">' + esc(meta.brand || 'tu marca') + '</b>'
  + (meta.geo ? ' para el mercado de ' + esc(meta.geo.texto) : '') + '. Lo tienes completo en el <b style="color:' + C.text + '">PDF adjunto</b>.'
  + '</td></tr>'
  + '<tr><td style="padding:18px 34px 6px">'
  + '<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="background:' + C.dark + ';border-radius:12px"><tr>'
  + '<td style="padding:18px 26px">'
  + '<span style="font:800 40px ' + F + ';color:#fff">' + (score2 === null ? 's/d' : score2) + '</span>'
  + '<span style="font:600 13px ' + F + ';color:' + C.onDarkMuted + '"> / 100 · GEO Score</span><br>'
  + '<span style="font:600 13px ' + F + ';color:#fff">Visibilidad en IA: ' + esc(g(inf2,'veredicto_visibilidad.nivel') || 's/d') + '</span>'
  + '</td></tr></table>'
  + '</td></tr>'
  + '<tr><td style="padding:16px 34px 34px;font:400 13px/1.7 ' + F + ';color:' + C.mutedL + '">'
  + 'Recuerda: los resultados son una muestra puntual y los modelos varían entre ejecuciones.<br><br>— BranDevs · GEOpulse'
  + '</td></tr></table></td></tr></table></body></html>';

const texto = [
  'INFORME GEOPULSE - ' + (meta.brand || ''),
  meta.domain || '',
  meta.geo ? 'Mercado: ' + meta.geo.texto : '',
  '',
  'GEO SCORE: ' + (score2 === null ? 's/d' : score2) + '/100',
  'VISIBILIDAD EN IA: ' + (g(inf2,'veredicto_visibilidad.nivel') || 's/d'),
  '',
  'Tienes el informe completo en el PDF adjunto.',
  '',
  '- BranDevs / GEOpulse'
].join('\n');

return [{
  json: {
    to: meta.email,
    subject: 'Informe GEOpulse \u00b7 ' + (meta.brand || 'tu marca') + ' \u00b7 GEO Score ' + (score2 === null ? 's/d' : score2) + '/100',
    bodyEmail,
    text: texto,
    nombreArchivo,
    _debug: { bytes_pdf_html: htmlPdf.length }
  },
  // Gotenberg exige el HTML como un fichero llamado index.html: lo entregamos como binario.
  binary: {
    index_html: {
      data: Buffer.from(htmlPdf, 'utf8').toString('base64'),
      mimeType: 'text/html',
      fileName: 'index.html'
    }
  }
}];
"""

CODE_RECO = r"""// RECOMENDADOR DE SITIOS — 100% determinista, cero LLM.
// Cruza los dominios que el motor cita REALMENTE para el sector (fuentes_sector) con la
// huella verificada (donde la marca YA esta). Lo que el motor consulta y la marca no tiene = oportunidad.
const r = $input.first().json;
const norm = $('Normalizar Input').first().json;
const fs = r.fuentes_sector || {};
const hue = r.huella_digital || {};

const hostOf = (u) => { const m = String(u||'').match(/^https?:\/\/([^\/:?#]+)/i); return m ? m[1].toLowerCase().replace(/^www\./,'') : (typeof u==='string' ? u.toLowerCase().replace(/^www\./,'').split('/')[0] : null); };
const ownHost = hostOf(norm.domain);

// --- 1. Donde YA esta la marca (para NO recomendarlo): fuentes verificadas de la huella + dominio propio ---
const yaEsta = new Set([ownHost]);
for (const k of ['presencia_foros','medios','directorios','listas_sector']) {
  const o = hue[k];
  if (o && Array.isArray(o.fuentes)) o.fuentes.forEach(u => { const h = hostOf(u); if (h) yaEsta.add(h); });
}
// urls del propio cliente que el motor cito (tambien "ya esta")
if (Array.isArray(fs.urls_cliente)) fs.urls_cliente.forEach(u => { const h = hostOf(u); if (h) yaEsta.add(h); });

// --- 2. Clasificador de dominios por tipo de oportunidad ---
const DIRECTORIOS = /clutch\.co|goodfirms|sortlist|designrush|g2\.com|capterra|trustpilot|yelp\.|paginasamarillas|europages|expansion.*empresas|axesor|einforma|trustradius|glassdoor|indeed|manta\.com|crunchbase|ondirectory|hotfrog|cylex|infobel/i;
const MEDIOS = /news|noticias|prensa|diario|periodic|revista|magazine|blog|forbes|techcrunch|businessinsider|europapress|expansion|cincodias|elpais|elmundo|xataka|emprendedores|marketingdirecto|puromarketing|reasonwhy|marketing4ecommerce|ecommerce-news|muypymes|pymesyautonomos|genbeta/i;
const LISTAS = /mejores|best|top\d|top-|ranking|comparativa|listado|guia|guide|awards|premios/i;
const FOROS = /reddit\.com|quora\.|stackexchange|stackoverflow|foro|forum|discourse|forocoches|domestika.*foros/i;
// Ruido que nunca es una oportunidad de citacion (buscadores, redes, wikis, plataformas grandes)
const RUIDO = /^(google\.|bing\.|duckduckgo|youtube\.|facebook\.|instagram\.|twitter\.|x\.com|linkedin\.|tiktok\.|pinterest\.|wikipedia\.|wikidata\.|amazon\.|maps\.|translate\.|blogspot\.|wordpress\.com|medium\.com|github\.|gravatar)/i;

function clasificar(dom, contexto){
  if (RUIDO.test(dom)) return null;
  const t = dom + ' ' + (contexto || '');
  if (DIRECTORIOS.test(dom)) return 'directorios';
  if (LISTAS.test(t)) return 'listas_sector';
  if (MEDIOS.test(dom)) return 'medios';
  if (FOROS.test(dom)) return 'foros';
  return 'otros';   // dominio del sector sin tipo obvio: sigue siendo una oportunidad
}

// --- 3. Construir candidatos a partir de los dominios que el motor cita para el sector ---
const citados = Array.isArray(fs.dominios_citados) ? fs.dominios_citados : [];
const reco = { directorios: [], medios: [], listas_sector: [], foros: [], otros: [] };
const vistos = new Set();

for (const c of citados) {
  const dom = hostOf(c.dominio);
  if (!dom || dom === ownHost) continue;
  if (yaEsta.has(dom)) continue;              // ya esta dada de alta: se excluye
  if (vistos.has(dom)) continue;
  vistos.add(dom);
  const cat = clasificar(dom, '');
  if (cat === null) continue;                  // solo el RUIDO explicito se descarta (buscadores, redes)
  // Prioridad: cuantas mas veces lo cita el motor, mas alta (es donde mas mira para el sector)
  const veces = c.veces || 1;
  const prioridad = veces >= 5 ? 'alta' : veces >= 2 ? 'media' : 'baja';
  reco[cat].push({
    sitio: dom,
    veces_citado: veces,
    prioridad,
    motivo: 'El motor de IA cita este dominio ' + veces + (veces === 1 ? ' vez' : ' veces') + ' al responder sobre tu sector, pero tu marca no aparece en él.'
  });
}

// --- 4. Ordenar por prioridad y limitar a 8 por categoria ---
const ordenar = (arr) => arr.sort((a,b) => b.veces_citado - a.veces_citado).slice(0, 8);
for (const k of Object.keys(reco)) reco[k] = ordenar(reco[k]);

// --- 5. Resumen accionable ---
const totalReco = reco.directorios.length + reco.medios.length + reco.listas_sector.length + reco.foros.length + reco.otros.length;
const disponible = totalReco > 0;

let resumen;
if (!fs.disponible) {
  resumen = 'El motor de búsqueda no devolvió fuentes citadas en esta ejecución, así que no hay datos para recomendar sitios concretos. Repite la auditoría o revisa la conectividad de Perplexity.';
} else if (!disponible) {
  resumen = 'Buena señal: de los ' + citados.length + ' dominios que el motor cita para tu sector, tu marca ya está presente en los relevantes. No hay huecos obvios entre las fuentes que la IA consulta.';
} else {
  const partes = [];
  if (reco.directorios.length) partes.push(reco.directorios.length + ' directorios');
  if (reco.listas_sector.length) partes.push(reco.listas_sector.length + ' listas/rankings');
  if (reco.medios.length) partes.push(reco.medios.length + ' medios');
  if (reco.foros.length) partes.push(reco.foros.length + ' foros');
  if (reco.otros.length) partes.push(reco.otros.length + ' otros portales del sector');
  resumen = 'Estos son sitios que el motor de IA consulta para responder sobre tu sector y en los que tu marca todavía no aparece. Ganar una cita o un enlace en ellos es la vía más directa para que la IA empiece a mencionarte: ' + partes.join(', ') + '.';
}

return [{ json: {
  ...r,
  recomendaciones_huella: {
    disponible,
    total: totalReco,
    resumen,
    directorios: reco.directorios,
    medios: reco.medios,
    listas_sector: reco.listas_sector,
    foros: reco.foros,
    otros: reco.otros,
    ya_presente_en: [...yaEsta].filter(h => h !== ownHost).slice(0, 20)
  }
}}];
"""

CODE_FUSIONAR = r"""// FUSIONA las recomendaciones deterministas (motor ya las cita) con las descubiertas por el agente.
// El determinista es el suelo fiable; el agente aporta descubrimiento. Se deduplica por dominio.
const det = ($('Recomendar Sitios').first().json.recomendaciones_huella) || { disponible: false, directorios: [], medios: [], listas_sector: [], foros: [], otros: [], ya_presente_en: [] };
const rep = $('Recomendar Sitios').first().json;   // arrastra todo el reporte

// --- Parsear la salida del agente de descubrimiento (Responses API) ---
let agentOut = { recomendaciones: [], resumen: '' };
try {
  const j = $input.first().json;
  // La Responses API mete el texto en output[].content[].text; parseo defensivo
  let texto = '';
  if (typeof j.output_text === 'string') texto = j.output_text;
  else if (Array.isArray(j.output)) {
    for (const o of j.output) {
      const cont = o.content || [];
      for (const c of cont) if (c.type === 'output_text' && c.text) texto += c.text;
    }
  } else if (typeof j === 'string') texto = j;
  texto = texto.replace(/```json|```/g, '').trim();
  const m = texto.match(/\{[\s\S]*\}/);
  if (m) agentOut = JSON.parse(m[0]);
} catch (e) { agentOut = { recomendaciones: [], resumen: '', _parse_error: true }; }

const hostOf = (u) => { const m = String(u||'').match(/^https?:\/\/([^\/:?#]+)/i); return m ? m[1].toLowerCase().replace(/^www\./,'') : (typeof u==='string' ? u.toLowerCase().replace(/^www\./,'').split('/')[0] : null); };
// Clave de identidad = "marca de dominio": sin subdominios ni TLD.
// Asi es.sortlist.com, www.sortlist.com y sortlist.es cuentan como EL MISMO sitio (Sortlist),
// evitando recomendar variantes de un directorio donde la marca ya aparece.
const SUFIJOS = /\.(com|net|org|io|co|es|eu|info|biz|us|uk|de|fr|it|pt|mx|ar|cl|pe)$/i;
const marcaDom = (u) => {
  const h = hostOf(u);
  if (!h) return null;
  const sinTld = h.replace(SUFIJOS, '').replace(/\.(co|com)$/i, '');
  const partes = sinTld.split('.');
  return partes[partes.length - 1] || sinTld;
};
// --- Dominios ya presentes en la recomendacion determinista (para no duplicar) ---
const yaEnLista = new Set();
for (const k of ['directorios','medios','listas_sector','foros','otros']) {
  (det[k] || []).forEach(x => { const m = marcaDom(x.url || x.sitio); if (m) yaEnLista.add(m); });
}
(det.ya_presente_en || []).forEach(h => { const m = marcaDom('http://' + String(h)); if (m) yaEnLista.add(m); });

// --- Mapear categorias del agente a las del frontend ---
const CATMAP = { directorio:'directorios', nicho:'directorios', medio:'medios', lista:'listas_sector', comunidad:'foros', foro:'foros' };

// --- Construir el resultado fusionado, arrancando de las deterministas (marcadas "citado") ---
const out = { directorios: [], medios: [], listas_sector: [], foros: [], otros: [] };
for (const k of Object.keys(out)) {
  out[k] = (det[k] || []).map(x => ({ ...x, fuente: 'citado' }));
}

// --- Añadir las descubiertas por el agente, sin duplicar ---
let añadidas = 0;
for (const rec of (agentOut.recomendaciones || [])) {
  const sitio = hostOf(rec.url || rec.sitio) || String(rec.sitio || '').toLowerCase().replace(/^www\./,'');
  const marca = marcaDom(rec.url || rec.sitio) || sitio;
  if (!sitio || !marca) continue;
  if (yaEnLista.has(marca)) continue;   // ya está (determinista, huella o variante del mismo dominio)
  yaEnLista.add(marca);
  const cat = CATMAP[String(rec.categoria || '').toLowerCase()] || 'otros';
  const pr = ['alta','media','baja'].includes(String(rec.prioridad||'').toLowerCase()) ? rec.prioridad.toLowerCase() : 'media';
  out[cat].push({
    sitio,
    url: rec.url || null,
    prioridad: pr,
    motivo: rec.por_que || rec.motivo || 'Directorio o medio relevante para tu sector donde aún no apareces.',
    fuente: 'descubierto'
  });
  añadidas++;
}

// Ordenar cada categoria: primero prioridad alta, y dentro los "citado" (dato duro) antes que "descubierto"
const ordPri = { alta: 0, media: 1, baja: 2 };
const ordFte = { citado: 0, descubierto: 1 };
for (const k of Object.keys(out)) {
  out[k].sort((a, b) => (ordPri[a.prioridad] - ordPri[b.prioridad]) || (ordFte[a.fuente] - ordFte[b.fuente]));
  out[k] = out[k].slice(0, 8);   // tope de 8 por categoria
}

const total = out.directorios.length + out.medios.length + out.listas_sector.length + out.foros.length + out.otros.length;
const disponible = total > 0;
const citadas = ['directorios','medios','listas_sector','foros','otros'].reduce((n,k) => n + out[k].filter(x=>x.fuente==='citado').length, 0);
const descubiertas = total - citadas;

let resumen;
if (!disponible) {
  resumen = 'No se han encontrado sitios claros donde ganar presencia en esta ejecución. Repite la auditoría o revisa la conectividad del agente de descubrimiento.';
} else {
  const partes = [];
  if (out.directorios.length) partes.push(out.directorios.length + ' directorios');
  if (out.listas_sector.length) partes.push(out.listas_sector.length + ' listas/rankings');
  if (out.medios.length) partes.push(out.medios.length + ' medios');
  if (out.foros.length) partes.push(out.foros.length + ' foros/comunidades');
  if (out.otros.length) partes.push(out.otros.length + ' otros');
  resumen = 'Sitios donde ganar citaciones y enlaces para que la IA empiece a mencionarte: ' + partes.join(', ') + '. ' +
    (citadas ? citadas + ' los cita ya el motor para tu sector (dato duro)' : '') +
    (citadas && descubiertas ? '; ' : '') +
    (descubiertas ? descubiertas + ' descubiertos por búsqueda específica de tu sector' : '') + '.';
}

return [{ json: {
  ...rep,
  recomendaciones_huella: {
    disponible,
    total,
    citadas,
    descubiertas,
    resumen,
    directorios: out.directorios,
    medios: out.medios,
    listas_sector: out.listas_sector,
    foros: out.foros,
    otros: out.otros,
    ya_presente_en: det.ya_presente_en || []
  }
} }];
"""

# ============================================================
# HELPERS
# ============================================================

def http_get(name, url_expr, pos, timeout=15000, on_error=None, ua=None):
    # responseFormat text + outputPropertyName body: contrato explicito del campo de contenido
    # (n8n 2.x con autodeteccion pone el texto en `data`; asi queda siempre en `body`)
    params = {"url": url_expr, "options": {"timeout": timeout,
              "response": {"response": {"fullResponse": True, "neverError": True,
                                        "responseFormat": "text", "outputPropertyName": "body"}}}}
    if ua:
        params["sendHeaders"] = True
        params["headerParameters"] = {"parameters": [{"name": "User-Agent", "value": ua}]}
    node = {"parameters": params, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
            "position": pos, "name": name}
    if on_error:
        node["onError"] = on_error
    return node

def code(name, js, pos):
    return {"parameters": {"jsCode": js}, "type": "n8n-nodes-base.code",
            "typeVersion": 2, "position": pos, "name": name}

def openai_agent(name, model, system_prompt, user_expr, pos, temperature=None, max_tokens=None):
    # gpt-5.4-mini es un modelo de razonamiento: solo admite temperature=1 (el valor por defecto)
    # y rechaza max_tokens. Fijamos 1 explicitamente para que n8n no envie otro valor,
    # y omitimos maxTokens (el modelo usa su maximo de salida: 128K).
    opts = {"temperature": 1}
    return {"parameters": {
        "modelId": {"__rl": True, "value": model, "mode": "list", "cachedResultName": model},
        "messages": {"values": [{"content": system_prompt, "role": "system"}, {"content": user_expr, "role": "user"}]},
        "jsonOutput": True, "options": opts
    }, "type": "@n8n/n8n-nodes-langchain.openAi", "typeVersion": 1.8, "position": pos, "name": name}

def model_openai(name, pos):
    """Sonda a gpt-5.4-mini via HTTP (items concurrentes).
    SIN temperature: los modelos de razonamiento de OpenAI la rechazan (400)."""
    return {"parameters": {
        "method": "POST", "url": "https://api.openai.com/v1/chat/completions",
        "authentication": "predefinedCredentialType", "nodeCredentialType": "openAiApi",
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ model: 'gpt-5.4-mini', messages: [{ role: 'user', content: $json.prompt }] }) }}",
        "options": {"timeout": 90000, "response": {"response": {"fullResponse": True, "neverError": True}}}
    }, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
        "onError": "continueRegularOutput", "position": pos, "name": name}

def model_anthropic(name, pos):
    return {"parameters": {
        "method": "POST", "url": "https://api.anthropic.com/v1/messages",
        "authentication": "predefinedCredentialType", "nodeCredentialType": "anthropicApi",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "anthropic-version", "value": "2023-06-01"}]},
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ model: 'claude-sonnet-4-6', max_tokens: 1200, temperature: 0.4, messages: [{ role: 'user', content: $json.prompt }] }) }}",
        "options": {"timeout": 90000, "response": {"response": {"fullResponse": True, "neverError": True}}}
    }, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
        "onError": "continueRegularOutput", "position": pos, "name": name}

def model_perplexity(name, pos):
    # web_search_options.user_location: contrato verificado (country ISO-2 + region libre)
    body = ("={{ JSON.stringify({ model: 'sonar', messages: [{ role: 'user', content: $json.prompt }], "
            "web_search_options: { search_context_size: 'medium', "
            "user_location: $('Normalizar Input').first().json.geo.user_location } }) }}")
    return {"parameters": {
        "method": "POST", "url": "https://api.perplexity.ai/chat/completions",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendBody": True, "specifyBody": "json",
        "jsonBody": body,
        "options": {"timeout": 90000, "response": {"response": {"fullResponse": True, "neverError": True}}}
    }, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
        "onError": "continueRegularOutput", "position": pos, "name": name}

def model_gemini(name, pos):
    # Gemini via API de Google: cuerpo contents/parts, respuesta en candidates[].content.parts[].text.
    # Auth: Header Auth generica con header 'x-goog-api-key' = clave de Gemini.
    return {"parameters": {
        "method": "POST",
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
        "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ contents: [{ parts: [{ text: $json.prompt }] }], generationConfig: { temperature: 0.4, maxOutputTokens: 1600, thinkingConfig: { thinkingBudget: 0 } } }) }}",
        "options": {"timeout": 90000, "response": {"response": {"fullResponse": True, "neverError": True}}}
    }, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
        "onError": "continueRegularOutput", "position": pos, "name": name}

def merge(name, inputs, pos):
    return {"parameters": {"mode": "append", "numberInputs": inputs},
            "type": "n8n-nodes-base.merge", "typeVersion": 3, "position": pos, "name": name}

def sticky(content, pos, w, h, color=4):
    return {"parameters": {"content": content, "width": w, "height": h, "color": color},
            "type": "n8n-nodes-base.stickyNote", "typeVersion": 1, "position": pos,
            "name": "Nota " + content.split("\n")[0].replace("#", "").strip()}

# ============================================================
# CONSTRUCCIÓN
# ============================================================

C = "$('Consolidar Señales Web').first().json"
N = "$('Normalizar Input').first().json"

nodes = []
connections = {}

def connect(src, dst, out_idx=0, in_idx=0):
    c = connections.setdefault(src, {"main": []})
    while len(c["main"]) <= out_idx:
        c["main"].append([])
    c["main"][out_idx].append({"node": dst, "type": "main", "index": in_idx})

def chain(names):
    for a, b in zip(names, names[1:]):
        connect(a, b)

# --- Capa técnica ---
nodes.append({"parameters": {"httpMethod": "POST", "path": "geopulse-audit",
              "responseMode": "responseNode", "options": {}},
              "type": "n8n-nodes-base.webhook", "typeVersion": 2,
              "position": [-220, 300], "name": "Webhook GEOpulse"})
nodes.append(code("Normalizar Input", CODE_NORMALIZAR, [0, 300]))
nodes.append(http_get("GET llms.txt", "={{ $json.urls.llms_txt }}", [220, 300], ua=UA_CHROME))
nodes.append(http_get("GET robots.txt", "={{ " + N + ".urls.robots_txt }}", [440, 300], ua=UA_CHROME))
nodes.append(http_get("GET sitemap.xml", "={{ " + N + ".urls.sitemap }}", [660, 300], ua=UA_CHROME))
nodes.append(http_get("GET Home", "={{ " + N + ".home_url }}", [880, 300], timeout=20000, ua=UA_CHROME))
nodes.append(code("Preparar Fetch Bots", CODE_PREPARAR_BOTS, [1100, 300]))
nodes.append(http_get("Fetch como Bot IA", "={{ " + N + ".home_url }}", [1320, 300],
                      timeout=20000, on_error="continueRegularOutput", ua="={{ $json.ua }}"))
nodes.append(code("Analizar Acceso Edge", CODE_ANALIZAR_EDGE, [1540, 300]))
nodes.append({"parameters": {
    "method": "POST", "url": "https://validator.schema.org/validate",
    "sendBody": True, "contentType": "form-urlencoded",
    "bodyParameters": {"parameters": [{"name": "url", "value": "={{ " + N + ".home_url }}"}]},
    "options": {"timeout": 15000, "response": {"response": {"fullResponse": True, "neverError": True,
                                                            "responseFormat": "text", "outputPropertyName": "body"}}}},
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "onError": "continueRegularOutput",
    "position": [1760, 300], "name": "Validar Schema.org"})
nodes.append(code("Parsear Validación Schema", CODE_PARSEAR_VALIDACION, [1980, 300]))
nodes.append(code("Elegir Sitemap", CODE_ELEGIR_SITEMAP, [2640, 300]))
nodes.append(http_get("GET Sitemap Páginas", "={{ $json.sitemap_url }}", [2860, 300], ua=UA_CHROME))
nodes.append(code("Seleccionar Landings", CODE_SELECCIONAR_LANDINGS, [3080, 300]))
nodes.append(http_get("GET Landing", "={{ $json.url }}", [3300, 300],
                      on_error="continueRegularOutput", ua=UA_CHROME))
nodes.append(code("Analizar Landings", CODE_ANALIZAR_LANDINGS, [3520, 300]))
nodes.append(code("Consolidar Señales Web", CODE_CONSOLIDAR, [3740, 300]))

# Agentes técnicos
user_a1 = ("={{ JSON.stringify({ domain: " + C + ".domain, home_url: " + C + ".home_url, "
           "pagina_indicada: " + C + ".pagina_es_home ? null : " + C + ".pagina_url, "
           "llms_txt: " + C + ".llms_txt, "
           "schema_existe: " + C + ".schema_existe, jsonld: " + C + ".home.jsonld, "
           # Comprobacion DETERMINISTA de los campos de Organization/LocalBusiness.
           # El agente ya no juzga si un campo esta o no: se lo damos hecho.
           "schema_org_home: " + C + ".schema_org_home, schema_org_sitio: " + C + ".schema_org_sitio, "
           "schema_landings: (" + C + ".landings || []).map(l => ({ url: l.url, tipos: l.schema_tipos, "
           "org: l.schema_org, es_home: !!l.es_home, es_fallback_home: !!l.es_fallback_home })), "
           "validacion_schema_org: $('Parsear Validación Schema').first().json, "
           "sitemap_xml: " + C + ".sitemap_xml }) }}")
nodes.append(openai_agent("Agente 1 - Infraestructura GEO", "gpt-5.4-mini", PROMPT_A1_INFRA, user_a1, [3960, 300]))

user_a2 = ("={{ JSON.stringify({ robots_txt: { status: " + C + ".robots_txt.status, "
           "bots_detectados_por_categoria: " + C + ".robots_txt.bots_detectados_por_categoria, "
           "contenido: " + C + ".robots_txt.contenido }, acceso_edge: " + C + ".acceso_edge, "
           "landings: (" + C + ".landings || []).map(l => ({ url: l.url, status: l.status, title: l.title, headings: l.headings, es_fallback_home: !!l.es_fallback_home })), "
           "home: { status: " + C + ".home.status, url: " + C + ".home.url, meta_robots: " + C + ".home.meta_robots, "
           "x_robots_tag: " + C + ".home.x_robots_tag, canonical: " + C + ".home.canonical, "
           "headings: " + C + ".home.headings, render: " + C + ".home.render, "
           "response_time_ms: " + C + ".home.response_time_ms, word_count: " + C + ".home.word_count } }) }}")
nodes.append(openai_agent("Agente 2 - SEO Técnico", "gpt-5.4-mini", PROMPT_A2_SEO, user_a2, [4180, 300]))

user_a3 = ("={{ JSON.stringify({ keyword: " + N + ".keyword, title: " + C + ".home.title, "
           "meta_description: " + C + ".home.meta_description, headings: " + C + ".home.headings, "
           "texto_extracto: " + C + ".home.texto_extracto, word_count: " + C + ".home.word_count }) }}")
nodes.append(openai_agent("Agente 3 - Contenido y Entidades", "gpt-5.4-mini", PROMPT_A3_CONTENIDO, user_a3, [4400, 300]))

chain(["Webhook GEOpulse", "Normalizar Input", "GET llms.txt", "GET robots.txt", "GET sitemap.xml",
       "GET Home", "Preparar Fetch Bots", "Fetch como Bot IA", "Analizar Acceso Edge",
       "Validar Schema.org", "Parsear Validación Schema",
       "Elegir Sitemap", "GET Sitemap Páginas", "Seleccionar Landings", "GET Landing",
       "Analizar Landings", "Consolidar Señales Web",
       "Agente 1 - Infraestructura GEO", "Agente 2 - SEO Técnico",
       "Agente 3 - Contenido y Entidades"])

# --- LOS 4 AGENTES DE SONDEO (ramas paralelas) ---
EVAL_PROMPTS = {"D1": PROMPT_EVAL_D1, "D2": PROMPT_EVAL_D2, "D3": PROMPT_EVAL_D3, "D4": PROMPT_EVAL_D4}
EVAL_NAMES = {"D1": "Evaluador D1 - Descubrimiento", "D2": "Evaluador D2 - Competitivo",
              "D3": "Evaluador D3 - Conocimiento", "D4": "Evaluador D4 - Reputacion"}
Y = {"D1": -320, "D2": 100, "D3": 520, "D4": 940}

nodes.append(merge("Merge Bloques", 4, [6600, 300]))

for i, dx in enumerate(["D1", "D2", "D3", "D4"]):
    bloque, js = SONDAS[dx]
    y = Y[dx]
    nodes.append(code("Sondas " + dx, js, [4880, y]))
    nodes.append(model_openai(dx + " - ChatGPT", [5120, y - 135]))
    nodes.append(model_anthropic(dx + " - Claude", [5120, y - 45]))
    nodes.append(model_gemini(dx + " - Gemini", [5120, y + 45]))
    nodes.append(model_perplexity(dx + " - Perplexity", [5120, y + 135]))
    nodes.append(merge(dx + " - Merge", 4, [5360, y]))
    nodes.append(code(dx + " - Unir", code_unir(dx, bloque), [5600, y]))

    # Entrada de cada evaluador
    sondas_expr = "$('" + dx + " - Unir').first().json.sondas"
    geo_expr = "geo: " + N + ".geo.texto, "
    if dx == "D3":
        user = ("={{ JSON.stringify({ brand: " + N + ".brand, keyword: " + N + ".keyword, " + geo_expr +
                "sondas: " + sondas_expr + ".map(s => ({ pregunta: s.pregunta, respuestas: s.respuestas })), "
                "datos_verificados: { texto_web: " + C + ".home.texto_extracto.slice(0, 3000), "
                "title: " + C + ".home.title, meta_description: " + C + ".home.meta_description } }) }}")
    elif dx == "D2":
        user = ("={{ JSON.stringify({ brand: " + N + ".brand, keyword: " + N + ".keyword, " + geo_expr +
                "competitors: " + N + ".competitors, "
                "sondas: " + sondas_expr + ".map(s => ({ pregunta: s.pregunta, respuestas: s.respuestas })) }) }}")
    elif dx == "D4":
        user = ("={{ JSON.stringify({ brand: " + N + ".brand, keyword: " + N + ".keyword, " + geo_expr +
                "sondas: " + sondas_expr + " }) }}")
    else:
        user = ("={{ JSON.stringify({ brand: " + N + ".brand, keyword: " + N + ".keyword, " + geo_expr +
                "sondas: " + sondas_expr + ".map(s => ({ pregunta: s.pregunta, respuestas: s.respuestas })) }) }}")

    nodes.append(openai_agent(EVAL_NAMES[dx], "gpt-5.4-mini", EVAL_PROMPTS[dx], user, [5840, y], 0.2, 3000))

    # Cableado de la rama
    connect("Agente 3 - Contenido y Entidades", "Sondas " + dx)
    connect("Sondas " + dx, dx + " - ChatGPT")
    connect("Sondas " + dx, dx + " - Claude")
    connect("Sondas " + dx, dx + " - Gemini")
    connect("Sondas " + dx, dx + " - Perplexity")
    connect(dx + " - ChatGPT", dx + " - Merge", 0, 0)
    connect(dx + " - Claude", dx + " - Merge", 0, 1)
    connect(dx + " - Gemini", dx + " - Merge", 0, 2)
    connect(dx + " - Perplexity", dx + " - Merge", 0, 3)
    connect(dx + " - Merge", dx + " - Unir")
    connect(dx + " - Unir", EVAL_NAMES[dx])
    connect(EVAL_NAMES[dx], "Merge Bloques", 0, i)

# --- Consolidación, informe y cierre ---
nodes.append(code("Consolidar Sondeos", CODE_CONSOLIDAR_SONDEOS, [6840, 300]))
nodes.append(openai_agent("Agente Informe LLM", "gpt-5.4-mini", PROMPT_INFORME,
                          "={{ JSON.stringify($json) }}", [7080, 300], 0.3, 6000))

# SIN user_location: la huella se investiga de forma organica y global.
# La geolocalizacion solo aplica a las sondas LLM (D1-D4 y su Perplexity).
# Si tu cuenta devolviera 400 por la tool, cambia 'web_search' por 'web_search_preview'.
json_body_expr = ("={{ JSON.stringify({ model: 'gpt-5.4-mini', "
                  "tools: [{ type: 'web_search' }], "
                  "input: '" + PROMPT_A5_HUELLA_JS + "'"
                  ".replaceAll('__BRAND__', " + N + ".brand)"
                  ".replaceAll('__DOMAIN__', " + N + ".domain)"
                  ".replaceAll('__KEYWORD__', " + N + ".keyword)"
                  ".replaceAll('__CITACIONES__', JSON.stringify($('Consolidar Sondeos').first().json.fuentes_sector)) }) }}")
nodes.append({"parameters": {
    "method": "POST", "url": "https://api.openai.com/v1/responses",
    "authentication": "predefinedCredentialType", "nodeCredentialType": "openAiApi",
    "sendBody": True, "specifyBody": "json", "jsonBody": json_body_expr,
    "options": {"timeout": 150000}},
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
    "position": [7320, 300], "name": "Agente 5 - Huella Digital (web_search)"})
nodes.append(code("Extraer Huella", CODE_EXTRAER_HUELLA, [7560, 300]))
nodes.append(code("Calcular Score", CODE_SCORE, [7800, 300]))
nodes.append(code("Recomendar Sitios", CODE_RECO, [8040, 300]))

# --- Descubrimiento activo de directorios (agente con web_search, centrado en el SECTOR) ---
# Complementa al determinista: busca directorios/medios de nicho que el sondeo no citó.
# SIN user_location: busca local + internacional; el pais va en el prompt como contexto.
directorios_body = ("={{ JSON.stringify({ model: 'gpt-5.4-mini', "
                    "tools: [{ type: 'web_search' }], "
                    "input: '" + PROMPT_DIRECTORIOS_JS + "'"
                    ".replaceAll('__KEYWORD__', " + N + ".keyword)"
                    ".replaceAll('__PAIS__', " + N + ".geo.texto)"
                    ".replaceAll('__YA_PRESENTE__', JSON.stringify(($json.recomendaciones_huella && $json.recomendaciones_huella.ya_presente_en || []).concat([" + N + ".domain.replace(/^https?:\\/\\//,'').replace(/^www\\./,'')]))) }) }}")
nodes.append({"parameters": {
    "method": "POST", "url": "https://api.openai.com/v1/responses",
    "authentication": "predefinedCredentialType", "nodeCredentialType": "openAiApi",
    "sendBody": True, "specifyBody": "json", "jsonBody": directorios_body,
    "options": {"timeout": 150000, "response": {"response": {"fullResponse": False, "neverError": True}}}},
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
    "onError": "continueRegularOutput",
    "position": [8280, 300], "name": "Descubrir Directorios"})
nodes.append(code("Fusionar Recomendaciones", CODE_FUSIONAR, [8520, 300]))

nodes.append(openai_agent("Agente 6 - Director", "gpt-5.4-mini", PROMPT_A6_DIRECTOR,
                          "={{ JSON.stringify($json) }}", [8760, 300], 0.3, 2500))
nodes.append(code("Ensamblar Reporte", CODE_ENSAMBLAR, [8520, 300]))
nodes.append({"parameters": {"respondWith": "firstIncomingItem", "options": {}},
              "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1.1,
              "position": [8760, 300], "name": "Respond to Webhook"})

# --- Informe por email: plantilla pura, CERO LLM ---
# Si no hay email valido en el formulario, el Code node no emite items y no se envia nada.
nodes.append(code("Generar Informe HTML", CODE_EMAIL, [9240, 540]))

# --- HTML a PDF con Gotenberg (Chromium autoalojado; sin LLM, sin coste por documento) ---
# Requiere un Gotenberg accesible desde n8n. Docker: docker run -d -p 3000:3000 gotenberg/gotenberg:8
# Ajusta GOTENBERG_URL a tu instancia (p.ej. http://gotenberg:3000 si están en la misma red Docker).
GOTENBERG_URL = "http://gotenberg:3000/forms/chromium/convert/html"
nodes.append({
    "parameters": {
        "method": "POST",
        "url": GOTENBERG_URL,
        "sendBody": True,
        "contentType": "multipart-form-data",
        "bodyParameters": {"parameters": [
            {"parameterType": "formBinaryData", "name": "files", "inputDataFieldName": "index_html"},
            {"parameterType": "formData", "name": "marginTop", "value": "0.4"},
            {"parameterType": "formData", "name": "marginBottom", "value": "0.4"},
            {"parameterType": "formData", "name": "marginLeft", "value": "0.3"},
            {"parameterType": "formData", "name": "marginRight", "value": "0.3"},
            {"parameterType": "formData", "name": "printBackground", "value": "true"},
            {"parameterType": "formData", "name": "preferCssPageSize", "value": "true"}
        ]},
        "options": {"response": {"response": {"responseFormat": "file", "outputPropertyName": "data"}}, "timeout": 60000}
    },
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
    "onError": "continueRegularOutput",
    "position": [9480, 540], "name": "HTML a PDF"
})

nodes.append({
    "parameters": {
        "fromEmail": "informes@brandevs.com",
        "toEmail": "={{ $('Generar Informe HTML').item.json.to }}",
        "subject": "={{ $('Generar Informe HTML').item.json.subject }}",
        "emailFormat": "html",
        "html": "={{ $('Generar Informe HTML').item.json.bodyEmail }}",
        "options": {"attachments": "data"}
    },
    "type": "n8n-nodes-base.emailSend", "typeVersion": 2.1,
    "onError": "continueRegularOutput",
    "position": [9720, 540], "name": "Enviar Informe"
})


chain(["Merge Bloques", "Consolidar Sondeos", "Agente Informe LLM",
       "Agente 5 - Huella Digital (web_search)", "Extraer Huella", "Calcular Score",
       "Recomendar Sitios", "Descubrir Directorios", "Fusionar Recomendaciones",
       "Agente 6 - Director", "Ensamblar Reporte", "Respond to Webhook"])

# El email se cablea DESPUES del chain: asi "Respond to Webhook" queda primero en la rama
# y el usuario ve su informe en pantalla sin esperar al envio SMTP.
connect("Ensamblar Reporte", "Generar Informe HTML")
connect("Generar Informe HTML", "HTML a PDF")
connect("HTML a PDF", "Enviar Informe")

# --- Sticky notes ---
nodes.append(sticky("## 1. Repositorios reales (determinista)\nHTTP directo, fetch con los UAs reales de los bots (detecta bloqueo CDN/WAF) y validator.schema.org. Cero LLM: solo hechos verificables.",
                    [200, 40], 2200, 130, 7))
nodes.append(sticky("## 2. Los 4 agentes de sondeo (ramas paralelas)\nCada agente = 1 batería de 4 preguntas → 3 modelos (ChatGPT y Claude paramétricos, Perplexity grounded con citations) → evaluador propio en JSON.\nTODAS las preguntas se anclan al mercado (país + región) y se lanzan en el idioma de ese mercado. Perplexity recibe además user_location nativo.\nLas 4 preguntas de cada batería salen como 4 items al nodo HTTP, que lanza las peticiones JUNTAS: ahí está el paralelismo real.\n16 preguntas x 3 modelos = 48 sondeos.",
                    [4860, -520], 1200, 220, 5))
nodes.append(sticky("## 3. El 5º agente: informe detallado\nRecibe los 4 bloques ya evaluados (no 48 respuestas crudas) + las fuentes que el motor grounded citó de verdad, y redacta el informe completo: veredicto, dimensiones, competidores, gaps, plan y KPIs.",
                    [6820, 40], 1000, 150, 4))
nodes.append(sticky("## 4. Score + síntesis global\nSoV determinista a partir de los 4 bloques: descubrimiento 45%, competitivo 20%, conocimiento 20%, reputación 15%. El Director une causas técnicas con el resultado de visibilidad.",
                    [7780, 40], 900, 150, 6))

# Blindaje: estos nodos emiten SIEMPRE al menos un item aunque n8n los salte por falta de input
for _n in nodes:
    if _n["name"] in ("Seleccionar Landings", "GET Landing", "Analizar Landings"):
        _n["alwaysOutputData"] = True

workflow = {
    "name": "GEOpulse v10 - Descubrimiento activo de directorios (agente + determinista)",
    "nodes": nodes,
    "connections": connections,
    "settings": {"executionOrder": "v1"},
    "pinData": {},
    "meta": {"instanceId": "geopulse-template"}
}

# El guard permite `import build_workflow_v10` desde build_audit_panel.py para
# reutilizar 'nodes' y 'connections' sin regenerar este fichero. Ejecutarlo
# directamente se comporta exactamente igual que antes.
if __name__ == "__main__":
    # Junto al builder, no en el directorio desde el que se invoque: si no, el
    # JSON acaba donde toque estar en ese momento (la raiz del repo, por ejemplo)
    # y conviven dos copias distintas del mismo workflow. Los demas builders ya
    # lo hacen asi.
    _salida = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geopulse-workflow.json")
    with open(_salida, "w", encoding="utf-8") as f:
        json.dump(workflow, f, ensure_ascii=False, indent=2)

    print("OK - nodos:", len(nodes), "| conexiones:", len(connections))
    print("Escrito en:", _salida)

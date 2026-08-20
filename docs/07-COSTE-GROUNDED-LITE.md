# 07 · Coste de la versión *grounded* del análisis LITE

**Qué responde este informe:** cuánto sube el gasto en llamadas a los LLMs si el LITE pasa a hacer **todas** las
sondas con búsqueda web (grounded) en vez de paramétricas. Es la versión que se expone a internet, así que el
coste por análisis importa.

**Fecha de precios:** agosto 2026 (fuentes al final). Las **tarifas de búsqueda están documentadas**; los
**deltas de tokens son estimaciones** (dependen de cuánto contenido inyecte cada búsqueda). No son un número
cerrado: es un orden de magnitud honesto para decidir.

---

## Qué cambia exactamente

El LITE hace hoy, por análisis, **12 sondas de descubrimiento** (3 preguntas × 4 modelos) + 1 sonda de huella +
1 llamada de redacción del informe. De esas:

| Llamada | Nº por run | Hoy | Con grounding |
|---|---|---|---|
| Sonda ChatGPT | 3 | ❌ paramétrica | ✅ grounded (Responses API + `web_search`) |
| Sonda Claude | 3 | ❌ paramétrica | ✅ grounded (`web_search` tool) |
| Sonda Gemini | 3 | ❌ paramétrica | ✅ grounded (`google_search` tool) |
| Sonda Perplexity | 3 | ✅ ya grounded | ✅ sin cambio |
| Huella Perplexity | 1 | ✅ ya grounded | ✅ sin cambio |
| Informe ChatGPT (redactor) | 1 | ❌ paramétrica | ❌ **sigue paramétrica** (no es una sonda: escribe el informe con los datos ya recogidos; groundearla contaminaría la medición) |

→ **El grounding añade búsqueda web a 9 llamadas por análisis** (3 ChatGPT + 3 Claude + 3 Gemini). Perplexity ya
la tenía, así que no suma.

---

## Coste añadido por análisis

### 1) Tarifas de búsqueda (documentadas)

| Proveedor | Modelo (variante panel) | Tarifa | Llamadas/run | Coste/run |
|---|---|---|---|---|
| OpenAI | gpt-5.6-luna | $10 / 1.000 | 3 | **$0,030** |
| Anthropic | claude-haiku-4-5 | $10 / 1.000 | 3 | **$0,030** |
| Gemini | gemini-3.5-flash | $14 / 1.000 (5.000 gratis/mes) | 3 | **$0,042** |
| **Subtotal tarifas de búsqueda** | | | | **≈ $0,10 / run** |

> La variante panel usa **gemini-3.5-flash** ($14/1.000). Si se corriera el LITE *base* (gemini-2.5-flash) la
> tarifa de Gemini sería **$35/1.000** → $0,105/run solo en Gemini. Otra razón para exponer la variante panel.

### 2) Tokens extra (estimación)

El grounding inyecta los resultados de búsqueda como **input** y alarga la respuesta. Estimación conservadora
(~8k tokens input/llamada en OpenAI mini; ~4k en Claude/Gemini; +~500 output):

| Proveedor | Tokens extra/run (aprox.) | Coste/run (aprox.) |
|---|---|---|
| OpenAI | ~24k in + 1,5k out | ~$0,017 |
| Anthropic | ~12k in + 1,5k out | ~$0,023 |
| Gemini | ~12k in + 1,5k out | ~$0,011 |
| **Subtotal tokens extra** | | **≈ $0,05 / run** |

### 3) Total añadido

> **≈ $0,15 por análisis LITE** (rango honesto **$0,10 – $0,20** por la incertidumbre de los tokens).
> Las tarifas de búsqueda (~$0,10) son firmes; el resto es estimación.

Para contexto: el LITE actual cuesta **céntimos** por análisis (modelos baratos, sin tarifas de búsqueda salvo
la Perplexity que ya está). El grounding lo multiplica **aprox. ×3–×4**, pero **sigue siendo céntimos**.

---

## Proyección mensual (solo el AUMENTO)

| Análisis/mes | + Tarifas búsqueda | + Tokens | **+ Total/mes** |
|---|---|---|---|
| 100 | $10 | $5 | **≈ $15** |
| 500 | $51 | $22 | **≈ $73** |
| 1.000 | $102 | $45 | **≈ $147** |
| 5.000 | $510 | $225 | **≈ $735** |

> **Amortiguador de Gemini:** los primeros **5.000 prompts grounded/mes** de la familia Gemini 3.x son gratis
> (compartidos). A 3 sondas Gemini por run, eso cubre **~1.666 análisis/mes** sin coste de búsqueda en Gemini
> (≈ $70/mes de ahorro hasta ese punto). Por encima, $14/1.000.

Con el volumen que probablemente maneje una herramienta pública (cientos–pocos miles/mes), el aumento es de
**decenas a bajos cientos de dólares al mes**. Es "poco gasto" en absoluto, pero **crece linealmente con el uso**,
que es justo lo que importaba saber al ser la versión expuesta.

---

## Lo que NO es coste pero hay que decidir (honestidad)

1. **Grounding re-baseliza la nota.** Medir con búsqueda web cambia qué empresas aparecen → cambia la cuota de
   voz (SoV) → **cambia la nota** para la misma empresa. Eso **rompe la comparabilidad con auditorías previas** y,
   mientras el COMPLETO esté grounded y el LITE no, **entre LITE y COMPLETO** (regla dura de `CLAUDE.md`). Al
   activar grounding hay que **subir `analysis_version`** para señalar que los informes viejos y nuevos no se
   comparan. Los **pesos del score NO se tocan**: cambia lo que se mide, no la fórmula.
2. **Latencia.** Las llamadas grounded son más lentas (buscan antes de responder). El LITE es el tier "rápido";
   9 búsquedas en paralelo añaden segundos. El polling asíncrono del panel lo absorbe, pero el usuario espera más.
3. **Errores de búsqueda no se cobran** (las 3 APIs no facturan una búsqueda que falla), así que el coste real es
   una **cota superior**.

---

## Recomendación

El aumento es pequeño en absoluto (~$0,15/run) y el argumento de producto es sólido: sin grounding se analiza una
**alucinación de una memoria desfasada**, no la realidad. **Merece la pena.** La única cautela real no es el
dinero sino la **re-baselización de la nota**: conviene activarlo con un `analysis_version` nuevo y avisar de que
los informes grounded no se comparan con los paramétricos anteriores.

**Decisión pendiente (tuya):** ¿se implementa el grounding en LITE? Si sí, se aplica el mismo patrón que en el
COMPLETO (ya implementado): Responses API + `web_search` para ChatGPT, `web_search` tool para Claude,
`google_search` para Gemini; Perplexity sin cambio.

---

## Fuentes (agosto 2026)

- OpenAI web_search (Responses API), $10/1.000 + tokens de contenido: [developers.openai.com/api/docs/pricing](https://developers.openai.com/api/docs/pricing) · [comunidad OpenAI sobre el coste real de la web tool](https://community.openai.com/t/heads-up-web-search-tool-billing-can-be-higher-than-you-expect-here-s-why/1236954)
- Anthropic web search, $10/1.000 búsquedas + tokens: [platform.claude.com/docs — web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool)
- Gemini grounding, $14/1.000 (3.x, 5.000 gratis/mes) · $35/1.000 (2.5): [ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing)

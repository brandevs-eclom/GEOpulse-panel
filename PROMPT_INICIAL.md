# Prompt inicial para Claude Code

> Copia este texto como primer mensaje al arrancar el proyecto de Claude Code.
> Antes de pegarlo, asegúrate de que en el repo están las carpetas `docs/` y `workflows/`
> que acompañan a este documento.

---

Vamos a construir **GEOpulse Panel**, un panel de control interno para la agencia BranDevs que gestiona una herramienta de auditoría GEO (visibilidad de marcas en la IA) ya existente y en producción sobre n8n.

**Antes de escribir una sola línea de código, lee en este orden:**

1. `docs/00-CONTEXTO-PROYECTO.md` — qué es GEOpulse, qué existe ya y qué vamos a construir.
2. `docs/01-ARQUITECTURA-PANEL.md` — la arquitectura objetivo del panel y las decisiones ya tomadas.
3. `docs/02-CONTRATO-WORKFLOWS.md` — cómo se llaman los workflows de n8n, qué reciben y qué devuelven (el esquema completo del informe).
4. `docs/03-MODELO-DATOS.md` — el esquema de Postgres propuesto.
5. `docs/04-GESTION-WORKFLOWS.md` — cómo se generan y mantienen los workflows de n8n desde este mismo repo.
6. `docs/05-FASES.md` — el plan por fases. Construiremos por fases; no intentes hacerlo todo de una vez.

Cuando los hayas leído, **no empieces a programar todavía**. Primero:

- Proponme el **stack concreto** del panel (framework, ORM, librería de UI, gestión de estado, cómo servir el backend). En `docs/01` te explico las restricciones y por qué te dejo esta decisión a ti. Justifica cada elección en una o dos frases.
- Señala cualquier cosa de los documentos que te parezca incoherente, arriesgada o que falte por decidir.
- Propón la estructura de carpetas del repo.
- Espera mi visto bueno antes de generar código.

Trabajaremos igual que en el proyecto original: **cambios pequeños y verificables**, nada de reescrituras completas cuando basta un ajuste. Prefiero honestidad técnica sobre promesas optimistas: si algo tiene un riesgo o un coste, dímelo.

Una cosa importante sobre el tono del producto: la herramienta GEOpulse tiene como valor central la **honestidad de sus datos** (cuando algo no se puede medir, lo dice en vez de inventar un número). El panel debe respetar ese mismo principio: mostrar los avisos y los estados "no verificable" que ya trae cada informe, sin maquillarlos.

# 01 · Arquitectura del panel

## Decisiones ya tomadas (no re-abrir sin motivo)

Estas tres las decidió el responsable del proyecto. No las cuestiones salvo que veas un problema real:

1. **El panel lanza los análisis llamando a los webhooks de n8n que ya existen.** No reimplementamos la lógica GEO, ni orquestamos nodo a nodo. El backend del panel hace un `POST` al webhook y recibe el informe. n8n sigue siendo el motor.
2. **Persistencia en PostgreSQL.** La agencia ya usa Postgres en otros proyectos. Toda ejecución y su resultado se guardan ahí.
3. **El frontend del panel lo eliges tú (Claude Code) y lo justificas.** Ver más abajo.

## El reto de la llamada síncrona (léelo con atención)

Los dos webhooks de n8n responden de forma **síncrona**: el `POST` se queda abierto hasta que el análisis termina y entonces devuelve el JSON del informe. Esto es cómodo pero tiene una implicación fuerte:

- El **lite** tarda ~1-2 min (12 sondeos).
- El **completo** tarda **3-5 min** (64 sondeos + 4 agentes evaluadores + generación del informe).

Una petición HTTP de 5 minutos desde un navegador es frágil (timeouts de proxy, del propio fetch, del usuario que cierra la pestaña). Por eso, **el patrón del panel debe ser asíncrono aunque el webhook sea síncrono**:

```
Navegador → POST /api/runs (crea la ejecución en Postgres con estado "pendiente", responde YA con un id)
                 │
                 └─ el backend, en segundo plano, hace el POST al webhook de n8n,
                    espera el informe, y actualiza la fila en Postgres a "completado" (o "error")

Navegador → hace polling a GET /api/runs/:id cada pocos segundos hasta que el estado cambie
            (o usa SSE/websocket si lo prefieres; el polling es suficiente para uso interno)
```

Puntos a resolver en tu propuesta:
- Cómo ejecutas ese "trabajo en segundo plano" (un proceso worker, una cola, un simple `setImmediate`/promesa no-esperada con reintentos, un cron que recoge pendientes...). Para uso interno y bajo volumen, algo sencillo y robusto es mejor que una cola completa. Justifícalo.
- **Timeout e idempotencia**: el POST a n8n debe tener un timeout generoso (p. ej. 6-7 min) y la ejecución debe poder marcarse como "error" si n8n no responde. Si se reintenta, no debe duplicar filas.
- **Concurrencia**: cada análisis completo consume ~64 llamadas a APIs de pago. Debe haber un límite de análisis simultáneos configurable (p. ej. máx. 2-3 a la vez) para no disparar el gasto ni tumbar la instancia de n8n.

## Componentes

```
┌─────────────────────────────────────────────────────────┐
│  GEOpulse Panel                                          │
│                                                          │
│  Frontend (tú eliges)         Backend/API (tú eliges)    │
│  - Listado de ejecuciones     - POST /api/runs           │
│  - Formulario de lanzamiento  - GET  /api/runs           │
│  - Detalle de ejecución       - GET  /api/runs/:id       │
│    (render del informe)       - lógica de disparo a n8n  │
│                               - worker/proceso en 2º plano│
└───────────────┬──────────────────────┬──────────────────┘
                │                      │
                ▼                      ▼
        ┌──────────────┐      ┌──────────────────┐
        │  PostgreSQL  │      │  n8n (webhooks)  │
        │  ejecuciones │      │  geopulse-audit  │
        │  + informes  │      │  geopulse-lite2  │
        └──────────────┘      └──────────────────┘
```

## Sobre el stack del frontend (tu decisión)

Se te deja elegir porque conoces el ecosistema actual mejor que este documento. Restricciones y preferencias:

- **Es una app interna**, no una web pública que deba posicionar. No hay requisito de SSR/SEO. Prioriza velocidad de desarrollo y mantenibilidad.
- Debe convivir con un backend que hable con Postgres y con n8n. Un framework full-stack (tipo Next.js) simplifica tener API y UI juntas; un SPA + API separada también vale. Elige y justifica.
- **Reutilización del render**: los frontends actuales (`geopulse-lite2.html`, `geopulse-frontend-brandevs.html`) ya saben pintar el informe en JS vanilla con SVG. Puedes portar esa lógica a componentes o reescribirla; evalúa el coste. El esquema exacto del informe está en `docs/02`.
- La paleta y tipografía de BranDevs (para coherencia visual): acento `#EF3B2D`, fondo `#F6F5F2`, oscuro `#262523`, tipos `Manrope` (títulos) e `Inter` (texto). No es obligatorio calcarlo, pero conviene que el panel se sienta de la misma familia.

## Seguridad

- Es interna: como mínimo, protégela con autenticación (un login sencillo basta para fase 1; puede ser un usuario/contraseña o un proveedor si ya usáis alguno).
- **Los secretos viven en el backend**: las API keys de OpenAI/Anthropic/Gemini/Perplexity **NO** están en el panel — viven en las credenciales de n8n. El panel solo necesita la URL base de n8n y, si procede, un token para llamar a los webhooks. Nunca expongas secretos al navegador.
- La URL de los webhooks de n8n y las credenciales de Postgres van en variables de entorno, nunca en el repo.

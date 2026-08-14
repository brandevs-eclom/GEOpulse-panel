# 03 · Modelo de datos (PostgreSQL)

Propuesta de esquema. Es un punto de partida razonable; puedes ajustarlo al proponer el stack (p. ej. si el ORM sugiere otra convención). Justifica cualquier cambio.

## Principio

El JSON del informe es rico y evoluciona. **No lo normalices entero en columnas**: guarda el informe completo como `jsonb` y extrae a columnas solo lo que necesites para **listar, filtrar y ordenar** en la tabla de ejecuciones. Así el panel no se rompe cada vez que el informe gane un campo, y a la vez las consultas de listado son rápidas.

## Tabla `runs` (ejecuciones)

```sql
create table runs (
  id              uuid primary key default gen_random_uuid(),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),

  -- Petición
  tipo            text not null check (tipo in ('lite','completo')),
  brand           text not null,
  domain          text not null,          -- normalizado (host)
  keyword         text not null,
  pais            text not null default 'ES',
  region          text,
  payload         jsonb not null,         -- el body EXACTO enviado al webhook (idempotencia/reproducir)

  -- Estado del ciclo de vida
  estado          text not null default 'pendiente'
                    check (estado in ('pendiente','en_curso','completado','error')),
  started_at      timestamptz,            -- cuándo empezó el POST a n8n
  finished_at     timestamptz,            -- cuándo respondió (o falló)
  duracion_ms     integer,                -- finished_at - started_at
  error_mensaje   text,                   -- si estado='error'
  http_status     integer,               -- status del webhook si lo hubo

  -- Resultado (extraído del informe para la tabla; el informe entero va en informe_id)
  nota            integer,                -- meta → GEO Score (nullable)
  veredicto       text,                   -- posicionamiento.veredicto
  sov             integer,                -- por_area.sov (visibilidad IA), muy útil de listar
  sondeos         integer,                -- meta.sondeos (cuántos respondieron)
  tiene_avisos    boolean default false,  -- avisos.length > 0 (para marcar en la tabla)

  -- Quién lo lanzó (si hay auth de usuarios)
  lanzado_por     text
);
-- IMPLEMENTADO: `lanzado_por` acabó siendo `uuid references users(id) on delete set null`,
-- no `text`. Es la columna que decide quién ve qué: un miembro solo ve las suyas,
-- un admin las ve todas. Las ejecuciones anteriores a la autenticación tienen
-- NULL, así que solo las ven los admins, y al borrar una cuenta sus ejecuciones
-- se conservan (pasan a NULL) en vez de desaparecer.

create index on runs (created_at desc);
create index on runs (estado);
create index on runs (domain);
create index on runs (tipo);
```

## Tabla `informes` (el JSON completo, separado)

Separar el `jsonb` grande de la fila de listado mantiene la tabla `runs` ligera para paginar. Relación 1:1.

```sql
create table informes (
  run_id     uuid primary key references runs(id) on delete cascade,
  informe    jsonb not null,        -- el objeto informe COMPLETO tal cual lo devolvió n8n
  raw_body   text,                  -- cuerpo crudo de la respuesta (por si el JSON viene raro)
  created_at timestamptz not null default now()
);
```

> Alternativa: si prefieres una sola tabla, mete `informe jsonb` directamente en `runs`. La separación ayuda cuando la tabla crece y casi todas las consultas son de listado (no necesitan el informe entero). Decide y justifica.

## Tabla `users` (implementada)

```sql
create table users (
  id             uuid primary key default gen_random_uuid(),
  email          text not null unique,
  password_hash  text not null,          -- scrypt: 'scrypt$N$r$p$saltB64$hashB64'
  nombre         text,
  rol            text not null default 'miembro',   -- 'admin' | 'miembro'
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
```

Notas que condicionan cualquier cambio futuro aquí:

- **El `unique` de `email` NO es case-insensitive.** La normalización a minúsculas vive en las operaciones del workflow `panel-db` (`normEmail`). Cualquier operación nueva que toque `users` tiene que normalizar igual, o convivirán `Ana@x.com` y `ana@x.com` y el login será ambiguo.
- **`rol` no tiene CHECK**; el conjunto válido (`admin` | `miembro`) se valida en el workflow y en el panel. Un valor desconocido se degrada a `miembro` al leerlo: nunca se asciende solo.
- **No hay columna `activo`.** "Quitar el acceso" es borrar la fila; las ejecuciones se conservan porque `runs.lanzado_por` es `ON DELETE SET NULL`. Añadir una desactivación blanda exigiría una migración `0001`, y antes hay que arreglar el mecanismo (ver abajo).
- **No hay tabla de sesiones a propósito.** La sesión es un JWT firmado en cookie. Una tabla obligaría a un HTTP a n8n en cada petición y el panel hace polling cada 2,5-3 s. El precio aceptado es que no se puede revocar una sesión concreta.

## Consultas típicas que el panel hará

- **Listado paginado** con filtro por tipo/estado/dominio y orden por fecha o por nota → solo toca `runs`, rápido.
- **Detalle** de una ejecución → `runs` join `informes` por `run_id`.
- **Recoger pendientes/en curso huérfanas** (p. ej. tras un reinicio del backend) para reintentarlas o marcarlas en error → `where estado in ('pendiente','en_curso')`.
- **Métricas del dashboard** (opcional): nota media por sector, evolución de la visibilidad de un dominio en el tiempo (varias ejecuciones del mismo `domain`), reparto de veredictos. Todo agregando sobre `runs`.

## Migraciones

Usa el sistema de migraciones que traiga el stack/ORM que elijas (o SQL plano versionado). Deja el esquema inicial como primera migración. `gen_random_uuid()` requiere la extensión `pgcrypto` (o usa `uuid-ossp`); inclúyela en la migración inicial.

> **Aviso sobre el mecanismo actual, antes de escribir una migración `0001`.** `migrate` empaqueta todos los `.sql` de `db/migrations/` y los parte por `--> statement-breakpoint`. Ya se corrigió que los ficheros se unieran sin ese separador (la última sentencia de `0000` y la primera de `0001` habrían viajado juntas y solo se habría ejecutado una, **sin error visible**). Pero queda pendiente lo otro: **`migrate` no es idempotente y reaplica todo**, así que hoy no se puede lanzar dos veces. Antes de la primera migración de verdad hay que hacer que aplique solo lo pendiente. Es trabajo aparte, no se cuela dentro de otra cosa.

## Índice temporal para históricos

Como un mismo dominio se auditará varias veces (para ver evolución), conviene poder sacar "la última ejecución completada por dominio". Un índice sobre `(domain, created_at desc)` lo hace barato. Si más adelante hay muchos dominios y muchas ejecuciones, se puede añadir una vista materializada de "última por dominio".

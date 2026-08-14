#!/usr/bin/env python3
# panel-db — capa de datos del GEOpulse Panel.
#
# POR QUE EXISTE ESTE WORKFLOW
# El Postgres de GEOpulse vive dentro del servidor de n8n y no tiene salida al
# exterior, asi que el panel (que corre en Vercel) NO puede abrir una conexion
# directa. Toda lectura y escritura entra por aqui: el panel hace POST con un
# nombre de operacion, este workflow ejecuta la consulta con el nodo Postgres
# local y devuelve las filas.
#
# SEGURIDAD (leelo antes de tocar nada)
#   · El panel NUNCA envia SQL. Envia un nombre de operacion y unos parametros.
#     El SQL vive en la lista blanca de 'Resolver Operacion'. Si este webhook
#     aceptase SQL del cliente seria un "ejecuta lo que quieras" abierto a
#     internet, con toda la BD de la agencia detras.
#   · El webhook va protegido con Header Auth ('x-panel-secret'). Hay que crear
#     la credencial en n8n; su nombre esta en CRED_HEADER_AUTH.
#   · Los valores variables van SIEMPRE por $1,$2... (queryReplacement), nunca
#     concatenados dentro del SQL.
#
# COSTE OPERATIVO
# Cada consulta del panel es una ejecucion de n8n. Con polling, una sola pestaña
# de detalle abierta genera decenas de ejecuciones por minuto. Conviene poner
# este workflow en "Save successful executions: none" para no inflar el historial.
#
# Uso:  python build_panel_db.py     (o python3 en Linux/Mac)
import json
import os

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
DIR_MIGRACIONES = os.path.join(RAIZ, "src", "server", "db", "migrations")

WEBHOOK_PATH = "panel-db"
CRED_HEADER_AUTH = "GEOpulse Panel - Header Auth"
# Credencial de Postgres ya existente en n8n. Fijarla aqui hace que al reimportar
# el nodo 'Ejecutar SQL' quede enlazado solo, sin reasignarla a mano cada vez.
CRED_POSTGRES = "GEOpulse User"


def leer_migraciones() -> str:
    """Concatena el SQL generado por drizzle-kit, en orden.

    El esquema es 'codigo' en src/server/db/schema.ts; drizzle-kit lo convierte a
    SQL; aqui solo lo empaquetamos. Asi no hay dos fuentes de verdad del esquema.
    """
    if not os.path.isdir(DIR_MIGRACIONES):
        raise SystemExit(
            "No encuentro %s.\nEjecuta antes:  npm run db:generate" % DIR_MIGRACIONES
        )
    ficheros = sorted(f for f in os.listdir(DIR_MIGRACIONES) if f.endswith(".sql"))
    if not ficheros:
        raise SystemExit(
            "No hay .sql en %s.\nEjecuta antes:  npm run db:generate" % DIR_MIGRACIONES
        )
    trozos = []
    for nombre in ficheros:
        with open(os.path.join(DIR_MIGRACIONES, nombre), encoding="utf-8") as fh:
            trozos.append("-- === %s ===\n%s" % (nombre, fh.read().strip()))
    # OJO: entre ficheros hay que meter el separador a mano. 'migrate' parte el SQL
    # por '--> statement-breakpoint' (lo pone drizzle DENTRO de cada fichero, pero
    # no al final). Sin esto, la ultima sentencia de 0000 y la primera de 0001
    # viajarian en el mismo item y el nodo Postgres solo ejecutaria la primera:
    # media migracion aplicada y ningun error visible. Hoy solo hay un fichero,
    # asi que este separador no cambia nada; esta puesto para el dia que haya dos.
    return "\n--> statement-breakpoint\n".join(trozos)


MIGRACION_SQL = leer_migraciones()

# ============================================================
# CODE NODES
# ============================================================

# Nota: los '}}' que pueda haber aqui son inofensivos porque esto es jsCode de un
# nodo Code, no una expresion '={{ }}' de n8n (regla de docs/04).
CODE_RESOLVER = (
    r"""// Lista blanca de operaciones. El panel manda un nombre, nunca SQL.
const entrada = $json.body || $json;
const op = String(entrada.op || '').trim();
const params = (entrada.params && typeof entrada.params === 'object') ? entrada.params : {};

const MIGRACION = """
    + json.dumps(MIGRACION_SQL)
    + r""";

// Cada operacion declara su SQL y como ordenar sus parametros para $1,$2...
// 'requiere' documenta que campos son obligatorios; se valida antes de tocar la BD.
// Los valores de usuario (marca, dominio, ...) SIEMPRE van por $N (queryReplacement),
// nunca concatenados dentro del SQL: es la unica defensa contra inyeccion.
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const exigirUuid = (v, campo) => {
  const s = String(v).trim();
  if (!UUID_RE.test(s)) throw new Error((campo || 'id') + ' no es un UUID valido');
  return s;
};
// Filtro de propiedad: null = sin filtro (admin, lo ve todo). Se valida igual que
// un id para que nunca entre texto arbitrario en la consulta.
const filtroDueno = (v) => (v === undefined || v === null || v === '' ? null : exigirUuid(v, 'solo_de'));

// INVARIANTE: el unique de users.email en Postgres NO es case-insensitive. La
// normalizacion a minusculas vive AQUI. Cualquier operacion futura que toque
// users tiene que normalizar igual, o acabaran conviviendo 'Ana@x.com' y
// 'ana@x.com' y el login se volvera ambiguo.
const normEmail = (v) => String(v).trim().toLowerCase();

const ROLES = ['admin', 'miembro'];
const normRol = (v) => {
  const r = String(v).trim().toLowerCase();
  if (ROLES.indexOf(r) === -1) throw new Error('rol invalido: ' + r + ' (admin|miembro)');
  return r;
};

const OPS = {
  ping: {
    sql: 'select 1 as ok',
    requiere: [],
    orden: () => []
  },
  migrate: {
    // Se parte en una sentencia por item (mas abajo). No idempotente a proposito:
    // si las tablas ya existen, falla en vez de fingir. Cada item lleva params [].
    sql: MIGRACION,
    requiere: [],
    orden: () => []
  },
  check: {
    // Verificacion positiva: que tablas del panel existen de verdad.
    sql: "select table_name from information_schema.tables " +
         "where table_schema = 'public' " +
         "and table_name in ('runs', 'informes', 'users') " +
         "order by table_name",
    requiere: [],
    orden: () => []
  },
  whoami: {
    // Diagnostico: con que usuario/base conecta n8n y si puede crear en public.
    sql: "select current_user as usuario, current_database() as base, " +
         "has_schema_privilege(current_user, 'public', 'CREATE') as puede_crear_en_public",
    requiere: [],
    orden: () => []
  },

  // --- Ejecuciones (runs) ---
  count_active: {
    // Guard de concurrencia: cuantos analisis estan vivos ahora mismo.
    // NO se filtra por dueno a proposito: el tope es de gasto de la agencia, no
    // una cuota por persona. Dos miembros lanzando a la vez comparten el tope.
    sql: "select count(*)::int as activos from runs " +
         "where estado in ('pendiente', 'en_curso')",
    requiere: [],
    orden: () => []
  },
  create_run: {
    // Crea la ejecucion en 'pendiente' y devuelve su id. El payload (body exacto
    // para n8n) se guarda como jsonb para poder reproducir/reintentar.
    // lanzado_por es OPCIONAL: un reintento manual por curl (sin sesion) debe
    // seguir funcionando y se guarda sin dueno.
    requiere: ['tipo', 'brand', 'domain', 'keyword'],
    sql: "insert into runs (tipo, brand, domain, keyword, pais, region, payload, estado, lanzado_por) " +
         "values ($1, $2, $3, $4, $5, $6, $7::jsonb, 'pendiente', $8) " +
         "returning id, estado, created_at",
    orden: (p) => {
      const tipo = String(p.tipo).trim();
      if (tipo !== 'lite' && tipo !== 'completo') {
        throw new Error("tipo invalido: " + tipo + " (lite|completo)");
      }
      const pais = (p.pais ? String(p.pais).trim().toUpperCase() : 'ES') || 'ES';
      const region = p.region ? String(p.region).trim() : null;
      const payload = JSON.stringify(p.payload && typeof p.payload === 'object' ? p.payload : {});
      const lanzadoPor = p.lanzado_por ? exigirUuid(p.lanzado_por, 'lanzado_por') : null;
      return [tipo, String(p.brand).trim(), String(p.domain).trim(),
              String(p.keyword).trim(), pais, region, payload, lanzadoPor];
    }
  },
  list_runs: {
    // Listado paginado para la tabla. count(*) over() da el total sin 2a consulta.
    //
    // $3 es el filtro de propiedad: null lo ve todo (admin), un uuid ve solo las
    // suyas. Las ejecuciones historicas tienen lanzado_por NULL y por tanto NO
    // pasan el filtro: no tienen dueno, asi que solo las ve un admin. Es
    // deliberado; no aparecen en el listado de un companero nuevo como si fueran
    // suyas.
    sql: "select r.id, r.created_at, r.tipo, r.brand, r.domain, r.keyword, r.pais, r.region, " +
         "r.estado, r.nota, r.veredicto, r.sov, r.sondeos, r.tiene_avisos, r.duracion_ms, " +
         "r.error_mensaje, r.lanzado_por, u.email as lanzado_por_email, " +
         "cast(count(*) over() as integer) as _total " +
         "from runs r left join users u on u.id = r.lanzado_por " +
         "where ($3::uuid is null or r.lanzado_por = $3) " +
         "order by r.created_at desc limit $1 offset $2",
    requiere: [],
    orden: (p) => {
      let limit = parseInt(p.limit, 10);
      if (!Number.isFinite(limit) || limit <= 0) limit = 50;
      if (limit > 200) limit = 200;
      let offset = parseInt(p.offset, 10);
      if (!Number.isFinite(offset) || offset < 0) offset = 0;
      return [limit, offset, filtroDueno(p.solo_de)];
    }
  },
  get_run: {
    // Detalle: la fila + el informe (jsonb) si ya existe.
    // $2 = mismo filtro de propiedad que list_runs. Devolver 0 filas cuando la
    // ejecucion existe pero es de otro es lo correcto: el panel responde 404 y
    // no revela que ese id existe.
    requiere: ['id'],
    sql: "select r.id, r.created_at, r.updated_at, r.tipo, r.brand, r.domain, r.keyword, " +
         "r.pais, r.region, r.payload, r.estado, r.started_at, r.finished_at, " +
         "r.duracion_ms, r.error_mensaje, r.http_status, r.nota, r.veredicto, " +
         "r.sov, r.sondeos, r.tiene_avisos, r.lanzado_por, u.email as lanzado_por_email, " +
         "i.informe, i.raw_body " +
         "from runs r left join informes i on i.run_id = r.id " +
         "left join users u on u.id = r.lanzado_por " +
         "where r.id = $1 and ($2::uuid is null or r.lanzado_por = $2)",
    orden: (p) => [exigirUuid(p.id), filtroDueno(p.solo_de)]
  },
  delete_run: {
    // Borra una ejecucion. informes cae por ON DELETE CASCADE. Devuelve el id
    // borrado (0 filas si no existia o si es de otra persona).
    requiere: ['id'],
    sql: "delete from runs where id = $1 and ($2::uuid is null or lanzado_por = $2) returning id",
    orden: (p) => [exigirUuid(p.id), filtroDueno(p.solo_de)]
  },
  fail_run: {
    // Marca una ejecucion como fallida. La usa el panel cuando no consigue
    // disparar el analisis: sin esto la fila se quedaria 'pendiente' para siempre
    // y ademas ocuparia hueco en el tope de concurrencia.
    // Solo actua sobre ejecuciones aun vivas: no pisa un resultado ya guardado.
    requiere: ['id', 'mensaje'],
    sql: "update runs set estado = 'error', error_mensaje = $2, " +
         "finished_at = now(), updated_at = now() " +
         "where id = $1 and estado in ('pendiente', 'en_curso') returning id",
    orden: (p) => [exigirUuid(p.id), String(p.mensaje).slice(0, 2000)]
  },

  // --- Usuarios ---
  // El panel NUNCA manda ni recibe contrasenas en claro por aqui: el hash se
  // calcula y se verifica en el panel (runtime Node, scrypt). Aqui solo viaja el
  // hash ya calculado. Ojo: quien tenga el secreto de este webhook puede leer los
  // hashes; son scrypt con salt, no contrasenas, pero trata el secreto en
  // consecuencia.
  count_users: {
    // Lo usa el arranque inicial para saber si aun no hay ninguna cuenta.
    sql: 'select count(*)::int as total from users',
    requiere: [],
    orden: () => []
  },
  count_admins: {
    // Red de seguridad: impide quedarse sin ningun admin (nadie podria volver a
    // dar de alta a nadie sin repetir el arranque inicial).
    sql: "select count(*)::int as total from users where rol = 'admin'",
    requiere: [],
    orden: () => []
  },
  get_user_by_email: {
    // Login. Devuelve el hash para que el panel lo verifique.
    requiere: ['email'],
    sql: 'select id, email, nombre, rol, password_hash from users where email = $1 limit 1',
    orden: (p) => [normEmail(p.email)]
  },
  get_user: {
    requiere: ['id'],
    sql: 'select id, email, nombre, rol, created_at, updated_at from users where id = $1',
    orden: (p) => [exigirUuid(p.id)]
  },
  list_users: {
    // Cuantas ejecuciones lleva cada uno: sirve para saber que se pierde al
    // borrar una cuenta (sus ejecuciones se quedan sin dueno).
    sql: 'select u.id, u.email, u.nombre, u.rol, u.created_at, u.updated_at, ' +
         'cast(count(r.id) as integer) as ejecuciones ' +
         'from users u left join runs r on r.lanzado_por = u.id ' +
         'group by u.id order by u.created_at asc',
    requiere: [],
    orden: () => []
  },
  create_user: {
    requiere: ['email', 'password_hash', 'rol'],
    sql: 'insert into users (email, password_hash, nombre, rol) values ($1, $2, $3, $4) ' +
         'returning id, email, nombre, rol, created_at, updated_at',
    orden: (p) => [
      normEmail(p.email),
      String(p.password_hash),
      p.nombre ? String(p.nombre).trim() : null,
      normRol(p.rol)
    ]
  },
  update_user_rol: {
    // La condicion del 'exists' es la RED DE SEGURIDAD contra quedarse sin
    // ningun admin (nadie podria volver a dar de alta a nadie). Va aqui, en la
    // propia sentencia, y no solo como comprobacion previa en el panel: entre
    // "cuento admins" y "escribo" hay dos viajes HTTP distintos a n8n, y dos
    // degradaciones simultaneas pasarian las dos comprobaciones y dejarian cero.
    // Degradar a miembro solo se permite si queda OTRO admin distinto de esta
    // fila. Ascender a admin no se restringe nunca.
    requiere: ['id', 'rol'],
    sql: 'update users set rol = $2, updated_at = now() where id = $1 ' +
         "and ($2 = 'admin' or exists (" +
         "  select 1 from users a where a.rol = 'admin' and a.id <> $1)) " +
         'returning id, email, nombre, rol, created_at, updated_at',
    orden: (p) => [exigirUuid(p.id), normRol(p.rol)]
  },
  update_user_password: {
    // Reseteo de contrasena. No hay envio de correo en el proyecto, asi que la
    // nueva contrasena la comunica el admin por su cuenta.
    requiere: ['id', 'password_hash'],
    sql: 'update users set password_hash = $2, updated_at = now() where id = $1 ' +
         'returning id, email',
    orden: (p) => [exigirUuid(p.id), String(p.password_hash)]
  },
  delete_user: {
    // Quitar el acceso. runs.lanzado_por es ON DELETE SET NULL, asi que sus
    // ejecuciones NO se borran: se quedan sin dueno y pasan a verlas solo los
    // admins. Es la unica forma de revocar acceso, pero no es inmediata: la
    // cookie de sesion sigue siendo valida hasta que caduque (ver README).
    //
    // Mismo cerrojo que update_user_rol: no se puede borrar al ultimo admin.
    // Sin esto se podia dejar el panel con cero admins y sin forma de recuperarlo
    // salvo repitiendo el arranque inicial a mano.
    requiere: ['id'],
    sql: 'delete from users where id = $1 ' +
         "and (rol <> 'admin' or exists (" +
         "  select 1 from users a where a.rol = 'admin' and a.id <> $1)) " +
         'returning id, email',
    orden: (p) => [exigirUuid(p.id)]
  }
};

const def = OPS[op];
if (!def) {
  throw new Error('Operacion no permitida: ' + (op || '(vacia)') +
    '. Permitidas: ' + Object.keys(OPS).join(', '));
}

for (const campo of (def.requiere || [])) {
  if (params[campo] === undefined || params[campo] === null || params[campo] === '') {
    throw new Error('Falta el parametro obligatorio "' + campo + '" para la operacion ' + op);
  }
}

// migrate se parte en UNA sentencia por item. El nodo Postgres de n8n solo
// ejecuta la primera sentencia de un SQL con varias (sea cual sea el protocolo),
// asi que emitimos N items y el nodo corre cada CREATE por separado, en orden.
// Drizzle separa las sentencias con '--> statement-breakpoint', que es el corte
// mas fiable (no parte por ';' que podria aparecer dentro de un literal).
if (op === 'migrate') {
  const esSoloComentarios = (s) =>
    !s.split('\n').some(l => l.trim() && !l.trim().startsWith('--'));
  const sentencias = MIGRACION
    .split('--> statement-breakpoint')
    .map(s => s.trim())
    .filter(s => s && !esSoloComentarios(s));
  if (!sentencias.length) {
    throw new Error('La migracion no contiene sentencias ejecutables');
  }
  // params: [] en cada item: el nodo Postgres usa queryReplacement, y una sentencia
  // sola sin placeholders con lista de valores vacia se ejecuta sin problema.
  return sentencias.map((sql, i) => ({ json: { op, sql, params: [], seq: i } }));
}

return [{ json: { op, sql: def.sql, params: def.orden(params) } }];"""
)

CODE_FORMATEAR = r"""// Respuesta uniforme para el panel: { ok, op, rows }.
// 'Resolver Operacion' corre una sola vez, asi que .first() es seguro aqui
// (la regla de no usar .first() aplica a nodos que corren N veces).
const op = $('Resolver Operacion').first().json.op;

// El nodo Postgres devuelve un item vacio cuando la consulta no retorna filas
// (por ejemplo el DDL de migrate). Eso no es un error: son 0 filas.
const entradas = $input.all();
const rows = entradas
  .map(i => i.json)
  .filter(j => j && Object.keys(j).length > 0);

const salida = { ok: true, op, rows };
// En migrate cada sentencia es un item, asi que el nº de items ejecutados es
// una confirmacion util de que se corrio la migracion entera y no solo la 1ª.
if (op === 'migrate') salida.sentencias = entradas.length;

return [{ json: salida }];"""


# ============================================================
# NODOS
# ============================================================
nodes, conns = [], {}


def connect(a, b, idx=0):
    conns.setdefault(a, {"main": [[]]})
    conns[a]["main"][0].append({"node": b, "type": "main", "index": idx})


def code(name, js, pos):
    return {
        # mode explicito: 'runOnceForAllItems' hace que el nodo se ejecute UNA vez
        # aunque le lleguen 0 items. Importa en 'Formatear Respuesta': si el nodo
        # Postgres no emite filas, aun asi queremos construir y devolver la
        # respuesta { ok, ... } en lugar de dejar el webhook sin cuerpo.
        "parameters": {"mode": "runOnceForAllItems", "jsCode": js},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": pos,
        "name": name,
    }


nodes.append(
    {
        "parameters": {
            "httpMethod": "POST",
            "path": WEBHOOK_PATH,
            # Header Auth: n8n rechaza la peticion antes de ejecutar nada si el
            # secreto no cuadra. Mejor que comprobarlo en un Code node.
            "authentication": "headerAuth",
            "responseMode": "responseNode",
            "options": {},
        },
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [200, 300],
        "name": "Webhook",
        "webhookId": WEBHOOK_PATH,
        "credentials": {"httpHeaderAuth": {"name": CRED_HEADER_AUTH}},
    }
)

nodes.append(code("Resolver Operacion", CODE_RESOLVER, [420, 300]))

nodes.append(
    {
        "parameters": {
            "operation": "executeQuery",
            "query": "={{ $json.sql }}",
            # queryReplacement pasa los valores de $json.params a $1,$2... de forma
            # parametrizada (segura frente a inyeccion). Funciona porque CADA item
            # que llega aqui lleva UNA sola sentencia: las ops de datos son de una
            # sentencia, y migrate viene ya partido en una sentencia por item con
            # params []. El bug original (solo corria la 1a sentencia) era por
            # combinar queryReplacement con un SQL multi-sentencia; ya no ocurre.
            "options": {"queryReplacement": "={{ $json.params }}"},
        },
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.6,
        "position": [640, 300],
        "name": "Ejecutar SQL",
        "credentials": {"postgres": {"name": CRED_POSTGRES}},
        # Sin esto, una consulta que no devuelve filas (el DDL de migrate) corta
        # la cadena, el nodo Responder no llega a ejecutarse y el webhook se
        # queda colgado hasta el timeout.
        "alwaysOutputData": True,
    }
)

nodes.append(code("Formatear Respuesta", CODE_FORMATEAR, [860, 300]))

nodes.append(
    {
        "parameters": {"respondWith": "firstIncomingItem", "options": {}},
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1,
        "position": [1080, 300],
        "name": "Responder",
    }
)

CADENA = ["Webhook", "Resolver Operacion", "Ejecutar SQL", "Formatear Respuesta", "Responder"]
for a, b in zip(CADENA, CADENA[1:]):
    connect(a, b)

wf = {
    "name": "GEOpulse Panel - capa de datos (panel-db)",
    "nodes": nodes,
    "connections": conns,
    "settings": {"executionOrder": "v1"},
}

salida = os.path.join(AQUI, "panel-db-workflow.json")
with open(salida, "w", encoding="utf-8") as fh:
    json.dump(wf, fh, ensure_ascii=False, indent=2)

print("OK - nodos:", len(nodes), "| conexiones:", sum(len(c["main"][0]) for c in conns.values()))
print("SQL de migracion empaquetado:", len(MIGRACION_SQL), "caracteres")
print("Escrito en:", salida)

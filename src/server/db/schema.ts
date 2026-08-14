/**
 * Esquema PostgreSQL del panel (docs/03).
 *
 * Principio: el informe es rico y evoluciona, así que NO se normaliza en columnas.
 * Se guarda entero como jsonb en `informes` y solo se extrae a `runs` lo que hace
 * falta para listar, filtrar y ordenar.
 */

import { sql } from "drizzle-orm";
import {
  boolean,
  check,
  index,
  integer,
  jsonb,
  pgTable,
  text,
  timestamp,
  uuid,
} from "drizzle-orm/pg-core";

import { RUN_ESTADOS, RUN_TIPOS } from "@/lib/shared/status";

const listaSql = (valores: readonly string[]) =>
  sql.raw(valores.map((v) => `'${v}'`).join(", "));

/**
 * Usuarios del panel. Fase 1 usa Credentials (email + contraseña).
 * `rol` queda preparado para la fase 4 (quién puede lanzar completos, que cuestan).
 */
export const users = pgTable("users", {
  id: uuid("id")
    .primaryKey()
    .default(sql`gen_random_uuid()`),
  email: text("email").notNull().unique(),
  passwordHash: text("password_hash").notNull(),
  nombre: text("nombre"),
  rol: text("rol").notNull().default("miembro"),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

/** Ejecuciones. Tabla ligera: es la que se pagina en el listado. */
export const runs = pgTable(
  "runs",
  {
    id: uuid("id")
      .primaryKey()
      .default(sql`gen_random_uuid()`),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true })
      .notNull()
      .defaultNow(),

    // --- Petición ---
    tipo: text("tipo").notNull(),
    brand: text("brand").notNull(),
    /** Normalizado a host. */
    domain: text("domain").notNull(),
    keyword: text("keyword").notNull(),
    pais: text("pais").notNull().default("ES"),
    region: text("region"),
    /** El body EXACTO enviado al webhook: permite reproducir y reintentar. */
    payload: jsonb("payload").notNull(),

    // --- Ciclo de vida ---
    estado: text("estado").notNull().default("pendiente"),
    /** Cuándo se disparó n8n. */
    startedAt: timestamp("started_at", { withTimezone: true }),
    /** Cuándo llegó el callback (o falló). */
    finishedAt: timestamp("finished_at", { withTimezone: true }),
    duracionMs: integer("duracion_ms"),
    errorMensaje: text("error_mensaje"),
    httpStatus: integer("http_status"),

    // --- Resultado extraído del informe (para la tabla) ---
    /** GEO Score. Nullable a propósito: el informe puede no tener datos. */
    nota: integer("nota"),
    veredicto: text("veredicto"),
    /** por_area.sov: visibilidad en IA. */
    sov: integer("sov"),
    /** meta.sondeos: cuántos respondieron. */
    sondeos: integer("sondeos"),
    /** avisos.length > 0, para marcarlo en el listado. */
    tieneAvisos: boolean("tiene_avisos").notNull().default(false),

    lanzadoPor: uuid("lanzado_por").references(() => users.id, {
      onDelete: "set null",
    }),
  },
  (t) => [
    index("runs_created_at_idx").on(t.createdAt.desc()),
    index("runs_estado_idx").on(t.estado),
    index("runs_domain_idx").on(t.domain),
    index("runs_tipo_idx").on(t.tipo),
    // "última ejecución por dominio" para la vista de evolución (fase 3).
    index("runs_domain_created_at_idx").on(t.domain, t.createdAt.desc()),
    check("runs_tipo_check", sql`${t.tipo} in (${listaSql(RUN_TIPOS)})`),
    check("runs_estado_check", sql`${t.estado} in (${listaSql(RUN_ESTADOS)})`),
  ],
);

/**
 * El informe completo, separado de `runs` para que el listado no arrastre
 * jsonb grandes. Relación 1:1.
 */
export const informes = pgTable("informes", {
  runId: uuid("run_id")
    .primaryKey()
    .references(() => runs.id, { onDelete: "cascade" }),
  /** El objeto informe COMPLETO tal cual lo devolvió n8n. */
  informe: jsonb("informe").notNull(),
  /** Cuerpo crudo, por si el JSON viene raro y hay que depurar. */
  rawBody: text("raw_body"),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

export type Run = typeof runs.$inferSelect;
export type NuevoRun = typeof runs.$inferInsert;
export type Informe = typeof informes.$inferSelect;
export type User = typeof users.$inferSelect;

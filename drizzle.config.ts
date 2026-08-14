import { defineConfig } from "drizzle-kit";

/**
 * Drizzle se usa aquí SOLO como "esquema como código": `npm run db:generate`
 * compara schema.ts con la última migración y escribe el SQL nuevo.
 *
 * NO se conecta nunca a la base de datos, porque no puede: el Postgres está
 * dentro del servidor de n8n y no tiene salida al exterior. Por eso no hay
 * `dbCredentials` ni comandos `migrate`/`studio` (fallarían).
 *
 * El SQL generado se aplica invocando la operación `migrate` del workflow
 * `panel-db`, que sí corre junto a la base de datos. Ver workflows/build_panel_db.py.
 */
export default defineConfig({
  schema: "./src/server/db/schema.ts",
  out: "./src/server/db/migrations",
  dialect: "postgresql",
  strict: true,
  verbose: true,
});

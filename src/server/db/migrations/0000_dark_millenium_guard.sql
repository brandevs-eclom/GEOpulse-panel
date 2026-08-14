-- Nota: NO se crea la extensión pgcrypto. gen_random_uuid() es núcleo desde
-- PostgreSQL 13, y crear extensiones exige superusuario, privilegio que el
-- usuario de n8n no tiene ni debe tener. docs/03 la mencionaba como opción para
-- PG antiguos; aquí no hace falta.
CREATE TABLE "informes" (
	"run_id" uuid PRIMARY KEY NOT NULL,
	"informe" jsonb NOT NULL,
	"raw_body" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "runs" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"tipo" text NOT NULL,
	"brand" text NOT NULL,
	"domain" text NOT NULL,
	"keyword" text NOT NULL,
	"pais" text DEFAULT 'ES' NOT NULL,
	"region" text,
	"payload" jsonb NOT NULL,
	"estado" text DEFAULT 'pendiente' NOT NULL,
	"started_at" timestamp with time zone,
	"finished_at" timestamp with time zone,
	"duracion_ms" integer,
	"error_mensaje" text,
	"http_status" integer,
	"nota" integer,
	"veredicto" text,
	"sov" integer,
	"sondeos" integer,
	"tiene_avisos" boolean DEFAULT false NOT NULL,
	"lanzado_por" uuid,
	CONSTRAINT "runs_tipo_check" CHECK ("runs"."tipo" in ('lite', 'completo')),
	CONSTRAINT "runs_estado_check" CHECK ("runs"."estado" in ('pendiente', 'en_curso', 'completado', 'error'))
);
--> statement-breakpoint
CREATE TABLE "users" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"email" text NOT NULL,
	"password_hash" text NOT NULL,
	"nombre" text,
	"rol" text DEFAULT 'miembro' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "users_email_unique" UNIQUE("email")
);
--> statement-breakpoint
ALTER TABLE "informes" ADD CONSTRAINT "informes_run_id_runs_id_fk" FOREIGN KEY ("run_id") REFERENCES "public"."runs"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "runs" ADD CONSTRAINT "runs_lanzado_por_users_id_fk" FOREIGN KEY ("lanzado_por") REFERENCES "public"."users"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "runs_created_at_idx" ON "runs" USING btree ("created_at" DESC NULLS LAST);--> statement-breakpoint
CREATE INDEX "runs_estado_idx" ON "runs" USING btree ("estado");--> statement-breakpoint
CREATE INDEX "runs_domain_idx" ON "runs" USING btree ("domain");--> statement-breakpoint
CREATE INDEX "runs_tipo_idx" ON "runs" USING btree ("tipo");--> statement-breakpoint
CREATE INDEX "runs_domain_created_at_idx" ON "runs" USING btree ("domain","created_at" DESC NULLS LAST);
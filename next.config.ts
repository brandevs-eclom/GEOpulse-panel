import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // El panel es interno: no queremos que Next filtre la cabecera con la versión.
  poweredByHeader: false,
  // Hay package-lock.json en carpetas padre, así que Next infiere mal la raíz del
  // workspace y el file tracing del despliegue saldría incorrecto. La fijamos aquí.
  outputFileTracingRoot: path.resolve(__dirname),
};

export default nextConfig;

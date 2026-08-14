/**
 * Puerta de entrada del panel: sin cookie de sesión válida, no se pasa.
 *
 * RUNTIME EDGE (el que usa Next por defecto para el middleware). Consecuencia
 * que hay que respetar al pie de la letra: aquí SOLO se verifica la firma de la
 * cookie. No se consulta la base de datos y no se importa nada de `node:crypto`
 * (ni `@/server/auth/password` ni `@/server/n8n/client`), o el build de Edge
 * rompe. Si `npm run build` falla con un módulo no soportado, es que se ha
 * colado un import de Node por aquí.
 *
 * Efecto secundario a tener presente: como no se consulta la BD, un usuario al
 * que borres conserva el acceso hasta que su cookie caduque (12 h). Para cortar
 * en el acto hay que rotar AUTH_SECRET, y eso cierra la sesión de todos.
 */

import { NextResponse, type NextRequest } from "next/server";

import { COOKIE_SESION, verificarSesion } from "@/server/auth/session";

export const config = {
  /**
   * Todo queda dentro salvo lo que aparece aquí. Las excepciones y su porqué:
   *  · login / api/auth/login  → si no, no habría forma de entrar.
   *  · api/auth/logout         → salir tiene que funcionar aunque la cookie esté
   *                              caducada; si no, te quedas con una cookie
   *                              inservible que no puedes quitarte.
   *  · api/auth/bootstrap      → creación de la primera cuenta; se protege sola
   *                              con el secreto de panel-db y solo funciona
   *                              mientras no exista ningún usuario.
   *  · api/health              → para poder monitorizarlo desde fuera sin
   *                              credenciales. La ruta recorta lo que enseña
   *                              cuando no hay sesión.
   * `/preview-informe` NO está exento: es una herramienta de desarrollo y no
   * gana nada estando abierta.
   */
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|login|api/auth/login|api/auth/logout|api/auth/bootstrap|api/health).*)",
  ],
};

export async function middleware(req: NextRequest) {
  const sesion = await verificarSesion(req.cookies.get(COOKIE_SESION)?.value);
  if (sesion) return NextResponse.next();

  const { pathname, search } = req.nextUrl;

  // A una llamada de API se le responde 401, nunca un redirect: quien llama es
  // un fetch del navegador y un 307 a una página HTML le llegaría como basura.
  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "no_autenticado" }, { status: 401 });
  }

  const destino = req.nextUrl.clone();
  destino.pathname = "/login";
  destino.search = "";
  destino.searchParams.set("next", pathname + search);
  return NextResponse.redirect(destino);
}

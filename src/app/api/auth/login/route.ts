import { NextResponse } from "next/server";

import type { Sesion } from "@/lib/shared/auth";
import { exigirSesion } from "@/server/auth/guard";
import { verifyPassword } from "@/server/auth/password";
import {
  COOKIE_SESION,
  TTL_SEGUNDOS,
  firmarSesion,
  opcionesCookie,
} from "@/server/auth/session";
import { getUserByEmail } from "@/server/users/repo";

export const runtime = "nodejs"; // scrypt vive en node:crypto
export const dynamic = "force-dynamic";

/**
 * Hash válido de una contraseña aleatoria que nadie conoce.
 *
 * Se verifica contra este cuando el email NO existe, para que un login fallido
 * cueste lo mismo exista o no la cuenta. Sin esto, el tiempo de respuesta
 * delataría qué emails están dados de alta (unos 100 ms de diferencia, de sobra
 * para medirlo desde fuera).
 */
const HASH_SENUELO =
  "scrypt$32768$8$1$gSNddSLTqagMjNurrG7CkA==$7C/uemeF0GLOEDZaaoEuTlkLHIjzvLCWwV3sKwPTeok=";

/** POST /api/auth/login — { email, password } → cookie de sesión. */
export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "json_invalido" }, { status: 400 });
  }

  const b = (body ?? {}) as Record<string, unknown>;
  const email = typeof b.email === "string" ? b.email.trim() : "";
  const password = typeof b.password === "string" ? b.password : "";
  if (!email || !password) {
    return NextResponse.json({ error: "credenciales_invalidas" }, { status: 401 });
  }

  try {
    const usuario = await getUserByEmail(email);
    const valida = await verifyPassword(
      password,
      usuario?.passwordHash ?? HASH_SENUELO,
    );

    // Mismo cuerpo y mismo código tanto si el email no existe como si la
    // contraseña es incorrecta: el panel no confirma qué cuentas hay.
    if (!usuario || !valida) {
      return NextResponse.json(
        { error: "credenciales_invalidas" },
        { status: 401 },
      );
    }

    const sesion: Sesion = {
      id: usuario.id,
      email: usuario.email,
      nombre: usuario.nombre,
      rol: usuario.rol,
    };
    const res = NextResponse.json<Sesion>(sesion);
    res.cookies.set(COOKIE_SESION, await firmarSesion(sesion), opcionesCookie(TTL_SEGUNDOS));
    return res;
  } catch (err) {
    // Si n8n está caído no se puede ni entrar: la tabla de usuarios vive detrás
    // de él. Se devuelve 503, no un 401 engañoso.
    //
    // Pero SIN el `detalle`: esta ruta está exenta del middleware, así que la
    // llama cualquiera desde internet sin cookie. El mensaje de PanelDbError
    // arrastra hasta 300 caracteres del cuerpo de n8n, que puede incluir el
    // error del nodo Postgres (nombres de tabla, host, usuario de la base). Es
    // justo lo que /api/health se molesta en ocultar a quien no tiene sesión.
    // El motivo real queda en los logs del servidor, que sí puedes leer.
    console.error("[login] fallo al consultar usuarios:", err);
    return NextResponse.json(
      {
        error: "no_disponible",
        detalle:
          "No se puede iniciar sesión ahora mismo: el panel no consigue consultar la base de datos.",
      },
      { status: 503 },
    );
  }
}

/** GET /api/auth/login — quién soy. Útil para depurar la sesión desde curl. */
export async function GET() {
  const g = await exigirSesion();
  return g.ok ? NextResponse.json(g.sesion) : g.res;
}

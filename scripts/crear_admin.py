"""
Crea un usuario administrador, o asciende a admin uno que ya exista.

Por que existe: el panel de administracion ya permite a un admin cambiar el rol
de cualquiera (PATCH /admin/usuarios/{id}), pero eso no resuelve el arranque en
frio --hace falta ser admin para usarlo--, y POST /registro fija
`rol="biologo"` a pelo. El PRIMER administrador solo puede salir de la base de
datos, y hacerlo con SQL a mano obliga a acordarse de tres cosas que no son
obvias y que dejan la cuenta inservible si se olvidan: marcar
`email_verificado` (sin el, /login responde 403), dejar `activo` en cierto (una
cuenta desactivada no pasa de obtener_usuario_actual) y hashear la contraseña
con bcrypt exactamente como lo hace app/auth.py.

Funciona contra la base de datos que diga DATABASE_URL (app/config.py), igual
que scripts/migrate.py: SQLite en local, PostgreSQL dentro de Docker.

Uso:
    # Ver quien hay y con que rol
    python scripts/crear_admin.py --listar

    # Ascender una cuenta que ya existe (lo habitual)
    python scripts/crear_admin.py --email tu@correo.com

    # Crear una cuenta nueva ya verificada y con rol admin
    python scripts/crear_admin.py --email admin@local --nombre "Admin" --crear

    # Dentro de Docker, contra la base de datos real
    docker compose exec backend python scripts/crear_admin.py --email tu@correo.com

La contraseña NUNCA se pasa por la linea de comandos: se pide por teclado y no
se muestra, para que no quede en el historial del shell. Solo hace falta con
--crear; ascender a un usuario existente no la toca.
"""
import argparse
import getpass
import os
import sys

# Igual que en scripts/migrate.py: permite invocarlo desde cualquier directorio.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import models  # noqa: E402
from app.auth import hash_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402

LONGITUD_MINIMA_PASSWORD = 8  # la misma que exige schemas.UsuarioRegistro


def listar(db) -> None:
    usuarios = db.query(models.Usuario).order_by(models.Usuario.id).all()
    if not usuarios:
        print("No hay ningún usuario en la base de datos.")
        return

    print(f"{'id':>4}  {'rol':<8} {'verif':<6} {'activa':<7} email")
    print("-" * 68)
    for u in usuarios:
        rol = u.rol.value if u.rol else "biologo"
        print(f"{u.id:>4}  {rol:<8} {'sí' if u.email_verificado else 'no':<6} "
              f"{'sí' if u.activo else 'NO':<7} {u.email}")

    admins = [u for u in usuarios if u.rol and u.rol.value == "admin"]
    print(f"\n{len(admins)} admin(s) de {len(usuarios)} usuario(s).")


def pedir_password() -> str:
    """Pide la contraseña dos veces y sin eco. Solo se usa con --crear."""
    if not sys.stdin.isatty():
        sys.exit(
            "Para --crear hace falta una terminal interactiva donde teclear la "
            "contraseña.\nDentro de Docker, usa: docker compose exec backend "
            "python scripts/crear_admin.py ..."
        )
    while True:
        password = getpass.getpass("Contraseña para la cuenta nueva: ")
        if len(password) < LONGITUD_MINIMA_PASSWORD:
            print(f"Demasiado corta: mínimo {LONGITUD_MINIMA_PASSWORD} caracteres.")
            continue
        if password != getpass.getpass("Repítela: "):
            print("No coinciden.")
            continue
        return password


def ascender(db, usuario) -> None:
    """Pone rol=admin y, si hacía falta, marca el correo como verificado."""
    cambios = []

    if usuario.rol and usuario.rol.value == "admin":
        print(f"'{usuario.email}' ya era admin.")
    else:
        usuario.rol = models.RolUsuario.admin
        cambios.append("rol -> admin")

    # Sin esto la cuenta existe pero no puede iniciar sesión: /login devuelve
    # 403 mientras el correo no esté confirmado.
    if not usuario.email_verificado:
        usuario.email_verificado = True
        usuario.token_verificacion = None
        cambios.append("correo marcado como verificado")

    # Una cuenta desactivada no pasa de obtener_usuario_actual (app/auth.py),
    # asi que ascenderla sin reactivarla daria un admin que no puede entrar.
    if not usuario.activo:
        usuario.activo = True
        cambios.append("cuenta reactivada")

    if cambios:
        db.commit()
        print(f"'{usuario.email}' actualizado: " + ", ".join(cambios) + ".")


def crear(db, email: str, nombre: str) -> None:
    password = pedir_password()
    usuario = models.Usuario(
        nombre=nombre,
        email=email,
        password_hash=hash_password(password),
        rol=models.RolUsuario.admin,
        email_verificado=True,
        token_verificacion=None,
        activo=True,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    print(f"Admin creado: {usuario.email} (id {usuario.id}).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crea un administrador o asciende a admin un usuario existente.",
    )
    parser.add_argument("--email", help="correo de la cuenta")
    parser.add_argument("--nombre", default="Administrador",
                        help="nombre a mostrar (solo al crear una cuenta nueva)")
    parser.add_argument("--crear", action="store_true",
                        help="crea la cuenta si no existe, pidiendo la contraseña por teclado")
    parser.add_argument("--listar", action="store_true",
                        help="muestra los usuarios y sus roles, y no cambia nada")
    args = parser.parse_args()

    if not args.listar and not args.email:
        parser.error("hace falta --email (o --listar para ver qué hay).")

    db = SessionLocal()
    try:
        if args.listar:
            listar(db)
            return

        email = args.email.strip().lower()
        usuario = db.query(models.Usuario).filter(models.Usuario.email == email).first()

        if usuario is not None:
            ascender(db, usuario)
        elif args.crear:
            crear(db, email, args.nombre)
        else:
            # No se crea nada sin pedirlo: un correo mal escrito en --email es
            # mucho mas probable que la intencion de dar de alta un admin nuevo.
            sys.exit(
                f"No existe ningún usuario con el correo '{email}'.\n"
                f"Si quieres crearlo, añade --crear. Para ver los que hay: "
                f"python scripts/crear_admin.py --listar"
            )

        print("\nSi esa cuenta tenía la sesión abierta, ciérrala y vuelve a entrar: "
              "el enlace 'Sistema' del menú se decide con el rol que venía en el "
              "token del último login.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

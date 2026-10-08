"""Crea un usuario del panel interno (administrador o agente). Sin esto nadie
puede iniciar sesión (los clientes de Easy Office nunca tienen cuenta).

Uso (con los contenedores levantados):
    docker compose exec backend python scripts/crear_user.py <rol> "Nombre Apellido" correo@easyoffice.cl
    (pide la contraseña sin mostrarla en pantalla)

<rol> es "administrador" o "agente", tal como está cargado en la tabla rol
(ver db/init/02_seed.sql).
"""
import getpass
import sys
from pathlib import Path

# Permite importar "app" al correr el script directamente.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.seguridad import hash_password  # noqa: E402
from app.utils import normalizar_email, tiene_alias_mas  # noqa: E402

# Política para cuentas reales: más estricta que el login, que solo valida el
# largo para no revelarle la política a un atacante.
_LONGITUD_MINIMA = 12
_ROLES_VALIDOS = ("administrador", "agente")


def main() -> None:
    if len(sys.argv) != 4 or sys.argv[1] not in _ROLES_VALIDOS:
        print(__doc__)
        raise SystemExit(1)

    nombre_rol, nombre, email = sys.argv[1], sys.argv[2], normalizar_email(sys.argv[3])
    if tiene_alias_mas(email):
        print("No se permiten direcciones con '+' (ej: admin+test@x.cl). Usa el correo real.")
        raise SystemExit(1)

    password = getpass.getpass("Contraseña: ")
    if len(password) < _LONGITUD_MINIMA:
        print(f"La contraseña debe tener al menos {_LONGITUD_MINIMA} caracteres.")
        raise SystemExit(1)
    if password != getpass.getpass("Repite la contraseña: "):
        print("Las contraseñas no coinciden.")
        raise SystemExit(1)

    db = SessionLocal()
    try:
        if db.query(models.Usuario).filter(models.Usuario.email == email).first() is not None:
            print(f"Ya existe un usuario con el email {email}.")
            raise SystemExit(1)

        rol = db.query(models.Rol).filter(models.Rol.nombre == nombre_rol).first()
        if rol is None:
            print(f"No existe el rol '{nombre_rol}'. Revisa que se haya cargado db/init/02_seed.sql.")
            raise SystemExit(1)

        db.add(models.Usuario(
            nombre=nombre,
            email=email,
            password_hash=hash_password(password),
            id_rol=rol.id_rol,
        ))
        db.commit()
        print(f"Usuario '{nombre_rol}' creado: {email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

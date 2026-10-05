"""Crea un usuario administrador. Sin esto nadie puede iniciar sesión en el panel
(los clientes de Easy Office nunca tienen cuenta).

Uso (con los contenedores levantados):
    docker compose exec backend python scripts/crear_admin.py "Nombre Apellido" correo@easyoffice.cl
    (pide la contraseña sin mostrarla en pantalla)
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


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)

    nombre, email = sys.argv[1], normalizar_email(sys.argv[2])
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

        rol_admin = db.query(models.Rol).filter(models.Rol.nombre == "administrador").first()
        if rol_admin is None:
            print("No existe el rol 'administrador'. Revisa que se haya cargado db/init/02_seed.sql.")
            raise SystemExit(1)

        db.add(models.Usuario(
            nombre=nombre,
            email=email,
            password_hash=hash_password(password),
            id_rol=rol_admin.id_rol,
        ))
        db.commit()
        print(f"Administrador creado: {email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

"""Crea el primer usuario administrador. Sin esto nadie puede hacer login
(los clientes de Easy Office nunca tienen cuenta).

Uso:
    python scripts/crear_admin.py "Nombre Apellido" correo@easyoffice.cl
    (pide la contraseña de forma interactiva, sin mostrarla en pantalla)
"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.email_utils import normalizar_email, tiene_alias_mas
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.rol import Rol
from app.models.usuario import Usuario

# Política de contraseña para cuentas reales (más estricta que el login, que
# solo valida longitud para no revelar la política a un atacante).
_LONGITUD_MINIMA = 12


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)

    nombre, email = sys.argv[1], normalizar_email(sys.argv[2])
    if tiene_alias_mas(email):
        print(
            "No se permiten direcciones con '+' (alias de buzón, ej: admin+test@x.cl). "
            "Usa el correo real sin el signo '+'."
        )
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
        if db.query(Usuario).filter(Usuario.email == email).first() is not None:
            print(f"Ya existe un usuario con el email {email}.")
            raise SystemExit(1)

        rol_admin = db.query(Rol).filter(Rol.nombre == "administrador").first()
        if rol_admin is None:
            print("No existe el rol 'administrador'. Corre las migraciones primero: alembic upgrade head")
            raise SystemExit(1)

        usuario = Usuario(
            nombre=nombre,
            email=email,
            password_hash=hash_password(password),
            id_rol=rol_admin.id_rol,
        )
        db.add(usuario)
        db.commit()
        print(f"Administrador creado: {email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

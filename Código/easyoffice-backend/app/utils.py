"""Utilidades pequeñas compartidas por schemas y crud."""


def normalizar_email(email: str) -> str:
    """Minúsculas y sin espacios. Es la forma en que se guarda y se busca el
    email en el login, para que 'Admin@X.cl' y 'admin@x.cl' sean la misma
    cuenta (y no dos filas distintas que se saltan el UNIQUE)."""
    return email.strip().lower()


def tiene_alias_mas(email: str) -> bool:
    """Detecta direcciones con '+' en la parte local (ej: admin+test@x.cl).
    Muchos proveedores entregan admin+test@x.cl en la misma bandeja que
    admin@x.cl; si se aceptaran, una persona podría tener varias cuentas."""
    return "+" in email.split("@", 1)[0]


def normalizar_rut(rut: str | None) -> str | None:
    """Quita puntos y espacios, pasa a mayúsculas (para el dígito verificador 'k'),
    y convierte un string vacío en None. Así '12.345.678-9', '12345678-9 ' y
    '12345678-9' se guardan y comparan siempre de la misma forma, evitando
    clientes duplicados por RUT con distinto formato."""
    if rut is None:
        return None
    limpio = rut.strip().replace(".", "").replace(" ", "").upper()
    return limpio or None
def normalizar_email(email: str) -> str:
    """Minúsculas + sin espacios. Es la forma canónica que se guarda y con la
    que se busca en login, para que 'Admin@X.cl' y 'admin@x.cl' sean la misma
    cuenta (y no dos filas distintas que bypasean el UNIQUE)."""
    return email.strip().lower()


def tiene_alias_mas(email: str) -> bool:
    """Detecta direcciones con '+' en la parte local (ej: admin+test@x.cl).

    Muchos proveedores (Gmail y otros) entregan admin+test@x.cl en la MISMA
    bandeja que admin@x.cl. Si el sistema las tratara como cuentas distintas,
    una sola persona podría terminar con varias cuentas "únicas" que en
    realidad son la misma identidad -> se rechazan al crear la cuenta.
    """
    local = email.split("@", 1)[0]
    return "+" in local

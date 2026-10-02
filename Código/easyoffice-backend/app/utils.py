"""Utilidades pequeñas compartidas por schemas y crud."""


def normalizar_rut(rut: str | None) -> str | None:
    """Quita puntos y espacios, pasa a mayúsculas (para el dígito verificador 'k'),
    y convierte un string vacío en None. Así '12.345.678-9', '12345678-9 ' y
    '12345678-9' se guardan y comparan siempre de la misma forma, evitando
    clientes duplicados por RUT con distinto formato."""
    if rut is None:
        return None
    limpio = rut.strip().replace(".", "").replace(" ", "").upper()
    return limpio or None
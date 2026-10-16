"""
Reglas de las condiciones del contrato que fija el agente al convertir una solicitud: valores permitidos, cálculo del vencimiento 
y folio automático.

Los valores permitidos salen de la planilla de Easy Office (hoja INFORMACIONES). Si ellos cambian algún ciclo o duración, se ajusta aquí 
y en nada más.
"""
import calendar
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app import models

CICLOS_PAGO = ("ÚNICO", "ANUAL", "SEMESTRAL", "TRIMESTRAL", "MENSUAL")
DURACIONES_MESES = (12, 6, 4, 3, 1)
MAX_SERVICIOS = 3
PRECIO_MAXIMO = 100_000_000


def normalizar_ciclo(valor: str) -> str:
    """'unico', 'Único' y 'ÚNICO' son el mismo ciclo; el resto, en mayúsculas."""
    ciclo = valor.strip().upper()
    return "ÚNICO" if ciclo == "UNICO" else ciclo


def sumar_meses(base: date, meses: int) -> tuple[date, bool]:
    """
    Suma meses de calendario. Devuelve (fecha, recortada): `recortada` es True si el día no existía en el mes de destino (31-ene + 1 mes) 
    y se usó el último día de ese mes.
    """
    indice = base.month - 1 + meses
    anio, mes = base.year + indice // 12, indice % 12 + 1
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    dia = min(base.day, ultimo_dia)
    return date(anio, mes, dia), dia != base.day


def calcular_vencimiento(inicio: date, duracion_meses: int) -> date:
    """
    Mismo día N meses después, menos un día (15-ene-2026 + 12 meses -> 14-ene-2027). Si el día no existe en el mes de destino, vence el 
    último día de ese mes. Es solo una propuesta: no considera feriados ni días hábiles, el agente la revisa.
    """
    destino, recortada = sumar_meses(inicio, duracion_meses)
    return destino if recortada else destino - timedelta(days=1)


def siguiente_folio(db: Session, sucursal: models.Sucursal, anio: int) -> str:
    """
    Folio 'LF-01-2026': iniciales de la sucursal, correlativo de esa sucursal en ese año (2 dígitos mínimo, sigue creciendo: 99 -> 100) 
    y año. La unicidad la garantiza la base (índice único); si dos agentes calculan el mismo número a la vez, el segundo en guardar 
    recibe el conflicto.
    """
    prefijo, sufijo = f"{sucursal.iniciales}-", f"-{anio}"
    existentes = (
        db.query(models.Tramite.folio)
        .filter(models.Tramite.id_sucursal == sucursal.id_sucursal)
        .filter(models.Tramite.folio.like(f"{prefijo}%{sufijo}"))
        .all()
    )
    mayor = 0
    for (folio,) in existentes:
        numero = folio[len(prefijo):-len(sufijo)]
        if numero.isdigit():
            mayor = max(mayor, int(numero))
    return f"{prefijo}{mayor + 1:02d}{sufijo}"
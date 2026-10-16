from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import condiciones, models, schemas
from app.database import get_db
from app.seguridad import get_usuario_actual

router = APIRouter(prefix="/api", tags=["catalogos"])


@router.get("/sucursales", response_model=list[schemas.SucursalOut])
def listar_sucursales(
    db: Session = Depends(get_db),
    _usuario: models.Usuario = Depends(get_usuario_actual),
):
    """
    Uso del panel de agentes/admins (requiere login): sucursales activas de Easy Office, para elegir en qué sucursal se firma el contrato.
    """
    consulta = (
        select(models.Sucursal)
        .where(models.Sucursal.activa.is_(True))
        .order_by(models.Sucursal.nombre)
    )
    return db.scalars(consulta).all()


@router.get("/servicios-ofrecidos", response_model=list[schemas.ServicioOfrecidoOut])
def listar_servicios_ofrecidos(
    db: Session = Depends(get_db),
    _usuario: models.Usuario = Depends(get_usuario_actual),
):
    """
    Uso del panel de agentes/admins (requiere login): catálogo de servicios activos que vende Easy Office, con precio y ciclo de 
    pago de referencia.

    """
    consulta = (
        select(models.ServicioOfrecido)
        .where(models.ServicioOfrecido.activo.is_(True))
        .order_by(models.ServicioOfrecido.nombre)
    )
    return db.scalars(consulta).all()



@router.get("/opciones-contrato", response_model=schemas.OpcionesContratoOut)
def opciones_contrato(_usuario: models.Usuario = Depends(get_usuario_actual)):
    """
    Uso del panel de agentes/admins (requiere login): ciclos de pago, duraciones y máximo de servicios permitidos, para que el panel 
    no los repita a mano.
    """
    return schemas.OpcionesContratoOut(
        ciclos_pago=list(condiciones.CICLOS_PAGO),
        duraciones_meses=list(condiciones.DURACIONES_MESES),
        max_servicios=condiciones.MAX_SERVICIOS,
    )
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/api/solicitudes-contacto", tags=["solicitudes-contacto"])


@router.post("", response_model=schemas.SolicitudContactoOut, status_code=status.HTTP_201_CREATED)
def crear_solicitud_contacto(datos: schemas.SolicitudContactoCreate, db: Session = Depends(get_db)):
    """Público — usado por el formulario 'Contrata aquí' del sitio easyoffice-web.
    No genera código de seguimiento; solo deja la solicitud para que un agente
    la gestione y confirme el pago manual."""
    if datos.servicio_id is not None and not crud.servicio_existe(db, datos.servicio_id):
        raise HTTPException(status_code=404, detail="El servicio indicado no existe.")
    return crud.crear_solicitud(db, datos)


@router.post("/{id_solicitud}/convertir", response_model=schemas.TramiteOut)
def convertir_solicitud(
    id_solicitud: int,
    datos: schemas.ConvertirSolicitudRequest,
    db: Session = Depends(get_db),
):
    """Uso del panel de agentes (no del sitio público): confirma que el pago
    manual fue recibido y convierte la solicitud en un trámite real, generando
    el código de 8 caracteres que luego el agente entrega al cliente."""
    solicitud = crud.obtener_solicitud(db, id_solicitud)
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada.")

    try:
        tramite = crud.convertir_solicitud_a_tramite(
            db, solicitud, datos.id_usuario_responsable
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        # No se pudo generar un código único tras varios intentos: no es un
        # error del cliente, pero tampoco debe salir como 500 sin mensaje.
        raise HTTPException(status_code=500, detail=str(e))

    return schemas.TramiteOut(
        id_tramite=tramite.id_tramite,
        codigo_seguimiento=tramite.codigo_seguimiento,
        estado_actual=tramite.estado_actual,
        nombre_servicio=tramite.servicio.nombre,
    )
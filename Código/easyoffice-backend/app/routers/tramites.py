from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app import campos_servicio, crud, models, schemas
from app.database import get_db
from app.seguridad import get_usuario_actual, limiter

router = APIRouter(prefix="/api/tramites", tags=["tramites"])


@router.get("", response_model=schemas.TramitesPaginaOut)
def listar_tramites(
    servicio_id: Optional[int] = Query(default=None, ge=1),
    estado: Optional[str] = Query(default=None, max_length=30),
    agente_id: Optional[int] = Query(default=None, ge=1),
    q: Optional[str] = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _usuario: models.Usuario = Depends(get_usuario_actual),
):
    """Uso del panel de agentes/admins (requiere login): lista los trámites, los más recientemente actualizados primero. 
    Devuelve datos de clientes, por eso NO puede quedar público. Filtros opcionales: ?servicio_id, ?estado, ?agente_id y ?q 
    (nombre o RUT del cliente, o código del trámite)."""
    return crud.listar_tramites(
        db,
        servicio_id=servicio_id,
        estado=estado,
        agente_id=agente_id,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/resumen", response_model=schemas.TramitesResumenOut)
def resumen_tramites(
    db: Session = Depends(get_db),
    _usuario: models.Usuario = Depends(get_usuario_actual),
):
    """Uso del panel (requiere login): KPIs de la cabecera y las opciones de los filtros (servicios y agentes activos). 
    Solo números y nombres."""
    return crud.resumen_tramites(db)


@router.get("/codigo/{codigo}", response_model=schemas.SeguimientoOut)
@limiter.limit("30/minute")
def consultar_tramite_por_codigo(request: Request, codigo: str, db: Session = Depends(get_db)):
    """Público — usado por la página de seguimiento del sitio easyoffice-web.
    Limitado por IP: el código es la única credencial, así que se frena el que pruebe códigos a ciegas."""
    if len(codigo.strip()) != 8:
        raise HTTPException(status_code=400, detail="El código debe tener 8 caracteres.")

    tramite = crud.obtener_tramite_por_codigo(db, codigo)
    if not tramite:
        raise HTTPException(status_code=404, detail="No encontramos un trámite con ese código.")

    return schemas.SeguimientoOut(
        codigo_seguimiento=tramite.codigo_seguimiento,
        nombre_servicio=tramite.servicio.nombre,
        estado_actual=tramite.estado_actual,
        documento_disponible=crud.documento_disponible(tramite),
    )

@router.get("/codigo/{codigo}/formulario", response_model=schemas.FormularioOut)
@limiter.limit("30/minute")
def obtener_formulario_cliente(request: Request, codigo: str, db: Session = Depends(get_db)):
    """Público — el cliente entra con su código de seguimiento (no tiene cuenta).

    Devuelve los campos que debe completar según su servicio. Si su empresa ya estaba vinculada, los datos que ya existen 
    salen ENMASCARADOS y marcados como registrados; nunca completos. Si ya envió sus datos, solo informa el estado.
    Límite de 30 consultas por minuto por IP (el código es la única credencial)."""
    if len(codigo.strip()) != 8:
        raise HTTPException(status_code=400, detail="El código debe tener 8 caracteres.")

    tramite = crud.obtener_tramite_por_codigo(db, codigo)
    if not tramite:
        raise HTTPException(status_code=404, detail="No encontramos un trámite con ese código.")

    return crud.obtener_formulario(tramite)

@router.post("/codigo/{codigo}/datos", response_model=schemas.SeguimientoOut)
@limiter.limit("10/minute")
def enviar_datos_cliente(
    request: Request,
    codigo: str,
    envio: schemas.EnvioDatosIn,
    db: Session = Depends(get_db),
):
    """Público — el cliente envía UNA sola vez los datos que faltan de su empresa.

    Exige el consentimiento y la confirmación de que no podrá editar. Si hay campos con errores responde 422 con todos 
    juntos ({"mensaje", "errores"}); si el trámite ya recibió datos, ya no admite envíos o el RUT no se puede registrar, responde 409. 
    Devuelve solo el estado del trámite, nunca los datos ingresados. Límite de 10 envíos por minuto por IP."""
    if len(codigo.strip()) != 8:
        raise HTTPException(status_code=400, detail="El código debe tener 8 caracteres.")

    tramite = crud.obtener_tramite_por_codigo(db, codigo)
    if not tramite:
        raise HTTPException(status_code=404, detail="No encontramos un trámite con ese código.")

    try:
        tramite = crud.registrar_envio_datos(db, tramite, envio)
    except campos_servicio.ErrorCampos as e:
        raise HTTPException(
            status_code=422,
            detail={"mensaje": "Revisa los campos marcados.", "errores": e.errores},
        )
    except crud.EnvioDatosRechazado as e:
        raise HTTPException(status_code=409, detail=e.mensaje)

    return schemas.SeguimientoOut(
        codigo_seguimiento=tramite.codigo_seguimiento,
        nombre_servicio=tramite.servicio.nombre,
        estado_actual=tramite.estado_actual,
        documento_disponible=crud.documento_disponible(tramite),
    )
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/api/tramites", tags=["tramites"])


@router.get("/codigo/{codigo}", response_model=schemas.SeguimientoOut)
def consultar_tramite_por_codigo(codigo: str, db: Session = Depends(get_db)):
    """Público — usado por la página de seguimiento del sitio easyoffice-web."""
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
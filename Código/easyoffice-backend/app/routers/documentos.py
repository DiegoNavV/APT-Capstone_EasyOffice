from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import documentos, models, schemas
from app.database import get_db
from app.seguridad import get_usuario_actual

router = APIRouter(prefix="/api/tramites", tags=["documentos"])


def _tramite_o_404(db: Session, id_tramite: int) -> models.Tramite:
    tramite = db.get(models.Tramite, id_tramite)
    if tramite is None:
        raise HTTPException(status_code=404, detail="Trámite no encontrado.")
    return tramite


@router.post("/{id_tramite}/documento", response_model=schemas.DocumentoGeneradoOut)
def generar_documento(
    id_tramite: int,
    db: Session = Depends(get_db),
    _usuario: models.Usuario = Depends(get_usuario_actual),
):
    """
    Panel (requiere login): genera el PDF del trámite con la plantilla activa de su servicio. Si ya existía uno, lo reemplaza. 
    Responde 409 si no hay plantilla o el trámite ya está firmado, 422 si faltan datos (con la lista) y 502 si falla la conversión a PDF.
    """
    tramite = _tramite_o_404(db, id_tramite)
    try:
        return documentos.generar(db, tramite)
    except documentos.DocumentoNoGenerable as e:
        detalle = {"mensaje": e.mensaje, "faltantes": e.faltantes} if e.faltantes else e.mensaje
        raise HTTPException(status_code=e.codigo_http, detail=detalle)


@router.get("/{id_tramite}/documento")
def descargar_documento(
    id_tramite: int,
    db: Session = Depends(get_db),
    _usuario: models.Usuario = Depends(get_usuario_actual),
):
    """Panel (requiere login): descarga el último PDF generado del trámite."""
    tramite = _tramite_o_404(db, id_tramite)
    ruta = documentos.ruta_del_documento(tramite)
    if ruta is None:
        raise HTTPException(status_code=404, detail="Este trámite todavía no tiene un documento generado.")
    return FileResponse(ruta, media_type="application/pdf", filename=documentos.nombre_para_descargar(tramite))
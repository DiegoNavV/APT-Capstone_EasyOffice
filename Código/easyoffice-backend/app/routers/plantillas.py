from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import models, plantillas, schemas
from app.database import get_db
from app.marcas_documento import (
    CATALOGO_MARCAS, MAX_TAMANO_BYTES, PlantillaInvalida,
)
from app.seguridad import get_usuario_actual

router = APIRouter(prefix="/api/plantillas", tags=["plantillas"])

_TIPO_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _salida(p: models.PlantillaDocumento) -> schemas.PlantillaOut:
    return schemas.PlantillaOut(
        id_plantilla=p.id_plantilla,
        id_servicio=p.id_servicio,
        nombre_servicio=p.servicio.nombre,
        nombre=p.nombre,
        version=p.version,
        activa=p.activa,
        fecha_creacion=p.fecha_creacion,
        nombre_original=p.nombre_original,
        tamano_bytes=p.tamano_bytes,
        hash_sha256=p.hash_sha256,
        marcas=p.marcas or [],
        subida_por=p.usuario_subio.nombre if p.usuario_subio else None,
    )


@router.get("/configuracion", response_model=schemas.ConfiguracionPlantillasOut)
def configuracion(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(get_usuario_actual),
):
    """
    Disponible para cualquier usuario con sesión: dice si puede gestionar plantillas y, si puede, entrega los servicios 
    y las marcas disponibles.
    """
    if not plantillas.puede_gestionar(usuario):
        return schemas.ConfiguracionPlantillasOut(
            puede_gestionar=False, max_tamano_mb=0, servicios=[], marcas=[]
        )
    servicios = (
        db.query(models.ServicioContratado)
        .filter(models.ServicioContratado.activo.is_(True))
        .order_by(models.ServicioContratado.id_servicio)
        .all()
    )
    return schemas.ConfiguracionPlantillasOut(
        puede_gestionar=True,
        max_tamano_mb=MAX_TAMANO_BYTES // (1024 * 1024),
        servicios=[{"id_servicio": s.id_servicio, "nombre": s.nombre} for s in servicios],
        marcas=[schemas.MarcaOut(nombre=n, descripcion=d) for n, d in CATALOGO_MARCAS.items()],
    )


@router.get("", response_model=list[schemas.PlantillaOut])
def listar_plantillas(
    id_servicio: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _usuario: models.Usuario = Depends(plantillas.requiere_gestor_plantillas),
):
    return [_salida(p) for p in plantillas.listar(db, id_servicio)]


@router.post("", response_model=schemas.PlantillaOut, status_code=201)
async def subir_plantilla(
    id_servicio: int = Form(),
    nombre: str | None = Form(default=None, max_length=150),
    activar: bool = Form(default=True),
    archivo: UploadFile = File(),
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(plantillas.requiere_gestor_plantillas),
):
    """
    Sube una versión nueva de la plantilla de un servicio. Con `activar` (por defecto) pasa a ser la versión en uso y la 
    anterior queda guardada.
    """
    servicio = db.get(models.ServicioContratado, id_servicio)
    if servicio is None or not servicio.activo:
        raise HTTPException(status_code=404, detail="El servicio no existe o no está activo.")

    nombre_original = (archivo.filename or "plantilla.docx").strip()
    if not nombre_original.lower().endswith(".docx"):
        raise HTTPException(status_code=422, detail="El archivo debe ser un documento Word (.docx).")

    # Se lee un byte de más para detectar archivos que superan el máximo sin
    # cargar un archivo enorme completo en memoria.
    contenido = await archivo.read(MAX_TAMANO_BYTES + 1)
    nombre_final = (nombre or "").strip() or servicio.nombre

    try:
        plantilla = plantillas.crear_version(
            db, servicio, nombre_final, nombre_original, contenido, usuario, activar
        )
    except PlantillaInvalida as e:
        raise HTTPException(status_code=422, detail=str(e))
    except plantillas.ConflictoDePlantilla as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _salida(plantilla)


@router.post("/{id_plantilla}/activar", response_model=schemas.PlantillaOut)
def activar_plantilla(
    id_plantilla: int,
    db: Session = Depends(get_db),
    _usuario: models.Usuario = Depends(plantillas.requiere_gestor_plantillas),
):
    plantilla = db.get(models.PlantillaDocumento, id_plantilla)
    if plantilla is None:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada.")
    try:
        plantilla = plantillas.activar(db, plantilla)
    except plantillas.ConflictoDePlantilla as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _salida(plantilla)


@router.get("/{id_plantilla}/descargar")
def descargar_plantilla(
    id_plantilla: int,
    db: Session = Depends(get_db),
    _usuario: models.Usuario = Depends(plantillas.requiere_gestor_plantillas),
):
    plantilla = db.get(models.PlantillaDocumento, id_plantilla)
    if plantilla is None:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada.")
    ruta = plantillas.ruta_absoluta(plantilla)
    if not ruta.is_file():
        raise HTTPException(status_code=404, detail="Archivo de plantilla no disponible.")
    return FileResponse(
        ruta,
        media_type=_TIPO_DOCX,
        filename=f"{plantilla.servicio.nombre} v{plantilla.version}.docx",
    )
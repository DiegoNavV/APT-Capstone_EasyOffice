"""
Plantillas de documentos: quién puede gestionarlas, dónde se guardan los archivos y cómo se crean/activan las versiones.

Reglas:
  - Cada archivo subido es una VERSIÓN nueva del servicio (1, 2, 3...).
  - Las versiones anteriores se conservan siempre (trazabilidad). No hay borrado.
  - Solo una versión por servicio está activa; esa es la que usará la generación de documentos.
  - Los archivos se guardan en PLANTILLAS_DIR (un volumen de Docker), fuera de Git, para que las plantillas reales de Easy Office 
    nunca queden públicas.
"""
import hashlib
import os
import uuid
from pathlib import Path

from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.marcas_documento import revisar_docx
from app.seguridad import get_usuario_actual

# SUPUESTO A CONFIRMAR CON EASY OFFICE: hoy solo el administrador gestiona plantillas. Si deciden que también lo hagan los 
# agentes, se cambia SIN tocar código: ROLES_GESTORES_PLANTILLAS="administrador,agente" en el .env.
ROLES_GESTORES_POR_DEFECTO = "administrador"


class ConflictoDePlantilla(Exception):
    """La operación choca con el estado actual (archivo repetido, versión
    simultánea). El mensaje se muestra al usuario."""


def roles_gestores() -> set[str]:
    crudo = os.getenv("ROLES_GESTORES_PLANTILLAS", ROLES_GESTORES_POR_DEFECTO)
    return {r.strip().lower() for r in crudo.split(",") if r.strip()}


def puede_gestionar(usuario: models.Usuario) -> bool:
    return usuario.rol_nombre.lower() in roles_gestores()


def requiere_gestor_plantillas(
    usuario: models.Usuario = Depends(get_usuario_actual),
) -> models.Usuario:
    if not puede_gestionar(usuario):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para gestionar plantillas.",
        )
    return usuario


def directorio_plantillas() -> Path:
    # Se lee en cada uso (no al importar) para que las pruebas puedan cambiarlo.
    return Path(os.getenv("PLANTILLAS_DIR", "/app/plantillas"))


def ruta_absoluta(plantilla: models.PlantillaDocumento) -> Path:
    """Ruta real del archivo. Se verifica que quede dentro de PLANTILLAS_DIR,
    por si alguna vez la ruta guardada en la base fuera manipulada."""
    base = directorio_plantillas().resolve()
    ruta = (base / plantilla.ruta_archivo).resolve()
    if base not in ruta.parents:
        raise HTTPException(status_code=404, detail="Archivo de plantilla no disponible.")
    return ruta


def _numero_de_version(texto: str) -> int:
    try:
        return int(float(texto))
    except ValueError:
        return 0


def listar(db: Session, id_servicio: int | None = None) -> list[models.PlantillaDocumento]:
    q = db.query(models.PlantillaDocumento)
    if id_servicio is not None:
        q = q.filter(models.PlantillaDocumento.id_servicio == id_servicio)
    filas = q.all()
    # Por servicio, la versión más nueva primero.
    filas.sort(key=lambda p: (p.id_servicio, -_numero_de_version(p.version)))
    return filas


def crear_version(
    db: Session,
    servicio: models.ServicioContratado,
    nombre: str,
    nombre_original: str,
    contenido: bytes,
    usuario: models.Usuario,
    activar: bool,
) -> models.PlantillaDocumento:
    """
    Valida el archivo (PlantillaInvalida si no sirve), lo guarda en disco y registra la versión nueva. Si `activar`,
    deja las demás versiones inactivas.
    """
    marcas = revisar_docx(contenido)
    hash_archivo = hashlib.sha256(contenido).hexdigest()

    existentes = (
        db.query(models.PlantillaDocumento)
        .filter(models.PlantillaDocumento.id_servicio == servicio.id_servicio)
        .all()
    )
    for p in existentes:
        if p.hash_sha256 == hash_archivo:
            raise ConflictoDePlantilla(
                f"Este archivo es idéntico a la versión {p.version} que ya está guardada."
            )
    version = str(max([_numero_de_version(p.version) for p in existentes] + [0]) + 1)

    relativa = f"servicio_{servicio.id_servicio}/v{version}_{uuid.uuid4().hex[:8]}.docx"
    destino = directorio_plantillas() / relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)

    try:
        if activar:
            db.query(models.PlantillaDocumento).filter(
                models.PlantillaDocumento.id_servicio == servicio.id_servicio,
                models.PlantillaDocumento.activa.is_(True),
            ).update({"activa": False})
            db.flush()
        plantilla = models.PlantillaDocumento(
            id_servicio=servicio.id_servicio,
            nombre=nombre,
            version=version,
            ruta_archivo=relativa,
            activa=activar,
            nombre_original=nombre_original[:255],
            hash_sha256=hash_archivo,
            tamano_bytes=len(contenido),
            marcas=marcas,
            id_usuario_subio=usuario.id_usuario,
        )
        db.add(plantilla)
        db.commit()
    except IntegrityError:
        db.rollback()
        destino.unlink(missing_ok=True)
        raise ConflictoDePlantilla(
            "Otra persona subió una versión al mismo tiempo. Intenta de nuevo."
        )
    except Exception:
        db.rollback()
        destino.unlink(missing_ok=True)
        raise
    db.refresh(plantilla)
    return plantilla


def activar(db: Session, plantilla: models.PlantillaDocumento) -> models.PlantillaDocumento:
    """Deja esta versión como la activa de su servicio (las demás pasan a inactivas)."""
    if plantilla.activa:
        return plantilla
    try:
        db.query(models.PlantillaDocumento).filter(
            models.PlantillaDocumento.id_servicio == plantilla.id_servicio,
            models.PlantillaDocumento.activa.is_(True),
        ).update({"activa": False})
        db.flush()
        plantilla.activa = True
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictoDePlantilla("No se pudo activar la versión. Intenta de nuevo.")
    db.refresh(plantilla)
    return plantilla
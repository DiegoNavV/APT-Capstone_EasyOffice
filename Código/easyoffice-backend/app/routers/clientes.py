from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.database import get_db
from app.seguridad import get_usuario_actual

router = APIRouter(prefix="/api/clientes", tags=["clientes"])


@router.get("", response_model=schemas.ClientesPaginaOut)
def listar_clientes(
    q: Optional[str] = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _usuario: models.Usuario = Depends(get_usuario_actual),
):
    """Uso del panel de agentes/admins (requiere login): lista los clientes, los más recientemente creados primero,
    con cuántos trámites tiene cada uno. Devuelve datos de clientes, por eso NO puede quedar público.
    Filtro opcional ?q (nombre o RUT)."""
    return crud.listar_clientes(db, q=q, limit=limit, offset=offset)


@router.get("/{id_cliente}", response_model=schemas.ClienteDetalleOut)
def obtener_cliente(
    id_cliente: int,
    db: Session = Depends(get_db),
    _usuario: models.Usuario = Depends(get_usuario_actual),
):
    """Uso del panel de agentes/admins (requiere login): ficha de cliente 360° -- datos de contacto, empresas
    vinculadas y el historial completo de sus trámites."""
    detalle = crud.obtener_cliente_detalle(db, id_cliente)
    if not detalle:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")
    return detalle

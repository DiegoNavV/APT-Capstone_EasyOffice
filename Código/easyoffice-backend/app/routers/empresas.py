from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.database import get_db
from app.seguridad import get_usuario_actual

router = APIRouter(prefix="/api/empresas", tags=["empresas"])


@router.get("", response_model=list[schemas.EmpresaOpcionOut])
def buscar_empresas(
    q: str = Query(min_length=2, max_length=100),
    db: Session = Depends(get_db),
    _usuario: models.Usuario = Depends(get_usuario_actual),
):
    """Uso del panel de agentes/admins (requiere login): buscador de empresas por razón social o RUT para vincularlas al 
    convertir una solicitud.
    Devuelve como máximo 10 resultados y solo id, RUT y razón social; los datos detallados de la empresa nunca salen por aquí."""
    return crud.buscar_empresas(db, q)
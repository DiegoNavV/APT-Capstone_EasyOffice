"""Esquemas Pydantic del módulo solicitud_contacto / tramite (seguimiento)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.utils import normalizar_rut


# ---------- Solicitud de contacto (formulario público "Contrata aquí") ----------

class SolicitudContactoCreate(BaseModel):
    nombre: str = Field(max_length=150)
    rut: Optional[str] = Field(default=None, max_length=15)
    email: Optional[EmailStr] = None
    telefono: Optional[str] = Field(default=None, max_length=20)
    servicio_id: Optional[int] = None
    mensaje: Optional[str] = None

    @field_validator("nombre")
    @classmethod
    def nombre_no_vacio(cls, v):
        if not v or not v.strip():
            raise ValueError("El nombre no puede estar vacío.")
        return v.strip()

    @field_validator("rut")
    @classmethod
    def normalizar_rut_campo(cls, v):
        # Convierte "" en None y uniforma formato ("12.345.678-9" -> "12345678-9")
        # para no crear clientes duplicados por un RUT escrito distinto.
        return normalizar_rut(v)


class SolicitudContactoOut(BaseModel):
    id_solicitud: int
    nombre: str
    rut: Optional[str]
    email: Optional[str]
    telefono: Optional[str]
    mensaje: Optional[str]
    estado: str
    id_servicio: Optional[int]
    fecha_creacion: datetime

    class Config:
        from_attributes = True


# ---------- Conversión solicitud -> trámite (acción del agente) ----------

class ConvertirSolicitudRequest(BaseModel):
    id_usuario_responsable: Optional[int] = None


class TramiteOut(BaseModel):
    id_tramite: int
    codigo_seguimiento: str
    estado_actual: str
    nombre_servicio: str

    class Config:
        from_attributes = True


# ---------- Seguimiento público por código ----------

class SeguimientoOut(BaseModel):
    codigo_seguimiento: str
    nombre_servicio: str
    estado_actual: str
    documento_disponible: bool
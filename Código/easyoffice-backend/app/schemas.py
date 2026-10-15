"""Esquemas Pydantic: login del panel y módulo solicitud_contacto / tramite (seguimiento)."""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field, StrictBool, field_validator

from app.utils import normalizar_email, normalizar_rut


# ---------- Login del panel (agentes y administradores) ----------

class LoginRequest(BaseModel):
    email: EmailStr
    # Solo se valida el largo; la seguridad la da el hash Argon2id. Exigir
    # "complejidad" (mayúsculas, símbolos) está desaconsejado por NIST/OWASP.
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalizar_email_campo(cls, v):
        # "Admin@X.cl " y "admin@x.cl" son la misma cuenta.
        return normalizar_email(v)


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class UsuarioOut(BaseModel):
    id_usuario: int
    nombre: str
    email: str
    rol_nombre: str
    ultimo_login: Optional[datetime]

    class Config:
        from_attributes = True


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

# ---------- Listado de solicitudes (panel de agentes/admins) ----------

class SolicitudListadoOut(BaseModel):
    id_solicitud: int
    nombre: str
    rut: Optional[str]
    email: Optional[str]
    telefono: Optional[str]
    mensaje: Optional[str]
    estado: str
    id_servicio: Optional[int]
    nombre_servicio: Optional[str]
    id_tramite_generado: Optional[int]
    # Solo viene cuando la solicitud ya fue convertida; el agente lo necesita para reenviarle el código al cliente si lo perdió.
    codigo_seguimiento: Optional[str]
    fecha_creacion: datetime


# ---------- Aviso de solicitudes nuevas (consulta periódica del panel) ----------

class NovedadesSolicitudesOut(BaseModel):
    # Solo números, nunca datos de las solicitudes.
    nuevas: int
    ultimo_id: int

# ---------- Conversión solicitud -> trámite (acción del agente) ----------

class ConvertirSolicitudIn(BaseModel):
    """Cuerpo OPCIONAL de la conversión. Sin cuerpo (o con id_empresa nulo) el trámite queda sin empresa vinculada, como hasta ahora; 
    el vínculo siempre lo decide el agente, nunca el cliente."""
    id_empresa: Optional[int] = Field(default=None, ge=1)


class EmpresaOpcionOut(BaseModel):
    """Lo mínimo para que el agente identifique una empresa en el panel. A propósito NO incluye `datos` (representante, domicilio, etc.)."""
    id_empresa: int
    rut_empresa: str
    razon_social: str

    class Config:
        from_attributes = True


class TramiteOut(BaseModel):
    id_tramite: int
    codigo_seguimiento: str
    estado_actual: str
    nombre_servicio: str

    class Config:
        from_attributes = True


# ---------- Formulario del cliente (público, con el código del trámite) ----------

class CampoFormularioOut(BaseModel):
    clave: str
    etiqueta: str
    tipo: str            # texto | rut | email | celular | fecha
    ayuda: str
    max_largo: int
    # True: la empresa vinculada ya tiene este dato; el cliente no lo escribe.
    registrado: bool
    # Solo si `registrado`: el dato enmascarado (nunca completo, salvo la fecha).
    valor_enmascarado: Optional[str] = None


class FormularioOut(BaseModel):
    codigo_seguimiento: str
    nombre_servicio: str
    estado_actual: str
    # True si el cliente ya envió sus datos: solo se informa el estado.
    datos_enviados: bool
    # False si no se puede completar ahora (ya enviado, el trámite ya no está en
    # espera de datos, o el servicio aún no tiene formulario definido).
    formulario_disponible: bool
    # Vacía cuando el formulario no está disponible.
    campos: list[CampoFormularioOut]


class EnvioDatosIn(BaseModel):
    """Lo que el cliente envía UNA sola vez con su código. Los valores de los campos se validan después contra la definición 
    del servicio (así se informan todos los errores juntos, campo por campo). Las tres confirmaciones son estrictas (true/false reales) 
    y las exige el servidor, no solo el formulario."""
    model_config = {"extra": "forbid"}

    campos: dict[str, Any] = Field(default_factory=dict)
    solicitante_es_representante: StrictBool
    consentimiento_aceptado: StrictBool
    acepta_no_editar: StrictBool


# ---------- Seguimiento público por código ----------

class SeguimientoOut(BaseModel):
    codigo_seguimiento: str
    nombre_servicio: str
    estado_actual: str
    documento_disponible: bool


# ---------- Listado de trámites del panel (requiere login) ----------

class ClienteListadoOut(BaseModel):
    """Cliente tal como se muestra en el listado. Hoy son los datos de contacto
    de quien pidió el trámite; cuando el cliente complete los datos de su
    empresa, aquí saldrán la razón social y el RUT de la empresa."""
    nombre: str
    rut: Optional[str] = None
    datos_pendientes: bool  # True mientras no existan los datos de empresa


class TramiteListadoOut(BaseModel):
    id_tramite: int
    codigo_seguimiento: str
    cliente: ClienteListadoOut
    id_servicio: int
    nombre_servicio: str
    estado_actual: str
    id_usuario_responsable: Optional[int] = None
    nombre_agente: Optional[str] = None
    fecha_actualizacion: Optional[datetime] = None


class TramitesPaginaOut(BaseModel):
    items: list[TramiteListadoOut]
    total: int  # total que cumple los filtros (sin paginar)


class TramitesKpisOut(BaseModel):
    pendientes_datos: int  # el cliente aún no completa sus datos
    en_proceso: int        # firma o revisión en curso
    firmados_24h: int      # pasaron a "firmado" en las últimas 24 horas
    entregados: int


class OpcionServicioOut(BaseModel):
    id_servicio: int
    nombre: str


class OpcionAgenteOut(BaseModel):
    id_usuario: int
    nombre: str


class TramitesResumenOut(BaseModel):
    kpis: TramitesKpisOut
    servicios: list[OpcionServicioOut]
    agentes: list[OpcionAgenteOut]


# ---------- Catálogos para armar el contrato (panel de agentes) ----------

class SucursalOut(BaseModel):
    id_sucursal: int
    iniciales: str
    nombre: str
    direccion: str
    comuna: str
    region: str
    rol_propiedad: Optional[str] = None

    class Config:
        from_attributes = True


class ServicioOfrecidoOut(BaseModel):
    id_servicio_ofrecido: int
    nombre: str
    descripcion: Optional[str] = None
    precio_referencia: Optional[int] = None
    ciclo_pago_defecto: Optional[str] = None

    class Config:
        from_attributes = True
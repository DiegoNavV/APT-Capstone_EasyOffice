"""Esquemas Pydantic: login del panel y módulo solicitud_contacto / tramite (seguimiento)."""
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field, StrictBool, field_validator, model_validator

from app import condiciones
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
    folio: Optional[str] = None
    fecha_creacion: datetime


# ---------- Aviso de solicitudes nuevas (consulta periódica del panel) ----------

class NovedadesSolicitudesOut(BaseModel):
    # Solo números, nunca datos de las solicitudes.
    nuevas: int
    ultimo_id: int

# ---------- Conversión solicitud -> trámite (acción del agente) ----------

class ServicioCondicionIn(BaseModel):
    """
    Un servicio del contrato. El agente decide solo precio y ciclo; el nombre y la descripción los copia el servidor desde el catálogo.
    """
    id_servicio_ofrecido: int = Field(ge=1)
    precio: int = Field(ge=0, le=condiciones.PRECIO_MAXIMO)
    ciclo_pago: str

    @field_validator("ciclo_pago")
    @classmethod
    def ciclo_valido(cls, v):
        ciclo = condiciones.normalizar_ciclo(v)
        if ciclo not in condiciones.CICLOS_PAGO:
            raise ValueError("Ciclo de pago no válido. Opciones: " + ", ".join(condiciones.CICLOS_PAGO) + ".")
        return ciclo


class CondicionesIn(BaseModel):
    servicios: list[ServicioCondicionIn] = Field(min_length=1, max_length=condiciones.MAX_SERVICIOS)
    duracion_meses: int
    fecha_inicio: date
    # Opcional: sin valor, el servidor lo calcula. Con valor se respeta (el agente puede corregirlo por feriados, días hábiles, etc.).
    fecha_vencimiento: Optional[date] = None

    @field_validator("duracion_meses")
    @classmethod
    def duracion_valida(cls, v):
        if v not in condiciones.DURACIONES_MESES:
            raise ValueError("Duración no válida. Opciones (meses): " + ", ".join(map(str, condiciones.DURACIONES_MESES)) + ".")
        return v

    @model_validator(mode="after")
    def revisar_conjunto(self):
        ids = [s.id_servicio_ofrecido for s in self.servicios]
        if len(ids) != len(set(ids)):
            raise ValueError("Hay un servicio repetido en el contrato.")
        if self.fecha_vencimiento is not None and self.fecha_vencimiento <= self.fecha_inicio:
            raise ValueError("El vencimiento debe ser posterior a la fecha de inicio.")
        return self


class ConvertirSolicitudIn(BaseModel):
    """
    Cuerpo OPCIONAL de la conversión. Sin cuerpo (o con todo nulo) el trámite queda sin empresa, sin sucursal y sin condiciones, 
    como hasta ahora; el panel es quien las pide siempre. Todo lo decide el agente, nunca el cliente.
    """
    id_empresa: Optional[int] = Field(default=None, ge=1)
    id_sucursal: Optional[int] = Field(default=None, ge=1)
    condiciones: Optional[CondicionesIn] = None

    @model_validator(mode="after")
    def condiciones_requieren_sucursal(self):
        if self.condiciones is not None and self.id_sucursal is None:
            raise ValueError("Para fijar las condiciones del contrato hay que indicar la sucursal.")
        return self


class EmpresaOpcionOut(BaseModel):
    """
    Lo mínimo para que el agente identifique una empresa en el panel. A propósito NO incluye `datos` (representante, domicilio, etc.).
    """
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
    folio: Optional[str] = None

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

class VistaPreviaIn(BaseModel):
    """Lo que el cliente ya escribió, para ver el borrador antes de enviar. No se
    guarda nada y no exige las confirmaciones (esas son del envío definitivo)."""
    model_config = {"extra": "forbid"}

    campos: dict[str, Any] = Field(default_factory=dict)

# ---------- Seguimiento público por código ----------

class SeguimientoOut(BaseModel):
    codigo_seguimiento: str
    nombre_servicio: str
    estado_actual: str
    documento_disponible: bool


# ---------- Listado de trámites del panel (requiere login) ----------

class ClienteListadoOut(BaseModel):
    """
    Cliente tal como se muestra en el listado. Hoy son los datos de contacto de quien pidió el trámite; cuando el cliente complete 
    los datos de su empresa, aquí saldrán la razón social y el RUT de la empresa.
    """
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
    # True si ya se generó un PDF del trámite (ver /api/tramites/{id}/documento).
    tiene_documento: bool = False
    folio: Optional[str] = None  # el panel lo usa para nombrar el PDF descargado


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


class ReporteConteoOut(BaseModel):
    etiqueta: str
    cantidad: int


class ReporteTramitesOut(BaseModel):
    """Conteos agregados para la vista de Reportes del panel. `puede_ver` es false para quienes no tienen permiso
    (el panel muestra solo un aviso) -- exclusivo de administradores, confirmado con el cliente (ver
    Resumen_Alcance_Proyecto_EasyOffice.docx: "panel de resumen" es una función exclusiva del administrador)."""
    puede_ver: bool
    total: int = 0
    por_estado: list[ReporteConteoOut] = []
    por_servicio: list[ReporteConteoOut] = []
    por_agente: list[ReporteConteoOut] = []


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



class OpcionesContratoOut(BaseModel):
    """Valores permitidos para armar las condiciones; el panel los pide en vez de repetirlos."""
    ciclos_pago: list[str]
    duraciones_meses: list[int]
    max_servicios: int


# ---------- Plantillas de documentos ----------

class PlantillaOut(BaseModel):
    id_plantilla: int
    id_servicio: int
    nombre_servicio: str
    nombre: str
    version: str
    activa: bool
    fecha_creacion: datetime
    nombre_original: Optional[str] = None
    tamano_bytes: Optional[int] = None
    hash_sha256: Optional[str] = None
    marcas: list[str] = []
    subida_por: Optional[str] = None


class MarcaOut(BaseModel):
    nombre: str
    descripcion: str


class ConfiguracionPlantillasOut(BaseModel):
    """
    Lo que necesita el panel para dibujar la pantalla. `puede_gestionar` es false para quienes no tienen permiso 
    (el panel oculta la gestión).
    """
    puede_gestionar: bool
    max_tamano_mb: int
    servicios: list[dict[str, Any]]
    marcas: list[MarcaOut]


# ---------- Documento generado de un trámite ----------

class DocumentoGeneradoOut(BaseModel):
    id_tramite: int
    folio: Optional[str] = None
    nombre_archivo: str
    tamano_bytes: int
    hash_sha256: str
    version_plantilla: str
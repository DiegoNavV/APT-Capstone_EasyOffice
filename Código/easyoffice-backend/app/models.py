"""
Modelos SQLAlchemy. Deben coincidir con db/init/01_schema.sql (esquema v4).

  - Login del panel (Épica A): rol, usuario, refresh_token
  - Formulario de contacto -> solicitud -> trámite:
    tipo_tramite, solicitud_contacto, cliente, tramite, historial_estado
  - Datos que el cliente entrega con su código: empresa, representante_legal, datos_empresa_tramite
  - Catálogos: estado_tramite, ciclo_pago_defecto, sucursal, servicio_ofrecido

Varios atributos de Python conservan su nombre anterior aunque la columna de la base se llame distinto
(p. ej. `id_cliente = Column("id", ...)`): así el resto de la app, la API y el panel no cambian. El nombre
real de la columna es siempre el primer argumento de Column.

Las restricciones CHECK, los triggers y el resto de las reglas viven en db/init/; acá solo se repite lo que
SQLAlchemy necesita para crear las tablas en los tests (SQLite).
"""
from sqlalchemy import (
    JSON, Boolean, Column, Date, ForeignKey, Index, Integer, SmallInteger, String, Text, TIMESTAMP, func, text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base

# JSONB en PostgreSQL; JSON genérico en SQLite (tests). none_as_null: un None de Python se guarda como NULL de
# SQL y no como el valor JSON 'null' (que los CHECK de la base, p. ej. condiciones => sucursal, tomarían como dato).
_JSON = JSON(none_as_null=True).with_variant(JSONB(none_as_null=True), "postgresql")


# ---------------------------------------------------------------------------
# Catálogos fijos (sus filas se cargan en db/init/03_catalogos.sql)
# ---------------------------------------------------------------------------

class EstadoTramite(Base):
    """Estados posibles de un trámite. Clave natural: la app compara por código."""

    __tablename__ = "estado_tramite"

    codigo = Column(String(30), primary_key=True)
    etiqueta = Column(String(50), nullable=False)
    orden = Column(SmallInteger, nullable=False, unique=True)
    es_final = Column(Boolean, nullable=False)
    documento_disponible = Column(Boolean, nullable=False)
    permite_regenerar = Column(Boolean, nullable=False)


class CicloPagoDefecto(Base):
    """Ciclos de pago (ÚNICO, ANUAL...). Los códigos son los de CICLOS_PAGO en app/condiciones.py."""

    __tablename__ = "ciclo_pago_defecto"

    codigo = Column(String(20), primary_key=True)
    nombre = Column(String(100), nullable=False)
    meses = Column(SmallInteger)
    orden = Column(SmallInteger, nullable=False)
    activo = Column(Boolean, nullable=False, default=True)


# ---------------------------------------------------------------------------
# Login del panel
# ---------------------------------------------------------------------------

class Rol(Base):
    __tablename__ = "rol"

    id_rol = Column("id", Integer, primary_key=True)
    nombre = Column(String(50), nullable=False, unique=True)  # "administrador" | "agente"
    descripcion = Column(String(500), nullable=False, default="")


class Usuario(Base):
    """Cuentas del panel interno (administradores y agentes). Los clientes de
    Easy Office no tienen cuenta."""

    __tablename__ = "usuario"

    id_usuario = Column("id", Integer, primary_key=True)
    id_rol = Column("rol_id", Integer, ForeignKey("rol.id"), nullable=False)
    nombre = Column(String(150), nullable=False)
    email = Column(String(250), nullable=False, unique=True)
    password_hash = Column("hash_pswd", String(255), nullable=False)
    activo = Column(Boolean, nullable=False, default=True)
    fecha_creacion = Column(TIMESTAMP, nullable=False, server_default=func.now())

    # Bloqueo por fuerza bruta: se suma 1 por cada contraseña incorrecta y,
    # al llegar al máximo, la cuenta queda bloqueada hasta `bloqueado_hasta`.
    intentos_fallidos = Column(Integer, nullable=False, default=0)
    bloqueado_hasta = Column(TIMESTAMP)
    ultimo_login = Column(TIMESTAMP)

    rol = relationship("Rol")

    @property
    def rol_nombre(self) -> str:
        return self.rol.nombre


class RefreshToken(Base):
    """Una fila por sesión iniciada. Solo se guarda el hash del token.

    Rotación: cada vez que se usa en /api/auth/refresh, el token se marca
    `revocado` y se enlaza al nuevo con `reemplazado_por_id`. Si después alguien
    presenta un token ya revocado, es señal de robo y se cierran todas las
    sesiones del usuario (ver app/routers/auth.py)."""

    __tablename__ = "refresh_token"

    id_refresh_token = Column("id", Integer, primary_key=True)
    id_usuario = Column("usuario_id", Integer, ForeignKey("usuario.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    creado_en = Column(TIMESTAMP, nullable=False, server_default=func.now())
    expira_en = Column(TIMESTAMP, nullable=False)
    revocado = Column(Boolean, nullable=False, default=False)
    # Un token reemplaza a uno solo; SET NULL deja borrar tokens viejos aunque otro apunte a ellos.
    reemplazado_por_id = Column(
        "refresh_token_id", Integer, ForeignKey("refresh_token.id", ondelete="SET NULL"), unique=True
    )


# ---------------------------------------------------------------------------
# Solicitud -> trámite
# ---------------------------------------------------------------------------

class Cliente(Base):
    """Persona que contrata. Sin login; se busca o crea por RUN al convertir una solicitud."""

    __tablename__ = "cliente"

    id_cliente = Column("id", Integer, primary_key=True)
    nombre = Column(String(150), nullable=False)
    rut = Column("run", String(15), nullable=False, unique=True)
    email = Column(String(150))
    telefono = Column("numero_contacto", String(15))
    fecha_creacion = Column(TIMESTAMP, nullable=False, server_default=func.now())


class ServicioContratado(Base):
    """Tipo de trámite que automatiza la plataforma (tabla tipo_tramite). No es lo mismo que
    ServicioOfrecido, que es lo que vende Easy Office."""

    __tablename__ = "tipo_tramite"

    id_servicio = Column("id", Integer, primary_key=True)
    nombre = Column(String(150), nullable=False, unique=True)
    descripcion = Column(String(150), nullable=False, default="")
    requiere_revision_humana = Column("revision_humana", Boolean, nullable=False, default=False)
    activo = Column(Boolean, nullable=False, default=True)


class SolicitudContacto(Base):
    """Formulario público "Contrata aquí". Un agente la convierte en trámite o la descarta.
    El vínculo con el trámite vive en `tramite.solicitud_contacto_id` (ver `tramite`)."""

    __tablename__ = "solicitud_contacto"

    id_solicitud = Column("id", Integer, primary_key=True)
    id_servicio = Column("tipo_tramite_id", Integer, ForeignKey("tipo_tramite.id"))
    # Nullable solo por la anonimización: mientras no se anonimice, el CHECK de la base exige nombre.
    nombre = Column(String(150))
    rut = Column("run", String(15))
    email = Column(String(150))
    telefono = Column("numero_contacto", String(15))
    mensaje = Column(String(500))
    estado = Column(String(30), nullable=False, default="pendiente")  # pendiente | convertida | descartada
    id_usuario_asignado = Column("usuario_id", Integer, ForeignKey("usuario.id"))
    fecha_asignacion = Column(TIMESTAMP)
    motivo_descarte = Column(String(500))
    fecha_cierre = Column(TIMESTAMP)
    fecha_anonimizacion = Column(TIMESTAMP)
    fecha_creacion = Column(TIMESTAMP, nullable=False, server_default=func.now())
    fecha_actualizacion = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())

    servicio = relationship("ServicioContratado")
    tramite = relationship("Tramite", back_populates="solicitud_origen", uselist=False)

    @property
    def id_tramite_generado(self) -> int | None:
        """El trámite que salió de esta solicitud (None si aún no se convierte)."""
        return self.tramite.id_tramite if self.tramite else None


class RepresentanteLegal(Base):
    """Persona natural que representa a una o más empresas y firma los documentos.
    Puede ser o no el cliente que hizo la solicitud."""

    __tablename__ = "representante_legal"

    id_representante = Column("id", Integer, primary_key=True)
    rut = Column("run", String(15), nullable=False, unique=True)
    nombre = Column(String(150), nullable=False)
    domicilio = Column(String(200))
    comuna = Column(String(200))
    region = Column(String(200))
    fecha_creacion = Column(TIMESTAMP, nullable=False, server_default=func.now())


class Empresa(Base):
    """Empresa cliente. Sus datos se guardan UNA sola vez y se reutilizan entre trámites.

    Los atributos se llaman igual que las claves de app/campos_servicio.py (`giro_principal`, `celular`...),
    aunque la columna tenga otro nombre. Los datos del representante viven en su propia tabla; las
    propiedades `representante_legal`, `rut_representante`, etc. los leen desde ahí, para que el resto de
    la app trate los 12 campos del contrato igual.

    El cliente solo puede COMPLETAR campos que faltan, nunca sobrescribir los existentes; los cambios los
    hace un agente. `datos` queda para campos extra que Easy Office agregue después."""

    __tablename__ = "empresa"

    id_empresa = Column("id", Integer, primary_key=True)
    rut_empresa = Column("rut", String(15), nullable=False, unique=True)
    razon_social = Column(String(200), nullable=False)
    giro_principal = Column("giro_comercial", String(200))
    email = Column(String(150))
    celular = Column("contacto", String(9))
    fecha_escritura = Column(Date)
    notaria = Column(String(200))
    # Para modificar `datos` hay que asignar un diccionario nuevo (SQLAlchemy no detecta cambios dentro del JSON).
    datos = Column(_JSON, default=dict)
    fecha_creacion = Column(TIMESTAMP, nullable=False, server_default=func.now())
    fecha_actualizacion = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
    id_representante = Column(
        "representante_legal_id", Integer, ForeignKey("representante_legal.id"), nullable=False, index=True
    )

    representante = relationship("RepresentanteLegal")
    tramites = relationship("Tramite", back_populates="empresa")

    @property
    def representante_legal(self) -> str | None:
        return self.representante.nombre if self.representante else None

    @property
    def rut_representante(self) -> str | None:
        return self.representante.rut if self.representante else None

    @property
    def domicilio_representante(self) -> str | None:
        return self.representante.domicilio if self.representante else None

    @property
    def comuna_representante(self) -> str | None:
        return self.representante.comuna if self.representante else None

    @property
    def region_representante(self) -> str | None:
        return self.representante.region if self.representante else None


class Sucursal(Base):
    """Sucursal de Easy Office. Sus datos van en el contrato; las iniciales forman el folio (LF-01-2026)."""

    __tablename__ = "sucursal"

    id_sucursal = Column("id", Integer, primary_key=True)
    iniciales = Column(String(10), nullable=False, unique=True)
    nombre = Column(String(150), nullable=False, unique=True)
    direccion = Column(String(150), nullable=False)
    comuna = Column(String(100), nullable=False)
    region = Column(String(100), nullable=False)
    rol_propiedad = Column(String(30), nullable=False)
    activa = Column(Boolean, nullable=False, default=True)


class ServicioOfrecido(Base):
    """Catálogo de lo que vende Easy Office (domicilio tributario, bodega, etc.) con precio y ciclo de pago de referencia. No es lo mismo
    que ServicioContratado, que son los trámites de la plataforma."""

    __tablename__ = "servicio_ofrecido"

    id_servicio_ofrecido = Column("id", Integer, primary_key=True)
    nombre = Column(String(150), nullable=False, unique=True)
    descripcion = Column(Text)
    precio_referencia = Column(Integer)
    ciclo_pago_defecto = Column("ciclo_pago_defecto_codigo", String(20), ForeignKey("ciclo_pago_defecto.codigo"))
    activo = Column(Boolean, nullable=False, default=True)


class Tramite(Base):
    """Se crea únicamente cuando un agente confirma el pago y convierte una solicitud_contacto."""

    __tablename__ = "tramite"

    id_tramite = Column("id", Integer, primary_key=True)
    id_cliente = Column("cliente_id", Integer, ForeignKey("cliente.id"), nullable=False, index=True)
    id_usuario_responsable = Column("usuario_id", Integer, ForeignKey("usuario.id"), nullable=False, index=True)
    id_servicio = Column("tipo_tramite_id", Integer, ForeignKey("tipo_tramite.id"), nullable=False, index=True)
    # Una solicitud genera como máximo un trámite (relación 1:1).
    id_solicitud_origen = Column(
        "solicitud_contacto_id", Integer, ForeignKey("solicitud_contacto.id"), nullable=False, unique=True
    )
    id_empresa = Column("empresa_id", Integer, ForeignKey("empresa.id"), index=True)
    id_sucursal = Column("sucursal_id", Integer, ForeignKey("sucursal.id"), index=True)
    # Condiciones del contrato que ingresa el agente (ver crud al convertir una solicitud).
    folio = Column(String(20), unique=True)
    condiciones = Column(_JSON)
    # unique=True ya crea su propio indice -- no se repite index=True aparte.
    codigo_seguimiento = Column(String(8), nullable=False, unique=True)
    estado_actual = Column(
        "estado_tramite_codigo", String(30), ForeignKey("estado_tramite.codigo"),
        nullable=False, default="esperando_datos", index=True,
    )
    ruta_documento_generado = Column(String(255))
    fecha_creacion = Column(TIMESTAMP, nullable=False, server_default=func.now())
    fecha_actualizacion = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())
    # Versión de la plantilla con la que se generó el documento (va junto con ruta_documento_generado).
    id_plantilla = Column("plantilla_documento_id", Integer, ForeignKey("plantilla_documento.id"), index=True)

    cliente = relationship("Cliente")
    servicio = relationship("ServicioContratado")
    usuario_responsable = relationship("Usuario")
    solicitud_origen = relationship("SolicitudContacto", back_populates="tramite")
    empresa = relationship("Empresa", back_populates="tramites")
    sucursal = relationship("Sucursal")
    plantilla = relationship("PlantillaDocumento")
    datos_empresa = relationship("DatosEmpresaTramite", back_populates="tramite", uselist=False)


class DatosEmpresaTramite(Base):
    """Comprobante del envío ÚNICO de datos que hace el cliente con su código.

    La PK en tramite_id garantiza el "solo una vez" a nivel de base de datos:
    un segundo intento falla aunque se salten las validaciones. Los datos
    de la empresa en sí viven en la tabla `empresa`."""

    __tablename__ = "datos_empresa_tramite"

    id_tramite = Column("tramite_id", Integer, ForeignKey("tramite.id"), primary_key=True)
    solicitante_es_representante = Column(Boolean, nullable=False)
    # Versión del texto de consentimiento (tratamiento de datos y no edición) que aceptó el cliente.
    version_consentimiento = Column(String(20), nullable=False)
    fecha_envio = Column(TIMESTAMP, nullable=False, server_default=func.now())

    tramite = relationship("Tramite", back_populates="datos_empresa")


class HistorialEstado(Base):
    """Bitácora append-only de cambios de estado. `origen`: agente (con usuario), cliente o sistema (sin usuario).
    En Postgres, un trigger copia cada estado nuevo a tramite.estado_tramite_codigo."""

    __tablename__ = "historial_estado"

    id_historial = Column("id", Integer, primary_key=True)
    id_tramite = Column("tramite_id", Integer, ForeignKey("tramite.id"), nullable=False)
    estado = Column("estado_tramite_codigo", String(30), ForeignKey("estado_tramite.codigo"), nullable=False)
    origen = Column(String(50), nullable=False)  # agente | cliente | sistema
    comentario = Column(Text)
    id_usuario = Column("usuario_id", Integer, ForeignKey("usuario.id"))
    fecha = Column(TIMESTAMP, nullable=False, server_default=func.now())

    __table_args__ = (Index("idx_historial_tramite_fecha", "tramite_id", "fecha"),)


class PlantillaDocumento(Base):
    """
    Una versión de la plantilla Word de un tipo de trámite (contrato, autorización...).
    Las versiones nunca se borran: subir un archivo crea una versión nueva y la anterior queda guardada. Solo una versión por servicio
    puede estar activa (índice único parcial). El archivo vive fuera de la base, en PLANTILLAS_DIR;
    aquí solo se guarda su ruta relativa.
    """

    __tablename__ = "plantilla_documento"
    __table_args__ = (
        Index("uq_plantilla_tipo_version", "tipo_tramite_id", "version", unique=True),
        Index("uq_plantilla_tipo_hash", "tipo_tramite_id", "hash_sha256", unique=True),
        Index(
            "uq_plantilla_activa_por_tipo", "tipo_tramite_id", unique=True,
            postgresql_where=text("activo"), sqlite_where=text("activo"),
        ),
    )

    id_plantilla = Column("id", Integer, primary_key=True)
    id_servicio = Column("tipo_tramite_id", Integer, ForeignKey("tipo_tramite.id"), nullable=False)
    nombre = Column(String(150), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    ruta_archivo = Column(String(255), nullable=False, unique=True)
    activa = Column("activo", Boolean, nullable=False, default=True)
    fecha_creacion = Column(TIMESTAMP, nullable=False, server_default=func.now())
    nombre_original = Column(String(255), nullable=False)
    hash_sha256 = Column(String(64), nullable=False)
    tamano_bytes = Column(Integer, nullable=False)
    marcas = Column(_JSON, nullable=False, default=list)
    id_usuario_subio = Column("usuario_id", Integer, ForeignKey("usuario.id"), nullable=False)

    servicio = relationship("ServicioContratado")
    usuario_subio = relationship("Usuario")

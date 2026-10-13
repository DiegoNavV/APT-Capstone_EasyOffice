"""
Modelos SQLAlchemy. Deben coincidir con db/init/01_schema.sql.

  - Login del panel (Épica A): rol, usuario, refresh_token
  - Formulario de contacto -> solicitud -> trámite:
    servicio_contratado, solicitud_contacto, cliente, tramite, historial_estado
  - Datos que el cliente entrega con su código: datos_empresa_tramite
"""
from sqlalchemy import (
    JSON, CheckConstraint, Column, Integer, String, Text, Boolean, TIMESTAMP,
    ForeignKey, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class Rol(Base):
    __tablename__ = "rol"

    id_rol = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(50), nullable=False, unique=True)  # "administrador" | "agente"
    descripcion = Column(Text)


class Usuario(Base):
    """Cuentas del panel interno (administradores y agentes). Los clientes de
    Easy Office no tienen cuenta."""

    __tablename__ = "usuario"

    id_usuario = Column(Integer, primary_key=True, index=True)
    id_rol = Column(Integer, ForeignKey("rol.id_rol"), nullable=False)
    nombre = Column(String(150), nullable=False)
    email = Column(String(150), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    activo = Column(Boolean, nullable=False, default=True)
    fecha_creacion = Column(TIMESTAMP, server_default=func.now())

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

    id_refresh_token = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    creado_en = Column(TIMESTAMP, server_default=func.now())
    expira_en = Column(TIMESTAMP, nullable=False)
    revocado = Column(Boolean, nullable=False, default=False)
    reemplazado_por_id = Column(Integer, ForeignKey("refresh_token.id_refresh_token"))


class Cliente(Base):
    __tablename__ = "cliente"

    id_cliente = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    rut = Column(String(15), unique=True)
    email = Column(String(150))
    telefono = Column(String(20))
    fecha_creacion = Column(TIMESTAMP, server_default=func.now())


class ServicioContratado(Base):
    __tablename__ = "servicio_contratado"

    id_servicio = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    descripcion = Column(Text)
    requiere_revision_humana = Column(Boolean, nullable=False, default=False)
    activo = Column(Boolean, nullable=False, default=True)


class SolicitudContacto(Base):
    __tablename__ = "solicitud_contacto"

    id_solicitud = Column(Integer, primary_key=True, index=True)
    id_servicio = Column(Integer, ForeignKey("servicio_contratado.id_servicio"), nullable=True)
    nombre = Column(String(150), nullable=False)
    rut = Column(String(15))
    email = Column(String(150))
    telefono = Column(String(20))
    mensaje = Column(Text)
    estado = Column(String(30), nullable=False, default="pendiente")
    id_usuario_asignado = Column(Integer, ForeignKey("usuario.id_usuario"), nullable=True)
    id_tramite_generado = Column(Integer, ForeignKey("tramite.id_tramite"), nullable=True)
    fecha_creacion = Column(TIMESTAMP, server_default=func.now())
    fecha_actualizacion = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    servicio = relationship("ServicioContratado")


class Tramite(Base):
    __tablename__ = "tramite"

    id_tramite = Column(Integer, primary_key=True, index=True)
    id_cliente = Column(Integer, ForeignKey("cliente.id_cliente"), nullable=False)
    id_servicio = Column(Integer, ForeignKey("servicio_contratado.id_servicio"), nullable=False)
    id_usuario_responsable = Column(Integer, ForeignKey("usuario.id_usuario"), nullable=True)
    id_solicitud_origen = Column(Integer, ForeignKey("solicitud_contacto.id_solicitud"), nullable=True)
    codigo_seguimiento = Column(String(8), nullable=False, unique=True, index=True)
    estado_actual = Column(String(30), nullable=False, default="generado")
    ruta_documento_generado = Column(String(255))
    fecha_creacion = Column(TIMESTAMP, server_default=func.now())
    fecha_actualizacion = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    cliente = relationship("Cliente")
    servicio = relationship("ServicioContratado")
    usuario_responsable = relationship("Usuario")
    datos_empresa = relationship("DatosEmpresaTramite", back_populates="tramite", uselist=False)


class DatosEmpresaTramite(Base):
    """Datos de la empresa que el cliente entrega UNA sola vez con su código.

    El solicitante (quien llenó el formulario público) vive en
    solicitud_contacto/cliente; aquí va la empresa. `razon_social` y
    `rut_empresa` son columnas propias porque la lista del panel las muestra y
    las busca; el resto de los campos varía según el servicio y se guarda en
    `datos`, con los nombres de columna de los Excel de Easy Office.

    La clave única en id_tramite garantiza el envío único a nivel de base de
    datos: un segundo intento falla aunque se salten las validaciones."""

    __tablename__ = "datos_empresa_tramite"
    __table_args__ = (CheckConstraint("consentimiento_aceptado", name="ck_datos_empresa_consentimiento"),)

    id_datos = Column(Integer, primary_key=True, index=True)
    id_tramite = Column(Integer, ForeignKey("tramite.id_tramite"), nullable=False, unique=True)
    razon_social = Column(String(200), nullable=False)
    rut_empresa = Column(String(15), nullable=False, index=True)
    # JSONB en PostgreSQL; JSON genérico en SQLite (tests).
    datos = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict)
    solicitante_es_representante = Column(Boolean, nullable=False)
    consentimiento_aceptado = Column(Boolean, nullable=False)
    fecha_envio = Column(TIMESTAMP, nullable=False, server_default=func.now())

    tramite = relationship("Tramite", back_populates="datos_empresa")

class HistorialEstado(Base):
    __tablename__ = "historial_estado"

    id_historial = Column(Integer, primary_key=True, index=True)
    id_tramite = Column(Integer, ForeignKey("tramite.id_tramite"), nullable=False)
    estado = Column(String(30), nullable=False)
    comentario = Column(Text)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), nullable=True)
    fecha = Column(TIMESTAMP, server_default=func.now())
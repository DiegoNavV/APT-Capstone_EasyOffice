"""
Modelos SQLAlchemy. Deben coincidir con db/init/01_schema.sql.

  - Login del panel (Épica A): rol, usuario, refresh_token
  - Formulario de contacto -> solicitud -> trámite:
    servicio_contratado, solicitud_contacto, cliente, tramite, historial_estado
  - Datos que el cliente entrega con su código: empresa, datos_empresa_tramite
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

class Empresa(Base):
    """Empresa cliente. Sus datos se guardan UNA sola vez y se reutilizan entre
    trámites. `razon_social` y `rut_empresa` son columnas propias porque el panel
    las muestra y las busca; el resto de los campos varía según el servicio y va
    en `datos`.

    El cliente solo puede COMPLETAR campos que faltan, nunca sobrescribir los
    existentes; los cambios los hace un agente. Para modificar `datos` hay que
    asignar un diccionario nuevo (SQLAlchemy no detecta cambios dentro del JSON)."""

    __tablename__ = "empresa"

    id_empresa = Column(Integer, primary_key=True, index=True)
    rut_empresa = Column(String(15), nullable=False, unique=True)
    razon_social = Column(String(200), nullable=False)
    # JSONB en PostgreSQL; JSON genérico en SQLite (tests).
    datos = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict)
    fecha_creacion = Column(TIMESTAMP, nullable=False, server_default=func.now())
    fecha_actualizacion = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())

    tramites = relationship("Tramite", back_populates="empresa")


class Sucursal(Base):
    """Sucursal de Easy Office. Sus datos van en el contrato; las iniciales forman el folio (LF-01-2026)."""

    __tablename__ = "sucursal"

    id_sucursal = Column(Integer, primary_key=True, index=True)
    iniciales = Column(String(5), nullable=False, unique=True)
    nombre = Column(String(100), nullable=False)
    direccion = Column(String(200), nullable=False)
    comuna = Column(String(100), nullable=False)
    region = Column(String(100), nullable=False)
    rol_propiedad = Column(String(30))
    activa = Column(Boolean, nullable=False, default=True)

class ServicioOfrecido(Base):
    """Catálogo de lo que vende Easy Office (domicilio tributario, bodega, etc.) con precio y ciclo de pago de referencia. No es lo mismo 
    que ServicioContratado, que son los trámites de la plataforma."""

    __tablename__ = "servicio_ofrecido"

    id_servicio_ofrecido = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False, unique=True)
    descripcion = Column(Text)
    precio_referencia = Column(Integer)
    ciclo_pago_defecto = Column(String(20))
    activo = Column(Boolean, nullable=False, default=True)


class Tramite(Base):
    __tablename__ = "tramite"

    id_tramite = Column(Integer, primary_key=True, index=True)
    id_cliente = Column(Integer, ForeignKey("cliente.id_cliente"), nullable=False)
    id_servicio = Column(Integer, ForeignKey("servicio_contratado.id_servicio"), nullable=False)
    id_usuario_responsable = Column(Integer, ForeignKey("usuario.id_usuario"), nullable=True)
    id_solicitud_origen = Column(Integer, ForeignKey("solicitud_contacto.id_solicitud"), nullable=True)
    id_empresa = Column(Integer, ForeignKey("empresa.id_empresa"), nullable=True)
    id_sucursal = Column(Integer, ForeignKey("sucursal.id_sucursal"), nullable=True)
    # Condiciones del contrato que ingresa el agente (ver crud al convertir una solicitud).
    folio = Column(String(20), unique=True)
    condiciones = Column(JSON().with_variant(JSONB(), "postgresql"))
    codigo_seguimiento = Column(String(8), nullable=False, unique=True, index=True)
    estado_actual = Column(String(30), nullable=False, default="generado")
    ruta_documento_generado = Column(String(255))
    fecha_creacion = Column(TIMESTAMP, server_default=func.now())
    fecha_actualizacion = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    cliente = relationship("Cliente")
    servicio = relationship("ServicioContratado")
    usuario_responsable = relationship("Usuario")
    empresa = relationship("Empresa", back_populates="tramites")
    sucursal = relationship("Sucursal")
    datos_empresa = relationship("DatosEmpresaTramite", back_populates="tramite", uselist=False)


class DatosEmpresaTramite(Base):
    """Registro del envío ÚNICO de datos que hace el cliente con su código.

    La clave única en id_tramite garantiza el "solo una vez" a nivel de base de
    datos: un segundo intento falla aunque se salten las validaciones. Los datos
    de la empresa en sí viven en la tabla `empresa`."""

    __tablename__ = "datos_empresa_tramite"
    __table_args__ = (CheckConstraint("consentimiento_aceptado", name="ck_datos_empresa_consentimiento"),)

    id_datos = Column(Integer, primary_key=True, index=True)
    id_tramite = Column(Integer, ForeignKey("tramite.id_tramite"), nullable=False, unique=True)
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
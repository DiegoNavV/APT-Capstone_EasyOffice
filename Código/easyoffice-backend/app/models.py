"""
Modelos SQLAlchemy — SOLO las tablas que usa el módulo
"formulario de contacto -> solicitud -> trámite":

  servicio_contratado, solicitud_contacto, cliente, tramite, historial_estado

No se incluyen rol/usuario con lógica de autenticación: ese es otro módulo
(Épica A). Acá usuario solo existe como tabla mínima para que la FK de
id_usuario_asignado / id_usuario_responsable funcione.
"""
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, TIMESTAMP, ForeignKey, func
)
from sqlalchemy.orm import relationship

from app.database import Base


class Usuario(Base):
    __tablename__ = "usuario"

    id_usuario = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    email = Column(String(150), nullable=False, unique=True)


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

    cliente = relationship("Cliente")
    servicio = relationship("ServicioContratado")


class HistorialEstado(Base):
    __tablename__ = "historial_estado"

    id_historial = Column(Integer, primary_key=True, index=True)
    id_tramite = Column(Integer, ForeignKey("tramite.id_tramite"), nullable=False)
    estado = Column(String(30), nullable=False)
    comentario = Column(Text)
    id_usuario = Column(Integer, ForeignKey("usuario.id_usuario"), nullable=True)
    fecha = Column(TIMESTAMP, server_default=func.now())
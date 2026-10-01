from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, false, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Usuario(Base):
    """Cuentas de administradores y agentes. Los clientes de Easy Office
    nunca tienen cuenta (ver Definiciones_Desarrollo_CRM_EasyOffice.docx)."""

    __tablename__ = "usuario"

    id_usuario: Mapped[int] = mapped_column(primary_key=True)
    id_rol: Mapped[int] = mapped_column(ForeignKey("rol.id_rol"), nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    # --- Control de fuerza bruta por cuenta ---
    intentos_fallidos: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime)
    ultimo_login: Mapped[datetime | None] = mapped_column(DateTime)

    # --- 2FA (TOTP) ---
    # totp_secret queda en NULL hasta /auth/2fa/setup; totp_habilitado solo
    # pasa a True tras confirmar un código válido en /auth/2fa/enable (así
    # nunca se le exige 2FA a alguien que configuró mal su app autenticadora).
    totp_secret: Mapped[str | None] = mapped_column(String(32))
    totp_habilitado: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())

    rol: Mapped["Rol"] = relationship(back_populates="usuarios")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )

    @property
    def rol_nombre(self) -> str:
        return self.rol.nombre

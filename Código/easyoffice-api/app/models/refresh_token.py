from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class RefreshToken(Base):
    """Nunca se guarda el token en texto plano, solo su hash SHA-256.

    Soporta rotación con detección de reuso: al refrescar, el token usado se
    marca revocado y se enlaza al nuevo via `reemplazado_por_id`. Si alguien
    presenta un token ya revocado (robado y usado después de que el dueño
    legítimo ya rotó), es señal de robo: se revocan todas las sesiones del
    usuario.
    """

    __tablename__ = "refresh_token"

    id_refresh_token: Mapped[int] = mapped_column(primary_key=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("usuario.id_usuario"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    expira_en: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revocado: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    reemplazado_por_id: Mapped[int | None] = mapped_column(ForeignKey("refresh_token.id_refresh_token"))

    usuario: Mapped["Usuario"] = relationship(back_populates="refresh_tokens")

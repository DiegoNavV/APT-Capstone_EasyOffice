"""Motor y sesiones de base de datos."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _crear_engine():
    settings = get_settings()
    url = settings.database_url
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    else:
        # Sin esto, una base de datos caída deja la petición colgada.
        connect_args = {"connect_timeout": settings.dependency_timeout_seconds}
    # pool_pre_ping: descarta conexiones muertas (ej. tras reiniciar Postgres).
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


engine = _crear_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

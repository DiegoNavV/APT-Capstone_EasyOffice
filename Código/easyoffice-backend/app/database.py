import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# En Docker Compose, DATABASE_URL apunta al servicio "db" (Postgres).
# Para pruebas unitarias, el archivo de tests sobreescribe esta URL por SQLite en memoria.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://easyoffice:easyoffice@db:5432/crm_easyoffice",
)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
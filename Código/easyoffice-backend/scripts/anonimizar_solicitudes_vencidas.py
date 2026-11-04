"""Anonimiza las solicitudes de contacto descartadas hace más de
app.retencion_datos.MESES_RETENCION_SOLICITUD_DESCARTADA meses (Ley 21.719).

Pensado para correr periódicamente (cron / tarea programada del despliegue), no a mano.

Uso (con los contenedores levantados):
    docker compose exec backend python scripts/anonimizar_solicitudes_vencidas.py
"""
import sys
from pathlib import Path

# Permite importar "app" al correr el script directamente.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal  # noqa: E402
from app.retencion_datos import anonimizar_solicitudes_vencidas  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        total = anonimizar_solicitudes_vencidas(db)
        print(f"{total} solicitud(es) de contacto anonimizada(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()

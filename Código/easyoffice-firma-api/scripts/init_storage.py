"""Crea el bucket de documentos en MinIO si no existe (idempotente).

Se ejecuta al arrancar el contenedor de la API (ver scripts/entrypoint.sh).
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.core.storage import get_storage_client  # noqa: E402


def main(intentos: int = 10) -> None:
    bucket = get_settings().s3_bucket_documents
    cliente = get_storage_client()
    for intento in range(1, intentos + 1):
        try:
            if not cliente.bucket_exists(bucket):
                cliente.make_bucket(bucket)
                print(f"Bucket creado: {bucket}")
            else:
                print(f"Bucket ya existe: {bucket}")
            return
        except Exception as exc:  # noqa: BLE001
            print(f"MinIO no disponible (intento {intento}/{intentos}): {type(exc).__name__}")
            time.sleep(2)
    raise SystemExit("No se pudo inicializar el almacenamiento.")


if __name__ == "__main__":
    main()

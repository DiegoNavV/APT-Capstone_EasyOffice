"""Cliente de almacenamiento S3/MinIO con tiempos de espera acotados.

Sin timeout, el cliente de MinIO reintenta por varios minutos si el servicio
está caído, y el health check o el arranque quedarían colgados.
"""
import urllib3
from minio import Minio

from app.core.config import get_settings


def get_storage_client() -> Minio:
    s = get_settings()
    http_client = urllib3.PoolManager(
        timeout=urllib3.Timeout(connect=s.dependency_timeout_seconds, read=s.dependency_timeout_seconds),
        retries=urllib3.Retry(total=1, backoff_factor=0.2),
    )
    return Minio(
        s.s3_endpoint,
        access_key=s.s3_access_key,
        secret_key=s.s3_secret_key,
        secure=s.s3_secure,
        http_client=http_client,
    )

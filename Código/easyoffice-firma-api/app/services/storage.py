"""Almacenamiento de archivos (PDF originales y firmados).

En la API se usa MinIO (compatible con S3). Los tests usan MemoryStorage para
no depender de servicios externos.
"""
import io
from typing import Protocol

from app.core.config import get_settings


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str = "application/pdf") -> None: ...

    def get(self, key: str) -> bytes: ...


class MinioStorage:
    def __init__(self) -> None:
        from app.core.storage import get_storage_client

        self._client = get_storage_client()
        self._bucket = get_settings().s3_bucket_documents

    def put(self, key: str, data: bytes, content_type: str = "application/pdf") -> None:
        self._client.put_object(self._bucket, key, io.BytesIO(data), length=len(data), content_type=content_type)

    def get(self, key: str) -> bytes:
        respuesta = self._client.get_object(self._bucket, key)
        try:
            return respuesta.read()
        finally:
            respuesta.close()
            respuesta.release_conn()


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, content_type: str = "application/pdf") -> None:
        self.objects[key] = bytes(data)

    def get(self, key: str) -> bytes:
        return self.objects[key]


def get_storage() -> Storage:
    """Dependencia de FastAPI (los tests la reemplazan por MemoryStorage)."""
    return MinioStorage()

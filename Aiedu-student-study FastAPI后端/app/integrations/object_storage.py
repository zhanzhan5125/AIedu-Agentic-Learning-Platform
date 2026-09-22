from __future__ import annotations

import io
from pathlib import Path

from app.core.config import get_settings


class ObjectStorage:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _client(self):
        from minio import Minio
        return Minio(
            self.settings.minio_endpoint,
            access_key=self.settings.minio_access_key,
            secret_key=self.settings.minio_secret_key,
            secure=self.settings.minio_secure,
        )

    def ensure_bucket(self) -> None:
        if self.settings.object_storage_backend != "minio":
            return
        client = self._client()
        if not client.bucket_exists(self.settings.minio_bucket):
            client.make_bucket(self.settings.minio_bucket)

    def put(self, key: str, content: bytes, content_type: str) -> None:
        if self.settings.object_storage_backend == "minio":
            self.ensure_bucket()
            self._client().put_object(
                self.settings.minio_bucket, key, io.BytesIO(content), len(content), content_type=content_type
            )
            return
        root = Path(self.settings.upload_dir).resolve() / "course-resources"
        target = (root / key).resolve()
        if root not in target.parents:
            raise ValueError("invalid object key")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def get(self, key: str) -> bytes:
        if self.settings.object_storage_backend == "minio":
            response = self._client().get_object(self.settings.minio_bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        return (Path(self.settings.upload_dir).resolve() / "course-resources" / key).read_bytes()

    def delete(self, key: str) -> None:
        if self.settings.object_storage_backend == "minio":
            self._client().remove_object(self.settings.minio_bucket, key)
            return
        target = Path(self.settings.upload_dir).resolve() / "course-resources" / key
        if target.is_file():
            target.unlink()


object_storage = ObjectStorage()

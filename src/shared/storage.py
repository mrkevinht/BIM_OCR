from __future__ import annotations

import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Tuple
from urllib.parse import urlparse

import boto3
from botocore.client import Config
from loguru import logger

from .config import get_settings


class StorageManager:
    """Thin wrapper around an S3-compatible object store."""

    def __init__(self) -> None:
        settings = get_settings()

        config_kwargs = {"signature_version": "s3v4"}
        if settings.storage_force_path_style:
            config_kwargs["s3"] = {"addressing_style": "path"}

        self._client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint or None,
            aws_access_key_id=settings.storage_access_key or None,
            aws_secret_access_key=settings.storage_secret_key or None,
            region_name=settings.storage_region or None,
            config=Config(**config_kwargs),
        )
        self._bucket = settings.storage_bucket
        self._prefix = settings.storage_prefix.strip("/")
        self._local_root = Path(settings.local_storage_root).resolve()

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def prefix(self) -> str:
        return self._prefix

    @property
    def local_root(self) -> Path:
        """Base directory used for temporary scratch space."""
        self._local_root.mkdir(parents=True, exist_ok=True)
        return self._local_root

    def build_key(self, *parts: str) -> str:
        clean_parts = [p.strip("/") for p in parts if p]
        key_body = "/".join(part for part in clean_parts if part)
        if self._prefix and key_body:
            return f"{self._prefix}/{key_body}"
        if self._prefix:
            return self._prefix
        return key_body

    def build_uri(self, key: str) -> str:
        return f"s3://{self._bucket}/{key}"

    @staticmethod
    def parse_uri(uri: str) -> Tuple[str, str]:
        parsed = urlparse(uri)
        if parsed.scheme != "s3":
            raise ValueError(f"Unsupported URI scheme for storage: {uri}")
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        return bucket, key

    def strip_prefix(self, key: str) -> str:
        if self._prefix:
            prefix_with_sep = f"{self._prefix}/"
            if key.startswith(prefix_with_sep):
                return key[len(prefix_with_sep) :]
            if key == self._prefix:
                return ""
        return key

    def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )

    def upload_file(self, key: str, file_path: Path, *, content_type: str | None = None) -> None:
        with file_path.open("rb") as handle:
            self.put_bytes(key, handle.read(), content_type=content_type)

    def download_to_path(self, key: str, file_path: Path) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        self._client.download_file(self._bucket, key, str(file_path))

    def get_bytes(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    def delete_prefix(self, prefix: str) -> None:
        paginator = self._client.get_paginator("list_objects_v2")
        objects_to_delete = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                objects_to_delete.append({"Key": obj["Key"]})

        if not objects_to_delete:
            logger.debug("No objects found under prefix %s for deletion", prefix)
            return

        logger.info("Deleting %s objects under prefix %s", len(objects_to_delete), prefix)
        for batch_start in range(0, len(objects_to_delete), 1000):
            chunk = objects_to_delete[batch_start : batch_start + 1000]
            self._client.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": chunk, "Quiet": True},
            )

    async def async_put_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> None:
        await asyncio.to_thread(self.put_bytes, key, data, content_type=content_type)

    async def async_delete_prefix(self, prefix: str) -> None:
        await asyncio.to_thread(self.delete_prefix, prefix)

    async def async_download_to_path(self, key: str, file_path: Path) -> None:
        await asyncio.to_thread(self.download_to_path, key, file_path)


@lru_cache(maxsize=1)
def get_storage_manager() -> StorageManager:
    return StorageManager()

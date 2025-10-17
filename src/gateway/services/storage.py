from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import UploadFile
from loguru import logger

from shared import get_settings
from shared.storage import StorageManager, get_storage_manager


settings = get_settings()
storage_manager: StorageManager = get_storage_manager()


async def persist_upload(upload: UploadFile, job_id: str) -> str:
    """
    Save the uploaded PDF to the shared object storage.

    Returns an S3 URI so that downstream tasks (including remote workers) can access it.
    """

    content_type = (
        upload.content_type
        or mimetypes.guess_type(upload.filename)[0]
        or "application/pdf"
    )
    key = storage_manager.build_key(job_id, "input", upload.filename)

    logger.debug("Uploading document for job {} to {}", job_id, key)
    contents = await upload.read()
    await storage_manager.async_put_bytes(key, contents, content_type=content_type)
    await upload.seek(0)
    return storage_manager.build_uri(key)


def get_local_workspace(job_id: str) -> Path:
    """
    Return the local scratch directory used for processing the job.

    The directory mirrors the remote storage layout to simplify caching and debugging.
    """

    workspace = storage_manager.local_root / job_id
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def download_to_workspace(storage_uri: str, job_id: str) -> Path:
    """
    Ensure the given storage object is available on the local filesystem.

    Returns the absolute path to the downloaded file.
    """

    bucket, key = storage_manager.parse_uri(storage_uri)
    if bucket != storage_manager.bucket:
        raise ValueError(f"Storage bucket mismatch: expected {storage_manager.bucket}, got {bucket}")

    relative_key = storage_manager.strip_prefix(key)
    local_path = get_local_workspace(job_id) / Path(relative_key or Path(key).name)
    if local_path.is_file():
        return local_path

    logger.debug("Downloading %s to %s", key, local_path)
    storage_manager.download_to_path(key, local_path)
    return local_path


def upload_page_image(job_id: str, filename: str, data: bytes) -> str:
    key = storage_manager.build_key(job_id, "pages", filename)
    storage_manager.put_bytes(key, data, content_type="image/png")
    return storage_manager.build_uri(key)


async def purge_job_cache(job_id: str, *, remove_original: bool = False) -> None:
    """
    Remove cached artefacts for the job from shared storage and clear local scratch data.

    Set ``remove_original`` to ``True`` to also delete the original uploaded document.
    """

    prefixes = [storage_manager.build_key(job_id, "pages")]
    if remove_original:
        prefixes.append(storage_manager.build_key(job_id, "input"))

    for prefix in prefixes:
        logger.info("Purging storage for job %s under prefix %s", job_id, prefix)
        await storage_manager.async_delete_prefix(prefix)

    local_workspace = storage_manager.local_root / job_id
    if local_workspace.exists():
        for path in sorted(local_workspace.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                path.rmdir()
        local_workspace.rmdir()

from pathlib import Path

from fastapi import UploadFile
from loguru import logger

from shared import get_settings


settings = get_settings()


async def persist_upload(upload: UploadFile, job_id: str) -> str:
    """
    Save the uploaded PDF to local storage (or a mounted object store).

    Returns the absolute file path so that downstream tasks can open it.
    """

    destination_dir = Path(settings.local_storage_root) / job_id
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / upload.filename

    logger.debug("Persisting upload for job {} to {}", job_id, destination)

    contents = await upload.read()
    destination.write_bytes(contents)
    await upload.seek(0)
    return str(destination.resolve())

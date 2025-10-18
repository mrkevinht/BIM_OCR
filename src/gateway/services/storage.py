from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile
from loguru import logger

from shared import get_settings

settings = get_settings()


def _job_root(job_id: str) -> Path:
    root = Path(settings.local_storage_root).resolve() / job_id
    root.mkdir(parents=True, exist_ok=True)
    return root


async def persist_upload(upload: UploadFile, job_id: str) -> str:
    """
    Save the uploaded PDF to local storage for downstream processing.
    """

    destination_dir = _job_root(job_id)
    destination = destination_dir / upload.filename

    logger.debug("Persisting upload for job %s to %s", job_id, destination)
    contents = await upload.read()
    destination.write_bytes(contents)
    await upload.seek(0)
    return str(destination)


def get_local_workspace(job_id: str) -> Path:
    """
    Return the local scratch directory used to store derived artefacts such as page images.
    """

    workspace = _job_root(job_id) / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def download_to_workspace(source_path: str, job_id: str) -> Path:
    """
    For local storage we can simply reuse the persisted file path.
    """

    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"Persisted document not found: {source_path}")
    return path


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def purge_job_cache(job_id: str, remove_original: bool = False) -> None:
    """
    Remove derived artefacts for the job. Optionally delete the original upload.
    """

    root = _job_root(job_id)
    if not root.exists():
        return

    workspace = root / "workspace"
    if workspace.exists():
        logger.info("Purging workspace cache for job %s under %s", job_id, workspace)
        for child in sorted(workspace.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        workspace.rmdir()

    if remove_original:
        logger.info("Removing original upload for job %s", job_id)
        for item in root.iterdir():
            if item.is_file():
                item.unlink(missing_ok=True)
            elif item.is_dir() and item.name != "workspace":
                for sub in sorted(item.rglob("*"), reverse=True):
                    if sub.is_file():
                        sub.unlink(missing_ok=True)
                    elif sub.is_dir():
                        sub.rmdir()
                item.rmdir()

    # Clean up root directory if empty
    try:
        next(root.iterdir())
    except StopIteration:
        root.rmdir()

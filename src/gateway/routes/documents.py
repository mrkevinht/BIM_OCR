from __future__ import annotations

import asyncio
from typing import List

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile
from loguru import logger

from shared.config import Settings, get_settings
from shared.schemas import DocumentJob, DocumentStatus, TaskType

from .. import tasks as gateway_tasks
from ..services import storage
from ..store import document_store

router = APIRouter(tags=["documents"])


def get_config() -> Settings:
    return get_settings()


@router.get("/documents", response_model=List[DocumentJob])
async def list_documents() -> List[DocumentJob]:
    return await document_store.list_jobs()


@router.get("/documents/{job_id}", response_model=DocumentJob)
async def get_document(job_id: str) -> DocumentJob:
    job = await document_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return job


@router.post(
    "/documents",
    response_model=DocumentJob,
    status_code=201,
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tasks: List[TaskType] = Query([TaskType.LAYOUT, TaskType.ROOMS, TaskType.ANNOTATIONS]),
    settings: Settings = Depends(get_config),
) -> DocumentJob:
    allowed_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
    extension = Path(file.filename).suffix.lower()
    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Only PDF or image uploads (png, jpg, webp) are supported",
        )

    job = await document_store.create_job(filename=file.filename, tasks=tasks)
    storage_uri = await storage.persist_upload(file, job.id)
    job_metadata = {
        "storage": "local",
        "path": storage_uri,
        "dpi": settings.page_image_dpi,
        "source_extension": extension or ".pdf",
    }
    job = job.model_copy(
        update={
            "storage_uri": storage_uri,
            "status": DocumentStatus.PROCESSING,
            "metadata": job_metadata,
        }
    )
    await document_store.upsert(job)

    background_tasks.add_task(gateway_tasks.enqueue_document_processing, job, storage_uri)
    logger.info("Job %s queued with tasks=%s", job.id, tasks)
    return job


@router.post("/documents/{job_id}/qa", status_code=202)
async def trigger_qa(
    job_id: str,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    job = await document_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if job.storage_uri is None:
        raise HTTPException(status_code=400, detail="Original document not available")

    if TaskType.QA not in job.tasks:
        job.tasks.append(TaskType.QA)
        await document_store.upsert(job)

    background_tasks.add_task(gateway_tasks.enqueue_document_processing, job, job.storage_uri)
    return {"status": "queued"}


@router.delete("/documents/{job_id}/cache", status_code=204)
async def clear_cache(job_id: str, remove_original: bool = Query(False)) -> Response:
    job = await document_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Document not found")

    await asyncio.to_thread(storage.purge_job_cache, job_id, remove_original)
    metadata = dict(job.metadata)
    metadata.update({"cache_cleared": True})
    if remove_original:
        job_update = {"storage_uri": None, "metadata": metadata}
    else:
        job_update = {"metadata": metadata}
    await document_store.upsert(job.model_copy(update=job_update))
    logger.info("Cleared cache for job %s (remove_original=%s)", job_id, remove_original)
    return Response(status_code=204)

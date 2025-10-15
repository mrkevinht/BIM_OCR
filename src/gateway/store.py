import asyncio
from datetime import datetime
from typing import Dict, List, Sequence
from uuid import uuid4

from loguru import logger

from shared.schemas import DocumentJob, DocumentStatus, TaskType


class DocumentStore:
    """Minimal in-memory repository. Replace with a persistent database in production."""

    def __init__(self) -> None:
        self._documents: Dict[str, DocumentJob] = {}
        self._lock = asyncio.Lock()

    async def create_job(self, filename: str, tasks: Sequence[TaskType]) -> DocumentJob:
        async with self._lock:
            job_id = uuid4().hex
            job = DocumentJob(id=job_id, filename=filename, tasks=list(tasks))
            self._documents[job_id] = job
            logger.debug("Created job {}", job_id)
            return job

    async def list_jobs(self) -> List[DocumentJob]:
        async with self._lock:
            return list(self._documents.values())

    async def get_job(self, job_id: str) -> DocumentJob | None:
        async with self._lock:
            return self._documents.get(job_id)

    async def update_status(self, job_id: str, status: DocumentStatus) -> DocumentJob | None:
        async with self._lock:
            job = self._documents.get(job_id)
            if job is None:
                return None
            job.status = status
            job.updated_at = datetime.utcnow()
            self._documents[job_id] = job
            logger.debug("Updated job {} to {}", job_id, status)
            return job

    async def upsert(self, job: DocumentJob) -> DocumentJob:
        async with self._lock:
            job.updated_at = datetime.utcnow()
            self._documents[job.id] = job
            logger.debug("Upserted job {}", job.id)
            return job


document_store = DocumentStore()

from __future__ import annotations

import asyncio
from typing import List

from celery import Celery
from loguru import logger

from shared import get_settings
from shared.schemas import DocumentJob

from .services import pdf_pipeline, runpod_client

settings = get_settings()

celery_app = Celery("bim_gateway", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    worker_max_tasks_per_child=50,
)


def enqueue_document_processing(job: DocumentJob, pdf_path: str) -> None:
    logger.info("Queueing document %s for processing", job.id)
    celery_app.send_task(
        "gateway.process_document",
        args=[job.model_dump(mode="json"), pdf_path],
    )


@celery_app.task(name="gateway.process_document", bind=True)
def process_document(self, job_payload: dict, pdf_path: str) -> List[dict]:
    job = DocumentJob.model_validate(job_payload)
    logger.info("Worker started processing job %s", job.id)

    attachments = pdf_pipeline.rasterize_pdf(pdf_path, job.id)
    llm_requests = pdf_pipeline.build_llm_requests(job, attachments)

    async def _submit_all() -> List[dict]:
        if not llm_requests:
            logger.warning("No LLM requests created for job %s", job.id)
            return []

        async with runpod_client.RunPodClient() as client:
            responses = await client.submit_batch(llm_requests)
        logger.info("Received %s responses from RunPod for job %s", len(responses), job.id)
        return [response.model_dump(mode="json") for response in responses]

    try:
        return asyncio.run(_submit_all())
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Processing failed for job %s: %s", job.id, exc)
        raise

from __future__ import annotations

import base64
from io import BytesIO
from typing import List

from loguru import logger

from shared import get_settings
from shared.schemas import Attachment, DocumentJob, LLMRequest, TaskType

from . import storage

settings = get_settings()


def rasterize_pdf(pdf_path: str, job_id: str) -> List[Attachment]:
    """
    Convert a PDF into page-level PNG images and return them as inline attachments.

    Returns a list of Attachment objects for downstream requests.
    """

    logger.info("Rasterising PDF for job %s", job_id)
    local_pdf = storage.download_to_workspace(pdf_path, job_id)
    output_dir = storage.get_local_workspace(job_id) / "pages"

    try:
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise RuntimeError(
            "pdf2image is required for rasterization. Ensure poppler is installed."
        ) from exc

    images = convert_from_path(str(local_pdf), dpi=settings.page_image_dpi)
    attachments: List[Attachment] = []
    for index, image in enumerate(images):
        page_name = f"page-{index:04d}.png"
        image_path = output_dir / page_name
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()
        storage.write_bytes(image_path, image_bytes)

        attachments.append(
            Attachment(
                filename=page_name,
                content_type="image/png",
                data_base64=base64.b64encode(image_bytes).decode("ascii"),
            )
        )
        logger.debug("Rendered page %s -> %s (inline attachment)", index, page_name)

    return attachments


def build_llm_requests(job: DocumentJob, attachments: List[Attachment]) -> List[LLMRequest]:
    """
    Create structured prompts for Qwen based on the job's requested tasks.
    """

    requests: List[LLMRequest] = []
    if not job.tasks:
        logger.warning("Job {} has no tasks configured, skipping prompt build", job.id)
        return requests

    base_prompts = {
        TaskType.LAYOUT: (
            "Analyze the architectural floor plan image and describe the primary layout "
            "elements including walls, structural grids, circulation paths, and key symbols. "
            "Return JSON with 'layout', 'symbols', and 'notes' arrays."
        ),
        TaskType.ROOMS: (
            "Extract every room with name, usage, area, and bounding polygon. "
            "Respond in JSON: {\"rooms\": [{\"name\": str, \"area\": float, "
            "\"level\": str | null, \"polygon\": [[x, y], ...]]}]. Coordinates normalised 0-1."
        ),
        TaskType.ANNOTATIONS: (
            "List dimensions, annotations, and legend items along with their coordinates. "
            "Return JSON with 'dimensions' and 'annotations' arrays."
        ),
        TaskType.QA: (
            "Evaluate the plan for basic code compliance and QA rules provided in the context. "
            "Output JSON {\"qa_results\": [{\"rule\": str, \"severity\": str, \"message\": str}]}."
        ),
        TaskType.COMPARE: (
            "Compare the supplied plan with context drawings and summarise differences. "
            "Output JSON {\"diffs\": [{\"description\": str, \"severity\": str}]}."
        ),
    }

    for page_index, attachment in enumerate(attachments):
        for task in job.tasks:
            prompt = base_prompts.get(task)
            if not prompt:
                logger.warning("No prompt template for task {}", task)
                continue

            request = LLMRequest(
                document_id=job.id,
                page_indices=[page_index],
                task=task,
                prompt=prompt,
                attachments=[attachment],
                context={"filename": job.filename},
            )
            requests.append(request)
            logger.debug(
                "Prepared LLM request for job {} page {} task {}", job.id, page_index, task
            )

    return requests

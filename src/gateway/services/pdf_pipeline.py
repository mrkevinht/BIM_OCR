from __future__ import annotations

from io import BytesIO
from typing import List

from loguru import logger

from shared import get_settings
from shared.schemas import DocumentJob, LLMRequest, TaskType

from . import storage

settings = get_settings()


def rasterize_pdf(pdf_uri: str, job_id: str) -> List[str]:
    """
    Convert a PDF into page-level PNG images and persist them to shared storage.

    Returns a list of storage URIs pointing to the generated images.
    """

    logger.info("Rasterising PDF for job %s", job_id)
    local_pdf = storage.download_to_workspace(pdf_uri, job_id)
    output_dir = storage.get_local_workspace(job_id) / "pages"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise RuntimeError(
            "pdf2image is required for rasterization. Ensure poppler is installed."
        ) from exc

    images = convert_from_path(str(local_pdf), dpi=settings.page_image_dpi)
    image_uris: List[str] = []
    for index, image in enumerate(images):
        page_name = f"page-{index:04d}.png"
        image_path = output_dir / page_name
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()
        image_path.write_bytes(image_bytes)

        uri = storage.upload_page_image(job_id, page_name, image_bytes)
        image_uris.append(uri)
        logger.debug("Rendered page %s -> %s", index, uri)

    return image_uris


def build_llm_requests(job: DocumentJob, image_paths: List[str]) -> List[LLMRequest]:
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

    for page_index, image_path in enumerate(image_paths):
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
                attachments=[image_path],
                context={"filename": job.filename},
            )
            requests.append(request)
            logger.debug(
                "Prepared LLM request for job {} page {} task {}", job.id, page_index, task
            )

    return requests

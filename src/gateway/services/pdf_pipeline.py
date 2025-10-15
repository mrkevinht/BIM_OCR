from __future__ import annotations

from pathlib import Path
from typing import List

from loguru import logger

from shared import get_settings
from shared.schemas import DocumentJob, LLMRequest, TaskType

settings = get_settings()


def rasterize_pdf(pdf_path: str, job_id: str) -> List[str]:
    """
    Convert a PDF into page-level PNG images for downstream vision inference.

    Returns a list of absolute file paths pointing to the generated images.
    """

    logger.info("Rasterising PDF for job {}", job_id)
    output_dir = Path(settings.local_storage_root) / job_id / "pages"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise RuntimeError(
            "pdf2image is required for rasterization. Ensure poppler is installed."
        ) from exc

    images = convert_from_path(pdf_path, dpi=settings.page_image_dpi)
    image_paths: List[str] = []
    for index, image in enumerate(images):
        image_path = output_dir / f"page-{index:04d}.png"
        image.save(image_path, "PNG")
        image_paths.append(str(image_path.resolve()))
        logger.debug("Rendered page {} -> {}", index, image_path)

    return image_paths


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

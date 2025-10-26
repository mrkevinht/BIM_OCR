from __future__ import annotations

import base64
from io import BytesIO
from math import sqrt
from pathlib import Path
from typing import List

from loguru import logger

from shared import get_settings
from shared.schemas import Attachment, DocumentJob, LLMBatchRequest, LLMTaskPrompt, TaskType

from . import storage

settings = get_settings()

MAX_BODY_BYTES = 7 * 1024 * 1024  # keep comfortably below 10MiB serverless limit
MAX_IMAGE_PIXELS = 4_000_000
INITIAL_JPEG_QUALITY = 85
MIN_JPEG_QUALITY = 45


def rasterize_pdf(pdf_path: str, job_id: str) -> List[Attachment]:
    """
    Convert an uploaded document into page-level JPEG images and return them as inline attachments.

    Returns a list of Attachment objects for downstream requests.
    """

    logger.info("Rasterising PDF for job %s", job_id)
    local_path = storage.download_to_workspace(pdf_path, job_id)
    output_dir = storage.get_local_workspace(job_id) / "pages"

    suffix = Path(local_path).suffix.lower()
    if suffix == ".pdf":
        return _rasterize_pdf_document(local_path, output_dir)
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return _make_single_page_attachment(local_path, output_dir)

    raise RuntimeError(f"Unsupported document type: {suffix}")


def _rasterize_pdf_document(local_pdf: Path, output_dir: Path) -> List[Attachment]:
    try:
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise RuntimeError(
            "pdf2image is required for rasterization. Ensure poppler is installed."
        ) from exc

    images = convert_from_path(str(local_pdf), dpi=settings.page_image_dpi)
    attachments: List[Attachment] = []
    for index, image in enumerate(images):
        attachment = _build_attachment(image, output_dir, index)
        attachments.append(attachment)
        logger.debug(
            "Rendered page %s -> %s (inline attachment)",
            index,
            attachment.filename,
        )

    return attachments


def _make_single_page_attachment(source_path: Path, output_dir: Path) -> List[Attachment]:
    logger.debug("Wrapping image %s as single-page attachment", source_path.name)
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required to process image uploads.") from exc

    image = Image.open(source_path)
    attachment = _build_attachment(image, output_dir, page_index=0)
    return [attachment]


def _build_attachment(image, output_dir: Path, page_index: int) -> Attachment:
    from PIL import Image

    if image.mode not in {"RGB", "RGBA"}:
        image = image.convert("RGB")

    image = _clamp_image_dimensions(image)

    quality = INITIAL_JPEG_QUALITY
    image_bytes = _encode_image(image, quality)

    while len(image_bytes) > MAX_BODY_BYTES and quality > MIN_JPEG_QUALITY:
        quality = max(MIN_JPEG_QUALITY, quality - 10)
        image_bytes = _encode_image(image, quality)

    if len(image_bytes) > MAX_BODY_BYTES:
        raise RuntimeError(
            f"Attachment for page {page_index} still exceeds size limit after compression "
            f"({len(image_bytes)} bytes)"
        )

    filename = f"page-{page_index:04d}.jpg"
    image_path = output_dir / filename
    storage.write_bytes(image_path, image_bytes)

    return Attachment(
        filename=filename,
        content_type="image/jpeg",
        data_base64=base64.b64encode(image_bytes).decode("ascii"),
    )


def _clamp_image_dimensions(image):
    width, height = image.size
    total_pixels = width * height
    if total_pixels <= MAX_IMAGE_PIXELS:
        return image.convert("RGB") if image.mode != "RGB" else image

    scale = sqrt(MAX_IMAGE_PIXELS / total_pixels)
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))

    from PIL import Image

    logger.warning(
        "Downscaling image from %sx%s to %sx%s to meet size limits",
        width,
        height,
        new_size[0],
        new_size[1],
    )
    return image.resize(new_size, Image.Resampling.LANCZOS).convert("RGB")


def _encode_image(image, quality: int) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def build_llm_requests(job: DocumentJob, attachments: List[Attachment]) -> List[LLMBatchRequest]:
    """
    Create structured prompts for Qwen based on the job's requested tasks.
    """

    requests: List[LLMBatchRequest] = []
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
        prompts: List[LLMTaskPrompt] = []
        for task in job.tasks:
            prompt = base_prompts.get(task)
            if not prompt:
                logger.warning("No prompt template for task {}", task)
                continue
            prompts.append(LLMTaskPrompt(task=task, prompt=prompt))

        if not prompts:
            continue

        request = LLMBatchRequest(
            document_id=job.id,
            page_indices=[page_index],
            tasks=prompts,
            attachments=[attachment],
            context={"filename": job.filename},
        )
        requests.append(request)
        logger.debug(
            "Prepared multi-task LLM request for job {} page {} tasks {}",
            job.id,
            page_index,
            [task.task for task in prompts],
        )

    return requests

from fastapi import FastAPI, HTTPException
from loguru import logger

from shared import get_settings
from shared.schemas import LLMBatchRequest, LLMResponse

from . import inference

settings = get_settings()

app = FastAPI(
    title="BIM OCR RunPod Worker",
    version="0.1.0",
    description="Thin wrapper exposing Qwen2.5-VL inference for BIM/OCR tasks.",
)


@app.get("/healthz")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "model": settings.model_version}


@app.post("/analyze", response_model=list[LLMResponse])
async def analyze(request: LLMBatchRequest) -> list[LLMResponse]:
    try:
        result = await inference.run_analysis(request)
        logger.info(
            "Processed RunPod batch for document %s page_indices=%s tasks=%s",
            request.document_id,
            request.page_indices,
            [task.task for task in request.tasks],
        )
        return result
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Inference failed: %s", exc)
        raise HTTPException(status_code=500, detail="Inference failed") from exc

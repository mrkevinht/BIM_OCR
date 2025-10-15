from fastapi import FastAPI, HTTPException
from loguru import logger

from shared import get_settings
from shared.schemas import LLMRequest, LLMResponse

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


@app.post("/analyze", response_model=LLMResponse)
async def analyze(request: LLMRequest) -> LLMResponse:
    try:
        result = await inference.run_analysis(request)
        logger.info(
            "Processed RunPod request %s for document %s task %s",
            result.request_id,
            request.document_id,
            request.task,
        )
        return result
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Inference failed: %s", exc)
        raise HTTPException(status_code=500, detail="Inference failed") from exc

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from loguru import logger
import runpod
from pydantic import ValidationError

from shared.schemas import LLMBatchRequest
from worker.inference import run_analysis


async def _process_event(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload = event.get("input", {})
    request = LLMBatchRequest.model_validate(payload)
    responses = await run_analysis(request)
    return [response.model_dump(mode="json") for response in responses]


def handler(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        results = asyncio.run(_process_event(event))
        return {"results": results}
    except ValidationError as exc:
        logger.error("Invalid payload received: %s", exc)
        return {"error": "validation_error", "details": exc.errors()}
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Unhandled error in serverless handler: %s", exc)
        return {"error": "internal_error", "message": str(exc)}


def main() -> None:
    runpod.serverless.start({"handler": handler})


if __name__ == "__main__":
    main()

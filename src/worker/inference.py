from __future__ import annotations

import asyncio
import time
from uuid import uuid4

from loguru import logger

from shared import get_settings
from shared.schemas import LLMBatchRequest, LLMResponse, TaskType

settings = get_settings()


async def run_analysis(request: LLMBatchRequest) -> list[LLMResponse]:
    """
    Placeholder inference routine.

    Replace this with real calls into Qwen2.5-VL (via vLLM, lmdeploy, or the RunPod SDK).
    """

    start_time = time.perf_counter()

    # Simulate some async workload while the real model would run.
    results: list[LLMResponse] = []
    for task_prompt in request.tasks:
        task_start = time.perf_counter()
        await asyncio.sleep(0.1)

        parsed_json = _build_stub_payload(task_prompt.task)
        raw_text = f"[stub] Completed {task_prompt.task} analysis for document {request.document_id}"
        latency_ms = int((time.perf_counter() - task_start) * 1000)

        logger.debug(
            "Stub inference completed request=%s task=%s latency_ms=%s",
            request.document_id,
            task_prompt.task,
            latency_ms,
        )

        results.append(
            LLMResponse(
                request_id=uuid4().hex,
                document_id=request.document_id,
                model_version=settings.model_version,
                task=task_prompt.task,
                raw_text=raw_text,
                parsed_json=parsed_json,
                tokens_input=None,
                tokens_output=None,
                latency_ms=latency_ms,
            )
        )

    logger.debug(
        "Stub batch completed document=%s total_tasks=%s total_latency_ms=%s",
        request.document_id,
        len(results),
        int((time.perf_counter() - start_time) * 1000),
    )

    return results


def _build_stub_payload(task: TaskType) -> dict:
    if task == TaskType.ROOMS:
        return {
            "rooms": [
                {
                    "id": "room-1",
                    "name": "Lobby",
                    "area_m2": 42.0,
                    "level": "Level 01",
                    "polygon": [[0.1, 0.1], [0.6, 0.1], [0.6, 0.4], [0.1, 0.4]],
                    "confidence": 0.5,
                }
            ]
        }
    if task == TaskType.LAYOUT:
        return {"layout": [{"type": "wall", "points": [[0.0, 0.0], [1.0, 0.0]]}]}
    if task == TaskType.ANNOTATIONS:
        return {
            "annotations": [
                {"id": "a-1", "text": "Detail A", "bbox": [0.2, 0.2, 0.3, 0.25], "confidence": 0.6}
            ],
            "dimensions": [],
        }
    if task == TaskType.QA:
        return {
            "qa_results": [
                {
                    "rule": "min_corridor_width",
                    "severity": "warning",
                    "message": "Corridor between Grid B and C under 1.2m",
                }
            ]
        }
    if task == TaskType.COMPARE:
        return {
            "diffs": [
                {"id": "diff-1", "description": "Lobby area increased by 5%", "severity": "info"}
            ]
        }
    return {}

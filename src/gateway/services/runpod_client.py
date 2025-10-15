from __future__ import annotations

from typing import Iterable, List

import httpx
from loguru import logger

from shared import get_settings
from shared.schemas import LLMRequest, LLMResponse

settings = get_settings()


class RunPodClient:
    """Thin HTTP client used to communicate with the Qwen inference worker."""

    def __init__(self, endpoint: str | None = None, api_key: str | None = None) -> None:
        self._endpoint = endpoint or settings.runpod_endpoint
        self._api_key = api_key or settings.runpod_api_key
        self._client = httpx.AsyncClient(base_url=self._endpoint, timeout=120.0)

    async def __aenter__(self) -> "RunPodClient":
        return self

    async def __aexit__(self, *exc_info) -> None:  # type: ignore[override]
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def submit(self, request: LLMRequest) -> LLMResponse:
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        logger.info(
            "Submitting request to RunPod: doc=%s task=%s pages=%s",
            request.document_id,
            request.task,
            request.page_indices,
        )

        response = await self._client.post(
            "/analyze",
            json=request.model_dump(mode="json"),
            headers=headers,
        )
        response.raise_for_status()

        payload = response.json()
        return LLMResponse(
            request_id=payload.get("request_id", ""),
            document_id=request.document_id,
            model_version=payload.get("model_version", "qwen2.5-vl-72b"),
            task=request.task,
            raw_text=payload.get("raw_text", ""),
            parsed_json=payload.get("parsed_json"),
            tokens_input=payload.get("tokens_input"),
            tokens_output=payload.get("tokens_output"),
            latency_ms=payload.get("latency_ms"),
        )

    async def submit_batch(self, requests: Iterable[LLMRequest]) -> List[LLMResponse]:
        results: List[LLMResponse] = []
        for request in requests:
            try:
                result = await self.submit(request)
                results.append(result)
            except httpx.HTTPError as exc:
                logger.exception("RunPod request failed for job %s", request.document_id)
                raise RuntimeError("RunPod request failed") from exc
        return results

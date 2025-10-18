from __future__ import annotations

import asyncio
from typing import Iterable, List

import httpx
from loguru import logger

from shared import get_settings
from shared.schemas import LLMRequest, LLMResponse

settings = get_settings()


class RunPodClient:
    """Thin HTTP client used to communicate with the Qwen inference worker."""

    def __init__(self, endpoint: str | None = None, api_key: str | None = None) -> None:
        configured_endpoint = (endpoint or settings.runpod_endpoint).rstrip("/")
        if configured_endpoint.endswith("/run") and "api.runpod.ai" in configured_endpoint:
            configured_endpoint = configured_endpoint[: -len("/run")]
        self._endpoint = configured_endpoint
        self._api_key = api_key or settings.runpod_api_key
        self._client = httpx.AsyncClient(base_url=self._endpoint, timeout=120.0)
        self._is_serverless = "api.runpod.ai" in self._endpoint

    async def __aenter__(self) -> "RunPodClient":
        return self

    async def __aexit__(self, *exc_info) -> None:  # type: ignore[override]
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def submit(self, request: LLMRequest) -> LLMResponse:
        if self._is_serverless:
            return await self._submit_serverless(request)

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
        return self._build_response(payload, request)

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

    async def _submit_serverless(self, request: LLMRequest) -> LLMResponse:
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = request.model_dump(mode="json")
        logger.info(
            "Submitting serverless RunPod request: doc=%s task=%s pages=%s",
            request.document_id,
            request.task,
            request.page_indices,
        )
        response = await self._client.post(
            "/run",
            json={"input": payload},
            headers=headers,
        )
        response.raise_for_status()
        job_info = response.json()
        job_id = job_info.get("id")
        if not job_id:
            raise RuntimeError("RunPod response missing job id")

        while True:
            status_response = await self._client.get(f"/status/{job_id}", headers=headers)
            status_response.raise_for_status()
            status_payload = status_response.json()
            status = status_payload.get("status")
            if status == "COMPLETED":
                output = status_payload.get("output")
                if isinstance(output, list):
                    output = output[0] if output else {}
                if not isinstance(output, dict):
                    raise RuntimeError("Unexpected serverless output format")
                return self._build_response(output, request)
            if status in {"FAILED", "CANCELLED"}:
                error_msg = status_payload.get("error", "Unknown error")
                raise RuntimeError(f"RunPod job {job_id} failed: {error_msg}")
            await asyncio.sleep(1.0)

    @staticmethod
    def _build_response(payload: dict, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            request_id=payload.get("request_id", ""),
            document_id=request.document_id,
            model_version=payload.get("model_version", settings.model_version),
            task=request.task,
            raw_text=payload.get("raw_text", ""),
            parsed_json=payload.get("parsed_json"),
            tokens_input=payload.get("tokens_input"),
            tokens_output=payload.get("tokens_output"),
            latency_ms=payload.get("latency_ms"),
        )

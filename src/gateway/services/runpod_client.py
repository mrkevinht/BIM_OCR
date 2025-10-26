from __future__ import annotations

import asyncio
import time
from typing import Iterable, List

import httpx
from loguru import logger

from shared import get_settings
from shared.schemas import LLMBatchRequest, LLMResponse, TaskType

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
        self._timeout_seconds = max(0, settings.runpod_serverless_timeout_seconds)
        self._poll_interval = max(0.2, settings.runpod_poll_interval_seconds)

    async def __aenter__(self) -> "RunPodClient":
        return self

    async def __aexit__(self, *exc_info) -> None:  # type: ignore[override]
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def submit(self, request: LLMBatchRequest) -> List[LLMResponse]:
        if self._is_serverless:
            return await self._submit_serverless(request)

        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        logger.info(
            "Submitting request to RunPod: doc=%s tasks=%s pages=%s",
            request.document_id,
            [task.task for task in request.tasks],
            request.page_indices,
        )

        response = await self._client.post(
            "/analyze",
            json=request.model_dump(mode="json"),
            headers=headers,
        )
        self._ensure_success(response, request, action="POST /analyze")

        payload = response.json()
        return self._build_responses(payload, request)

    async def submit_batch(self, requests: Iterable[LLMBatchRequest]) -> List[LLMResponse]:
        results: List[LLMResponse] = []
        for request in requests:
            try:
                result = await self.submit(request)
                results.extend(result)
            except Exception as exc:
                logger.exception("RunPod request failed for job %s", request.document_id)
                raise
        return results

    async def _submit_serverless(self, request: LLMBatchRequest) -> List[LLMResponse]:
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = request.model_dump(mode="json")
        logger.info(
            "Submitting serverless RunPod request: doc=%s tasks=%s pages=%s",
            request.document_id,
            [task.task for task in request.tasks],
            request.page_indices,
        )
        response = await self._client.post(
            "/run",
            json={"input": payload},
            headers=headers,
        )
        self._ensure_success(response, request, action="POST /run")
        job_info = response.json()
        job_id = job_info.get("id")
        if not job_id:
            raise RuntimeError("RunPod response missing job id")

        poll_attempts = 0
        deadline = time.monotonic() + self._timeout_seconds if self._timeout_seconds else None

        while True:
            if deadline and time.monotonic() >= deadline:
                task_names = [task.task for task in request.tasks]
                timeout_msg = (
                    f"RunPod job {job_id} exceeded timeout of {self._timeout_seconds}s "
                    f"(tasks={task_names}, pages={request.page_indices})"
                )
                raise RuntimeError(timeout_msg)

            poll_attempts += 1
            status_response = await self._client.get(f"/status/{job_id}", headers=headers)
            try:
                status_response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code in {429, 500, 502, 503, 504}:
                    delay = min(5.0, 1.0 + poll_attempts * 0.5)
                    logger.warning(
                        "Transient error when polling RunPod status for job %s (HTTP %s). Retrying in %.1fs",
                        job_id,
                        status_code,
                        delay,
                    )
                    sleep_for = delay
                    if deadline:
                        sleep_for = max(0.0, min(delay, deadline - time.monotonic()))
                    await asyncio.sleep(sleep_for)
                    continue
                raise RuntimeError(self._format_http_error(exc, request, "GET /status")) from exc

            status_payload = status_response.json()
            status = status_payload.get("status")
            if status == "COMPLETED":
                output = status_payload.get("output")
                if isinstance(output, list):
                    output = output[0] if output else {}
                return self._build_responses(output, request)
            if status in {"FAILED", "CANCELLED"}:
                error_msg = status_payload.get("error", "Unknown error")
                raise RuntimeError(f"RunPod job {job_id} failed: {error_msg}")
            sleep_for = self._poll_interval
            if deadline:
                sleep_for = max(0.0, min(self._poll_interval, deadline - time.monotonic()))
            await asyncio.sleep(sleep_for)

    @staticmethod
    def _normalize_task(raw_task: str | TaskType | None, request: LLMBatchRequest) -> TaskType:
        if isinstance(raw_task, TaskType):
            return raw_task
        if isinstance(raw_task, str):
            try:
                return TaskType(raw_task)
            except ValueError:
                logger.warning("Unknown task value '%s' returned by RunPod; defaulting to first task.", raw_task)
        return request.tasks[0].task if request.tasks else TaskType.LAYOUT

    def _build_responses(self, payload: dict | list, request: LLMBatchRequest) -> List[LLMResponse]:
        if payload is None:
            raise RuntimeError("RunPod response payload is empty")

        if isinstance(payload, list):
            entries = payload
        else:
            responses_field = payload.get("responses")
            if isinstance(responses_field, list):
                entries = responses_field
            else:
                entries = [payload]

        responses: List[LLMResponse] = []
        for entry in entries:
            if not isinstance(entry, dict):
                logger.warning("Skipping malformed response entry: %s", entry)
                continue
            task = self._normalize_task(entry.get("task"), request)
            responses.append(
                LLMResponse(
                    request_id=entry.get("request_id", ""),
                    document_id=request.document_id,
                    model_version=entry.get("model_version", settings.model_version),
                    task=task,
                    raw_text=entry.get("raw_text", ""),
                    parsed_json=entry.get("parsed_json"),
                    tokens_input=entry.get("tokens_input"),
                    tokens_output=entry.get("tokens_output"),
                    latency_ms=entry.get("latency_ms"),
                )
            )
        return responses

    def _ensure_success(self, response: httpx.Response, request: LLMBatchRequest, *, action: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(self._format_http_error(exc, request, action)) from exc

    def _format_http_error(
        self,
        exc: httpx.HTTPStatusError,
        request: LLMBatchRequest,
        action: str,
    ) -> str:
        status_code = exc.response.status_code
        body_text = exc.response.text.strip()
        if len(body_text) > 1000:
            body_preview = f"{body_text[:1000]}…"
        else:
            body_preview = body_text or "<empty body>"

        hint = ""
        if status_code == 401:
            hint = "Verify RUNPOD_API_KEY for endpoint %s" % self._endpoint
        elif status_code == 403:
            hint = "API key lacks permission for endpoint %s" % self._endpoint

        tasks_repr = [task.task for task in request.tasks] if request.tasks else []
        message = (
            "RunPod %s failed with HTTP %s for job %s (tasks=%s, pages=%s): %s"
            % (
                action,
                status_code,
                request.document_id,
                tasks_repr,
                request.page_indices,
                body_preview,
            )
        )

        if hint:
            message = f"{message}. Hint: {hint}"

        logger.error(message)
        return message

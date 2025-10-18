# BIM_OCR

Pipeline scaffolding for a BIM-focused OCR system that ingests architectural PDFs, delegates multimodal reasoning to a RunPod-hosted Qwen2.5-VL-72B worker, and returns structured BIM-ready data.

## Features
- FastAPI gateway for uploads, job tracking, and QA triggers.
- Celery worker orchestrating PDF rasterisation, prompt construction, and RunPod calls.
- RunPod-ready microservice exposing `/analyze` for Qwen inference (stubbed for local dev).
- Shared Pydantic schemas for BIM payloads, LLM requests, and QA outputs.
- Dockerised development stack with Redis; jobs are streamed to RunPod over HTTP (no shared S3 required).

## Project Layout
```
src/
├── gateway/            # Public API + orchestration logic
│   ├── main.py
│   ├── routes/
│   ├── services/
│   └── tasks.py
├── shared/             # Config + Pydantic schemas shared across services
└── worker/             # RunPod-facing inference wrapper
Dockerfile.gateway      # Builds the API/Celery image
Dockerfile.worker       # Builds the RunPod worker image
docker-compose.yml      # Local development stack
pyproject.toml          # Dependencies and package metadata
```

## Getting Started
1. **Prerequisites**
   - Docker Engine + Docker Compose v2
   - Poppler and Ghostscript if running the gateway outside Docker (for `pdf2image`)

2. **Run the stack**
   ```bash
   # Run against Runpod (needs docker/.env.runpod with endpoint/token)
   docker compose --env-file docker/.env.runpod up gateway celery redis

   # or run fully local with the stub worker
   docker compose --profile local-worker up gateway celery redis runpod-worker
   ```
   Services:
   - Gateway API: http://localhost:8000 (Swagger UI at `/docs`)
   - RunPod worker stub (profile `local-worker`): http://localhost:8100
   - Redis: localhost:6379

3. **Upload a PDF**
   ```bash
   curl -F "file=@/path/to/plan.pdf" "http://localhost:8000/api/v1/documents?tasks=layout&tasks=rooms"
   ```
   The gateway stores the PDF, queues processing, and the Celery worker submits stub requests to the RunPod service.

## Environment Variables
The services rely on `shared.config.Settings`. Override via `.env` or Docker env vars:

| Variable | Purpose | Default |
|----------|---------|---------|
| `RUNPOD_ENDPOINT` | URL pointing to the inference worker | `http://runpod-worker:8000` |
| `RUNPOD_API_KEY` | Bearer token passed to the worker | _empty_ |
| `REDIS_URL` | Celery broker/backend connection | `redis://redis:6379/0` |
| `LOCAL_STORAGE_ROOT` | Path for persisted uploads and images | `data/uploads` |
| `MODEL_VERSION` | Qwen model identifier reported downstream | `qwen2.5-vl-72b` |

## Next Steps
1. Replace the stubbed `worker.inference.run_analysis` with real Qwen2.5-VL integration (vLLM or lmdeploy).
2. Swap the in-memory `DocumentStore` with a persistent database (PostgreSQL) and add migrations.
3. Persist results to durable storage and integrate with downstream BIM tooling (e.g., Revit via MCP).
4. Harden QA/diff engines and add automated tests (`pytest`) plus linting (`ruff`).

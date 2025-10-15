# BIM_OCR

Pipeline scaffolding for a BIM-focused OCR system that ingests architectural PDFs, delegates multimodal reasoning to a RunPod-hosted Qwen2.5-VL-72B worker, and returns structured BIM-ready data.

## Features
- FastAPI gateway for uploads, job tracking, and QA triggers.
- Celery worker orchestrating PDF rasterisation, prompt construction, and RunPod calls.
- RunPod-ready microservice exposing `/analyze` for Qwen inference (stubbed for local dev).
- Shared Pydantic schemas for BIM payloads, LLM requests, and QA outputs.
- Dockerised development stack with Redis and MinIO for local experimentation.

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

2. **Build and run the stack**
   ```bash
   docker compose up --build
   ```
   Services:
   - Gateway API: http://localhost:8000 (Swagger UI at `/docs`)
   - RunPod worker stub: http://localhost:8100
   - MinIO console: http://localhost:9001 (user/pass `minioadmin`)
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
3. Implement storage adapters for MinIO/S3 and push JSON outputs to Revit via MCP.
4. Harden QA/diff engines and add automated tests (`pytest`) plus linting (`ruff`).

# Gateway Usage Guide

This guide shows how to run the FastAPI gateway, upload architectural PDFs, and send jobs either to the local stub worker or to the real Runpod endpoint. Files are streamed directly via HTTP (base64 payloads), so you no longer need MinIO or a shared S3 bucket.

---

## 1. Start the stack

The gateway needs Redis (Celery broker). Two ways to run:

### 1.1 Run against the real Runpod worker

1. Create `docker/.env.runpod` (git-ignored) with:
   ```
   RUNPOD_ENDPOINT=https://api.runpod.ai/v2/<endpoint-id>/run
   RUNPOD_API_KEY=<runpod-api-key-if-required>
   ```
   After editing the file, restart the stack (`docker compose down`, then run the desired `docker compose ...` command).

2. Start gateway + Celery + Redis:
   ```powershell
   cd D:\AI\vscode\qwen2.5-VL-72B\BIM_OCR
   docker compose --env-file docker/.env.runpod up gateway celery redis
   ```

   Default `RUNPOD_ENDPOINT` is the local stub at `http://runpod-worker:8000`; the env file overrides it.

### 1.2 Run with the local stub worker

If you want offline testing without touching Runpod, start the bundled worker profile:

```powershell
cd D:\AI\vscode\qwen2.5-VL-72B\BIM_OCR
docker compose --profile local-worker up gateway celery redis runpod-worker
```

In this mode, keep the defaults (`RUNPOD_ENDPOINT=http://runpod-worker:8000`). The stub simply echoes fake responses.

Stop the stack with `Ctrl+C`, or run `docker compose down` from another shell.

---

## 2. Use the Swagger UI

1. Open `http://localhost:8000/docs`.
2. Click **Try it out** on any endpoint before entering data; otherwise the inputs stay read-only.
3. Press **Execute** to send the request. Swagger displays the equivalent `curl` command, request payload, and server response.

---

## 3. Key endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/documents` | Upload a PDF and queue processing. Parameters: `tasks` query (default `layout,rooms,annotations`), `file` body (multipart). |
| `GET`  | `/api/v1/documents` | List known jobs from the in-memory store. |
| `GET`  | `/api/v1/documents/{job_id}` | Inspect a single job. |
| `POST` | `/api/v1/documents/{job_id}/qa` | Add QA task to an existing job and requeue it. |
| `DELETE` | `/api/v1/documents/{job_id}/cache` | Remove cached page images; pass `remove_original=true` to delete the original PDF as well. |
| `GET`  | `/healthz` | Lightweight readiness check. |

---

## 4. Processing workflow

1. Gateway saves the uploaded PDF to local disk (`data/uploads/<job_id>/`).
2. Celery worker rasterises each page into PNG, encodes them in base64, and sends the data inline to the Runpod endpoint using JSON.
3. Runpod (real or stub) returns JSON which the worker logs (persistence still TODO).
4. Cache cleanup endpoint deletes the generated images and optionally the original PDF.

---

## 5. Helpful curl snippets

Upload a document:
```bash
curl -X POST "http://localhost:8000/api/v1/documents?tasks=layout&tasks=rooms" \
     -H "accept: application/json" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@02-SITE BASEMENT.pdf;type=application/pdf"
```

Fetch job info:
```bash
curl http://localhost:8000/api/v1/documents/<job_id>
```

Trigger QA:
```bash
curl -X POST http://localhost:8000/api/v1/documents/<job_id>/qa
```

Clear cache:
```bash
curl -X DELETE http://localhost:8000/api/v1/documents/<job_id>/cache
```

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Upload fails immediately | File is not a PDF | Only `.pdf` uploads are accepted. |
| `Error -2 connecting to redis:6379` | Gateway started without Redis | Use compose to start `redis` service or update `REDIS_URL` to an existing broker. |
| No requests visible on Runpod dashboard | Gateway still calling local stub | Set `RUNPOD_ENDPOINT` in `docker/.env.runpod` and run compose with `--env-file docker/.env.runpod`. Do not start `runpod-worker` when sending to Runpod. |
| `UnicodeEncodeError` mentioning `Bearer` when calling Runpod | `RUNPOD_API_KEY` contains placeholder text or the word `Bearer` | Put only the raw Runpod token in `RUNPOD_API_KEY` (leave empty if Runpod endpoint does not need a key). |
| Port 8000 already in use | Previous container still bound to 8000 | `docker ps` then `docker stop <container>` or change mapping (`-p 8001:8000`). |
| Swagger has no "Choose file" button | Form is read-only | Click **Try it out** first. |

---

## 7. Operational tips

- **Hot reload:** Gateway runs with `--reload`, so code changes under `src/` reload automatically.
- **Large files:** Adjust Uvicorn limits or front with nginx if you need bigger uploads.
- **Persistence:** `DocumentStore` is in-memory; restart clears history. Replace with a database if you need durability.
- **Security:** Authentication is not enforced yet. Add FastAPI dependencies (API key, JWT, etc.) before exposing publicly.

---

## 8. Quick command reference

| Scenario | Command |
|----------|---------|
| Run against Runpod | `docker compose --env-file docker/.env.runpod up gateway celery redis` |
| Run fully local (stub worker) | `docker compose --profile local-worker up gateway celery redis runpod-worker` |
| Stop all containers | `docker compose down` |
| Rebuild images (after dependency changes) | `docker compose build gateway celery runpod-worker` |

Now you are ready to upload PDFs through Swagger UI or any HTTP client and see them processed by the gateway.


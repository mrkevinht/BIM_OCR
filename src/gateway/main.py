from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from shared import get_settings

from .routes import documents

settings = get_settings()

app = FastAPI(
    title="BIM OCR Gateway",
    version="0.1.0",
    description="Public API for uploading architectural PDFs and orchestrating Qwen OCR workflows.",
)

frontend_dir = Path(__file__).resolve().parent / "web"
if frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dir), name="assets")
    favicon_path = frontend_dir / "favicon.ico"
else:
    favicon_path = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router, prefix=settings.api_prefix)


@app.on_event("startup")
async def startup_event() -> None:
    logger.info("Gateway starting up in environment={}", settings.environment)


@app.get("/", include_in_schema=False)
async def index() -> HTMLResponse:
    """Serve the lightweight chat-style frontend."""
    if not frontend_dir.exists():
        return HTMLResponse("<h1>BIM OCR Gateway</h1><p>Frontend assets missing.</p>", status_code=200)

    index_path = frontend_dir / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            "<h1>BIM OCR Gateway</h1><p>frontend/web/index.html missing.</p>",
            status_code=200,
        )

    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    if favicon_path and favicon_path.exists():
        return FileResponse(favicon_path)
    return Response(status_code=204)


@app.get("/healthz", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}

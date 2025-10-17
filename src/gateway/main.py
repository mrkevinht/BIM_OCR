from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from shared import get_settings

from .routes import documents

settings = get_settings()

app = FastAPI(
    title="BIM OCR Gateway",
    version="0.1.0",
    description="Public API for uploading architectural PDFs and orchestrating Qwen OCR workflows.",
)

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
async def index() -> RedirectResponse:
    """Redirect the root URL to the interactive documentation."""
    return RedirectResponse(url="/docs")


@app.get("/healthz", tags=["health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}

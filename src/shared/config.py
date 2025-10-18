from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Centralised configuration pulled from environment variables.

    These settings are reused by the FastAPI gateway, Celery worker,
    and the RunPod inference wrapper so that every component stays in sync.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "dev"
    api_prefix: str = "/api/v1"

    # RunPod inference endpoint
    runpod_endpoint: str = "http://runpod-worker:8000"
    runpod_api_key: str | None = None
    model_version: str = "qwen2.5-vl-72b"

    # Local storage root
    local_storage_root: str = "data/uploads"

    # Messaging / task queue
    redis_url: str = "redis://redis:6379/0"

    # Database placeholder (swap with actual connection string when ready)
    database_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/bim_ocr"

    # Security / CORS
    cors_allow_origins: List[str] = ["*"]

    # File processing toggles
    max_concurrent_pages: int = 5
    page_image_dpi: int = 300
    enable_debug_prompts: bool = False

    # Revit MCP integration
    revit_mcp_endpoint: str = "http://revit-mcp:5000"
    revit_mcp_api_key: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


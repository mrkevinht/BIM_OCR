from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class TaskType(str, Enum):
    LAYOUT = "layout"
    ROOMS = "rooms"
    ANNOTATIONS = "annotations"
    QA = "qa"
    COMPARE = "compare"


class BoundingBox(BaseModel):
    """Stores a bounding box with normalised coordinates (0-1) relative to the page."""

    x_min: float = Field(ge=0.0, le=1.0)
    y_min: float = Field(ge=0.0, le=1.0)
    x_max: float = Field(ge=0.0, le=1.0)
    y_max: float = Field(ge=0.0, le=1.0)


class Polygon(BaseModel):
    points: List[List[float]] = Field(
        default_factory=list,
        description="List of [x, y] points in normalised page coordinates.",
    )


class Annotation(BaseModel):
    id: str
    text: str
    bbox: Optional[BoundingBox] = None
    category: str | None = Field(default=None, description="Legend, note, tag, etc.")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class Dimension(BaseModel):
    id: str
    text: str
    value_m: float
    bbox: Optional[BoundingBox] = None
    related_space_ids: List[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class BIMRoom(BaseModel):
    id: str
    name: str
    area_m2: float | None = None
    level: str | None = None
    height_m: float | None = None
    polygon: Polygon | None = None
    annotations: List[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class QAResult(BaseModel):
    id: str
    rule: str
    severity: str
    message: str
    location: BoundingBox | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiffEntry(BaseModel):
    id: str
    description: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    severity: str | None = None


class BIMPayload(BaseModel):
    document_id: str
    model_version: str
    rooms: List[BIMRoom] = Field(default_factory=list)
    dimensions: List[Dimension] = Field(default_factory=list)
    annotations: List[Annotation] = Field(default_factory=list)
    qa_results: List[QAResult] = Field(default_factory=list)
    diffs: List[DiffEntry] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Attachment(BaseModel):
    filename: str
    content_type: str
    data_base64: str


class LLMTaskPrompt(BaseModel):
    task: TaskType
    prompt: str


class LLMRequest(BaseModel):
    document_id: str
    page_indices: List[int]
    task: TaskType
    prompt: str
    attachments: List[Attachment] = Field(
        default_factory=list,
        description="Inline attachments (base64 encoded) that provide image or document context.",
    )
    context: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    request_id: str
    document_id: str
    model_version: str
    task: TaskType
    raw_text: str
    parsed_json: dict[str, Any] | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    latency_ms: int | None = None
    received_at: datetime = Field(default_factory=datetime.utcnow)


class LLMBatchRequest(BaseModel):
    document_id: str
    page_indices: List[int]
    tasks: List[LLMTaskPrompt] = Field(default_factory=list)
    attachments: List[Attachment] = Field(
        default_factory=list,
        description="Inline attachments (base64 encoded) that provide image or document context.",
    )
    context: dict[str, Any] = Field(default_factory=dict)


class DocumentJob(BaseModel):
    id: str
    filename: str
    status: DocumentStatus = DocumentStatus.PENDING
    tasks: List[TaskType] = Field(default_factory=list)
    num_pages: int | None = None
    submitted_by: str | None = None
    storage_uri: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

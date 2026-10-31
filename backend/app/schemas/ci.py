from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.analysis import CIDebugOutput


class WorkflowRunResponse(BaseModel):
    id: UUID
    repo_id: UUID
    name: str
    status: str
    conclusion: str | None = None
    head_sha: str | None = None
    html_url: str | None = None
    jobs: list[dict] = []
    logs_text: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class CIAnalysisResponse(BaseModel):
    analysis_id: UUID | str
    result: CIDebugOutput


class CIReproductionRequest(BaseModel):
    # No shell strings, environment overrides, image names or host paths.
    command: list[str] = Field(default_factory=lambda: ["python", "-m", "pytest", "-q"], min_length=1, max_length=32)
    working_directory: str = Field(default=".", max_length=300)

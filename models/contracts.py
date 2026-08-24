from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.artifacts import MediaAsset
from models.enums import Command, Mode, Profile, Stage, StageStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


class ArtifactRecord(StrictModel):
    artifact_id: str
    artifact_type: str
    path: str
    sha256: str
    input_hash: str
    created_by_stage: str
    created_at: datetime = Field(default_factory=utc_now)
    valid: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class StageRecord(StrictModel):
    status: StageStatus = StageStatus.PENDING
    input_hash: str | None = None
    output_hash: str | None = None
    attempts: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class ProjectState(StrictModel):
    schema_version: str = "1.3"
    project_id: str
    source_path: str
    source_hash: str
    mode: Mode
    profile: Profile
    current_stage: Stage = Stage.SOURCE_ANALYSIS
    status: str = "created"
    stages: dict[str, StageRecord]
    artifacts: dict[str, ArtifactRecord] = Field(default_factory=dict)
    last_action: str = "created"
    pending_tasks: list[str] = Field(default_factory=list)
    export_version: int = 0
    cache: dict[str, str] = Field(default_factory=dict)
    stage_instructions: dict[str, str | None] = Field(default_factory=dict)
    # Imported assets are explicit project inputs, not free-form AI instructions.
    user_assets: list[MediaAsset] = Field(default_factory=list)
    last_error: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    cancelled: bool = False


class ControlRequest(StrictModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    command: Command
    project_id: str | None = None
    source: str | None = None
    mode: Mode | None = None
    profile: Profile | None = None
    instructions: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("source")
    @classmethod
    def source_must_not_be_directory(cls, value: str | None) -> str | None:
        if value and Path(value).name in {"", ".", ".."}:
            raise ValueError("source должен указывать на файл")
        return value


class ControlResponse(StrictModel):
    request_id: str
    success: bool
    project_id: str | None = None
    status: str
    current_stage: str | None = None
    message: str
    artifacts: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    next_action: str | None = None
    requires_user_action: bool = False
    data: dict[str, Any] = Field(default_factory=dict)

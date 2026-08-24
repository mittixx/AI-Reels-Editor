from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from core.dependency_graph import ARTIFACT_FOR_STAGE, STAGE_ORDER, DependencyGraph
from core.errors import ProjectNotFoundError, StateError, ValidationAppError
from core.io_utils import atomic_write_json, read_json_model, sha256_file
from core.paths import ProjectPaths
from models.contracts import ArtifactRecord, ProjectState, StageRecord
from models.enums import Mode, Profile, Stage, StageStatus

PROJECT_ID_PATTERN = re.compile(r"^reel_[0-9]{8}_[0-9]{6}_[a-f0-9]{6}$")


class ProjectManager:
    def __init__(self, paths: ProjectPaths, graph: DependencyGraph | None = None) -> None:
        self.paths = paths
        self.graph = graph or DependencyGraph()
        self.paths.ensure()

    def project_dir(self, project_id: str) -> Path:
        if not PROJECT_ID_PATTERN.fullmatch(project_id):
            raise ValidationAppError("Некорректный project_id")
        return self.paths.projects / project_id

    def state_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "project_state.json"

    def create(self, source: Path, mode: Mode, profile: Profile) -> ProjectState:
        source = source.expanduser().resolve()
        if not source.is_file():
            raise ValidationAppError(f"Исходное видео не найдено: {source}")
        if source.stat().st_size <= 0:
            raise ValidationAppError("Исходное видео пустое")
        source_hash = sha256_file(source)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        project_id = f"reel_{timestamp}_{uuid4().hex[:6]}"
        stages = {stage.value: StageRecord() for stage in STAGE_ORDER}
        state = ProjectState(
            project_id=project_id,
            source_path=str(source),
            source_hash=source_hash,
            mode=mode,
            profile=profile,
            stages=stages,
        )
        project_dir = self.project_dir(project_id)
        for folder in ("artifacts", "working", "generated/motion", "renders", "cache", "capcut_package"):
            (project_dir / folder).mkdir(parents=True, exist_ok=True)
        self.save(state)
        return state

    def load(self, project_id: str) -> ProjectState:
        path = self.state_path(project_id)
        if not path.is_file():
            raise ProjectNotFoundError(f"Проект не найден: {project_id}")
        return read_json_model(path, ProjectState)

    def save(self, state: ProjectState) -> None:
        state.updated_at = datetime.now(UTC)
        atomic_write_json(self.state_path(state.project_id), state)

    def assert_source_unchanged(self, state: ProjectState) -> None:
        source = Path(state.source_path)
        if not source.is_file():
            raise StateError(f"Исходное видео недоступно: {source}")
        if sha256_file(source) != state.source_hash:
            raise StateError("Исходное видео изменилось. Создайте новый проект, чтобы не смешивать версии.")

    def mark_started(self, state: ProjectState, stage: Stage, input_hash: str) -> None:
        record = state.stages[stage.value]
        record.status = StageStatus.IN_PROGRESS
        record.input_hash = input_hash
        record.attempts += 1
        record.started_at = datetime.now(UTC)
        record.error_code = None
        record.error_message = None
        state.current_stage = stage
        state.status = "running"
        state.last_action = f"start:{stage.value}"
        self.save(state)

    def mark_completed(
        self,
        state: ProjectState,
        stage: Stage,
        output_hash: str,
        artifact: ArtifactRecord | None = None,
    ) -> None:
        record = state.stages[stage.value]
        record.status = StageStatus.COMPLETED
        record.output_hash = output_hash
        record.completed_at = datetime.now(UTC)
        if artifact:
            state.artifacts[artifact.artifact_type] = artifact
        state.last_action = f"complete:{stage.value}"
        self.save(state)

    def mark_skipped(self, state: ProjectState, stage: Stage, reason: str) -> None:
        record = state.stages[stage.value]
        record.status = StageStatus.SKIPPED
        record.output_hash = reason
        record.completed_at = datetime.now(UTC)
        state.last_action = f"skip:{stage.value}"
        self.save(state)

    def mark_failed(self, state: ProjectState, stage: Stage, code: str, message: str) -> None:
        record = state.stages[stage.value]
        record.status = StageStatus.FAILED
        record.error_code = code
        record.error_message = message
        state.status = "failed"
        state.last_error = {"stage": stage.value, "code": code, "message": message}
        state.last_action = f"fail:{stage.value}"
        self.save(state)

    def invalidate(self, state: ProjectState, stages: set[Stage]) -> None:
        project_dir = self.project_dir(state.project_id)
        for stage in stages:
            state.stages[stage.value] = StageRecord()
            artifact_name = ARTIFACT_FOR_STAGE.get(stage)
            if artifact_name:
                state.artifacts.pop(artifact_name, None)
                # Artifacts are retained on disk for audit/recovery; manifest validity controls reuse.
        state.current_stage = min(stages, key=STAGE_ORDER.index) if stages else state.current_stage
        state.status = "revision_pending"
        state.last_error = None
        state.last_action = "selective_invalidation"
        atomic_write_json(project_dir / "invalidation.json", {
            "schema_version": "1.3",
            "project_id": state.project_id,
            "invalidated": sorted(stage.value for stage in stages),
            "created_at": datetime.now(UTC).isoformat(),
        })
        self.save(state)

    def list_projects(self) -> list[ProjectState]:
        states: list[ProjectState] = []
        for path in sorted(self.paths.projects.glob("reel_*/project_state.json"), reverse=True):
            try:
                states.append(read_json_model(path, ProjectState))
            except ValidationAppError:
                continue
        return states

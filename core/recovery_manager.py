from __future__ import annotations

from pathlib import Path

from core.dependency_graph import STAGE_ORDER
from core.io_utils import sha256_file
from models.contracts import ProjectState, StageRecord
from models.enums import Stage, StageStatus


class RecoveryManager:
    def repair_state(self, state: ProjectState) -> list[str]:
        warnings: list[str] = []
        invalid_from: Stage | None = None
        for stage in STAGE_ORDER:
            record = state.stages[stage.value]
            if record.status == StageStatus.IN_PROGRESS:
                record.status = StageStatus.PENDING
                warnings.append(f"Этап {stage.value} возвращён в pending после прерывания")
            if record.status == StageStatus.COMPLETED:
                stage_artifacts = [a for a in state.artifacts.values() if a.created_by_stage == stage.value]
                for artifact in stage_artifacts:
                    path = Path(artifact.path)
                    if not path.is_file() or sha256_file(path) != artifact.sha256:
                        invalid_from = stage
                        warnings.append(f"Artifact этапа {stage.value} отсутствует или повреждён")
                        break
            if invalid_from:
                break
        if invalid_from:
            start = STAGE_ORDER.index(invalid_from)
            for stage in STAGE_ORDER[start:]:
                state.stages[stage.value] = StageRecord()
                for artifact in state.artifacts.values():
                    if artifact.created_by_stage == stage.value:
                        artifact.valid = False
            state.current_stage = invalid_from
            state.status = "recovery_pending"
        return warnings

    @staticmethod
    def completed_or_skipped(state: ProjectState) -> set[Stage]:
        return {
            Stage(name)
            for name, record in state.stages.items()
            if record.status in {StageStatus.COMPLETED, StageStatus.SKIPPED}
        }

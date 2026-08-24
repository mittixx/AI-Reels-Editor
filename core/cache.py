from __future__ import annotations

from pathlib import Path

from core.io_utils import sha256_file
from models.contracts import ProjectState
from models.enums import Stage, StageStatus


class CacheManager:
    def stage_hit(self, state: ProjectState, stage: Stage, input_hash: str) -> bool:
        record = state.stages[stage.value]
        if record.status not in {StageStatus.COMPLETED, StageStatus.SKIPPED}:
            return False
        if record.input_hash != input_hash:
            return False
        if record.status == StageStatus.SKIPPED:
            return record.output_hash is not None
        records = [item for item in state.artifacts.values() if item.created_by_stage == stage.value and item.valid]
        if not records:
            return False
        for artifact in records:
            path = Path(artifact.path)
            if not path.is_file() or sha256_file(path) != artifact.sha256:
                return False
        return True

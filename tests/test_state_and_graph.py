from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.cache import CacheManager
from core.dependency_graph import STAGE_ORDER, DependencyGraph
from core.io_utils import atomic_write_json, atomic_write_text, sha256_data, sha256_file
from core.paths import ProjectPaths
from core.project_manager import ProjectManager
from core.recovery_manager import RecoveryManager
from models.contracts import ArtifactRecord
from models.enums import Mode, Profile, Stage, StageStatus


def test_sha256_file_stable(tmp_path: Path) -> None:
    path = tmp_path / "a.bin"
    path.write_bytes(b"same")
    assert sha256_file(path) == sha256_file(path)


def test_sha256_data_order_independent() -> None:
    assert sha256_data({"a": 1, "b": 2}) == sha256_data({"b": 2, "a": 1})


def test_atomic_text_replaces(tmp_path: Path) -> None:
    path = tmp_path / "state.txt"
    atomic_write_text(path, "one")
    atomic_write_text(path, "two")
    assert path.read_text() == "two"
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_json_valid(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    atomic_write_json(path, {"schema_version": "1.3", "x": 1})
    assert json.loads(path.read_text())["x"] == 1


def test_dependency_graph_acyclic_and_ordered() -> None:
    graph = DependencyGraph()
    completed: set[Stage] = set()
    for expected in STAGE_ORDER:
        assert graph.first_runnable(completed) == expected
        completed.add(expected)
    assert graph.first_runnable(completed) is None


def test_selective_invalidation_broll_preserves_transcript() -> None:
    affected = DependencyGraph().for_revision("broll")
    assert Stage.VISUAL_PLAN in affected
    assert Stage.MASTER_RENDER in affected
    assert Stage.TRANSCRIPTION not in affected
    assert Stage.SOURCE_ANALYSIS not in affected


def test_selective_invalidation_hook_preserves_source() -> None:
    affected = DependencyGraph().for_revision("hook")
    assert Stage.SPEECH_ANALYSIS in affected
    assert Stage.TRANSCRIPTION not in affected


def test_unknown_revision_scope() -> None:
    with pytest.raises(ValueError):
        DependencyGraph().for_revision("everything")


def test_project_manager_create_and_load(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    manager = ProjectManager(ProjectPaths(tmp_path / "app"))
    state = manager.create(source, Mode.FAST, Profile.EXPERT)
    loaded = manager.load(state.project_id)
    assert loaded.source_hash == sha256_file(source)
    assert len(loaded.stages) == len(STAGE_ORDER)


def test_source_change_detected(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"v1")
    manager = ProjectManager(ProjectPaths(tmp_path / "app"))
    state = manager.create(source, Mode.FAST, Profile.EXPERT)
    source.write_bytes(b"v2")
    with pytest.raises(Exception, match="изменилось"):
        manager.assert_source_unchanged(state)


def test_recovery_resets_in_progress(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    manager = ProjectManager(ProjectPaths(tmp_path / "app"))
    state = manager.create(source, Mode.FAST, Profile.EXPERT)
    state.stages[Stage.TRANSCRIPTION.value].status = StageStatus.IN_PROGRESS
    warnings = RecoveryManager().repair_state(state)
    assert state.stages[Stage.TRANSCRIPTION.value].status == StageStatus.PENDING
    assert warnings


def test_recovery_invalidates_corrupt_artifact(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    manager = ProjectManager(ProjectPaths(tmp_path / "app"))
    state = manager.create(source, Mode.FAST, Profile.EXPERT)
    artifact = manager.project_dir(state.project_id) / "artifacts" / "video_info.json"
    artifact.write_text("good")
    state.stages[Stage.SOURCE_ANALYSIS.value].status = StageStatus.COMPLETED
    state.artifacts[artifact.name] = ArtifactRecord(
        artifact_id="a", artifact_type=artifact.name, path=str(artifact), sha256=sha256_file(artifact),
        input_hash="i", created_by_stage=Stage.SOURCE_ANALYSIS.value,
    )
    artifact.write_text("corrupt")
    RecoveryManager().repair_state(state)
    assert state.stages[Stage.SOURCE_ANALYSIS.value].status == StageStatus.PENDING


def test_cache_hit_requires_hash_and_artifact(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    manager = ProjectManager(ProjectPaths(tmp_path / "app"))
    state = manager.create(source, Mode.FAST, Profile.EXPERT)
    artifact = manager.project_dir(state.project_id) / "artifacts" / "x.json"
    artifact.write_text("{}")
    record = state.stages[Stage.SOURCE_ANALYSIS.value]
    record.status = StageStatus.COMPLETED
    record.input_hash = "input"
    state.artifacts[artifact.name] = ArtifactRecord(
        artifact_id="a", artifact_type=artifact.name, path=str(artifact), sha256=sha256_file(artifact),
        input_hash="input", created_by_stage=Stage.SOURCE_ANALYSIS.value,
    )
    assert CacheManager().stage_hit(state, Stage.SOURCE_ANALYSIS, "input")
    artifact.write_text("changed")
    assert not CacheManager().stage_hit(state, Stage.SOURCE_ANALYSIS, "input")

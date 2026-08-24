from __future__ import annotations

from pathlib import Path

from core.control_service import ControlService
from core.io_utils import atomic_write_json, sha256_file
from core.paths import ProjectPaths
from core.project_manager import ProjectManager
from models.artifacts import MediaAsset, MediaManifest
from models.contracts import ControlRequest
from models.enums import Command, Mode, Profile, Stage, StageStatus


class FakePipeline:
    def __init__(self, manager: ProjectManager) -> None:
        self.manager = manager
        self.calls: list[tuple[str, str | None, Stage | None]] = []

    def run(self, project_id, instructions=None, stop_after=None):
        self.calls.append((project_id, instructions, stop_after))
        state = self.manager.load(project_id)
        state.status = "partial" if stop_after else "completed"
        self.manager.save(state)
        return state


class FakeDoctor:
    def run(self):
        return {"schema_version": "1.3", "ok": True, "checks": []}


class FakeCapCut:
    pass


def service(runtime_config):
    manager = ProjectManager(ProjectPaths(runtime_config.root))
    pipeline = FakePipeline(manager)
    return ControlService(runtime_config, manager, pipeline, FakeDoctor(), FakeCapCut()), manager, pipeline


def test_create_routes_through_pipeline(runtime_config, tmp_path: Path) -> None:
    control, manager, pipeline = service(runtime_config)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    response = control.execute(ControlRequest(
        command=Command.CREATE_REEL, source=str(source), mode=Mode.FAST, profile=Profile.EXPERT,
    ))
    assert response.success
    assert response.project_id
    assert len(pipeline.calls) == 1


def test_status_does_not_run_pipeline(runtime_config, tmp_path: Path) -> None:
    control, manager, pipeline = service(runtime_config)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    state = manager.create(source, Mode.FAST, Profile.EXPERT)
    response = control.execute(ControlRequest(command=Command.STATUS, project_id=state.project_id))
    assert response.success
    assert pipeline.calls == []


def test_resume_uses_same_pipeline(runtime_config, tmp_path: Path) -> None:
    control, manager, pipeline = service(runtime_config)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    state = manager.create(source, Mode.FAST, Profile.EXPERT)
    control.execute(ControlRequest(command=Command.RESUME, project_id=state.project_id))
    assert pipeline.calls[0][0] == state.project_id


def test_revise_broll_preserves_transcription(runtime_config, tmp_path: Path) -> None:
    control, manager, pipeline = service(runtime_config)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    state = manager.create(source, Mode.FAST, Profile.EXPERT)
    for record in state.stages.values():
        record.status = StageStatus.COMPLETED
    manager.save(state)
    response = control.execute(ControlRequest(
        command=Command.REVISE, project_id=state.project_id, instructions="Меньше B-roll", parameters={"scope": "broll"},
    ))
    revised = manager.load(state.project_id)
    assert response.success
    assert revised.stages[Stage.TRANSCRIPTION.value].status == StageStatus.COMPLETED
    assert pipeline.calls


def test_missing_project_is_structured_error(runtime_config) -> None:
    control, *_ = service(runtime_config)
    response = control.execute(ControlRequest(command=Command.STATUS, project_id="reel_20260824_120000_abcdef"))
    assert not response.success
    assert response.errors[0]["code"] == "PROJECT_NOT_FOUND"


def test_doctor_control_response(runtime_config) -> None:
    control, *_ = service(runtime_config)
    response = control.execute(ControlRequest(command=Command.DOCTOR))
    assert response.success
    assert response.status == "healthy"


def test_import_asset_records_stable_catalog_and_existing_manifest(
    runtime_config, tmp_path: Path, monkeypatch
) -> None:
    control, manager, _ = service(runtime_config)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    state = manager.create(source, Mode.FAST, Profile.EXPERT)
    artifact_dir = manager.project_dir(state.project_id) / "artifacts"
    atomic_write_json(artifact_dir / "media_manifest.json", MediaManifest(
        project_id=state.project_id,
        assets=[MediaAsset(id="source", type="video", path=str(source), sha256=sha256_file(source), source="user")],
    ))
    imported = tmp_path / "imported.mp4"
    imported.write_bytes(b"asset")
    asset = MediaAsset(id="asset_stable", type="video", path=str(imported), sha256=sha256_file(imported), source="user", duration=1)
    monkeypatch.setattr("core.control_service.AssetCatalog.import_asset", lambda *args: asset)
    response = control.execute(ControlRequest(
        command=Command.IMPORT_ASSET, project_id=state.project_id,
        parameters={"file": str(imported), "kind": "video"},
    ))
    assert response.success and response.data["asset_id"] == "asset_stable"
    saved = manager.load(state.project_id)
    assert saved.user_assets[0].id == "asset_stable"
    manifest = MediaManifest.model_validate_json((artifact_dir / "media_manifest.json").read_text())
    assert {item.id for item in manifest.assets} == {"source", "asset_stable"}

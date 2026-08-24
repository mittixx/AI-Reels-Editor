from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core.errors import ValidationAppError
from core.quality_control import QualityControl
from core.render_planner import RenderPlanner
from core.render_router import RenderRouter
from integrations.ffmpeg import FFmpegAdapter
from integrations.hyperframes import HyperFramesIntegration
from integrations.motion_canvas import MotionCanvasIntegration
from integrations.process import run_process
from models.artifacts import (
    EditPlan,
    MediaAsset,
    MediaManifest,
    MotionItem,
    MotionPlan,
    TimeRange,
    VideoInfo,
    VisualItem,
    VisualPlan,
)


def _video(tmp_path: Path, duration: float = 2) -> VideoInfo:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    from core.io_utils import sha256_file
    return VideoInfo(project_id="p", source_path=str(source), source_hash=sha256_file(source), duration=duration, width=1080, height=1920, orientation="portrait", fps=30, video_codec="h264", has_audio=True, decodable=True, file_size=source.stat().st_size)


def test_hyperframes_prefers_cmd_on_windows(tmp_path: Path) -> None:
    cli = tmp_path / "hyperframes"
    cmd = tmp_path / "hyperframes.cmd"
    cli.write_text("linux", encoding="utf-8")
    cmd.write_text("windows", encoding="utf-8")
    integration = HyperFramesIntegration(local_cli=cli)
    assert integration._installed_cli(platform="nt") == cmd
    assert integration._installed_cli(platform="posix") == cli


@pytest.mark.skipif(os.name != "nt", reason="requires real Windows cmd.exe")
def test_windows_cmd_subprocess_launches_for_hyperframes_and_motion(tmp_path: Path) -> None:
    script = tmp_path / "fake-tool.cmd"
    script.write_text("@echo off\r\necho launcher-ok\r\nexit /b 0\r\n", encoding="utf-8")
    result = run_process([str(script)], check=False)
    assert result.returncode == 0 and "launcher-ok" in result.stdout
    node_project = tmp_path / "motion"
    node_project.mkdir()
    (node_project / "package.json").write_text("{}", encoding="utf-8")
    item = MotionItem(id="x", visual_id="v", component="Callout", start=0, duration=1, data={"text": "x"}, preset="default", output_path=str(tmp_path / "out.mp4"), cache_key="x")
    job = MotionCanvasIntegration(npm_bin=str(script)).render(node_project, item, tmp_path / "jobs")
    assert job.process.returncode == 0


def test_corrupt_image_is_rejected_before_render(tmp_path: Path) -> None:
    video = _video(tmp_path)
    image = tmp_path / "bad.png"
    image.write_bytes(b"not png")
    from core.io_utils import sha256_file
    visual = VisualPlan(project_id="p", output_duration=2, profile="expert", items=[VisualItem(id="shot", intent="screenshot", start=0, duration=1, asset_id="bad")])
    manifest = MediaManifest(project_id="p", assets=[MediaAsset(id="source", type="video", path=video.source_path, sha256=video.source_hash, source="user"), MediaAsset(id="bad", type="image", path=str(image), sha256=sha256_file(image), source="user")])
    edit = EditPlan(project_id="p", keep_ranges=[TimeRange(id="k", start=0, end=2)], estimated_duration=2)
    with pytest.raises(ValidationAppError, match="image asset"):
        RenderPlanner(RenderRouter()).plan(tmp_path, video, edit, visual, MotionPlan(project_id="p", required=False), manifest, {})


def test_zoom_across_cut_is_rejected(tmp_path: Path) -> None:
    video = _video(tmp_path)
    visual = VisualPlan(project_id="p", output_duration=2, profile="expert", items=[VisualItem(id="z", intent="simple_zoom", start=.5, duration=1)])
    edit = EditPlan(project_id="p", keep_ranges=[TimeRange(id="a", start=0, end=1), TimeRange(id="b", start=10, end=11)], estimated_duration=2)
    manifest = MediaManifest(project_id="p", assets=[])
    with pytest.raises(ValueError, match="пересекает монтажный cut"):
        RenderPlanner(RenderRouter()).plan(tmp_path, video, edit, visual, MotionPlan(project_id="p", required=False), manifest, {})


def test_broll_duration_contract_uses_offset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core import render_validation
    asset = tmp_path / "asset.mp4"
    asset.write_bytes(b"media")
    from core.io_utils import sha256_file
    op = __import__("models.artifacts", fromlist=["RenderOperation"]).RenderOperation(id="b", operation="b_roll", renderer="hyperframes", start=0, duration=3, inputs=["a"], parameters={"media_offset": .5})
    plan = __import__("models.artifacts", fromlist=["RenderPlan"]).RenderPlan(project_id="p", fps=30, duration=3, operations=[op], output_path=str(tmp_path / "draft.mp4"), cache_key="x")
    manifest = MediaManifest(project_id="p", assets=[MediaAsset(id="a", type="video", path=str(asset), sha256=sha256_file(asset), source="user")])
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "probe", lambda _: {"format": {"duration": "2"}, "streams": [{"codec_type": "video", "width": 1, "height": 1, "avg_frame_rate": "25/1"}]})
    monkeypatch.setattr(adapter, "decode_check", lambda _: True)
    with pytest.raises(ValidationAppError, match="media duration"):
        render_validation.validate_media_operations(plan, manifest, adapter)
    op.parameters["loop"] = True
    render_validation.validate_media_operations(plan, manifest, adapter)


def test_modified_motion_mp4_sha_is_rejected_before_master_render(tmp_path: Path) -> None:
    from core import render_validation
    motion = tmp_path / "motion.mp4"
    motion.write_bytes(b"original")
    from core.io_utils import sha256_file
    manifest = MediaManifest(project_id="p", assets=[MediaAsset(id="motion", type="motion", path=str(motion), sha256=sha256_file(motion), source="generated")])
    motion.write_bytes(b"modified")
    operation = __import__("models.artifacts", fromlist=["RenderOperation"]).RenderOperation(id="m", operation="animated_stat", renderer="motion_canvas", start=0, duration=1, inputs=["motion"])
    plan = __import__("models.artifacts", fromlist=["RenderPlan"]).RenderPlan(project_id="p", fps=30, duration=1, operations=[operation], output_path=str(tmp_path / "draft.mp4"), cache_key="x")
    with pytest.raises(ValidationAppError, match="изменён после manifest"):
        render_validation.validate_media_operations(plan, manifest)


def test_black_output_is_critical(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "black.mp4"
    output.write_bytes(b"x")
    adapter = FFmpegAdapter()
    monkeypatch.setattr(adapter, "probe", lambda _: {"format": {"duration": "2"}, "streams": [{"codec_type": "video", "width": 1080, "height": 1920, "avg_frame_rate": "25/1", "codec_name": "h264"}, {"codec_type": "audio"}]})
    monkeypatch.setattr(adapter, "decode_check", lambda _: True)
    monkeypatch.setattr(adapter, "black_frames", lambda _: [{"start": 0, "end": 2, "duration": 2}])
    report = QualityControl(adapter).inspect("p", output)
    assert not report.export_allowed and any(issue.code == "BLACK_OUTPUT" and issue.severity == "critical" for issue in report.issues)


def test_schemas_match_current_models() -> None:
    from models.artifacts import EditPlan, MotionPlan, RenderPlan, Transcript, VisualPlan
    from models.contracts import ControlRequest, ControlResponse, ProjectState
    root = Path(__file__).resolve().parents[1] / "schemas"
    for model in (ControlRequest, ControlResponse, ProjectState, Transcript, EditPlan, VisualPlan, MotionPlan, RenderPlan):
        assert json.loads((root / f"{model.__name__}.schema.json").read_text(encoding="utf-8")) == model.model_json_schema()

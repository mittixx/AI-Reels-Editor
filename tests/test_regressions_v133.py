from __future__ import annotations

import json
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

from core.asset_catalog import AssetCatalog
from core.errors import ValidationAppError
from core.io_utils import sha256_file
from core.media_manager import MediaManager
from core.render_planner import RenderPlanner
from core.render_router import RenderRouter
from core.transcriber import FasterWhisperProvider
from core.visual_planner import VisualPlanner
from integrations.hyperframes import HyperFramesIntegration
from models.artifacts import (
    EditPlan,
    MediaAsset,
    MediaManifest,
    MotionPlan,
    SpeechAnalysis,
    TimeRange,
    Transcript,
    TranscriptSegment,
    VideoInfo,
    VisualItem,
    VisualPlan,
)


def _video(path: Path, duration: float = 20) -> VideoInfo:
    path.write_bytes(b"source")
    return VideoInfo(
        project_id="p", source_path=str(path), source_hash=sha256_file(path), duration=duration,
        width=1080, height=1920, orientation="portrait", fps=30, video_codec="h264",
        audio_codec="aac", has_audio=True, decodable=True, file_size=path.stat().st_size,
    )


def _make_mp4(path: Path, color: str = "red") -> None:
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg unavailable")
    result = subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x240:d=1:r=25",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ], capture_output=True, text=True, timeout=120, check=False)
    assert result.returncode == 0, result.stderr


def test_windows_motion_launcher_uses_explicit_cmd_contract() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable")
    script = (
        "import {buildNpmServeLaunchSpec} from './node_tools/motion_canvas/scripts/process_launcher.mjs';"
        "console.log(JSON.stringify({win:buildNpmServeLaunchSpec({platform:'win32',comSpec:'C:/Windows/System32/cmd.exe',runtimeRoot:'C:/jobs/job_1',port:9321}),linux:buildNpmServeLaunchSpec({platform:'linux',runtimeRoot:'/tmp/job_1',port:9321})}));"
    )
    result = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    payload = json.loads(result.stdout)
    assert payload["win"]["command"].endswith("cmd.exe")
    assert payload["win"]["args"][:3] == ["/d", "/s", "/c"]
    assert "npm.cmd" in payload["win"]["args"][3]
    assert payload["win"]["shell"] is False
    assert payload["linux"] == {"command": "npm.cmd", "args": ["run", "serve", "--", "/tmp/job_1", "--port", "9321", "--strictPort"], "shell": False}


def test_corrupt_broll_with_matching_manifest_sha_is_rejected_before_render(tmp_path: Path) -> None:
    source = _video(tmp_path / "source.mp4", duration=4)
    corrupt = tmp_path / "corrupt.mp4"
    corrupt.write_bytes(b"not an mp4 but sha matches this manifest")
    visual = VisualPlan(project_id="p", output_duration=4, profile="expert", items=[
        VisualItem(id="b", intent="b_roll", start=0, duration=1, asset_id="asset_bad"),
    ])
    manifest = MediaManifest(project_id="p", assets=[
        MediaAsset(id="source", type="video", path=source.source_path, sha256=source.source_hash, source="user", duration=4),
        MediaAsset(id="asset_bad", type="video", path=str(corrupt), sha256=sha256_file(corrupt), source="user"),
    ])
    edit = EditPlan(project_id="p", keep_ranges=[TimeRange(id="k", start=0, end=4)], estimated_duration=4)
    with pytest.raises(ValidationAppError, match="ffprobe|decode-check"):
        RenderPlanner(RenderRouter()).plan(tmp_path, source, edit, visual, MotionPlan(project_id="p", required=False), manifest, {})


def test_broll_without_imported_asset_is_rejected_before_master_render(tmp_path: Path) -> None:
    source = _video(tmp_path / "source.mp4", duration=4)
    visual = VisualPlan(project_id="p", output_duration=4, profile="expert", items=[
        VisualItem(id="b", intent="b_roll", start=0, duration=1, asset_id="missing"),
    ])
    with pytest.raises(ValidationAppError, match="imported asset catalog"):
        MediaManager().build_manifest(source, MotionPlan(project_id="p", required=False), visual, [])


def test_zoom_contract_maps_output_time_to_original_source_offset(tmp_path: Path) -> None:
    source = _video(tmp_path / "source.mp4")
    edit = EditPlan(project_id="p", keep_ranges=[TimeRange(id="k", start=10, end=14)], estimated_duration=4)
    visual = VisualPlan(project_id="p", output_duration=4, profile="expert", items=[
        VisualItem(id="z", intent="simple_zoom", start=2, duration=1),
    ])
    manifest = MediaManifest(project_id="p", assets=[MediaAsset(id="source", type="video", path=source.source_path, sha256=source.source_hash, source="user")])
    plan = RenderPlanner(RenderRouter()).plan(tmp_path, source, edit, visual, MotionPlan(project_id="p", required=False), manifest, {})
    zoom = next(item for item in plan.operations if item.id == "z")
    assert zoom.parameters["source_media_start"] == 12
    assert zoom.parameters["source_media_end"] == 13
    base = tmp_path / "base.mp4"
    base.write_bytes(b"base")
    composition = tmp_path / "composition"
    HyperFramesIntegration().prepare(composition, base, plan, manifest, [], {"accent_color": "#fff", "background": "#000"})
    html = (composition / "index.html").read_text(encoding="utf-8")
    assert 'data-media-start="12.000000"' in html and 'data-media-end="13.000000"' in html


def test_asset_import_has_stable_id_and_catalog_metadata(tmp_path: Path, runtime_config) -> None:
    source = tmp_path / "clip.mp4"
    _make_mp4(source)
    project = tmp_path / "project"
    asset = AssetCatalog(runtime_config).import_asset(project, source, "video", [])
    second = AssetCatalog(runtime_config).import_asset(project, source, "video", [asset])
    assert asset.id == second.id and asset.path == second.path
    assert asset.metadata["decode_checked"] is True
    assert Path(asset.path).is_file()


def test_visual_planner_receives_catalog_and_rejects_unknown_asset(tmp_path: Path) -> None:
    from integrations.ai_client import BaseAIProvider
    class Provider(BaseAIProvider):
        name = "test"
        def generate(self, purpose, prompt, context, output_model):
            assert context["available_assets"][0]["asset_id"] == "asset_known"
            return VisualPlan(project_id="p", output_duration=2, profile="expert", items=[
                VisualItem(id="b", intent="b_roll", start=0, duration=1, asset_id="asset_unknown"),
            ])
    transcript = Transcript(project_id="p", language="ru", source_duration=2, segments=[TranscriptSegment(id="s", start=0, end=1, text="С‚РµРєСЃС‚")], first_speech=0, last_speech=1, transcript_end=1, audio_end=2, coverage_complete=True, provider="test")
    speech = SpeechAnalysis(project_id="p", content_type="x", topic="x", hook_candidates=["x"], selected_hook="x", strong_phrases=[], weak_phrases=[], fillers=[], repetitions=[], pauses=[], semantic_duplicates=[], confidence="HIGH", suggested_actions=[])
    edit = EditPlan(project_id="p", keep_ranges=[TimeRange(id="k", start=0, end=2)], estimated_duration=2)
    known = MediaAsset(id="asset_known", type="video", path=str(tmp_path / "x.mp4"), sha256="a" * 64, source="user")
    with pytest.raises(ValidationAppError, match="РѕС‚СЃСѓС‚СЃС‚РІСѓСЋС‰РёР№ asset_id"):
        VisualPlanner(Path(__file__).resolve().parents[1], Provider()).plan(transcript, speech, edit, "expert", "fast", available_assets=[known])


def _install_fake_faster_whisper(monkeypatch: pytest.MonkeyPatch, duration: float | None, segments: list[object]) -> None:
    class FakeModel:
        def __init__(self, *args, **kwargs):
            pass
        def transcribe(self, *args, **kwargs):
            return iter(segments), types.SimpleNamespace(language="ru", language_probability=0.9, duration=duration, duration_after_vad=2.0)
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel))


@pytest.mark.parametrize(("provider_duration", "expected"), [(10.0, True), (7.0, False)])
def test_faster_whisper_coverage_uses_provider_duration_not_last_speech(tmp_path: Path, runtime_config, monkeypatch: pytest.MonkeyPatch, provider_duration: float, expected: bool) -> None:
    segment = types.SimpleNamespace(start=0.0, end=2.0, text="СЂРµС‡СЊ", words=[])
    _install_fake_faster_whisper(monkeypatch, provider_duration, [segment])
    source = _video(tmp_path / "source.mp4", duration=10)
    transcript = FasterWhisperProvider(runtime_config).transcribe("p", Path(source.source_path), source)
    assert transcript.coverage_complete is expected
    assert transcript.audio_end == provider_duration


def test_faster_whisper_trailing_silence_and_empty_transcription(tmp_path: Path, runtime_config, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _video(tmp_path / "source.mp4", duration=10)
    speech = types.SimpleNamespace(start=0.0, end=2.0, text="СЂРµС‡СЊ", words=[])
    _install_fake_faster_whisper(monkeypatch, 10.0, [speech])
    assert FasterWhisperProvider(runtime_config).transcribe("p", Path(source.source_path), source).coverage_complete
    _install_fake_faster_whisper(monkeypatch, 10.0, [])
    with pytest.raises(ValidationAppError, match="РўСЂР°РЅСЃРєСЂРёРїС†РёСЏ РїСѓСЃС‚Р°"):
        FasterWhisperProvider(runtime_config).transcribe("p", Path(source.source_path), source)

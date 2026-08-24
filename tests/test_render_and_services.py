from __future__ import annotations

from pathlib import Path

import pytest

from core.exporter import Exporter
from core.media_manager import MediaManager
from core.motion_planner import MOTION_COMPONENTS, MotionPlanner
from core.render_router import ROUTES, RenderRouter
from core.subtitle_builder import SubtitleBuilder
from integrations.capcut_bridge import CapCutBridge
from integrations.hyperframes import HyperFramesIntegration
from models.artifacts import (
    EditPlan,
    MediaManifest,
    MotionPlan,
    QCReport,
    TimeRange,
    Transcript,
    TranscriptSegment,
    VideoInfo,
    VisualData,
    VisualItem,
    VisualPlan,
)
from models.enums import RendererType


def transcript() -> Transcript:
    return Transcript(
        project_id="p", language="ru", source_duration=4,
        segments=[TranscriptSegment(id="s1", start=0, end=2, text="Первая фраза"), TranscriptSegment(id="s2", start=2, end=4, text="Вторая фраза")],
        first_speech=0, last_speech=4, transcript_end=4, audio_end=4, coverage_complete=True, provider="mock",
    )


def edit() -> EditPlan:
    return EditPlan(project_id="p", keep_ranges=[TimeRange(id="k", start=0, end=4)], estimated_duration=4)


def visual() -> VisualPlan:
    return VisualPlan(
        project_id="p", output_duration=4, profile="expert",
        items=[VisualItem(id="h", intent="hook_text", start=0, duration=2, text="Hook")],
    )


@pytest.mark.parametrize("operation,expected", [(name, renderer) for name, renderer in ROUTES.items()])
def test_render_router(operation: str, expected: RendererType) -> None:
    assert RenderRouter().route(operation) == expected


def test_render_router_unknown() -> None:
    with pytest.raises(ValueError):
        RenderRouter().route("magic")


def test_subtitle_builder_and_srt(tmp_path: Path) -> None:
    cues = SubtitleBuilder().build(transcript(), edit())
    path = tmp_path / "subtitles.srt"
    SubtitleBuilder().write_srt(path, cues)
    assert "00:00:00,000 --> 00:00:02,000" in path.read_text(encoding="utf-8")


def test_motion_plan_only_when_required(tmp_path: Path) -> None:
    assert not MotionPlanner().plan(tmp_path, visual()).required
    plan = VisualPlan(
        project_id="p", output_duration=4, profile="expert",
        items=[VisualItem(id="m", intent="animated_stat", start=0, duration=3, data={"value": 42})],
    )
    result = MotionPlanner().plan(tmp_path, plan)
    assert result.required
    assert result.items[0].component == "AnimatedStat"


def test_motion_plan_converts_visual_data_to_dict(tmp_path: Path) -> None:
    plan = VisualPlan(
        project_id="p",
        output_duration=4,
        profile="expert",
        items=[
            VisualItem(
                id="m",
                intent="animated_stat",
                start=0,
                duration=3,
                data=VisualData(value=42, label="Views"),
            )
        ],
    )

    result = MotionPlanner().plan(tmp_path, plan)

    assert result.items[0].data == {"value": 42, "path": None, "label": "Views"}


def test_motion_plan_uses_empty_dict_for_missing_visual_data(tmp_path: Path) -> None:
    plan = VisualPlan(
        project_id="p",
        output_duration=4,
        profile="expert",
        items=[VisualItem(id="m", intent="animated_stat", start=0, duration=3)],
    )

    result = MotionPlanner().plan(tmp_path, plan)

    assert result.items[0].data == {}


def test_motion_component_library_complete() -> None:
    expected = {"AnimatedStat", "AnimatedCounter", "Comparison", "ProcessFlow", "Timeline", "Quote", "CodeHighlight", "FeatureList", "ProductFeature", "BeforeAfter", "Callout", "Chart", "Diagram"}
    assert set(MOTION_COMPONENTS.values()) == expected


def test_media_manifest_source(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    video = VideoInfo(
        project_id="p", source_path=str(source), source_hash=__import__("core.io_utils", fromlist=["sha256_file"]).sha256_file(source),
        duration=4, width=1080, height=1920, orientation="portrait", fps=30,
        video_codec="h264", audio_codec="aac", has_audio=True, decodable=True, file_size=5,
    )
    manifest = MediaManager().build_manifest(
        video,
        MotionPlan(project_id="p", required=False),
        visual(),
    )
    assert manifest.assets[0].source == "user"


def test_exporter_blocks_failed_qc(tmp_path: Path) -> None:
    draft, source = tmp_path / "draft.mp4", tmp_path / "source.mp4"
    draft.write_bytes(b"draft")
    source.write_bytes(b"source")
    report = QCReport(project_id="p", target_path=str(draft), passed=False, export_allowed=False)
    with pytest.raises(Exception, match="заблокирован"):
        Exporter().export("p", draft, source, tmp_path / "out", 1, report)


def test_exporter_versions_and_protects_source(tmp_path: Path) -> None:
    draft, source = tmp_path / "draft.mp4", tmp_path / "source.mp4"
    draft.write_bytes(b"draft")
    source.write_bytes(b"source")
    report = QCReport(project_id="p", target_path=str(draft), passed=True, export_allowed=True)
    output = Exporter().export("p", draft, source, tmp_path / "out", 1, report)
    assert output.name == "p_v001.mp4"
    assert source.read_bytes() == b"source"


def test_capcut_package_contains_only_remaining_tasks(tmp_path: Path) -> None:
    draft = tmp_path / "draft.mp4"
    draft.write_bytes(b"draft")
    plan = VisualPlan(
        project_id="p", output_duration=4, profile="expert",
        items=[
            VisualItem(id="done", intent="hook_text", start=0, duration=1),
            VisualItem(id="manual", intent="beauty_adjustment", start=1, duration=2),
        ],
    )
    package = CapCutBridge().package(tmp_path, draft, transcript(), edit(), plan, MediaManifest(project_id="p", assets=[]))
    remaining = __import__("json").loads((package / "remaining_tasks.json").read_text())
    assert [item["id"] for item in remaining["tasks"]] == ["manual"]
    assert (package / "subtitles.srt").is_file()


def test_hyperframes_has_no_unsafe_npx_fallback(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="Локальный HyperFrames CLI"):
        HyperFramesIntegration().command("lint", tmp_path, "--json")


def test_hyperframes_prefers_installed_cli(tmp_path: Path) -> None:
    cli = tmp_path / "hyperframes"
    cli.write_text("", encoding="utf-8")
    command = HyperFramesIntegration(local_cli=cli).command("lint", tmp_path, "--json")
    assert command[0] == str(cli)
    assert all("npx" not in part for part in command)

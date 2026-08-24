from __future__ import annotations

from pathlib import Path

import pytest

from core.edit_planner import EditPlanner
from core.exporter import Exporter
from core.io_utils import sha256_file
from core.motion_planner import MotionPlanner
from core.paths import ProjectPaths
from core.pipeline import Pipeline
from core.project_manager import ProjectManager
from core.speech_analyzer import SpeechAnalyzer
from core.transcriber import MockTranscriptionProvider
from core.visual_planner import VisualPlanner
from integrations.ai_client import MockProvider
from models.artifacts import (
    AudioAnalysis,
    MediaAsset,
    QCReport,
    Transcript,
    TranscriptSegment,
    VideoInfo,
)
from models.enums import Mode, Profile, Stage, StageStatus
from renderers.base_renderer import RenderResult


class FakeVideoAnalyzer:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, project_id, source, expected_hash):
        self.calls += 1
        return VideoInfo(
            project_id=project_id, source_path=str(source), source_hash=expected_hash, duration=4,
            width=1080, height=1920, orientation="portrait", fps=30, video_codec="h264",
            audio_codec="aac", has_audio=True, decodable=True, file_size=source.stat().st_size,
        )


class FakeAudioAnalyzer:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, project_id, source, video):
        self.calls += 1
        return AudioAnalysis(project_id=project_id, has_audio=True, channels=2, sample_rate=48000)


class FakeFFmpegRenderer:
    def render_base_edit(self, source, edit, output):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"base-edit")
        return RenderResult(True, output)


class FakeHyperFramesRenderer:
    def __init__(self) -> None:
        self.calls = 0

    def render(self, project_dir, base_edit, transcript, edit, visual, plan, manifest, profile):
        self.calls += 1
        output = Path(plan.output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"hyperframes-draft")
        return RenderResult(True, output, {"mock": True})


class FakeMotionRenderer:
    def render_plan(self, project_dir, plan):
        return RenderResult(True, None, {"outputs": []})


class FakeQC:
    def inspect(self, project_id, target, expected_duration=None):
        return QCReport(
            project_id=project_id, target_path=str(target), passed=True, export_allowed=True,
            measured={"duration": expected_duration},
        )


def make_pipeline(runtime_config, tmp_path: Path):
    root = runtime_config.root
    for relative in ("prompts", "config/presets", "config/profiles", "output/final"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    source_root = Path(__file__).resolve().parents[1]
    for name in ("speech_analysis_v1.3.md", "edit_plan_v1.3.md", "visual_plan_v1.3.md"):
        (root / "prompts" / name).write_text((source_root / "prompts" / name).read_text(encoding="utf-8"), encoding="utf-8")
    (root / "config" / "presets" / "render.json").write_text('{"width":1080,"height":1920}', encoding="utf-8")
    (root / "config" / "profiles" / "expert.json").write_text(
        (source_root / "config" / "profiles" / "expert.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    manager = ProjectManager(ProjectPaths(root))
    video = FakeVideoAnalyzer()
    audio = FakeAudioAnalyzer()
    hyperframes = FakeHyperFramesRenderer()
    provider = MockProvider()
    pipeline = Pipeline(
        runtime_config, manager, video, audio, MockTranscriptionProvider(),
        SpeechAnalyzer(root, provider), EditPlanner(root, provider), VisualPlanner(root, provider),
        MotionPlanner(), FakeFFmpegRenderer(), hyperframes, FakeMotionRenderer(), FakeQC(), Exporter(),
    )
    return pipeline, manager, video, audio, hyperframes


def test_full_mock_pipeline_and_cache(runtime_config, tmp_path: Path) -> None:
    pipeline, manager, video, audio, hyperframes = make_pipeline(runtime_config, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")
    state = manager.create(source, Mode.FAST, Profile.EXPERT)
    result = pipeline.run(state.project_id)
    assert result.status == "completed"
    assert result.stages[Stage.EXPORT.value].status == StageStatus.COMPLETED
    assert Path(result.artifacts["final.mp4"].path).is_file()
    assert video.calls == audio.calls == hyperframes.calls == 1
    second = pipeline.run(state.project_id)
    assert second.status == "completed"
    assert video.calls == audio.calls == hyperframes.calls == 1


def test_resume_from_first_unfinished(runtime_config, tmp_path: Path) -> None:
    pipeline, manager, video, audio, hyperframes = make_pipeline(runtime_config, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")
    state = manager.create(source, Mode.FAST, Profile.EXPERT)
    pipeline.run(state.project_id, stop_after=Stage.TRANSCRIPTION)
    partial = manager.load(state.project_id)
    assert partial.stages[Stage.TRANSCRIPTION.value].status == StageStatus.COMPLETED
    assert partial.stages[Stage.SPEECH_ANALYSIS.value].status == StageStatus.PENDING
    pipeline.run(state.project_id)
    assert manager.load(state.project_id).status == "completed"
    assert video.calls == 1
    assert audio.calls == 1


def test_failed_in_progress_recovers(runtime_config, tmp_path: Path) -> None:
    pipeline, manager, *_ = make_pipeline(runtime_config, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")
    state = manager.create(source, Mode.FAST, Profile.EXPERT)
    state.stages[Stage.SOURCE_ANALYSIS.value].status = StageStatus.IN_PROGRESS
    manager.save(state)
    result = pipeline.run(state.project_id, stop_after=Stage.SOURCE_ANALYSIS)
    assert result.stages[Stage.SOURCE_ANALYSIS.value].status == StageStatus.COMPLETED
    assert any("прерывания" in warning for warning in result.pending_tasks)


def test_motion_render_skipped_without_motion(runtime_config, tmp_path: Path) -> None:
    pipeline, manager, *_ = make_pipeline(runtime_config, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")
    state = manager.create(source, Mode.FAST, Profile.EXPERT)
    result = pipeline.run(state.project_id)
    assert result.stages[Stage.MOTION_RENDER.value].status == StageStatus.SKIPPED


def test_imported_asset_mutation_changes_visual_branch_input_hash(runtime_config, tmp_path: Path) -> None:
    pipeline, manager, *_ = make_pipeline(runtime_config, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")
    state = manager.create(source, Mode.FAST, Profile.EXPERT)
    asset_path = tmp_path / "asset.mp4"
    asset_path.write_bytes(b"first")
    state.user_assets.append(MediaAsset(
        id="asset_a", type="video", path=str(asset_path), sha256=sha256_file(asset_path), source="user",
    ))
    before = pipeline._stage_input_hash(state, Stage.VISUAL_PLAN)
    asset_path.write_bytes(b"changed")
    after = pipeline._stage_input_hash(state, Stage.VISUAL_PLAN)
    assert before != after


def test_changed_visual_prompt_invalidates_only_visual_and_downstream(
    runtime_config,
    tmp_path: Path,
) -> None:
    pipeline, manager, video, audio, hyperframes = make_pipeline(runtime_config, tmp_path)
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")
    state = manager.create(source, Mode.FAST, Profile.EXPERT)
    first = pipeline.run(state.project_id)
    transcript_hash = first.artifacts["transcript.json"].sha256
    prompt = runtime_config.root / "prompts" / "visual_plan_v1.3.md"
    prompt.write_text(prompt.read_text(encoding="utf-8") + "\nrevision", encoding="utf-8")

    second = pipeline.run(state.project_id)

    assert second.artifacts["transcript.json"].sha256 == transcript_hash
    assert video.calls == 1
    assert audio.calls == 1
    assert hyperframes.calls == 2
    assert any(item.startswith("cache_miss:visual_plan") for item in second.pending_tasks)


class IncompleteTranscriber:
    def transcribe(self, project_id, source, video):
        return Transcript(
            project_id=project_id,
            language="ru",
            source_duration=video.duration,
            segments=[TranscriptSegment(id="s", start=0, end=1, text="Неполная запись")],
            first_speech=0,
            last_speech=1,
            transcript_end=1,
            audio_end=video.duration,
            coverage_complete=False,
            provider="test",
        )


def test_incomplete_transcription_blocks_semantic_pipeline(runtime_config, tmp_path: Path) -> None:
    pipeline, manager, *_ = make_pipeline(runtime_config, tmp_path)
    pipeline.transcriber = IncompleteTranscriber()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")
    state = manager.create(source, Mode.FAST, Profile.EXPERT)

    with pytest.raises(Exception, match="неполная"):
        pipeline.run(state.project_id)

    failed = manager.load(state.project_id)
    assert failed.stages[Stage.SPEECH_ANALYSIS.value].status == StageStatus.FAILED

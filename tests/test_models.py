from __future__ import annotations

import pytest
from pydantic import ValidationError

from integrations.ai_client import MockProvider
from models.artifacts import (
    EditPlan,
    MotionPlan,
    QCIssue,
    QCReport,
    RenderOperation,
    RenderPlan,
    TimeRange,
    Transcript,
    TranscriptSegment,
    VideoInfo,
    VisualItem,
    VisualPlan,
)
from models.contracts import ControlRequest, ControlResponse
from models.enums import Command, Mode, Profile


def test_control_request_defaults() -> None:
    request = ControlRequest(command=Command.STATUS, project_id="reel_20260824_120000_abcdef")
    assert request.request_id
    assert request.parameters == {}


def test_control_request_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        ControlRequest(command=Command.STATUS, surprise=True)


def test_control_response_serializes() -> None:
    response = ControlResponse(request_id="1", success=True, status="ok", message="done")
    assert response.model_dump(mode="json")["success"] is True


def test_transcript_validation_valid() -> None:
    transcript = Transcript(
        project_id="p", language="ru", source_duration=4, segments=[TranscriptSegment(id="s", start=0, end=3.8, text="Тест")],
        first_speech=0, last_speech=3.8, transcript_end=3.8, audio_end=4, coverage_complete=True, provider="mock",
    )
    assert transcript.coverage_complete


def test_transcript_rejects_end_after_audio() -> None:
    with pytest.raises(ValidationError):
        Transcript(
            project_id="p", language="ru", source_duration=4, segments=[], transcript_end=5,
            audio_end=4, coverage_complete=False, provider="mock",
        )


def test_time_range_rejects_reverse() -> None:
    with pytest.raises(ValidationError):
        TimeRange(id="x", start=2, end=1)


def test_edit_plan_requires_positive_duration() -> None:
    with pytest.raises(ValidationError):
        EditPlan(project_id="p", keep_ranges=[], estimated_duration=0)


def test_visual_plan_contract() -> None:
    plan = VisualPlan(
        project_id="p", output_duration=3, profile="expert",
        items=[VisualItem(id="h", intent="hook_text", start=0, duration=2, text="Hook")],
    )
    assert plan.items[0].intent == "hook_text"


def test_motion_plan_contract_empty() -> None:
    plan = MotionPlan(project_id="p", required=False)
    assert plan.items == []


def test_render_plan_forces_hyperframes_master() -> None:
    plan = RenderPlan(
        project_id="p", fps=30, duration=3,
        operations=[RenderOperation(id="x", operation="subtitle", renderer="hyperframes", start=0, duration=3)],
        output_path="draft.mp4", cache_key="abc",
    )
    assert plan.master_renderer == "hyperframes"


def test_qc_report_blocks_critical() -> None:
    report = QCReport(
        project_id="p", target_path="x.mp4", passed=False, export_allowed=False,
        issues=[QCIssue(code="BAD", severity="critical", message="bad")],
    )
    assert not report.export_allowed


@pytest.mark.parametrize("mode", [Mode.FAST, Mode.DETAIL])
@pytest.mark.parametrize("profile", [Profile.EXPERT, Profile.SELLING, Profile.LIFESTYLE])
def test_modes_and_profiles(mode: Mode, profile: Profile) -> None:
    request = ControlRequest(command=Command.CREATE_REEL, source="video.mp4", mode=mode, profile=profile)
    assert request.mode == mode.value
    assert request.profile == profile.value


def test_mock_provider_structured_speech() -> None:
    result = MockProvider().generate(
        "speech_analysis", "prompt",
        {"project_id": "p", "duration": 3, "profile": "expert", "segments": [{"text": "Полезная мысль"}]},
        __import__("models.artifacts", fromlist=["SpeechAnalysis"]).SpeechAnalysis,
    )
    assert result.confidence == "MEDIUM"


def test_video_info_rejects_invalid_fps() -> None:
    with pytest.raises(ValidationError):
        VideoInfo(
            project_id="p", source_path="x", source_hash="h", duration=1, width=1, height=2,
            orientation="portrait", fps=0, video_codec="h264", has_audio=True, decodable=True, file_size=1,
        )

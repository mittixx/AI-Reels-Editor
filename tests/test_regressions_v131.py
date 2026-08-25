from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from core import cli
from core.errors import RenderError, ValidationAppError
from core.io_utils import sha256_file
from core.media_manager import MediaManager
from core.motion_planner import MotionPlanner
from core.quality_control import QualityControl
from core.render_planner import RenderPlanner
from core.render_router import RenderRouter
from core.subtitle_builder import SubtitleBuilder, SubtitleCue
from integrations.hyperframes import HyperFramesIntegration
from integrations.motion_canvas import MotionCanvasIntegration, MotionRenderJob
from integrations.process import ProcessResult
from models.artifacts import (
    EditPlan,
    MediaAsset,
    MediaManifest,
    MotionItem,
    MotionPlan,
    RenderOperation,
    RenderPlan,
    TimeRange,
    Transcript,
    TranscriptSegment,
    TranscriptWord,
    VideoInfo,
    VisualItem,
    VisualPlan,
)
from models.contracts import ControlResponse
from models.enums import ExitCode, Stage


def _video(tmp_path: Path) -> VideoInfo:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    return VideoInfo(
        project_id="p",
        source_path=str(source),
        source_hash=sha256_file(source),
        duration=4,
        width=1080,
        height=1920,
        orientation="portrait",
        fps=30,
        video_codec="h264",
        audio_codec="aac",
        has_audio=True,
        decodable=True,
        file_size=source.stat().st_size,
    )


def _edit() -> EditPlan:
    return EditPlan(
        project_id="p",
        keep_ranges=[TimeRange(id="keep", start=0, end=4)],
        estimated_duration=4,
    )


def _profile() -> dict[str, str]:
    return {"accent_color": "#B8FF5A", "background": "#0B0B0D"}


def test_visual_intent_rejects_unknown_operation() -> None:
    with pytest.raises(ValidationError, match="intent"):
        VisualItem(id="x", intent="invented_ai_effect", start=0, duration=1)


def test_broll_without_asset_is_rejected_before_master_render(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="b_roll С‚СЂРµР±СѓРµС‚ asset_id"):
        VisualItem(id="missing", intent="b_roll", start=0, duration=1)

    base = tmp_path / "base.mp4"
    base.write_bytes(b"base")
    plan = RenderPlan(
        project_id="p", fps=30, duration=1,
        operations=[RenderOperation(id="broll", operation="b_roll", renderer="hyperframes", start=0, duration=1)],
        output_path=str(tmp_path / "draft.mp4"), cache_key="missing-broll",
    )
    manifest = MediaManifest(project_id="p", assets=[])
    with pytest.raises(ValidationAppError, match="С‚СЂРµР±СѓРµС‚ РѕРґРёРЅ asset_id"):
        HyperFramesIntegration().prepare(tmp_path / "composition", base, plan, manifest, [], _profile())


def test_exported_visual_schema_contains_intent_allowlist() -> None:
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "VisualPlan.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    allowed = schema["$defs"]["VisualIntent"]["enum"]
    assert "b_roll" in allowed and "animated_stat" in allowed
    assert "invented_ai_effect" not in allowed


def test_edit_plan_rejects_overlap_and_duration_mismatch() -> None:
    with pytest.raises(ValidationError, match="РїРµСЂРµРєСЂС‹РІР°СЋС‚СЃСЏ"):
        EditPlan(
            project_id="p",
            keep_ranges=[
                TimeRange(id="a", start=0, end=2),
                TimeRange(id="b", start=1.5, end=3),
            ],
            estimated_duration=3.5,
        )
    with pytest.raises(ValidationError, match="estimated_duration"):
        EditPlan(
            project_id="p",
            keep_ranges=[TimeRange(id="a", start=0, end=2)],
            estimated_duration=1,
        )


def test_edit_plan_allows_half_second_duration_rounding() -> None:
    plan = EditPlan(
        project_id="p",
        keep_ranges=[TimeRange(id="a", start=0, end=33.82)],
        estimated_duration=33.64,
    )

    assert plan.estimated_duration == 33.64


def test_edit_plan_rejects_source_boundary() -> None:
    plan = EditPlan(
        project_id="p",
        keep_ranges=[TimeRange(id="a", start=0, end=5)],
        estimated_duration=5,
    )
    with pytest.raises(ValueError, match="source"):
        plan.validate_against_source(4)


def test_transcription_rejects_empty_and_blank() -> None:
    with pytest.raises(ValidationError):
        Transcript(
            project_id="p",
            language="ru",
            source_duration=4,
            segments=[],
            transcript_end=0,
            audio_end=4,
            coverage_complete=False,
            provider="mock",
        )
    with pytest.raises(ValidationError, match="text"):
        TranscriptSegment(id="s", start=0, end=1, text="   ")


def test_trailing_silence_is_valid_complete_coverage() -> None:
    transcript = Transcript(
        project_id="p",
        language="ru",
        source_duration=10,
        segments=[TranscriptSegment(id="s", start=0, end=2, text="Р РµС‡СЊ Р·Р°РєРѕРЅС‡РёР»Р°СЃСЊ")],
        first_speech=0,
        last_speech=2,
        transcript_end=2,
        audio_end=10,
        coverage_complete=True,
        provider="faster_whisper",
        provider_metadata={"trailing_silence_seconds": 8},
    )
    assert transcript.coverage_complete


def test_subtitles_partial_cut_use_only_overlapping_words_without_duplicates() -> None:
    transcript = Transcript(
        project_id="p",
        language="ru",
        source_duration=4,
        segments=[TranscriptSegment(
            id="s",
            start=0,
            end=4,
            text="РѕРґРёРЅ РґРІР° С‚СЂРё С‡РµС‚С‹СЂРµ",
            words=[
                TranscriptWord(text="РѕРґРёРЅ", start=0, end=1),
                TranscriptWord(text="РґРІР°", start=1, end=2),
                TranscriptWord(text="С‚СЂРё", start=2, end=3),
                TranscriptWord(text="С‡РµС‚С‹СЂРµ", start=3, end=4),
            ],
        )],
        first_speech=0,
        last_speech=4,
        transcript_end=4,
        audio_end=4,
        coverage_complete=True,
        provider="mock",
    )
    edit = EditPlan(
        project_id="p",
        keep_ranges=[
            TimeRange(id="a", start=0.5, end=1.5),
            TimeRange(id="b", start=2.5, end=3.5),
        ],
        estimated_duration=2,
    )
    cues = SubtitleBuilder().build(transcript, edit)
    assert [cue.text for cue in cues] == ["РѕРґРёРЅ РґРІР°", "С‚СЂРё С‡РµС‚С‹СЂРµ"]
    assert "РѕРґРёРЅ РґРІР° С‚СЂРё С‡РµС‚С‹СЂРµ" not in [cue.text for cue in cues]


class _QCAdapter:
    def __init__(self, *, decode: bool = True, black_error: bool = False) -> None:
        self.decode = decode
        self.black_error = black_error

    def probe(self, target: Path) -> dict:
        return {
            "streams": [
                {"codec_type": "video", "width": 1080, "height": 1920, "avg_frame_rate": "30/1", "codec_name": "h264"},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
            "format": {"duration": "4"},
        }

    def decode_check(self, target: Path) -> bool:
        return self.decode

    def black_frames(self, target: Path) -> list[dict[str, float]]:
        if self.black_error:
            raise RuntimeError("blackdetect failed")
        return []


def test_qc_decode_failure_is_critical_and_blocks_export(tmp_path: Path) -> None:
    target = tmp_path / "corrupt.mp4"
    target.write_bytes(b"not-empty")
    report = QualityControl(_QCAdapter(decode=False)).inspect("p", target, 4)  # type: ignore[arg-type]
    assert not report.export_allowed
    assert any(issue.code == "DECODE_FAILED" and issue.severity == "critical" for issue in report.issues)


def test_qc_blackdetect_failure_is_not_ignored(tmp_path: Path) -> None:
    target = tmp_path / "video.mp4"
    target.write_bytes(b"not-empty")
    report = QualityControl(_QCAdapter(black_error=True)).inspect("p", target, 4)  # type: ignore[arg-type]
    assert not report.export_allowed
    assert any(issue.code == "BLACKDETECT_FAILED" for issue in report.issues)


def test_cancelled_and_qc_failed_exit_codes() -> None:
    cancelled = ControlResponse(
        request_id="x", success=False, status="cancelled", message="cancelled"
    )
    failed_qc = ControlResponse(
        request_id="x", success=False, status="qc_failed", message="failed"
    )
    assert cli._exit_code(cancelled) == ExitCode.CANCELLED
    assert cli._exit_code(failed_qc) == ExitCode.QC_FAILED


def test_invalid_argparse_json_is_structured(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["control", "create", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == ExitCode.INVALID_REQUEST
    assert payload["errors"][0]["code"] == "INVALID_REQUEST"
    assert captured.err == ""


def test_broll_is_materialized_into_hyperframes_master(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    video = _video(tmp_path)
    broll = tmp_path / "broll.mp4"
    broll.write_bytes(b"b-roll")
    visual = VisualPlan(
        project_id="p",
        output_duration=4,
        profile="expert",
        items=[VisualItem(
            id="b1",
            intent="b_roll",
            start=1,
            duration=2,
            asset_id="broll_1",
            data={"path": str(broll)},
        )],
    )
    motion = MotionPlan(project_id="p", required=False)
    manifest = MediaManager().build_manifest(video, motion, visual, [MediaAsset(
        id="broll_1", type="video", path=str(broll), sha256=sha256_file(broll), source="user",
    )])
    monkeypatch.setattr("core.render_validation._validate_video_decodable", lambda *args: None)
    plan = RenderPlanner(RenderRouter()).plan(
        tmp_path,
        video,
        _edit(),
        visual,
        motion,
        manifest,
        {"width": 1080, "height": 1920},
    )
    base = tmp_path / "base.mp4"
    base.write_bytes(b"base")
    composition = tmp_path / "composition"
    HyperFramesIntegration().prepare(
        composition, base, plan, manifest, [], _profile()
    )
    html_text = (composition / "index.html").read_text(encoding="utf-8")
    assert 'data-operation="b_roll"' in html_text
    assert 'src="assets/broll_1-' in html_text
    metadata = json.loads((composition / "composition.json").read_text(encoding="utf-8"))
    assert "b1" in metadata["executed_operations"]


def test_motion_asset_flows_manifest_to_hyperframes_master(tmp_path: Path) -> None:
    video = _video(tmp_path)
    visual = VisualPlan(
        project_id="p",
        output_duration=4,
        profile="expert",
        items=[VisualItem(id="stat", intent="animated_stat", start=0, duration=2, data={"value": 42})],
    )
    motion = MotionPlanner().plan(tmp_path, visual)
    motion_path = Path(motion.items[0].output_path)
    motion_path.parent.mkdir(parents=True, exist_ok=True)
    motion_path.write_bytes(b"motion")
    manifest = MediaManager().build_manifest(video, motion, visual)
    motion_asset = next(asset for asset in manifest.assets if asset.type == "motion")
    assert motion_asset.metadata["pending"] is False
    plan = RenderPlanner(RenderRouter()).plan(
        tmp_path,
        video,
        _edit(),
        visual,
        motion,
        manifest,
        {"width": 1080, "height": 1920},
    )
    operation = next(item for item in plan.operations if item.id == "stat")
    assert operation.inputs == [motion.items[0].id]
    base = tmp_path / "base.mp4"
    base.write_bytes(b"base")
    composition = tmp_path / "composition"
    HyperFramesIntegration().prepare(
        composition, base, plan, manifest, [], _profile()
    )
    html_text = (composition / "index.html").read_text(encoding="utf-8")
    assert 'data-operation="animated_stat"' in html_text
    assert f'assets/{motion.items[0].id}-' in html_text


def test_hyperframes_executes_every_automatic_visual_operation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "base.mp4"
    video_asset = tmp_path / "overlay.mp4"
    image_asset = tmp_path / "image.png"
    motion_asset = tmp_path / "motion.mp4"
    for path, content in (
        (base, b"base"),
        (video_asset, b"video"),
        (image_asset, b"image"),
        (motion_asset, b"motion"),
    ):
        path.write_bytes(content)
    manifest = MediaManifest(project_id="p", assets=[
        MediaAsset(id="source", type="video", path=str(base), sha256=sha256_file(base), source="user"),
        MediaAsset(id="video", type="video", path=str(video_asset), sha256=sha256_file(video_asset), source="user"),
        MediaAsset(id="image", type="image", path=str(image_asset), sha256=sha256_file(image_asset), source="user"),
        MediaAsset(id="motion", type="motion", path=str(motion_asset), sha256=sha256_file(motion_asset), source="generated"),
    ])
    operations = [
        RenderOperation(id="base", operation="technical_cut", renderer="ffmpeg", start=0, duration=4),
        RenderOperation(id="hook", operation="hook_text", renderer="hyperframes", start=0, duration=1, parameters={"text": "Hook"}),
        RenderOperation(id="subs", operation="subtitle", renderer="hyperframes", start=0, duration=4),
        RenderOperation(id="broll", operation="b_roll", renderer="hyperframes", start=0, duration=1, inputs=["video"]),
        RenderOperation(id="screen", operation="screen_recording", renderer="hyperframes", start=1, duration=1, inputs=["video"]),
        RenderOperation(id="shot", operation="screenshot", renderer="hyperframes", start=1, duration=1, inputs=["image"]),
        RenderOperation(id="logo", operation="logo", renderer="hyperframes", start=0, duration=4, inputs=["image"]),
        RenderOperation(id="accent", operation="text_accent", renderer="hyperframes", start=1, duration=1, parameters={"text": "Fact"}),
        RenderOperation(id="zoom", operation="simple_zoom", renderer="hyperframes", start=2, duration=1, parameters={"source_media_start": 2, "source_media_end": 3}),
        RenderOperation(id="transition", operation="transition", renderer="hyperframes", start=1, duration=0.5),
        RenderOperation(id="simple-transition", operation="simple_transition", renderer="hyperframes", start=2, duration=0.5),
        RenderOperation(id="cta", operation="cta", renderer="hyperframes", start=3, duration=1, parameters={"text": "CTA"}),
        RenderOperation(id="motion-op", operation="animated_stat", renderer="motion_canvas", start=2, duration=1, inputs=["motion"]),
    ]
    plan = RenderPlan(
        project_id="p",
        fps=30,
        duration=4,
        operations=operations,
        output_path=str(tmp_path / "draft.mp4"),
        cache_key="all-operations",
    )
    composition = tmp_path / "all-operations"
    monkeypatch.setattr("core.render_validation._validate_video_decodable", lambda *args: None)
    monkeypatch.setattr("core.render_validation._validate_image", lambda *args: None)
    HyperFramesIntegration().prepare(
        composition,
        base,
        plan,
        manifest,
        [SubtitleCue(1, 0, 1, "Subtitle")],
        _profile(),
    )
    html_text = (composition / "index.html").read_text(encoding="utf-8")
    for operation in operations[1:]:
        if operation.operation == "subtitle":
            assert 'id="subtitle-1"' in html_text
        else:
            assert f'data-operation="{operation.operation}"' in html_text


def test_zoom_timing_contract_is_generated(tmp_path: Path) -> None:
    base = tmp_path / "base.mp4"
    base.write_bytes(b"base")
    plan = RenderPlan(
        project_id="p", fps=30, duration=4,
        operations=[RenderOperation(
            id="zoom", operation="simple_zoom", renderer="hyperframes", start=1.25, duration=0.75,
            parameters={"zoom_from": 1.0, "zoom_to": 1.16, "source_media_start": 1.25, "source_media_end": 2.0},
        )], output_path=str(tmp_path / "draft.mp4"), cache_key="zoom-timing",
    )
    composition = tmp_path / "zoom"
    manifest = MediaManifest(project_id="p", assets=[MediaAsset(id="source", type="video", path=str(base), sha256=sha256_file(base), source="user")])
    HyperFramesIntegration().prepare(composition, base, plan, manifest, [], _profile())
    contract = json.loads((composition / "composition.json").read_text(encoding="utf-8"))["animation_contract"]
    assert contract == [{
        "id": "zoom", "name": "zoom_zoom", "kind": "zoom", "start": 1.25, "end": 2.0,
        "duration": 0.75, "easing": "cubic-bezier(0.22, 1, 0.36, 1)",
        "from": {"scale": 1.0}, "to": {"scale": 1.16}, "source_media_start": 1.25, "source_media_end": 2.0,
    }]
    html_text = (composition / "index.html").read_text(encoding="utf-8")
    assert "@keyframes zoom_zoom" in html_text and 'animation:zoom_zoom 0.750000s' in html_text


def test_transition_timing_contract_is_generated(tmp_path: Path) -> None:
    base = tmp_path / "base.mp4"
    base.write_bytes(b"base")
    plan = RenderPlan(
        project_id="p", fps=30, duration=4,
        operations=[RenderOperation(
            id="wipe", operation="transition", renderer="hyperframes", start=2, duration=0.5,
        )], output_path=str(tmp_path / "draft.mp4"), cache_key="transition-timing",
    )
    composition = tmp_path / "transition"
    HyperFramesIntegration().prepare(composition, base, plan, MediaManifest(project_id="p", assets=[]), [], _profile())
    contract = json.loads((composition / "composition.json").read_text(encoding="utf-8"))["animation_contract"][0]
    assert contract["kind"] == "transition"
    assert (contract["start"], contract["end"], contract["duration"]) == (2, 2.5, 0.5)
    assert contract["from_layer"] == "a-roll" and contract["to_layer"] == "overlay"
    assert len(contract["keyframes"]) == 3
    html_text = (composition / "index.html").read_text(encoding="utf-8")
    assert "@keyframes transition_wipe" in html_text and 'data-animation="transition"' in html_text


def test_sequential_motion_jobs_never_reuse_stale_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    node_project = tmp_path / "node"
    node_project.mkdir()
    (node_project / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("integrations.motion_canvas.shutil.which", lambda _: "/bin/npm")
    seen_job_ids: list[str] = []
    seen_outputs: list[str] = []

    def fake_run(args, **kwargs):
        parts = [str(item) for item in args]
        if parts[0] == "ffprobe":
            return ProcessResult(tuple(parts), 0, '{"streams":[{"codec_name":"h264"}]}', "")
        if parts[0] == "ffmpeg":
            return ProcessResult(tuple(parts), 0, "", "")
        output = Path(parts[parts.index("--output") + 1])
        job_id = parts[parts.index("--job-id") + 1]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(f"fresh-{job_id}".encode())
        seen_job_ids.append(job_id)
        seen_outputs.append(str(output))
        payload = json.dumps({"success": True, "job_id": job_id, "output": str(output.resolve())})
        return ProcessResult(tuple(parts), 0, f"npm output\n{payload}\n", "")

    monkeypatch.setattr("integrations.motion_canvas.run_process", fake_run)
    integration = MotionCanvasIntegration()
    final_outputs = []
    for index in range(2):
        final = tmp_path / "final" / f"asset-{index}.mp4"
        final.parent.mkdir(parents=True, exist_ok=True)
        final.write_bytes(b"stale")
        item = MotionItem(
            id=f"motion-{index}",
            visual_id=f"visual-{index}",
            component="Callout",
            start=0,
            duration=1,
            data={"index": index},
            preset="default",
            output_path=str(final),
            cache_key=f"cache-{index}",
        )
        job = integration.render(node_project, item, tmp_path / "jobs")
        integration.validate_result(job, final)
        final_outputs.append(final.read_bytes())
    assert len(set(seen_job_ids)) == 2
    assert len(set(seen_outputs)) == 2
    assert final_outputs[0] != final_outputs[1]
    assert all(content != b"stale" for content in final_outputs)


def test_motion_partial_output_is_not_promoted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    expected = tmp_path / "jobs" / "partial.mp4"
    expected.parent.mkdir(parents=True)
    expected.write_bytes(b"partial-mp4")
    final = tmp_path / "final.mp4"
    process = ProcessResult(("npm.cmd",), 0, json.dumps({
        "success": True, "job_id": "partial", "output": str(expected.resolve()),
    }), "")
    job = MotionRenderJob(process, "partial", expected, expected.stat().st_mtime_ns)

    def fake_run(args, **kwargs):
        if args[0] == "ffprobe":
            return ProcessResult(tuple(args), 0, '{"streams":[{"codec_name":"h264"}]}', "")
        return ProcessResult(tuple(args), 1, "", "decode failed")

    monkeypatch.setattr("integrations.motion_canvas.run_process", fake_run)
    with pytest.raises(RenderError, match="decode-check"):
        MotionCanvasIntegration(stability_samples=1).validate_result(job, final)
    assert not final.exists()
    assert expected.exists()


def test_motion_wrong_output_path_is_rejected(tmp_path: Path) -> None:
    expected = tmp_path / "jobs" / "expected.mp4"
    expected.parent.mkdir(parents=True)
    expected.write_bytes(b"fresh")
    process = ProcessResult(("npm.cmd",), 0, json.dumps({
        "success": True, "job_id": "job", "output": str((tmp_path / "wrong.mp4").resolve()),
    }), "")
    job = MotionRenderJob(process, "job", expected, expected.stat().st_mtime_ns)
    with pytest.raises(RenderError, match="РЅРµРѕР¶РёРґР°РЅРЅС‹Р№ output path"):
        MotionCanvasIntegration(stability_samples=1).validate_result(job, tmp_path / "final.mp4")


def test_hyperframes_false_success_cannot_accept_old_draft(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = tmp_path / "hyperframes"
    cli.write_text("", encoding="utf-8")
    composition = tmp_path / "composition"
    composition.mkdir()
    old_draft = tmp_path / "renders" / "draft.mp4"
    old_draft.parent.mkdir()
    old_draft.write_bytes(b"old-draft")
    monkeypatch.setattr(
        "integrations.hyperframes.run_process",
        lambda args, **kwargs: ProcessResult(tuple(args), 0, "{}", ""),
    )
    integration = HyperFramesIntegration(local_cli=cli)
    job = integration.render(composition, old_draft, 30)
    with pytest.raises(RenderError, match="РЅРµ СЃРѕР·РґР°Р» РѕР¶РёРґР°РµРјС‹Р№ output"):
        integration.validate_render_job(job, old_draft)
    assert old_draft.read_bytes() == b"old-draft"


def test_motion_render_precedes_manifest_and_render_plan() -> None:
    from core.dependency_graph import STAGE_ORDER

    assert STAGE_ORDER.index(Stage.MOTION_RENDER) < STAGE_ORDER.index(Stage.MEDIA_MANIFEST)
    assert STAGE_ORDER.index(Stage.MEDIA_MANIFEST) < STAGE_ORDER.index(Stage.RENDER_PLAN)


def test_setup_windows_is_fail_fast() -> None:
    script = (Path(__file__).resolve().parents[1] / "setup_windows.ps1").read_text(encoding="utf-8")
    assert "npm ci" in script
    assert "npm install" not in script
    assert "Assert-ExitCode \"npm ci HyperFrames\"" in script
    assert "Assert-ExitCode \"РЈСЃС‚Р°РЅРѕРІРєР° HyperFrames browser\"" in script
    assert "Assert-ExitCode \"РЈСЃС‚Р°РЅРѕРІРєР° Playwright Chromium\"" in script
    assert "Assert-ExitCode \"Doctor\"" in script
    assert script.index("Assert-ExitCode \"Doctor\"") < script.index("РќР°СЃС‚СЂРѕР№РєР° Р·Р°РІРµСЂС€РµРЅР°")
    assert "catch {" in script and "exit 1" in script


def test_hyperframes_environment_disables_update_check() -> None:
    environment = HyperFramesIntegration._environment()
    assert environment["HYPERFRAMES_NO_UPDATE_CHECK"] == "1"


def test_whisper_doctor_distinguishes_package_and_model_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.doctor import Doctor

    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))
    ready, detail = Doctor._whisper_model_ready("small")
    assert not ready
    assert "РїРµСЂРІС‹Р№ Reel СЃРєР°С‡Р°РµС‚" in detail
    snapshot = tmp_path / "hf" / "hub" / "models--Systran--faster-whisper-small" / "snapshots" / "revision"
    snapshot.mkdir(parents=True)
    ready, _ = Doctor._whisper_model_ready("small")
    assert ready


def test_manifest_rejects_duplicate_asset_ids() -> None:
    asset = MediaAsset(id="same", type="video", path="a.mp4", sha256="x", source="user")
    with pytest.raises(ValidationError, match="unique|СѓРЅРёРєР°Р»СЊРЅС‹РјРё"):
        MediaManifest(project_id="p", assets=[asset, asset.model_copy()])


def test_render_plan_rejects_operation_outside_timeline() -> None:
    with pytest.raises(ValidationError, match="timeline"):
        RenderPlan(
            project_id="p",
            fps=30,
            duration=2,
            operations=[RenderOperation(
                id="late",
                operation="subtitle",
                renderer="hyperframes",
                start=1.5,
                duration=1,
            )],
            output_path="draft.mp4",
            cache_key="x",
        )

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from core.io_utils import sha256_file
from core.media_manager import MediaManager
from core.quality_control import QualityControl
from core.render_planner import RenderPlanner
from core.render_router import RenderRouter
from integrations.ffmpeg import FFmpegAdapter
from integrations.hyperframes import HyperFramesIntegration
from integrations.process import run_process
from models.artifacts import (
    EditPlan,
    MediaAsset,
    MotionPlan,
    TimeRange,
    VideoInfo,
    VisualItem,
    VisualPlan,
)


@pytest.mark.external
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg unavailable")
def test_real_ffmpeg_probe_and_decode(tmp_path: Path) -> None:
    output = tmp_path / "sample.mp4"
    run_process([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=1080x1920:d=1:r=25",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(output),
    ], timeout=120)
    adapter = FFmpegAdapter(timeout=120)
    probe = adapter.probe(output)
    assert any(stream.get("codec_type") == "video" for stream in probe["streams"])
    assert adapter.decode_check(output)


@pytest.mark.external
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg unavailable")
def test_real_corrupted_video_qc_blocks_export(tmp_path: Path) -> None:
    valid = tmp_path / "valid.mp4"
    corrupt = tmp_path / "corrupt.mp4"
    result = run_process([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:d=2:r=25",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "-c:a", "aac", str(valid),
    ], timeout=120, check=False)
    assert result.returncode == 0, result.stderr
    payload = valid.read_bytes()
    corrupt.write_bytes(payload[: max(1, len(payload) * 2 // 3)])
    report = QualityControl(FFmpegAdapter(timeout=120)).inspect("corrupt-real", corrupt)
    assert not report.passed
    assert not report.export_allowed
    assert any(issue.code in {"NOT_DECODABLE", "DECODE_FAILED"} for issue in report.issues)


@pytest.mark.external
@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg unavailable")
def test_real_full_black_video_is_critical(tmp_path: Path) -> None:
    target = tmp_path / "black.mp4"
    result = run_process([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=1:r=25",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest", "-t", "1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(target),
    ], timeout=120, check=False)
    assert result.returncode == 0, result.stderr
    report = QualityControl(FFmpegAdapter(timeout=120)).inspect("black-real", target, expected_duration=1)
    assert not report.export_allowed
    assert any(issue.code == "BLACK_OUTPUT" and issue.severity == "critical" for issue in report.issues)


@pytest.mark.external
def test_hyperframes_external_install_or_skip() -> None:
    root = Path(__file__).resolve().parents[1] / "node_tools" / "hyperframes"
    cli = root / "node_modules" / ".bin" / "hyperframes"
    if not cli.is_file():
        pytest.skip("HyperFrames node_modules unavailable")
    result = run_process([str(cli), "lint", "templates/base", "--json"], cwd=root, timeout=180, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.external
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg unavailable")
def test_real_broll_asset_validation_to_hyperframes_lint(tmp_path: Path) -> None:
    node_root = Path(__file__).resolve().parents[1] / "node_tools" / "hyperframes"
    cli = node_root / "node_modules" / ".bin" / "hyperframes"
    if not cli.is_file():
        pytest.skip("HyperFrames node dependencies unavailable")
    source, broll = tmp_path / "source.mp4", tmp_path / "broll.mp4"
    for target, color in ((source, "blue"), (broll, "red")):
        result = run_process([
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=1080x1920:d=1:r=25",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(target),
        ], timeout=120, check=False)
        assert result.returncode == 0, result.stderr
    video = VideoInfo(
        project_id="broll-real", source_path=str(source), source_hash=sha256_file(source), duration=1,
        width=1080, height=1920, orientation="portrait", fps=25, video_codec="h264",
        audio_codec="aac", has_audio=True, decodable=True, file_size=source.stat().st_size,
    )
    visual = VisualPlan(
        project_id="broll-real", output_duration=1, profile="expert",
        items=[VisualItem(id="broll", intent="b_roll", start=0, duration=1, asset_id="broll", data={"path": str(broll)})],
    )
    manifest = MediaManager().build_manifest(video, MotionPlan(project_id="broll-real", required=False), visual, [MediaAsset(
        id="broll", type="video", path=str(broll), sha256=sha256_file(broll), source="user", duration=1,
    )])
    plan = RenderPlanner(RenderRouter()).plan(
        tmp_path, video,
        EditPlan(project_id="broll-real", keep_ranges=[TimeRange(id="keep", start=0, end=1)], estimated_duration=1),
        visual, MotionPlan(project_id="broll-real", required=False), manifest, {"width": 1080, "height": 1920},
    )
    composition = tmp_path / "composition"
    integration = HyperFramesIntegration(local_cli=cli)
    integration.prepare(composition, source, plan, manifest, [], {"accent_color": "#B8FF5A", "background": "#0B0B0D"})
    lint = integration.lint(composition)
    assert lint.returncode == 0, lint.stderr


@pytest.mark.external
def test_motion_canvas_typecheck_or_skip() -> None:
    root = Path(__file__).resolve().parents[1] / "node_tools" / "motion_canvas"
    cli = root / "node_modules" / ".bin" / "tsc"
    if not cli.is_file():
        pytest.skip("Motion Canvas node_modules unavailable")
    result = run_process([str(cli), "--noEmit"], cwd=root, timeout=180, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.external
def test_motion_canvas_invalid_input_fails_before_browser(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "node_tools" / "motion_canvas"
    node = shutil.which("node")
    if node is None or not (root / "node_modules" / "playwright").is_dir():
        pytest.skip("Motion Canvas node dependencies unavailable")
    invalid = tmp_path / "invalid-motion.json"
    invalid.write_text(
        '{"schema_version":"1.3","job_id":"job","duration":1,"preset":"default","data":{}}',
        encoding="utf-8",
    )
    result = run_process([
        node, "scripts/render.mjs", "--input", str(invalid),
        "--output", str(tmp_path / "out.mp4"), "--job-id", "job",
    ], cwd=root, timeout=30, check=False)
    assert result.returncode != 0
    assert "unsupported component" in (result.stderr or result.stdout)


@pytest.mark.external
def test_motion_canvas_missing_input_fails_before_browser(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1] / "node_tools" / "motion_canvas"
    node = shutil.which("node")
    if node is None or not (root / "node_modules" / "playwright").is_dir():
        pytest.skip("Motion Canvas node dependencies unavailable")
    result = run_process([
        node, "scripts/render.mjs", "--input", str(tmp_path / "missing.json"),
        "--output", str(tmp_path / "out.mp4"), "--job-id", "job",
    ], cwd=root, timeout=30, check=False)
    assert result.returncode != 0
    assert "ENOENT" in (result.stderr or result.stdout)

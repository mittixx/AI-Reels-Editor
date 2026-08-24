from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.video_analyzer import VideoAnalyzer
from integrations.hyperframes import HyperFramesIntegration
from integrations.process import ProcessResult
from models.artifacts import RenderPlan, canonical_fps


@pytest.mark.parametrize(("input_fps", "expected"), [
    (30, "30/1"), (25, "25/1"), (29.97, "30000/1001"), (59.94, "60000/1001"),
])
def test_canonical_fps_preserves_exact_hyperframes_rates(input_fps: float, expected: str) -> None:
    assert canonical_fps(input_fps) == expected
    plan = RenderPlan(project_id="p", fps=input_fps, duration=1, operations=[], output_path="draft.mp4", cache_key="x")
    assert plan.fps_rational == expected


def test_video_analyzer_uses_ffprobe_rational_without_float_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"x")
    class Adapter:
        def probe(self, path: Path):
            return {"format": {"duration": "1"}, "streams": [{"codec_type": "video", "width": 10, "height": 10, "avg_frame_rate": "30000/1001", "r_frame_rate": "30/1", "codec_name": "h264"}]}
        def decode_check(self, path: Path): return True
    video = VideoAnalyzer(Adapter()).analyze("p", source, __import__("core.io_utils", fromlist=["sha256_file"]).sha256_file(source))
    assert video.fps_rational == "30000/1001"


def test_hyperframes_receives_rational_fps_not_decimal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cli = tmp_path / "hyperframes"
    cli.write_text("", encoding="utf-8")
    seen: list[list[str]] = []
    def fake_run(args, **kwargs):
        seen.append(list(args))
        return ProcessResult(tuple(args), 0, "{}", "")
    monkeypatch.setattr("integrations.hyperframes.run_process", fake_run)
    job = HyperFramesIntegration(local_cli=cli).render(tmp_path, tmp_path / "draft.mp4", "30/1")
    assert job.process.returncode == 0
    assert seen[0][seen[0].index("--fps") + 1] == "30/1"
    assert "30.000000" not in json.dumps(seen[0])

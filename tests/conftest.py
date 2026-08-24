from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.config import RuntimeConfig


@pytest.fixture
def runtime_config(tmp_path: Path) -> RuntimeConfig:
    raw: dict[str, Any] = {
        "schema_version": "1.3",
        "default_mode": "fast",
        "default_profile": "expert",
        "target": {"width": 1080, "height": 1920},
        "limits": {"external_timeout_seconds": 60, "max_render_attempts": 2},
        "versions": {"pipeline": "1.3.2", "prompt": "1.3.2", "hyperframes_template": "1.3.2", "motion_components": "1.3.2"},
    }
    return RuntimeConfig(
        root=tmp_path, raw=raw, ai_provider="mock", openai_api_key=None,
        openai_model="gpt-5.6-luna", transcription_provider="mock", whisper_model="small",
        whisper_device="cpu", whisper_compute_type="int8", ffmpeg_bin="ffmpeg",
        ffprobe_bin="ffprobe", hyperframes_bin="hyperframes", motion_canvas_bin="npm.cmd", log_level="INFO",
    )

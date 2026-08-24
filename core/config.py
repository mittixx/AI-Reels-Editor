from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from core.errors import ValidationAppError
from core.paths import ProjectPaths


@dataclass(frozen=True)
class RuntimeConfig:
    root: Path
    raw: dict[str, Any]
    ai_provider: str
    openai_api_key: str | None
    openai_model: str
    transcription_provider: str
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    ffmpeg_bin: str
    ffprobe_bin: str
    hyperframes_bin: str
    motion_canvas_bin: str
    log_level: str

    @property
    def timeout(self) -> int:
        return int(self.raw["limits"]["external_timeout_seconds"])


def load_config(root: Path | None = None, env_file: Path | None = None) -> RuntimeConfig:
    paths = ProjectPaths(root or ProjectPaths.discover().root)
    candidate = env_file or paths.root / ".env"
    if candidate.exists():
        load_dotenv(candidate, override=False)
    app_path = paths.root / "config" / "app.json"
    try:
        raw = json.loads(app_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationAppError(f"РќРµ СѓРґР°Р»РѕСЃСЊ РїСЂРѕС‡РёС‚Р°С‚СЊ config/app.json: {exc}") from exc
    required = {"schema_version", "target", "limits", "versions"}
    missing = required.difference(raw)
    if missing:
        raise ValidationAppError(f"Р’ app.json РѕС‚СЃСѓС‚СЃС‚РІСѓСЋС‚ РїРѕР»СЏ: {sorted(missing)}")
    return RuntimeConfig(
        root=paths.root,
        raw=raw,
        ai_provider=os.getenv("AI_PROVIDER", "mock").strip().lower(),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
        transcription_provider=os.getenv("TRANSCRIPTION_PROVIDER", "faster_whisper").strip().lower(),
        whisper_model=os.getenv("WHISPER_MODEL", "small"),
        whisper_device=os.getenv("WHISPER_DEVICE", "cpu"),
        whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
        ffmpeg_bin=os.getenv("FFMPEG_BIN", "ffmpeg"),
        ffprobe_bin=os.getenv("FFPROBE_BIN", "ffprobe"),
        hyperframes_bin=os.getenv("HYPERFRAMES_BIN", "hyperframes"),
        motion_canvas_bin=os.getenv("MOTION_CANVAS_BIN", "npm.cmd"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )


def load_profile(root: Path, profile: str) -> dict[str, Any]:
    path = root / "config" / "profiles" / f"{profile}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationAppError(f"РџСЂРѕС„РёР»СЊ {profile} РЅРµРґРѕСЃС‚СѓРїРµРЅ: {exc}") from exc
    if data.get("id") != profile:
        raise ValidationAppError(f"ID РїСЂРѕС„РёР»СЏ РЅРµ СЃРѕРІРїР°РґР°РµС‚: {profile}")
    return data


def load_preset(root: Path, name: str) -> dict[str, Any]:
    path = root / "config" / "presets" / f"{name}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationAppError(f"Preset {name} РЅРµРґРѕСЃС‚СѓРїРµРЅ: {exc}") from exc

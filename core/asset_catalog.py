from __future__ import annotations

import re
import shutil
from pathlib import Path

from core.config import RuntimeConfig
from core.errors import ValidationAppError
from core.io_utils import sha256_file
from integrations.ffmpeg import FFmpegAdapter
from models.artifacts import MediaAsset


class AssetCatalog:
    """Imports verified user media into an immutable, project-local asset catalogue."""

    def __init__(self, config: RuntimeConfig) -> None:
        self.ffmpeg = FFmpegAdapter(config.ffmpeg_bin, config.ffprobe_bin, config.timeout)

    def import_asset(
        self, project_dir: Path, source: Path, kind: str, existing: list[MediaAsset]
    ) -> MediaAsset:
        source = source.expanduser().resolve()
        if not source.is_file() or source.stat().st_size <= 0:
            raise ValidationAppError(f"Asset не найден или пуст: {source}")
        suffix = source.suffix.lower()
        if kind == "video":
            if suffix not in {".mp4", ".mov", ".mkv", ".webm"}:
                raise ValidationAppError("Video asset имеет неподдерживаемый file type")
            metadata = self._video_metadata(source)
        elif kind == "image":
            if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                raise ValidationAppError("Image asset имеет неподдерживаемый file type")
            metadata = {"file_type": suffix.lstrip(".")}
        else:
            raise ValidationAppError("Asset kind должен быть video или image")
        digest = sha256_file(source)
        asset_id = f"asset_{digest[:24]}"
        collision = next((item for item in existing if item.id == asset_id), None)
        if collision and collision.sha256 != digest:
            raise ValidationAppError("Коллизия stable asset_id; импорт отклонён")
        target_dir = project_dir / "assets"
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", source.stem).strip("._") or "asset"
        # The digest prefix prevents sanitized-name collisions deterministically.
        target = target_dir / f"{asset_id}_{safe_name}{suffix}"
        if not target.exists():
            shutil.copy2(source, target)
        if sha256_file(target) != digest:
            raise ValidationAppError("Импортированный asset не прошёл SHA-256 verification")
        return MediaAsset(
            id=asset_id, type=kind, path=str(target.resolve()), sha256=digest,
            source="user", duration=metadata.get("duration"), metadata=metadata,
        )

    def _video_metadata(self, source: Path) -> dict[str, object]:
        try:
            data = self.ffmpeg.probe(source)
        except Exception as exc:
            raise ValidationAppError(f"Video asset не прошёл ffprobe: {source.name}") from exc
        stream = next((item for item in data.get("streams", []) if item.get("codec_type") == "video"), None)
        if not stream:
            raise ValidationAppError("Video asset не содержит video stream")
        try:
            duration = float(data.get("format", {}).get("duration") or stream.get("duration") or 0)
            width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
        except (TypeError, ValueError) as exc:
            raise ValidationAppError("Video asset имеет невалидные duration/dimensions") from exc
        if duration <= 0 or width <= 0 or height <= 0:
            raise ValidationAppError("Video asset требует duration > 0 и валидные dimensions")
        if not self.ffmpeg.decode_check(source):
            raise ValidationAppError("Video asset не прошёл FFmpeg decode-check")
        return {
            "file_type": source.suffix.lower().lstrip("."), "duration": duration,
            "width": width, "height": height,
            "fps": stream.get("avg_frame_rate") or stream.get("r_frame_rate"),
            "video_codec": stream.get("codec_name"), "decode_checked": True,
        }

from __future__ import annotations

from pathlib import Path

from core.errors import ValidationAppError
from core.io_utils import sha256_file
from integrations.ffmpeg import FFmpegAdapter
from models.artifacts import MediaAsset, MediaManifest, RenderOperation, RenderPlan

MEDIA_OPERATIONS = {"b_roll", "screen_recording", "screenshot", "logo"}
VIDEO_MEDIA_OPERATIONS = {"b_roll", "screen_recording"}
IMAGE_MEDIA_OPERATIONS = {"screenshot", "logo"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def validate_media_operations(render_plan: RenderPlan, manifest: MediaManifest, ffmpeg: FFmpegAdapter | None = None) -> None:
    """Reject invalid media operations before the master renderer is invoked."""
    assets = {asset.id: asset for asset in manifest.assets}
    for operation in render_plan.operations:
        if operation.operation not in MEDIA_OPERATIONS and operation.renderer != "motion_canvas":
            continue
        if len(operation.inputs) != 1 or not operation.inputs[0].strip():
            raise ValidationAppError(
                f"Render operation {operation.id}: {operation.operation} С‚СЂРµР±СѓРµС‚ РѕРґРёРЅ asset_id"
            )
        asset = assets.get(operation.inputs[0])
        if asset is None:
            raise ValidationAppError(
                f"Render operation {operation.id}: asset_id {operation.inputs[0]} РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚ РІ media_manifest"
            )
        _validate_asset(operation, asset, ffmpeg or FFmpegAdapter())


def _validate_asset(operation: RenderOperation, asset: MediaAsset, ffmpeg: FFmpegAdapter) -> None:
    path = Path(asset.path)
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValidationAppError(
            f"Render operation {operation.id}: media asset {asset.id} РѕС‚СЃСѓС‚СЃС‚РІСѓРµС‚ РёР»Рё РїСѓСЃС‚"
        )
    if sha256_file(path) != asset.sha256:
        raise ValidationAppError(
            f"Render operation {operation.id}: media asset {asset.id} РёР·РјРµРЅС‘РЅ РїРѕСЃР»Рµ manifest"
        )
    suffix = path.suffix.lower()
    if operation.operation in VIDEO_MEDIA_OPERATIONS and (
        asset.type not in {"video", "motion"} or suffix not in VIDEO_SUFFIXES
    ):
        raise ValidationAppError(
            f"Render operation {operation.id}: {operation.operation} С‚СЂРµР±СѓРµС‚ Р»РѕРєР°Р»СЊРЅС‹Р№ video asset"
        )
    if operation.operation in VIDEO_MEDIA_OPERATIONS:
        _validate_video_decodable(operation, path, ffmpeg)
    if operation.operation in IMAGE_MEDIA_OPERATIONS and (
        asset.type != "image" or suffix not in IMAGE_SUFFIXES
    ):
        raise ValidationAppError(
            f"Render operation {operation.id}: {operation.operation} С‚СЂРµР±СѓРµС‚ Р»РѕРєР°Р»СЊРЅС‹Р№ image asset"
        )
    if operation.operation in IMAGE_MEDIA_OPERATIONS:
        _validate_image(operation, path, ffmpeg)


def _validate_video_decodable(operation: RenderOperation, path: Path, ffmpeg: FFmpegAdapter) -> None:
    """Do not let a syntactically named/correctly hashed corrupt MP4 reach HyperFrames."""
    try:
        data = ffmpeg.probe(path)
    except Exception as exc:
        raise ValidationAppError(
            f"Render operation {operation.id}: video asset РЅРµ РїСЂРѕС€С‘Р» ffprobe"
        ) from exc
    stream = next((item for item in data.get("streams", []) if item.get("codec_type") == "video"), None)
    if not stream:
        raise ValidationAppError(f"Render operation {operation.id}: video asset РЅРµ СЃРѕРґРµСЂР¶РёС‚ video stream")
    try:
        duration = float(data.get("format", {}).get("duration") or stream.get("duration") or 0)
        width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
        rate = str(stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/0")
    except (TypeError, ValueError) as exc:
        raise ValidationAppError(f"Render operation {operation.id}: video asset РёРјРµРµС‚ РЅРµРІР°Р»РёРґРЅС‹Рµ metadata") from exc
    if duration <= 0 or width <= 0 or height <= 0 or rate in {"0/0", "N/A", "0"}:
        raise ValidationAppError(
            f"Render operation {operation.id}: video asset С‚СЂРµР±СѓРµС‚ duration, dimensions Рё FPS"
        )
    if not ffmpeg.decode_check(path):
        raise ValidationAppError(
            f"Render operation {operation.id}: video asset РЅРµ РїСЂРѕС€С‘Р» FFmpeg decode-check"
        )
    offset = float(operation.parameters.get("media_offset", 0.0))
    if offset < 0 or (not operation.parameters.get("loop") and offset + operation.duration > duration + 0.05):
        raise ValidationAppError(f"Render operation {operation.id}: Р·Р°РїСЂРѕС€РµРЅРЅР°СЏ media duration РїСЂРµРІС‹С€Р°РµС‚ asset duration")


def _validate_image(operation: RenderOperation, path: Path, ffmpeg: FFmpegAdapter) -> None:
    try:
        data = ffmpeg.probe(path)
    except Exception as exc:
        raise ValidationAppError(f"Render operation {operation.id}: image asset РЅРµ РїСЂРѕС€С‘Р» ffprobe") from exc
    stream = next((item for item in data.get("streams", []) if item.get("codec_type") == "video"), None)
    if not stream or int(stream.get("width") or 0) <= 0 or int(stream.get("height") or 0) <= 0:
        raise ValidationAppError(f"Render operation {operation.id}: image asset РёРјРµРµС‚ РЅРµРІР°Р»РёРґРЅС‹Рµ dimensions")
    if not ffmpeg.decode_check(path):
        raise ValidationAppError(f"Render operation {operation.id}: image asset РЅРµ РїСЂРѕС€С‘Р» decode-check")

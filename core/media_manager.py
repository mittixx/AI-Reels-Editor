from __future__ import annotations

from pathlib import Path

from core.errors import ValidationAppError
from core.io_utils import sha256_file
from models.artifacts import MediaAsset, MediaManifest, MotionPlan, VideoInfo, VisualPlan


class MediaManager:
    def build_manifest(
        self,
        video: VideoInfo,
        motion: MotionPlan,
        visual: VisualPlan,
        user_assets: list[MediaAsset] | None = None,
    ) -> MediaManifest:
        assets = [MediaAsset(
            id="source", type="video", path=video.source_path, sha256=video.source_hash,
            source="user", duration=video.duration,
        )]
        for item in motion.items:
            path = Path(item.output_path)
            if not path.is_file() or path.stat().st_size == 0:
                raise ValidationAppError(f"Motion asset не создан: {item.id}")
            assets.append(MediaAsset(
                id=item.id, type="motion", path=str(path),
                sha256=sha256_file(path),
                source="generated", duration=item.duration,
                metadata={
                    "pending": False,
                    "component": item.component,
                    "visual_id": item.visual_id,
                    "cache_key": item.cache_key,
                },
            ))
        known_ids = {asset.id for asset in assets}
        for asset in user_assets or []:
            if asset.id in known_ids:
                raise ValidationAppError(f"Повторяющийся asset_id в user asset catalog: {asset.id}")
            assets.append(asset)
            known_ids.add(asset.id)
        allowed_user_ids = {asset.id for asset in user_assets or []}
        for item in visual.items:
            if item.asset_id and item.asset_id not in known_ids:
                raise ValidationAppError(
                    f"Visual item {item.id} выбрал asset_id вне imported asset catalog: {item.asset_id}"
                )
            if item.asset_id and item.asset_id not in {"source", *allowed_user_ids} and item.asset_id not in known_ids:
                raise ValidationAppError(f"Visual item {item.id} использует неизвестный asset_id")
        return MediaManifest(project_id=video.project_id, assets=assets)

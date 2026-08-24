from __future__ import annotations

from pathlib import Path
from typing import Any

from core.io_utils import sha256_data
from core.render_router import RenderRouter
from core.render_validation import validate_media_operations
from integrations.ffmpeg import FFmpegAdapter
from models.artifacts import (
    EditPlan,
    MediaManifest,
    MotionPlan,
    RenderOperation,
    RenderPlan,
    VideoInfo,
    VisualPlan,
)


class RenderPlanner:
    def __init__(self, router: RenderRouter, ffmpeg: FFmpegAdapter | None = None) -> None:
        self.router = router
        self.ffmpeg = ffmpeg

    def plan(
        self,
        project_dir: Path,
        video: VideoInfo,
        edit: EditPlan,
        visual: VisualPlan,
        motion: MotionPlan,
        manifest: MediaManifest,
        settings: dict,
    ) -> RenderPlan:
        operations = [RenderOperation(
            id="base_edit", operation="technical_cut", renderer=self.router.route("technical_cut").value,
            start=0.0, duration=edit.estimated_duration, inputs=[video.source_path],
            parameters={"keep_ranges": [item.model_dump(mode="json") for item in edit.keep_ranges]},
        )]
        motion_by_visual = {item.visual_id: item.id for item in motion.items}
        manifest_ids = {asset.id for asset in manifest.assets}
        for item in visual.items:
            renderer = self.router.route(item.intent)
            inputs: list[str] = []
            motion_asset_id = motion_by_visual.get(item.id)
            if motion_asset_id:
                inputs = [motion_asset_id]
            elif item.asset_id:
                inputs = [item.asset_id]
            missing = [asset_id for asset_id in inputs if asset_id not in manifest_ids]
            if missing:
                raise ValueError(f"Render operation {item.id}: assets отсутствуют в manifest: {missing}")
            parameters: dict[str, Any] = {"text": item.text, "data": item.data}
            if item.intent.value == "simple_zoom":
                if not self._within_single_keep_range(edit, item.start, item.start + item.duration):
                    raise ValueError("Zoom пересекает монтажный cut и должен быть направлен в fallback")
                source_start = self._source_offset(edit, item.start)
                source_end = self._source_offset(edit, item.start + item.duration, allow_endpoint=True)
                parameters.update({
                    "source_media_start": source_start,
                    "source_media_end": source_end,
                    "media_offset_contract": "original_source",
                })
            operations.append(RenderOperation(
                id=item.id, operation=item.intent.value, renderer=renderer.value,
                start=item.start, duration=item.duration,
                inputs=inputs,
                parameters=parameters,
            ))
        payload = {
            "video_hash": video.source_hash,
            "edit": edit.model_dump(mode="json"),
            "visual": visual.model_dump(mode="json"),
            "motion": motion.model_dump(mode="json"),
            "manifest": manifest.model_dump(mode="json"),
            "settings": settings,
            "renderer": "hyperframes@0.8.12",
        }
        plan = RenderPlan(
            project_id=video.project_id,
            fps=video.fps,
            fps_rational=video.fps_rational,
            duration=edit.estimated_duration,
            operations=operations,
            output_path=str(project_dir / "renders" / "draft.mp4"),
            cache_key=sha256_data(payload),
        )
        validate_media_operations(plan, manifest, self.ffmpeg)
        return plan

    @staticmethod
    def _source_offset(edit: EditPlan, output_time: float, allow_endpoint: bool = False) -> float:
        """Map the cut output timeline back to the original source timeline."""
        cursor = 0.0
        for keep in edit.keep_ranges:
            length = keep.end - keep.start
            endpoint = allow_endpoint and abs(output_time - (cursor + length)) <= 0.001
            if cursor <= output_time < cursor + length or endpoint:
                return keep.start + max(0.0, output_time - cursor)
            cursor += length
        raise ValueError("Zoom выходит за непрерывный edit timeline или пересекает cut")

    @staticmethod
    def _within_single_keep_range(edit: EditPlan, start: float, end: float) -> bool:
        cursor = 0.0
        for keep in edit.keep_ranges:
            output_end = cursor + keep.end - keep.start
            if cursor <= start and end <= output_end + 0.001:
                return True
            cursor = output_end
        return False

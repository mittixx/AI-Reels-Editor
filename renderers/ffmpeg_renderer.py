from __future__ import annotations

from pathlib import Path

from core.errors import RenderError
from integrations.ffmpeg import FFmpegAdapter
from integrations.process import run_process
from models.artifacts import EditPlan
from renderers.base_renderer import BaseRenderer, RenderResult


class FFmpegRenderer(BaseRenderer):
    name = "ffmpeg"

    def __init__(self, adapter: FFmpegAdapter) -> None:
        self.adapter = adapter

    def available(self) -> bool:
        return self.adapter.available()

    def render_base_edit(self, source: Path, edit: EditPlan, output: Path) -> RenderResult:
        output.parent.mkdir(parents=True, exist_ok=True)
        ranges = edit.keep_ranges
        if not ranges:
            raise RenderError("Edit plan не содержит keep ranges")
        if len(ranges) == 1 and ranges[0].start <= 0.01:
            args = [
                self.adapter.ffmpeg_bin, "-y", "-i", str(source), "-t", f"{ranges[0].end:.6f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(output),
            ]
        else:
            parts: list[str] = []
            labels: list[str] = []
            for index, item in enumerate(ranges):
                parts.append(f"[0:v]trim=start={item.start}:end={item.end},setpts=PTS-STARTPTS[v{index}]")
                parts.append(f"[0:a]atrim=start={item.start}:end={item.end},asetpts=PTS-STARTPTS[a{index}]")
                labels.append(f"[v{index}][a{index}]")
            parts.append(f"{''.join(labels)}concat=n={len(ranges)}:v=1:a=1[v][a]")
            args = [
                self.adapter.ffmpeg_bin, "-y", "-i", str(source), "-filter_complex", ";".join(parts),
                "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k", str(output),
            ]
        run_process(args, timeout=self.adapter.timeout)
        if not output.is_file() or output.stat().st_size == 0:
            raise RenderError("FFmpeg не создал base edit")
        return RenderResult(True, output, {"ranges": len(ranges)})

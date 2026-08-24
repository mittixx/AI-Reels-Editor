from __future__ import annotations

from pathlib import Path

from integrations.ffmpeg import FFmpegAdapter


class AudioProcessor:
    def __init__(self, ffmpeg: FFmpegAdapter) -> None:
        self.ffmpeg = ffmpeg

    def normalize(self, source: Path, output: Path) -> Path:
        self.ffmpeg.normalize_audio(source, output)
        return output

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from core.errors import ValidationAppError
from core.io_utils import sha256_file
from integrations.ffmpeg import FFmpegAdapter
from models.artifacts import VideoInfo


class VideoAnalyzer:
    def __init__(self, ffmpeg: FFmpegAdapter) -> None:
        self.ffmpeg = ffmpeg

    def analyze(self, project_id: str, source: Path, expected_hash: str) -> VideoInfo:
        if sha256_file(source) != expected_hash:
            raise ValidationAppError("Source hash изменился до анализа")
        data = self.ffmpeg.probe(source)
        streams = data.get("streams", [])
        video = next((item for item in streams if item.get("codec_type") == "video"), None)
        audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
        if not video:
            raise ValidationAppError("В файле нет видеопотока")
        width, height = int(video.get("width", 0)), int(video.get("height", 0))
        duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
        average_rate = str(video.get("avg_frame_rate") or "0/0")
        frame_rate = str(video.get("r_frame_rate") or "0/0")
        rate = average_rate if average_rate not in {"0/0", "N/A", "0/1"} else frame_rate
        rational_fps = rate if rate not in {"0/0", "N/A"} else "0/1"
        fps = float(Fraction(rational_fps))
        orientation = "portrait" if height > width else "landscape" if width > height else "square"
        return VideoInfo(
            project_id=project_id,
            source_path=str(source),
            source_hash=expected_hash,
            duration=duration,
            width=width,
            height=height,
            orientation=orientation,
            fps=fps,
            fps_rational=rational_fps,
            video_codec=str(video.get("codec_name") or "unknown"),
            audio_codec=str(audio.get("codec_name")) if audio else None,
            has_audio=audio is not None,
            decodable=self.ffmpeg.decode_check(source),
            file_size=source.stat().st_size,
        )

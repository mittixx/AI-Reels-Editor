from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from core.errors import DependencyError, ExternalProcessError
from integrations.process import ProcessResult, run_process


class FFmpegAdapter:
    def __init__(self, ffmpeg_bin: str = "ffmpeg", ffprobe_bin: str = "ffprobe", timeout: int = 1800) -> None:
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin
        self.timeout = timeout

    def available(self) -> bool:
        return shutil.which(self.ffmpeg_bin) is not None and shutil.which(self.ffprobe_bin) is not None

    def version(self) -> dict[str, str | None]:
        ffmpeg = run_process([self.ffmpeg_bin, "-version"], timeout=15, check=False)
        ffprobe = run_process([self.ffprobe_bin, "-version"], timeout=15, check=False)
        return {
            "ffmpeg": ffmpeg.stdout.splitlines()[0] if ffmpeg.returncode == 0 and ffmpeg.stdout else None,
            "ffprobe": ffprobe.stdout.splitlines()[0] if ffprobe.returncode == 0 and ffprobe.stdout else None,
        }

    def probe(self, source: Path) -> dict[str, Any]:
        if not self.available():
            raise DependencyError("FFmpeg/ffprobe не найдены. Установите FFmpeg и добавьте bin в PATH.")
        result = run_process([
            self.ffprobe_bin,
            "-v", "error",
            "-show_streams",
            "-show_format",
            "-of", "json",
            str(source),
        ], timeout=120)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ExternalProcessError("ffprobe вернул некорректный JSON") from exc

    def decode_check(self, source: Path) -> bool:
        result = run_process([
            self.ffmpeg_bin, "-v", "error", "-xerror", "-err_detect", "explode",
            "-i", str(source), "-map", "0", "-f", "null", "-"
        ], timeout=self.timeout, check=False)
        return result.returncode == 0

    def analyze_loudness(self, source: Path) -> dict[str, float | None]:
        result = run_process([
            self.ffmpeg_bin, "-hide_banner", "-nostats", "-i", str(source),
            "-vn", "-filter_complex", "ebur128=peak=true", "-f", "null", "-"
        ], timeout=self.timeout, check=False)
        text = result.stderr
        integrated = re.findall(r"I:\s*(-?inf|-?\d+(?:\.\d+)?)\s*LUFS", text)
        peaks = re.findall(r"Peak:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dBFS", text)
        return {
            "integrated_loudness_lufs": self._number(integrated[-1]) if integrated else None,
            "true_peak_db": self._number(peaks[-1]) if peaks else None,
        }

    def detect_silence(self, source: Path, noise_db: int = -38, minimum: float = 0.45) -> list[dict[str, float]]:
        result = run_process([
            self.ffmpeg_bin, "-hide_banner", "-nostats", "-i", str(source), "-vn",
            "-af", f"silencedetect=noise={noise_db}dB:d={minimum}", "-f", "null", "-"
        ], timeout=self.timeout, check=False)
        starts = [float(x) for x in re.findall(r"silence_start:\s*([\d.]+)", result.stderr)]
        ends = [
            (float(end), float(duration))
            for end, duration in re.findall(r"silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)", result.stderr)
        ]
        return [
            {"start": start, "end": end, "duration": duration}
            for start, (end, duration) in zip(starts, ends, strict=False)
            if end > start
        ]

    def black_frames(self, source: Path, threshold: int = 98, minimum: float = 0.5) -> list[dict[str, float]]:
        result = run_process([
            self.ffmpeg_bin, "-hide_banner", "-nostats", "-i", str(source),
            "-vf", f"blackdetect=d={minimum}:pic_th={threshold / 100:.2f}", "-an", "-f", "null", "-"
        ], timeout=self.timeout, check=False)
        if result.returncode != 0:
            tail = (result.stderr or result.stdout)[-800:].strip()
            raise ExternalProcessError(f"blackdetect завершился с ошибкой: {tail}")
        matches = re.findall(r"black_start:([\d.]+) black_end:([\d.]+) black_duration:([\d.]+)", result.stderr)
        return [{"start": float(a), "end": float(b), "duration": float(c)} for a, b, c in matches]

    def normalize_audio(self, source: Path, output: Path) -> ProcessResult:
        output.parent.mkdir(parents=True, exist_ok=True)
        return run_process([
            self.ffmpeg_bin, "-y", "-i", str(source), "-c:v", "copy",
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", str(output)
        ], timeout=self.timeout)

    def export_vertical(self, source: Path, output: Path, fps: float, crf: int = 18) -> ProcessResult:
        output.parent.mkdir(parents=True, exist_ok=True)
        filter_graph = (
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
        )
        return run_process([
            self.ffmpeg_bin, "-y", "-i", str(source), "-vf", filter_graph,
            "-r", f"{fps:.6f}", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output)
        ], timeout=self.timeout)

    @staticmethod
    def _number(value: str) -> float | None:
        return None if "inf" in value.lower() else float(value)

from __future__ import annotations

from pathlib import Path

from integrations.ffmpeg import FFmpegAdapter
from models.artifacts import AudioAnalysis, SilenceRange, VideoInfo


class AudioAnalyzer:
    def __init__(self, ffmpeg: FFmpegAdapter) -> None:
        self.ffmpeg = ffmpeg

    def analyze(self, project_id: str, source: Path, video_info: VideoInfo) -> AudioAnalysis:
        if not video_info.has_audio:
            return AudioAnalysis(project_id=project_id, has_audio=False, warnings=["В видео нет аудиодорожки"])
        probe = self.ffmpeg.probe(source)
        stream = next(item for item in probe["streams"] if item.get("codec_type") == "audio")
        loudness = self.ffmpeg.analyze_loudness(source)
        silences = [SilenceRange(**item) for item in self.ffmpeg.detect_silence(source)]
        peak = loudness["true_peak_db"]
        return AudioAnalysis(
            project_id=project_id,
            has_audio=True,
            channels=int(stream.get("channels") or 0) or None,
            sample_rate=int(stream.get("sample_rate") or 0) or None,
            integrated_loudness_lufs=loudness["integrated_loudness_lufs"],
            true_peak_db=peak,
            clipping_candidates=1 if peak is not None and peak > -0.1 else 0,
            silence_candidates=silences,
        )

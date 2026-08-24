from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from core.config import RuntimeConfig
from core.errors import DependencyError, ValidationAppError
from models.artifacts import Transcript, TranscriptSegment, TranscriptWord, VideoInfo


class BaseTranscriptionProvider(ABC):
    name = "base"

    @abstractmethod
    def transcribe(self, project_id: str, source: Path, video_info: VideoInfo) -> Transcript: ...


class MockTranscriptionProvider(BaseTranscriptionProvider):
    name = "mock"

    def transcribe(self, project_id: str, source: Path, video_info: VideoInfo) -> Transcript:
        end = video_info.duration
        text = "Тестовая расшифровка. Замените mock-провайдер на faster-whisper для реального видео."
        tokens = text.split()
        step = end / len(tokens)
        return Transcript(
            project_id=project_id,
            language="ru",
            source_duration=video_info.duration,
            segments=[TranscriptSegment(
                id="seg_001", start=0.0, end=end, text=text,
                words=[
                    TranscriptWord(
                        text=word,
                        start=index * step,
                        end=min(end, (index + 1) * step),
                    )
                    for index, word in enumerate(tokens)
                ],
            )],
            first_speech=0.0,
            last_speech=end,
            transcript_end=end,
            audio_end=video_info.duration,
            coverage_complete=True,
            provider=self.name,
            provider_metadata={"mock": True, "processed_audio_end": video_info.duration},
        )


class FasterWhisperProvider(BaseTranscriptionProvider):
    name = "faster_whisper"

    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config

    def transcribe(self, project_id: str, source: Path, video_info: VideoInfo) -> Transcript:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise DependencyError(
                "faster-whisper не установлен. Выполните: pip install -r requirements.txt"
            ) from exc
        try:
            model = WhisperModel(
                self.config.whisper_model,
                device=self.config.whisper_device,
                compute_type=self.config.whisper_compute_type,
            )
        except Exception as exc:
            raise DependencyError(
                "Модель faster-whisper не готова. При первом запуске она скачивается; "
                "проверьте сеть и повторите RESUME."
            ) from exc
        raw_segments, info = model.transcribe(str(source), word_timestamps=True, vad_filter=True)
        segments: list[TranscriptSegment] = []
        for index, segment in enumerate(raw_segments, start=1):
            words = [
                TranscriptWord(
                    text=word.word.strip(), start=float(word.start), end=float(word.end),
                    probability=float(word.probability) if word.probability is not None else None,
                )
                for word in (segment.words or [])
                if word.word.strip() and float(word.end) > float(word.start)
            ]
            text = segment.text.strip()
            if not text or float(segment.end) <= float(segment.start):
                continue
            segments.append(TranscriptSegment(
                id=f"seg_{index:04d}", start=float(segment.start), end=float(segment.end),
                text=text, words=words,
            ))
        if not segments:
            raise ValidationAppError(
                "Транскрипция пуста: речь не обнаружена или provider вернул невалидный результат"
            )
        first = segments[0].start
        last = segments[-1].end
        transcript_end = last
        provider_duration = self._provider_duration(info)
        # A detected speech segment does not prove the provider processed the whole file.
        # ``info.duration`` is the provider's actual decoded input duration; VAD duration only
        # describes speech retained by VAD and must never be promoted to full coverage.
        audio_end = min(video_info.duration, provider_duration) if provider_duration is not None else transcript_end
        tolerance = 0.5
        coverage_complete = (
            provider_duration is not None
            and provider_duration >= video_info.duration - tolerance
            and transcript_end <= audio_end + tolerance
        )
        return Transcript(
            project_id=project_id,
            language=getattr(info, "language", "unknown"),
            source_duration=video_info.duration,
            segments=segments,
            first_speech=first,
            last_speech=last,
            transcript_end=transcript_end,
            audio_end=audio_end,
            coverage_complete=coverage_complete,
            provider=self.name,
            provider_metadata={
                "model": self.config.whisper_model,
                "language_probability": getattr(info, "language_probability", None),
                "processed_audio_end": provider_duration,
                "provider_duration": provider_duration,
                "duration_after_vad": self._as_float(getattr(info, "duration_after_vad", None)),
                "coverage_reason": "provider_duration_reaches_source" if coverage_complete else "provider_duration_missing_or_short",
                "trailing_silence_seconds": max(0.0, video_info.duration - transcript_end),
            },
        )

    @staticmethod
    def _as_float(value: object) -> float | None:
        try:
            parsed = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    def _provider_duration(self, info: object) -> float | None:
        duration = self._as_float(getattr(info, "duration", None))
        return duration if duration and duration > 0 else None


def build_transcriber(config: RuntimeConfig) -> BaseTranscriptionProvider:
    if config.transcription_provider == "mock":
        return MockTranscriptionProvider()
    if config.transcription_provider == "faster_whisper":
        return FasterWhisperProvider(config)
    raise DependencyError(f"Неизвестный transcription provider: {config.transcription_provider}")

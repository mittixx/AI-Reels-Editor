from __future__ import annotations

from fractions import Fraction
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.enums import VisualIntent


def canonical_fps(value: str | float | int) -> str:
    """Return HyperFrames-safe exact fps without turning NTSC into a decimal."""
    if isinstance(value, str) and "/" in value:
        numerator, denominator = value.split("/", 1)
        fraction = Fraction(int(numerator), int(denominator))
    else:
        number = float(value)
        if abs(number - 29.97) < 0.02:
            fraction = Fraction(30000, 1001)
        elif abs(number - 59.94) < 0.02:
            fraction = Fraction(60000, 1001)
        else:
            fraction = Fraction(str(value)).limit_denominator(100000)
    if fraction <= 0:
        raise ValueError("fps РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ РїРѕР»РѕР¶РёС‚РµР»СЊРЅС‹Рј")
    return f"{fraction.numerator}/{fraction.denominator}"


class ArtifactModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1.3"
    project_id: str


class VideoInfo(ArtifactModel):
    source_path: str
    source_hash: str
    duration: float = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    orientation: Literal["portrait", "landscape", "square"]
    fps: float = Field(gt=0, le=240)
    fps_rational: str | None = None
    video_codec: str
    audio_codec: str | None = None
    has_audio: bool
    decodable: bool
    file_size: int = Field(gt=0)

    @model_validator(mode="after")
    def canonicalize_fps(self) -> VideoInfo:
        self.fps_rational = canonical_fps(self.fps_rational or self.fps)
        return self


class SilenceRange(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    duration: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> SilenceRange:
        if self.end <= self.start:
            raise ValueError("end РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ Р±РѕР»СЊС€Рµ start")
        return self


class AudioAnalysis(ArtifactModel):
    has_audio: bool
    channels: int | None = None
    sample_rate: int | None = None
    integrated_loudness_lufs: float | None = None
    true_peak_db: float | None = None
    clipping_candidates: int = 0
    silence_candidates: list[SilenceRange] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TranscriptWord(BaseModel):
    text: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    probability: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def ordered(self) -> TranscriptWord:
        if self.end <= self.start:
            raise ValueError("word end РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ Р±РѕР»СЊС€Рµ start")
        if not self.text.strip():
            raise ValueError("word text РЅРµ РјРѕР¶РµС‚ Р±С‹С‚СЊ РїСѓСЃС‚С‹Рј")
        return self


class TranscriptSegment(BaseModel):
    id: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str
    words: list[TranscriptWord] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def text_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("segment text РЅРµ РјРѕР¶РµС‚ Р±С‹С‚СЊ РїСѓСЃС‚С‹Рј")
        return value

    @model_validator(mode="after")
    def ordered(self) -> TranscriptSegment:
        if self.end <= self.start:
            raise ValueError("segment end РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ Р±РѕР»СЊС€Рµ start")
        for word in self.words:
            if word.start < self.start - 0.1 or word.end > self.end + 0.1:
                raise ValueError("word РІС‹С…РѕРґРёС‚ Р·Р° РіСЂР°РЅРёС†С‹ segment")
        return self


class Transcript(ArtifactModel):
    language: str
    source_duration: float = Field(gt=0)
    segments: list[TranscriptSegment] = Field(min_length=1)
    first_speech: float | None = None
    last_speech: float | None = None
    transcript_end: float = Field(ge=0)
    audio_end: float = Field(ge=0)
    coverage_complete: bool
    provider: str
    provider_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def verify_coverage(self) -> Transcript:
        if not self.language.strip() or not self.provider.strip():
            raise ValueError("language/provider РЅРµ РјРѕРіСѓС‚ Р±С‹С‚СЊ РїСѓСЃС‚С‹РјРё")
        if self.transcript_end > self.audio_end + 0.5:
            raise ValueError("transcript_end РІС‹С…РѕРґРёС‚ Р·Р° audio_end")
        if self.audio_end > self.source_duration + 0.5:
            raise ValueError("audio_end РІС‹С…РѕРґРёС‚ Р·Р° source_duration")
        previous_end = -0.1
        for segment in self.segments:
            if segment.start < previous_end - 0.1:
                raise ValueError("transcript segments РїРµСЂРµРєСЂС‹РІР°СЋС‚СЃСЏ РёР»Рё РЅРµ РѕС‚СЃРѕСЂС‚РёСЂРѕРІР°РЅС‹")
            if segment.end > self.audio_end + 0.5:
                raise ValueError("segment РІС‹С…РѕРґРёС‚ Р·Р° audio_end")
            previous_end = segment.end
        actual_end = self.segments[-1].end
        if abs(self.transcript_end - actual_end) > 0.1:
            raise ValueError("transcript_end РЅРµ СЃРѕРІРїР°РґР°РµС‚ СЃ РїРѕСЃР»РµРґРЅРёРј segment")
        if self.first_speech is None or self.last_speech is None:
            raise ValueError("first_speech/last_speech РѕР±СЏР·Р°С‚РµР»СЊРЅС‹ РґР»СЏ РЅРµРїСѓСЃС‚РѕР№ transcription")
        if abs(self.first_speech - self.segments[0].start) > 0.1:
            raise ValueError("first_speech РЅРµ СЃРѕРІРїР°РґР°РµС‚ СЃ РїРµСЂРІС‹Рј segment")
        if abs(self.last_speech - actual_end) > 0.1:
            raise ValueError("last_speech РЅРµ СЃРѕРІРїР°РґР°РµС‚ СЃ РїРѕСЃР»РµРґРЅРёРј segment")
        return self


class SpeechPause(ArtifactModel):
    start: float
    end: float
    reason: str | None = None


class SpeechAnalysis(ArtifactModel):
    content_type: str
    topic: str
    hook_candidates: list[str]
    selected_hook: str
    strong_phrases: list[str]
    weak_phrases: list[str]
    fillers: list[str]
    repetitions: list[str]
    pauses: list[SpeechPause]
    semantic_duplicates: list[str]
    cta: str | None = None
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    suggested_actions: list[str]


class TimeRange(BaseModel):
    id: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    action: Literal["keep", "cut", "shorten", "reorder", "move_hook", "review"] = "keep"
    reason: str = ""

    @model_validator(mode="after")
    def ordered(self) -> TimeRange:
        if self.end <= self.start:
            raise ValueError("invalid time range")
        return self


class EditPlan(ArtifactModel):
    keep_ranges: list[TimeRange] = Field(min_length=1)
    removed_ranges: list[TimeRange] = Field(default_factory=list)
    reordered: bool = False
    moved_hook: bool = False
    estimated_duration: float = Field(gt=0)
    review_required: bool = False
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_timeline(self) -> EditPlan:
        self._validate_non_overlapping(self.keep_ranges, "keep_ranges")
        self._validate_non_overlapping(self.removed_ranges, "removed_ranges")
        if not self.reordered:
            starts = [item.start for item in self.keep_ranges]
            if starts != sorted(starts):
                raise ValueError("keep_ranges РґРѕР»Р¶РЅС‹ Р±С‹С‚СЊ РѕС‚СЃРѕСЂС‚РёСЂРѕРІР°РЅС‹")
        actual = sum(item.end - item.start for item in self.keep_ranges)
        if abs(self.estimated_duration - actual) > 0.05:
            raise ValueError("estimated_duration РЅРµ СЃРѕРІРїР°РґР°РµС‚ СЃ СЃСѓРјРјРѕР№ keep_ranges")
        for keep in self.keep_ranges:
            for removed in self.removed_ranges:
                if min(keep.end, removed.end) - max(keep.start, removed.start) > 0.001:
                    raise ValueError("keep_ranges РїРµСЂРµСЃРµРєР°СЋС‚СЃСЏ СЃ removed_ranges")
        return self

    def validate_against_source(self, source_duration: float) -> None:
        for item in [*self.keep_ranges, *self.removed_ranges]:
            if item.end > source_duration + 0.05:
                raise ValueError("Edit range РІС‹С…РѕРґРёС‚ Р·Р° РґР»РёС‚РµР»СЊРЅРѕСЃС‚СЊ source")

    @staticmethod
    def _validate_non_overlapping(ranges: list[TimeRange], label: str) -> None:
        ordered = sorted(ranges, key=lambda item: (item.start, item.end))
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current.start < previous.end - 0.001:
                raise ValueError(f"{label} РїРµСЂРµРєСЂС‹РІР°СЋС‚СЃСЏ")

class VisualData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | int | float | bool | None = None
    path: str | None = None
    label: str | None = None


class VisualItem(BaseModel):
    id: str
    intent: VisualIntent
    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    text: str | None = None
    asset_id: str | None = None
    data: VisualData | None = None
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "HIGH"

    @model_validator(mode="after")
    def require_media_asset(self) -> VisualItem:
        media_intents = {
            VisualIntent.B_ROLL,
            VisualIntent.SCREEN_RECORDING,
            VisualIntent.SCREENSHOT,
            VisualIntent.LOGO,
        }

        if self.intent in media_intents and not (self.asset_id or "").strip():
            raise ValueError(
                f"Visual item {self.id}: {self.intent.value} С‚СЂРµР±СѓРµС‚ asset_id"
            )

        return self

class VisualPlan(ArtifactModel):
    output_duration: float = Field(gt=0)
    items: list[VisualItem]
    profile: str
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_items(self) -> VisualPlan:
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Visual item ids РґРѕР»Р¶РЅС‹ Р±С‹С‚СЊ СѓРЅРёРєР°Р»СЊРЅС‹РјРё")
        for item in self.items:
            if item.start + item.duration > self.output_duration + 0.05:
                raise ValueError(f"Visual item {item.id} РІС‹С…РѕРґРёС‚ Р·Р° output timeline")
        return self


class MotionItem(BaseModel):
    id: str
    visual_id: str
    component: str
    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    data: dict[str, Any] = Field(default_factory=dict)
    preset: str
    output_path: str
    cache_key: str

class MotionPlan(ArtifactModel):
    required: bool
    items: list[MotionItem] = Field(default_factory=list)


class MediaAsset(BaseModel):
    id: str
    type: str
    path: str
    sha256: str
    source: Literal["user", "generated", "derived", "cached"]
    duration: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MediaManifest(ArtifactModel):
    assets: list[MediaAsset]

    @model_validator(mode="after")
    def unique_assets(self) -> MediaManifest:
        ids = [asset.id for asset in self.assets]
        if len(ids) != len(set(ids)):
            raise ValueError("Media asset ids РґРѕР»Р¶РЅС‹ Р±С‹С‚СЊ СѓРЅРёРєР°Р»СЊРЅС‹РјРё")
        return self


class RenderOperation(BaseModel):
    id: str
    operation: str
    renderer: str
    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    inputs: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)


class RenderPlan(ArtifactModel):
    width: int = 1080
    height: int = 1920
    fps: float = Field(gt=0, le=240)
    fps_rational: str | None = None
    duration: float = Field(gt=0)
    operations: list[RenderOperation]
    master_renderer: Literal["hyperframes"] = "hyperframes"
    output_path: str
    cache_key: str

    @model_validator(mode="after")
    def validate_operations(self) -> RenderPlan:
        self.fps_rational = canonical_fps(self.fps_rational or self.fps)
        ids = [operation.id for operation in self.operations]
        if len(ids) != len(set(ids)):
            raise ValueError("Render operation ids РґРѕР»Р¶РЅС‹ Р±С‹С‚СЊ СѓРЅРёРєР°Р»СЊРЅС‹РјРё")
        for operation in self.operations:
            if operation.start + operation.duration > self.duration + 0.05:
                raise ValueError(f"Render operation {operation.id} РІС‹С…РѕРґРёС‚ Р·Р° timeline")
        return self


class QCIssue(BaseModel):
    code: str
    severity: Literal["critical", "warning", "info"]
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class QCReport(ArtifactModel):
    target_path: str
    passed: bool
    export_allowed: bool
    issues: list[QCIssue] = Field(default_factory=list)
    measured: dict[str, Any] = Field(default_factory=dict)




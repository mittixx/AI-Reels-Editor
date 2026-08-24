from __future__ import annotations

from enum import IntEnum, StrEnum


class Mode(StrEnum):
    FAST = "fast"
    DETAIL = "detail"


class Profile(StrEnum):
    EXPERT = "expert"
    SELLING = "selling"
    LIFESTYLE = "lifestyle"


class StageStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class Stage(StrEnum):
    SOURCE_ANALYSIS = "source_analysis"
    AUDIO_ANALYSIS = "audio_analysis"
    TRANSCRIPTION = "transcription"
    SPEECH_ANALYSIS = "speech_analysis"
    EDIT_PLAN = "edit_plan"
    VISUAL_PLAN = "visual_plan"
    MOTION_PLAN = "motion_plan"
    MEDIA_MANIFEST = "media_manifest"
    RENDER_PLAN = "render_plan"
    MOTION_RENDER = "motion_render"
    MASTER_RENDER = "master_render"
    QC = "qc"
    EXPORT = "export"


class Command(StrEnum):
    CREATE_REEL = "CREATE_REEL"
    STATUS = "STATUS"
    RESUME = "RESUME"
    REVISE = "REVISE"
    QC = "QC"
    EXPORT = "EXPORT"
    PACKAGE_CAPCUT = "PACKAGE_CAPCUT"
    LIST_PROJECTS = "LIST_PROJECTS"
    PROJECT_INFO = "PROJECT_INFO"
    CANCEL_SAFE = "CANCEL_SAFE"
    DOCTOR = "DOCTOR"
    IMPORT_ASSET = "IMPORT_ASSET"


class ExitCode(IntEnum):
    SUCCESS = 0
    GENERAL_ERROR = 1
    INVALID_REQUEST = 2
    PROJECT_NOT_FOUND = 3
    DEPENDENCY_MISSING = 4
    AI_UNAVAILABLE = 5
    RENDER_FAILED = 6
    USER_ACTION_REQUIRED = 7
    QC_FAILED = 8
    CANCELLED = 9


class RendererType(StrEnum):
    FFMPEG = "ffmpeg"
    HYPERFRAMES = "hyperframes"
    MOTION_CANVAS = "motion_canvas"
    CAPCUT = "capcut"


class VisualIntent(StrEnum):
    SUBTITLE = "subtitle"
    HOOK_TEXT = "hook_text"
    B_ROLL = "b_roll"
    SCREEN_RECORDING = "screen_recording"
    SCREENSHOT = "screenshot"
    LOGO = "logo"
    TEXT_ACCENT = "text_accent"
    SIMPLE_ZOOM = "simple_zoom"
    TRANSITION = "transition"
    SIMPLE_TRANSITION = "simple_transition"
    CTA = "cta"
    ANIMATED_STAT = "animated_stat"
    ANIMATED_COUNTER = "animated_counter"
    COMPARISON = "comparison"
    PROCESS_FLOW = "process_flow"
    TIMELINE = "timeline"
    QUOTE = "quote"
    CODE_ANIMATION = "code_animation"
    FEATURE_LIST = "feature_list"
    PRODUCT_FEATURE = "product_feature"
    BEFORE_AFTER = "before_after"
    CALLOUT = "callout"
    CHART = "chart"
    DIAGRAM = "diagram"
    COMPLEX_CAPCUT_EFFECT = "complex_capcut_effect"
    BEAUTY_ADJUSTMENT = "beauty_adjustment"
    MANUAL_VISUAL_FIX = "manual_visual_fix"


class CheckStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    MISCONFIGURED = "MISCONFIGURED"
    OPTIONAL_MISSING = "OPTIONAL_MISSING"

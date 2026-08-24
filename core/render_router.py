from __future__ import annotations

from models.enums import RendererType, VisualIntent

ROUTES: dict[str, RendererType] = {
    "technical_cut": RendererType.FFMPEG,
    "audio_normalization": RendererType.FFMPEG,
    "subtitle": RendererType.HYPERFRAMES,
    "hook_text": RendererType.HYPERFRAMES,
    "b_roll": RendererType.HYPERFRAMES,
    "screen_recording": RendererType.HYPERFRAMES,
    "screenshot": RendererType.HYPERFRAMES,
    "logo": RendererType.HYPERFRAMES,
    "text_accent": RendererType.HYPERFRAMES,
    "simple_zoom": RendererType.HYPERFRAMES,
    "transition": RendererType.HYPERFRAMES,
    "simple_transition": RendererType.HYPERFRAMES,
    "cta": RendererType.HYPERFRAMES,
    "animated_stat": RendererType.MOTION_CANVAS,
    "animated_counter": RendererType.MOTION_CANVAS,
    "comparison": RendererType.MOTION_CANVAS,
    "process_flow": RendererType.MOTION_CANVAS,
    "timeline": RendererType.MOTION_CANVAS,
    "quote": RendererType.MOTION_CANVAS,
    "code_animation": RendererType.MOTION_CANVAS,
    "feature_list": RendererType.MOTION_CANVAS,
    "product_feature": RendererType.MOTION_CANVAS,
    "before_after": RendererType.MOTION_CANVAS,
    "callout": RendererType.MOTION_CANVAS,
    "chart": RendererType.MOTION_CANVAS,
    "diagram": RendererType.MOTION_CANVAS,
    "complex_capcut_effect": RendererType.CAPCUT,
    "beauty_adjustment": RendererType.CAPCUT,
    "manual_visual_fix": RendererType.CAPCUT,
}


class RenderRouter:
    def route(self, operation: str | VisualIntent) -> RendererType:
        operation_name = operation.value if isinstance(operation, VisualIntent) else operation
        try:
            return ROUTES[operation_name]
        except KeyError as exc:
            raise ValueError(f"Нет deterministic route для операции: {operation_name}") from exc

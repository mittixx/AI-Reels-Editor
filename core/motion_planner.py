from __future__ import annotations

from pathlib import Path

from core.io_utils import sha256_data
from models.artifacts import MotionItem, MotionPlan, VisualPlan

MOTION_COMPONENTS = {
    "animated_stat": "AnimatedStat",
    "animated_counter": "AnimatedCounter",
    "comparison": "Comparison",
    "process_flow": "ProcessFlow",
    "timeline": "Timeline",
    "quote": "Quote",
    "code_animation": "CodeHighlight",
    "feature_list": "FeatureList",
    "product_feature": "ProductFeature",
    "before_after": "BeforeAfter",
    "callout": "Callout",
    "chart": "Chart",
    "diagram": "Diagram",
}


class MotionPlanner:
    def plan(self, project_dir: Path, visual_plan: VisualPlan, preset: str = "default") -> MotionPlan:
        items: list[MotionItem] = []
        for visual in visual_plan.items:
            component = MOTION_COMPONENTS.get(visual.intent)
            if not component:
                continue
            payload = {
                "component": component,
                "data": visual.data,
                "duration": visual.duration,
                "preset": preset,
                "component_version": "1.3.2",
            }
            cache_key = sha256_data(payload)
            item_id = f"motion_{len(items) + 1:03d}_{cache_key[:12]}"
            output = project_dir / "generated" / "motion" / f"{item_id}.mp4"
            items.append(MotionItem(
                id=item_id, visual_id=visual.id, component=component,
                start=visual.start, duration=visual.duration, data=visual.data, preset=preset,
                output_path=str(output), cache_key=cache_key,
            ))
        return MotionPlan(project_id=visual_plan.project_id, required=bool(items), items=items)


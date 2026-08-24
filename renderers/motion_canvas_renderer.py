from __future__ import annotations

from pathlib import Path

from integrations.motion_canvas import MotionCanvasIntegration
from models.artifacts import MotionPlan
from renderers.base_renderer import BaseRenderer, RenderResult


class MotionCanvasRenderer(BaseRenderer):
    name = "motion_canvas"

    def __init__(self, node_project: Path, integration: MotionCanvasIntegration) -> None:
        self.node_project = node_project
        self.integration = integration

    def available(self) -> bool:
        return self.integration.available(self.node_project)

    def render_plan(self, project_dir: Path, plan: MotionPlan) -> RenderResult:
        outputs: list[str] = []
        for item in plan.items:
            output = Path(item.output_path)
            job = self.integration.render(
                self.node_project,
                item,
                project_dir / "working" / "motion_jobs",
            )
            try:
                self.integration.validate_result(job, output)
            except Exception:
                self.integration.cleanup_job(job)
                raise
            outputs.append(str(output))
        return RenderResult(True, Path(outputs[-1]) if outputs else None, {"outputs": outputs})

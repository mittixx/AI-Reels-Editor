from __future__ import annotations

from pathlib import Path

from core.config import load_profile
from core.errors import DependencyError, RenderError
from core.render_validation import validate_media_operations
from core.subtitle_builder import SubtitleBuilder
from integrations.hyperframes import HyperFramesIntegration
from models.artifacts import EditPlan, MediaManifest, RenderPlan, Transcript, VisualPlan
from renderers.base_renderer import BaseRenderer, RenderResult


class HyperFramesRenderer(BaseRenderer):
    name = "hyperframes"

    def __init__(self, root: Path, integration: HyperFramesIntegration) -> None:
        self.root = root
        self.integration = integration

    def available(self) -> bool:
        return self.integration.available()

    def render(
        self,
        project_dir: Path,
        base_edit: Path,
        transcript: Transcript,
        edit_plan: EditPlan,
        visual_plan: VisualPlan,
        render_plan: RenderPlan,
        media_manifest: MediaManifest,
        profile_name: str,
    ) -> RenderResult:
        if not self.available():
            raise DependencyError(
                "Локальный HyperFrames CLI не установлен; выполните npm ci в node_tools/hyperframes"
            )
        validate_media_operations(render_plan, media_manifest)
        composition_dir = project_dir / "working" / "hyperframes"
        subtitles = SubtitleBuilder().build(transcript, edit_plan)
        self.integration.prepare(
            composition_dir,
            base_edit,
            render_plan,
            media_manifest,
            subtitles,
            load_profile(self.root, profile_name),
        )
        lint = self.integration.lint(composition_dir)
        if lint.returncode != 0:
            # One bounded correction: regenerate from the validated structured plans.
            self.integration.prepare(
                composition_dir,
                base_edit,
                render_plan,
                media_manifest,
                subtitles,
                load_profile(self.root, profile_name),
            )
            lint = self.integration.lint(composition_dir)
        self.integration.validate_result(lint)
        check = self.integration.check(composition_dir)
        self.integration.validate_result(check)
        output = Path(render_plan.output_path)
        job = self.integration.render(composition_dir, output, render_plan.fps_rational or "30/1")
        try:
            metadata = self.integration.validate_render_job(job, output)
        except Exception:
            self.integration.cleanup_job(job)
            raise
        if output.resolve() == Path(transcript.provider_metadata.get("source_path", "__none__")).resolve():
            raise RenderError("Renderer попытался перезаписать source")
        return RenderResult(True, output, metadata)

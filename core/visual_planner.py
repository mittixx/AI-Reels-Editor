from __future__ import annotations

from pathlib import Path

from core.errors import ValidationAppError
from integrations.ai_client import BaseAIProvider, read_prompt
from models.artifacts import EditPlan, MediaAsset, SpeechAnalysis, Transcript, VisualPlan


class VisualPlanner:
    def __init__(self, root: Path, provider: BaseAIProvider) -> None:
        self.root = root
        self.provider = provider

    def plan(
        self,
        transcript: Transcript,
        speech: SpeechAnalysis,
        edit_plan: EditPlan,
        profile: str,
        mode: str,
        instructions: str | None = None,
        available_assets: list[MediaAsset] | None = None,
    ) -> VisualPlan:
        context = {
            "project_id": transcript.project_id,
            "profile": profile,
            "mode": mode,
            "duration": edit_plan.estimated_duration,
            "selected_hook": speech.selected_hook,
            "speech_analysis": speech.model_dump(mode="json"),
            "edit_plan": edit_plan.model_dump(mode="json"),
            "instructions": instructions,
            "available_assets": [
                {"asset_id": asset.id, "type": asset.type, "duration": asset.duration, "metadata": asset.metadata}
                for asset in available_assets or []
            ],
        }
        plan = self.provider.generate("visual_plan", read_prompt(self.root, "visual_plan_v1.3.md"), context, VisualPlan)
        for item in plan.items:
            if item.start + item.duration > plan.output_duration + 0.1:
                raise ValueError(f"Visual item {item.id} выходит за output timeline")
            if item.asset_id and item.asset_id != "source" and item.asset_id not in {
                asset.id for asset in available_assets or []
            }:
                raise ValidationAppError(f"Visual item {item.id} выбрал отсутствующий asset_id: {item.asset_id}")
        return plan

from __future__ import annotations

from pathlib import Path

from integrations.ai_client import BaseAIProvider, read_prompt
from models.artifacts import EditPlan, SpeechAnalysis, Transcript


class EditPlanner:
    def __init__(self, root: Path, provider: BaseAIProvider) -> None:
        self.root = root
        self.provider = provider

    def plan(self, transcript: Transcript, speech: SpeechAnalysis, mode: str, instructions: str | None = None) -> EditPlan:
        context = {
            "project_id": transcript.project_id,
            "mode": mode,
            "duration": transcript.source_duration,
            "coverage_complete": transcript.coverage_complete,
            "segments": [segment.model_dump(mode="json") for segment in transcript.segments],
            "speech_analysis": speech.model_dump(mode="json"),
            "instructions": instructions,
        }
        plan = self.provider.generate("edit_plan", read_prompt(self.root, "edit_plan_v1.3.md"), context, EditPlan)
        self._validate(plan, transcript.source_duration)
        return plan

    @staticmethod
    def _validate(plan: EditPlan, source_duration: float) -> None:
        plan.validate_against_source(source_duration)

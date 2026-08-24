from __future__ import annotations

from pathlib import Path

from integrations.ai_client import BaseAIProvider, read_prompt
from models.artifacts import SpeechAnalysis, Transcript


class SpeechAnalyzer:
    def __init__(self, root: Path, provider: BaseAIProvider) -> None:
        self.root = root
        self.provider = provider

    def analyze(self, transcript: Transcript, profile: str, mode: str, instructions: str | None = None) -> SpeechAnalysis:
        context = {
            "project_id": transcript.project_id,
            "profile": profile,
            "mode": mode,
            "duration": transcript.source_duration,
            "coverage_complete": transcript.coverage_complete,
            "segments": [segment.model_dump(mode="json") for segment in transcript.segments],
            "instructions": instructions,
        }
        return self.provider.generate(
            "speech_analysis", read_prompt(self.root, "speech_analysis_v1.3.md"), context, SpeechAnalysis
        )

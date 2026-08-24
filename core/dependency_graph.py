from __future__ import annotations

from collections import deque

from models.enums import Stage

STAGE_ORDER: tuple[Stage, ...] = (
    Stage.SOURCE_ANALYSIS,
    Stage.AUDIO_ANALYSIS,
    Stage.TRANSCRIPTION,
    Stage.SPEECH_ANALYSIS,
    Stage.EDIT_PLAN,
    Stage.VISUAL_PLAN,
    Stage.MOTION_PLAN,
    Stage.MOTION_RENDER,
    Stage.MEDIA_MANIFEST,
    Stage.RENDER_PLAN,
    Stage.MASTER_RENDER,
    Stage.QC,
    Stage.EXPORT,
)

DEPENDENCIES: dict[Stage, set[Stage]] = {
    Stage.SOURCE_ANALYSIS: set(),
    Stage.AUDIO_ANALYSIS: {Stage.SOURCE_ANALYSIS},
    Stage.TRANSCRIPTION: {Stage.SOURCE_ANALYSIS, Stage.AUDIO_ANALYSIS},
    Stage.SPEECH_ANALYSIS: {Stage.TRANSCRIPTION},
    Stage.EDIT_PLAN: {Stage.SPEECH_ANALYSIS, Stage.TRANSCRIPTION},
    Stage.VISUAL_PLAN: {Stage.EDIT_PLAN, Stage.SPEECH_ANALYSIS},
    Stage.MOTION_PLAN: {Stage.VISUAL_PLAN},
    Stage.MEDIA_MANIFEST: {
        Stage.SOURCE_ANALYSIS,
        Stage.VISUAL_PLAN,
        Stage.MOTION_PLAN,
        Stage.MOTION_RENDER,
    },
    Stage.RENDER_PLAN: {Stage.EDIT_PLAN, Stage.VISUAL_PLAN, Stage.MEDIA_MANIFEST, Stage.MOTION_PLAN},
    Stage.MOTION_RENDER: {Stage.MOTION_PLAN},
    Stage.MASTER_RENDER: {Stage.RENDER_PLAN, Stage.MEDIA_MANIFEST},
    Stage.QC: {Stage.MASTER_RENDER},
    Stage.EXPORT: {Stage.QC},
}

ARTIFACT_FOR_STAGE: dict[Stage, str | None] = {
    Stage.SOURCE_ANALYSIS: "video_info.json",
    Stage.AUDIO_ANALYSIS: "audio_analysis.json",
    Stage.TRANSCRIPTION: "transcript.json",
    Stage.SPEECH_ANALYSIS: "speech_analysis.json",
    Stage.EDIT_PLAN: "edit_plan.json",
    Stage.VISUAL_PLAN: "visual_plan.json",
    Stage.MOTION_PLAN: "motion_plan.json",
    Stage.MEDIA_MANIFEST: "media_manifest.json",
    Stage.RENDER_PLAN: "render_plan.json",
    Stage.MOTION_RENDER: "motion_manifest.json",
    Stage.MASTER_RENDER: "draft.mp4",
    Stage.QC: "qc_report.json",
    Stage.EXPORT: None,
}

REVISION_ROOTS: dict[str, set[Stage]] = {
    "hook": {Stage.SPEECH_ANALYSIS, Stage.EDIT_PLAN, Stage.VISUAL_PLAN},
    "speech": {Stage.SPEECH_ANALYSIS},
    "edit": {Stage.EDIT_PLAN},
    "broll": {Stage.VISUAL_PLAN},
    "visual": {Stage.VISUAL_PLAN},
    "motion": {Stage.MOTION_PLAN},
    "subtitles": {Stage.VISUAL_PLAN},
    "render": {Stage.RENDER_PLAN},
}


class DependencyGraph:
    def __init__(self) -> None:
        self.dependencies = DEPENDENCIES
        self._validate_acyclic()

    def _validate_acyclic(self) -> None:
        visited: set[Stage] = set()
        active: set[Stage] = set()

        def visit(stage: Stage) -> None:
            if stage in active:
                raise ValueError("Dependency graph contains a cycle")
            if stage in visited:
                return
            active.add(stage)
            for dependency in self.dependencies[stage]:
                visit(dependency)
            active.remove(stage)
            visited.add(stage)

        for stage in STAGE_ORDER:
            visit(stage)

    def downstream(self, roots: set[Stage], include_roots: bool = True) -> set[Stage]:
        result = set(roots) if include_roots else set()
        queue = deque(roots)
        while queue:
            current = queue.popleft()
            for stage, dependencies in self.dependencies.items():
                if current in dependencies and stage not in result:
                    result.add(stage)
                    queue.append(stage)
        return result

    def for_revision(self, scope: str) -> set[Stage]:
        if scope not in REVISION_ROOTS:
            raise ValueError(f"Неизвестная область revision: {scope}")
        return self.downstream(REVISION_ROOTS[scope])

    def first_runnable(self, completed: set[Stage]) -> Stage | None:
        for stage in STAGE_ORDER:
            if stage not in completed and self.dependencies[stage].issubset(completed):
                return stage
        return None

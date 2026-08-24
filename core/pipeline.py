from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel

from core.audio_analyzer import AudioAnalyzer
from core.cache import CacheManager
from core.config import RuntimeConfig, load_preset
from core.dependency_graph import STAGE_ORDER, DependencyGraph
from core.edit_planner import EditPlanner
from core.errors import AppError, QCError, RenderError, ValidationAppError
from core.exporter import Exporter
from core.io_utils import atomic_write_json, read_json_model, sha256_data, sha256_file
from core.media_manager import MediaManager
from core.motion_planner import MotionPlanner
from core.project_manager import ProjectManager
from core.quality_control import QualityControl
from core.recovery_manager import RecoveryManager
from core.render_planner import RenderPlanner
from core.render_router import RenderRouter
from core.speech_analyzer import SpeechAnalyzer
from core.transcriber import BaseTranscriptionProvider
from core.video_analyzer import VideoAnalyzer
from core.visual_planner import VisualPlanner
from models.artifacts import (
    EditPlan,
    MediaManifest,
    MotionPlan,
    QCReport,
    RenderPlan,
    SpeechAnalysis,
    Transcript,
    VideoInfo,
    VisualPlan,
)
from models.contracts import ArtifactRecord, ProjectState
from models.enums import Stage, StageStatus
from renderers.ffmpeg_renderer import FFmpegRenderer
from renderers.hyperframes_renderer import HyperFramesRenderer
from renderers.motion_canvas_renderer import MotionCanvasRenderer

LOGGER = logging.getLogger(__name__)


class Pipeline:
    def __init__(
        self,
        config: RuntimeConfig,
        manager: ProjectManager,
        video_analyzer: VideoAnalyzer,
        audio_analyzer: AudioAnalyzer,
        transcriber: BaseTranscriptionProvider,
        speech_analyzer: SpeechAnalyzer,
        edit_planner: EditPlanner,
        visual_planner: VisualPlanner,
        motion_planner: MotionPlanner,
        ffmpeg_renderer: FFmpegRenderer,
        hyperframes_renderer: HyperFramesRenderer,
        motion_renderer: MotionCanvasRenderer,
        qc: QualityControl,
        exporter: Exporter,
    ) -> None:
        self.config = config
        self.manager = manager
        self.graph = DependencyGraph()
        self.cache = CacheManager()
        self.recovery = RecoveryManager()
        self.video_analyzer = video_analyzer
        self.audio_analyzer = audio_analyzer
        self.transcriber = transcriber
        self.speech_analyzer = speech_analyzer
        self.edit_planner = edit_planner
        self.visual_planner = visual_planner
        self.motion_planner = motion_planner
        self.ffmpeg_renderer = ffmpeg_renderer
        self.hyperframes_renderer = hyperframes_renderer
        self.motion_renderer = motion_renderer
        self.qc = qc
        self.exporter = exporter

    def run(self, project_id: str, instructions: str | None = None, stop_after: Stage | None = None) -> ProjectState:
        state = self.manager.load(project_id)
        self.manager.assert_source_unchanged(state)
        warnings = self.recovery.repair_state(state)
        if warnings:
            state.pending_tasks.extend(warnings)
            self.manager.save(state)
        state.cancelled = False
        semantic_stages = {Stage.SPEECH_ANALYSIS, Stage.EDIT_PLAN, Stage.VISUAL_PLAN}
        if instructions is not None:
            for stage in semantic_stages:
                if state.stages[stage.value].status not in {
                    StageStatus.COMPLETED,
                    StageStatus.SKIPPED,
                }:
                    state.stage_instructions[stage.value] = instructions
            self.manager.save(state)
        project_dir = self.manager.project_dir(project_id)
        for stage in STAGE_ORDER:
            if state.cancelled:
                state.status = "cancelled"
                self.manager.save(state)
                break
            input_hash = self._stage_input_hash(state, stage)
            if self.cache.stage_hit(state, stage, input_hash):
                if stop_after == stage:
                    break
                continue
            record = state.stages[stage.value]
            if record.status in {StageStatus.COMPLETED, StageStatus.SKIPPED}:
                invalidated = self.graph.downstream({stage})
                self.manager.invalidate(state, invalidated)
                state.pending_tasks.append(
                    f"cache_miss:{stage.value}:input_hash_changed"
                )
                self.manager.save(state)
                input_hash = self._stage_input_hash(state, stage)
            self.manager.mark_started(state, stage, input_hash)
            try:
                self._execute_stage(
                    state,
                    stage,
                    project_dir,
                    state.stage_instructions.get(stage.value),
                    input_hash,
                )
            except Exception as exc:
                code = exc.code if isinstance(exc, AppError) else type(exc).__name__
                self.manager.mark_failed(state, stage, code, str(exc))
                LOGGER.exception("Pipeline stage failed", extra={"project_id": project_id, "stage": stage.value, "error_code": code})
                raise
            state = self.manager.load(project_id)
            if stop_after == stage:
                break
        if all(record.status in {StageStatus.COMPLETED, StageStatus.SKIPPED} for record in state.stages.values()):
            state.status = "completed"
            state.last_error = None
            self.manager.save(state)
        return state

    def _stage_input_hash(self, state: ProjectState, stage: Stage) -> str:
        versions = self.config.raw.get("versions", {})
        version_inputs: dict[str, str | None] = {
            "pipeline": versions.get("pipeline"),
        }
        if stage in {Stage.SPEECH_ANALYSIS, Stage.EDIT_PLAN, Stage.VISUAL_PLAN}:
            version_inputs["prompt"] = versions.get("prompt")
        if stage in {Stage.MOTION_PLAN, Stage.MOTION_RENDER, Stage.MEDIA_MANIFEST}:
            version_inputs["motion_components"] = versions.get("motion_components")
        if stage in {Stage.RENDER_PLAN, Stage.MASTER_RENDER, Stage.QC, Stage.EXPORT}:
            version_inputs["hyperframes_template"] = versions.get("hyperframes_template")

        file_inputs: dict[str, str] = {}
        prompt_names = {
            Stage.SPEECH_ANALYSIS: "speech_analysis_v1.3.md",
            Stage.EDIT_PLAN: "edit_plan_v1.3.md",
            Stage.VISUAL_PLAN: "visual_plan_v1.3.md",
        }
        if stage in prompt_names:
            file_inputs["prompt"] = sha256_file(
                self.config.root / "prompts" / prompt_names[stage]
            )
        if stage in {Stage.VISUAL_PLAN, Stage.RENDER_PLAN, Stage.MASTER_RENDER}:
            file_inputs["profile"] = sha256_file(
                self.config.root / "config" / "profiles" / f"{state.profile}.json"
            )
        if stage in {Stage.RENDER_PLAN, Stage.MASTER_RENDER, Stage.QC}:
            file_inputs["render_preset"] = sha256_file(
                self.config.root / "config" / "presets" / "render.json"
            )
        if stage in {Stage.VISUAL_PLAN, Stage.MEDIA_MANIFEST, Stage.RENDER_PLAN, Stage.MASTER_RENDER, Stage.QC, Stage.EXPORT}:
            asset_inputs = []
            for asset in state.user_assets:
                asset_path = Path(asset.path)
                asset_inputs.append({
                    "asset": asset.model_dump(mode="json"),
                    "current_file_hash": sha256_file(asset_path) if asset_path.is_file() else "missing",
                })
            file_inputs["user_assets"] = sha256_data(asset_inputs)

        provider_inputs: dict[str, str] = {}
        if stage == Stage.TRANSCRIPTION:
            provider_inputs = {
                "provider": self.config.transcription_provider,
                "model": self.config.whisper_model,
                "device": self.config.whisper_device,
                "compute_type": self.config.whisper_compute_type,
            }
        elif stage in {Stage.SPEECH_ANALYSIS, Stage.EDIT_PLAN, Stage.VISUAL_PLAN}:
            provider_inputs = {
                "provider": self.config.ai_provider,
                "model": self.config.openai_model,
            }

        target = (
            self.config.raw.get("target")
            if stage in {Stage.RENDER_PLAN, Stage.MASTER_RENDER, Stage.QC, Stage.EXPORT}
            else None
        )
        return sha256_data({
            "stage": stage.value,
            "source": state.source_hash,
            "dependencies": {
                dependency.value: state.stages[dependency.value].output_hash
                for dependency in sorted(
                    self.graph.dependencies[stage],
                    key=lambda item: item.value,
                )
            },
            "mode": state.mode if stage not in {Stage.SOURCE_ANALYSIS, Stage.AUDIO_ANALYSIS} else None,
            "profile": state.profile if stage not in {Stage.SOURCE_ANALYSIS, Stage.AUDIO_ANALYSIS} else None,
            "instructions": state.stage_instructions.get(stage.value),
            "versions": version_inputs,
            "files": file_inputs,
            "providers": provider_inputs,
            "target": target,
        })

    def _execute_stage(self, state: ProjectState, stage: Stage, project_dir: Path, instructions: str | None, input_hash: str) -> None:
        artifacts = project_dir / "artifacts"
        source = Path(state.source_path)
        if stage == Stage.SOURCE_ANALYSIS:
            self._save_model(state, stage, self.video_analyzer.analyze(state.project_id, source, state.source_hash), artifacts / "video_info.json", input_hash)
        elif stage == Stage.AUDIO_ANALYSIS:
            video = read_json_model(artifacts / "video_info.json", VideoInfo)
            self._save_model(state, stage, self.audio_analyzer.analyze(state.project_id, source, video), artifacts / "audio_analysis.json", input_hash)
        elif stage == Stage.TRANSCRIPTION:
            video = read_json_model(artifacts / "video_info.json", VideoInfo)
            self._save_model(state, stage, self.transcriber.transcribe(state.project_id, source, video), artifacts / "transcript.json", input_hash)
        elif stage == Stage.SPEECH_ANALYSIS:
            transcript = read_json_model(artifacts / "transcript.json", Transcript)
            if not transcript.coverage_complete:
                raise ValidationAppError(
                    "Транскрипция помечена как неполная; semantic pipeline остановлен"
                )
            self._save_model(state, stage, self.speech_analyzer.analyze(transcript, str(state.profile), str(state.mode), instructions), artifacts / "speech_analysis.json", input_hash)
        elif stage == Stage.EDIT_PLAN:
            transcript = read_json_model(artifacts / "transcript.json", Transcript)
            speech = read_json_model(artifacts / "speech_analysis.json", SpeechAnalysis)
            self._save_model(state, stage, self.edit_planner.plan(transcript, speech, str(state.mode), instructions), artifacts / "edit_plan.json", input_hash)
        elif stage == Stage.VISUAL_PLAN:
            transcript = read_json_model(artifacts / "transcript.json", Transcript)
            speech = read_json_model(artifacts / "speech_analysis.json", SpeechAnalysis)
            edit = read_json_model(artifacts / "edit_plan.json", EditPlan)
            self._save_model(state, stage, self.visual_planner.plan(transcript, speech, edit, str(state.profile), str(state.mode), instructions, state.user_assets), artifacts / "visual_plan.json", input_hash)
        elif stage == Stage.MOTION_PLAN:
            visual = read_json_model(artifacts / "visual_plan.json", VisualPlan)
            self._save_model(state, stage, self.motion_planner.plan(project_dir, visual), artifacts / "motion_plan.json", input_hash)
        elif stage == Stage.MEDIA_MANIFEST:
            video = read_json_model(artifacts / "video_info.json", VideoInfo)
            motion = read_json_model(artifacts / "motion_plan.json", MotionPlan)
            visual = read_json_model(artifacts / "visual_plan.json", VisualPlan)
            self._save_model(
                state,
                stage,
                MediaManager().build_manifest(video, motion, visual, state.user_assets),
                artifacts / "media_manifest.json",
                input_hash,
            )
        elif stage == Stage.RENDER_PLAN:
            video = read_json_model(artifacts / "video_info.json", VideoInfo)
            edit = read_json_model(artifacts / "edit_plan.json", EditPlan)
            visual = read_json_model(artifacts / "visual_plan.json", VisualPlan)
            motion = read_json_model(artifacts / "motion_plan.json", MotionPlan)
            manifest = read_json_model(artifacts / "media_manifest.json", MediaManifest)
            plan = RenderPlanner(RenderRouter(), getattr(self.ffmpeg_renderer, "adapter", None)).plan(project_dir, video, edit, visual, motion, manifest, load_preset(self.config.root, "render"))
            self._save_model(state, stage, plan, artifacts / "render_plan.json", input_hash)
        elif stage == Stage.MOTION_RENDER:
            motion = read_json_model(artifacts / "motion_plan.json", MotionPlan)
            if not motion.required:
                self.manager.mark_skipped(state, stage, "motion_not_required")
            else:
                result = self.motion_renderer.render_plan(project_dir, motion)
                manifest_path = artifacts / "motion_manifest.json"
                atomic_write_json(manifest_path, {"schema_version": "1.3", "project_id": state.project_id, **result.metadata})
                self._record_file(state, stage, manifest_path, input_hash)
        elif stage == Stage.MASTER_RENDER:
            transcript = read_json_model(artifacts / "transcript.json", Transcript)
            edit = read_json_model(artifacts / "edit_plan.json", EditPlan)
            visual = read_json_model(artifacts / "visual_plan.json", VisualPlan)
            plan = read_json_model(artifacts / "render_plan.json", RenderPlan)
            manifest = read_json_model(artifacts / "media_manifest.json", MediaManifest)
            base_edit = project_dir / "working" / "base_edit.mp4"
            self.ffmpeg_renderer.render_base_edit(source, edit, base_edit)
            result = self.hyperframes_renderer.render(
                project_dir,
                base_edit,
                transcript,
                edit,
                visual,
                plan,
                manifest,
                str(state.profile),
            )
            if not result.output:
                raise RenderError("HyperFrames output не указан")
            self._record_file(state, stage, result.output, input_hash, artifact_type="draft.mp4")
        elif stage == Stage.QC:
            plan = read_json_model(artifacts / "render_plan.json", RenderPlan)
            report = self.qc.inspect(state.project_id, Path(plan.output_path), plan.duration)
            self._save_model(state, stage, report, artifacts / "qc_report.json", input_hash)
            if not report.export_allowed:
                raise QCError("Technical QC заблокировал экспорт")
        elif stage == Stage.EXPORT:
            plan = read_json_model(artifacts / "render_plan.json", RenderPlan)
            report = read_json_model(artifacts / "qc_report.json", QCReport)
            state.export_version += 1
            output = self.exporter.export(state.project_id, Path(plan.output_path), source, self.config.root / "output" / "final", state.export_version, report)
            self._record_file(state, stage, output, input_hash, artifact_type="final.mp4")
        else:
            raise ValueError(f"Unsupported stage: {stage}")

    def _save_model(self, state: ProjectState, stage: Stage, model: BaseModel, path: Path, input_hash: str) -> None:
        atomic_write_json(path, model)
        self._record_file(state, stage, path, input_hash)

    def _record_file(self, state: ProjectState, stage: Stage, path: Path, input_hash: str, artifact_type: str | None = None) -> None:
        digest = sha256_file(path)
        record = ArtifactRecord(
            artifact_id=f"{state.project_id}:{stage.value}", artifact_type=artifact_type or path.name,
            path=str(path.resolve()), sha256=digest, input_hash=input_hash, created_by_stage=stage.value,
        )
        self.manager.mark_completed(state, stage, digest, record)

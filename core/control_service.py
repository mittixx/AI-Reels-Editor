from __future__ import annotations

from pathlib import Path
from typing import Any

from core.asset_catalog import AssetCatalog
from core.config import RuntimeConfig
from core.dependency_graph import STAGE_ORDER, DependencyGraph
from core.doctor import Doctor
from core.errors import AppError, ValidationAppError
from core.io_utils import atomic_write_json, read_json_model
from core.pipeline import Pipeline
from core.project_manager import ProjectManager
from integrations.capcut_bridge import CapCutBridge
from models.artifacts import EditPlan, MediaManifest, QCReport, Transcript, VisualPlan
from models.contracts import ControlRequest, ControlResponse, ProjectState
from models.enums import Command, Mode, Profile, Stage, StageStatus


class ControlService:
    def __init__(
        self,
        config: RuntimeConfig,
        manager: ProjectManager,
        pipeline: Pipeline,
        doctor: Doctor,
        capcut: CapCutBridge,
    ) -> None:
        self.config = config
        self.manager = manager
        self.pipeline = pipeline
        self.doctor = doctor
        self.capcut = capcut
        self.graph = DependencyGraph()

    def execute(self, request: ControlRequest) -> ControlResponse:
        try:
            return self._dispatch(request)
        except AppError as exc:
            return ControlResponse(
                request_id=request.request_id, success=False, project_id=request.project_id,
                status="error", message=str(exc), errors=[{"code": exc.code, "message": str(exc)}],
                next_action="Исправьте указанную проблему и выполните RESUME" if request.project_id else None,
                requires_user_action=exc.requires_user_action,
            )
        except Exception as exc:
            return ControlResponse(
                request_id=request.request_id, success=False, project_id=request.project_id,
                status="error", message="Внутренняя ошибка. Подробности сохранены в logs.",
                errors=[{"code": type(exc).__name__, "message": str(exc)}],
                next_action="Выполните DOCTOR, затем STATUS и RESUME",
                requires_user_action=False,
            )

    def _dispatch(self, request: ControlRequest) -> ControlResponse:
        handlers = {
            Command.CREATE_REEL: self._create,
            Command.STATUS: self._status,
            Command.RESUME: self._resume,
            Command.REVISE: self._revise,
            Command.QC: self._qc,
            Command.EXPORT: self._export,
            Command.PACKAGE_CAPCUT: self._package_capcut,
            Command.LIST_PROJECTS: self._list_projects,
            Command.PROJECT_INFO: self._project_info,
            Command.CANCEL_SAFE: self._cancel,
            Command.DOCTOR: self._doctor,
            Command.IMPORT_ASSET: self._import_asset,
        }
        return handlers[request.command](request)

    def _create(self, request: ControlRequest) -> ControlResponse:
        if not request.source:
            raise ValidationAppError("Для CREATE_REEL требуется source")
        mode = request.mode or Mode(self.config.raw.get("default_mode", "fast"))
        profile = request.profile or Profile(self.config.raw.get("default_profile", "expert"))
        state = self.manager.create(Path(request.source), mode, profile)
        request.project_id = state.project_id
        stop_after = request.parameters.get("stop_after")
        stage = Stage(stop_after) if stop_after else None
        state = self.pipeline.run(state.project_id, request.instructions, stop_after=stage)
        return self._state_response(request, state, "Проект создан и pipeline выполнен")

    def _status(self, request: ControlRequest) -> ControlResponse:
        # Intentionally cheap: only project_state and its artifact manifest are read.
        state = self.manager.load(self._require_project(request))
        completed = sum(
            item.status in {StageStatus.COMPLETED, StageStatus.SKIPPED}
            for item in state.stages.values()
        )
        return self._state_response(
            request, state, f"Статус проекта: {state.status}",
            data={"completed_stages": completed, "total_stages": len(state.stages)},
        )

    def _resume(self, request: ControlRequest) -> ControlResponse:
        project_id = self._require_project(request)
        state = self.pipeline.run(project_id, request.instructions)
        return self._state_response(request, state, "Проект продолжен с первого незавершённого этапа")

    def _revise(self, request: ControlRequest) -> ControlResponse:
        project_id = self._require_project(request)
        scope = str(request.parameters.get("scope") or "")
        if not scope or not request.instructions:
            raise ValidationAppError("Для REVISE нужны scope и instructions")
        try:
            invalidated = self.graph.for_revision(scope)
        except ValueError as exc:
            raise ValidationAppError(str(exc)) from exc
        state = self.manager.load(project_id)
        self.manager.assert_source_unchanged(state)
        self.manager.invalidate(state, invalidated)
        state.pending_tasks.append(f"revision:{scope}:{request.instructions}")
        self.manager.save(state)
        state = self.pipeline.run(project_id, request.instructions)
        return self._state_response(
            request, state, f"Точечно пересчитана область {scope}",
            data={"invalidated_stages": [stage.value for stage in STAGE_ORDER if stage in invalidated]},
        )

    def _qc(self, request: ControlRequest) -> ControlResponse:
        project_id = request.project_id
        if project_id:
            state = self.manager.load(project_id)
            state.stages[Stage.QC.value].status = StageStatus.PENDING
            state.stages[Stage.EXPORT.value].status = StageStatus.PENDING
            self.manager.save(state)
            state = self.pipeline.run(project_id, stop_after=Stage.QC)
            report = read_json_model(
                self.manager.project_dir(project_id) / "artifacts" / "qc_report.json",
                QCReport,
            )
            return self._state_response(request, state, "QC выполнен", data={"qc": report.model_dump(mode="json")})
        target = request.parameters.get("target")
        if not target:
            raise ValidationAppError("Для standalone QC требуется target")
        report = self.pipeline.qc.inspect("standalone", Path(str(target)))
        return ControlResponse(
            request_id=request.request_id, success=report.passed, status="qc_passed" if report.passed else "qc_failed",
            message="QC выполнен", artifacts={"target": str(target)},
            errors=[] if report.passed else [{"code": "QC_FAILED", "message": "Technical QC не пройден"}],
            data={"qc": report.model_dump(mode="json")},
        )

    def _export(self, request: ControlRequest) -> ControlResponse:
        project_id = self._require_project(request)
        state = self.manager.load(project_id)
        state.stages[Stage.EXPORT.value].status = StageStatus.PENDING
        self.manager.save(state)
        state = self.pipeline.run(project_id)
        return self._state_response(request, state, "Экспорт выполнен")

    def _package_capcut(self, request: ControlRequest) -> ControlResponse:
        project_id = self._require_project(request)
        project_dir = self.manager.project_dir(project_id)
        artifacts = project_dir / "artifacts"
        transcript = read_json_model(artifacts / "transcript.json", Transcript)
        edit = read_json_model(artifacts / "edit_plan.json", EditPlan)
        visual = read_json_model(artifacts / "visual_plan.json", VisualPlan)
        manifest = read_json_model(artifacts / "media_manifest.json", MediaManifest)
        draft = project_dir / "renders" / "draft.mp4"
        if not draft.is_file():
            draft = project_dir / "working" / "base_edit.mp4"
        if not draft.is_file():
            raise ValidationAppError(
                "Нет draft.mp4 или base_edit.mp4 для CapCut package; сначала выполните RESUME"
            )
        package = self.capcut.package(
            project_dir,
            draft,
            transcript,
            edit,
            visual,
            manifest,
        )
        return ControlResponse(
            request_id=request.request_id, success=True, project_id=project_id, status="needs_finishing",
            current_stage="capcut_package", message="CapCut package создан",
            artifacts={"capcut_package": str(package)}, next_action="Выполнить только remaining_tasks.json",
            requires_user_action=True, data={"capcut_required": True},
        )

    def _list_projects(self, request: ControlRequest) -> ControlResponse:
        projects = self.manager.list_projects()
        return ControlResponse(
            request_id=request.request_id, success=True, status="ok", message=f"Найдено проектов: {len(projects)}",
            data={"projects": [
                {"project_id": item.project_id, "status": item.status, "current_stage": item.current_stage, "updated_at": item.updated_at.isoformat()}
                for item in projects
            ]},
        )

    def _project_info(self, request: ControlRequest) -> ControlResponse:
        state = self.manager.load(self._require_project(request))
        return self._state_response(request, state, "Информация о проекте", data={"state": state.model_dump(mode="json")})

    def _cancel(self, request: ControlRequest) -> ControlResponse:
        state = self.manager.load(self._require_project(request))
        state.cancelled = True
        state.status = "cancelled"
        state.last_action = "cancel_safe"
        self.manager.save(state)
        return self._state_response(request, state, "Безопасная отмена сохранена")

    def _doctor(self, request: ControlRequest) -> ControlResponse:
        data = self.doctor.run()
        return ControlResponse(
            request_id=request.request_id, success=data["ok"], status="healthy" if data["ok"] else "needs_setup",
            message="Диагностика завершена", data=data,
            next_action=None if data["ok"] else "Исправьте MISSING/MISCONFIGURED пункты",
            requires_user_action=not data["ok"],
        )

    def _import_asset(self, request: ControlRequest) -> ControlResponse:
        project_id = self._require_project(request)
        raw_path = request.parameters.get("file")
        kind = str(request.parameters.get("kind") or "")
        if not raw_path or kind not in {"video", "image"}:
            raise ValidationAppError("Для IMPORT_ASSET нужны --file и --kind video|image")
        state = self.manager.load(project_id)
        asset = AssetCatalog(self.config).import_asset(
            self.manager.project_dir(project_id), Path(str(raw_path)), kind, state.user_assets
        )
        if not any(existing.id == asset.id for existing in state.user_assets):
            state.user_assets.append(asset)
        manifest_path = self.manager.project_dir(project_id) / "artifacts" / "media_manifest.json"
        if manifest_path.is_file():
            manifest = read_json_model(manifest_path, MediaManifest)
            existing = {item.id: item for item in manifest.assets}
            existing[asset.id] = asset
            atomic_write_json(manifest_path, MediaManifest(project_id=project_id, assets=list(existing.values())))
        # Asset availability changes the visual/media/render dependency branch only.
        self.manager.invalidate(state, self.graph.downstream({Stage.VISUAL_PLAN}) | {Stage.VISUAL_PLAN})
        self.manager.save(state)
        return self._state_response(
            request, state, "Media asset импортирован",
            data={"asset": asset.model_dump(mode="json"), "asset_id": asset.id},
        )

    @staticmethod
    def _require_project(request: ControlRequest) -> str:
        if not request.project_id:
            raise ValidationAppError(f"Для {request.command} требуется project_id")
        return request.project_id

    @staticmethod
    def _state_response(request: ControlRequest, state: ProjectState, message: str, data: dict[str, Any] | None = None) -> ControlResponse:
        artifacts = {key: item.path for key, item in state.artifacts.items() if item.valid}
        errors = [state.last_error] if state.last_error else []
        if state.status == "cancelled" and not errors:
            errors = [{"code": "CANCELLED", "message": "Операция безопасно отменена"}]
        return ControlResponse(
            request_id=request.request_id, success=state.status not in {"failed", "cancelled"},
            project_id=state.project_id, status=state.status, current_stage=str(state.current_stage),
            message=message, artifacts=artifacts, warnings=list(state.pending_tasks),
            errors=errors,
            next_action="Готово" if state.status == "completed" else "Выполните STATUS или RESUME",
            requires_user_action=state.status == "failed", data=data or {},
        )

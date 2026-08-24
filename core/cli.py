from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Never

from pydantic import ValidationError

from core.config import load_config
from core.factory import build_control_service
from core.logging_setup import configure_logging
from models.contracts import ControlRequest, ControlResponse
from models.enums import Command, ExitCode, Mode, Profile


class ArgumentParsingError(ValueError):
    pass


class ControlArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ArgumentParsingError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = ControlArgumentParser(
        prog="AI_Reels_Editor",
        description="AI Reels Editor v1.3.4.1 — локальный orchestrator монтажа вертикальных видео",
    )
    parser.add_argument("--version", action="version", version="AI_Reels_Editor 1.3.4.1")
    sub = parser.add_subparsers(dest="top_command", required=True)

    doctor = sub.add_parser("doctor", help="Проверить окружение и зависимости")
    doctor.add_argument("--json", action="store_true")

    control = sub.add_parser("control", help="Work Control CLI/JSON contract")
    control_sub = control.add_subparsers(dest="control_command", required=True)
    _add_create(control_sub.add_parser("create", help="Создать и запустить Reel"))
    _add_project(control_sub.add_parser("status", help="Дешёвый статус"))
    _add_project(control_sub.add_parser("resume", help="Продолжить pipeline"))
    revise = control_sub.add_parser("revise", help="Точечная revision")
    revise.add_argument("project_id")
    revise.add_argument("--scope", required=True, choices=["hook", "speech", "edit", "broll", "visual", "motion", "subtitles", "render"])
    revise.add_argument("--instruction", required=True)
    revise.add_argument("--json", action="store_true")
    asset = control_sub.add_parser("import-asset", help="Импортировать локальный media asset в проект")
    asset.add_argument("project_id")
    asset.add_argument("--file", required=True)
    asset.add_argument("--kind", required=True, choices=["video", "image"])
    asset.add_argument("--json", action="store_true")
    for name in ("qc", "export", "package-capcut", "info", "cancel"):
        _add_project(control_sub.add_parser(name, help=f"Control command: {name}"))
    listing = control_sub.add_parser("list", help="Список проектов")
    listing.add_argument("--json", action="store_true")
    control_doctor = control_sub.add_parser("doctor", help="Диагностика через ControlService")
    control_doctor.add_argument("--json", action="store_true")

    new = sub.add_parser("new", help="Создать новый Reel")
    _add_create(new, positional_source=True)
    _add_project(sub.add_parser("status", help="Статус проекта"))
    _add_project(sub.add_parser("resume", help="Продолжить проект"))
    _add_project(sub.add_parser("render", help="Продолжить проект до render/export"))
    analyze = sub.add_parser("analyze", help="Создать проект и выполнить анализ до transcription")
    _add_create(analyze, positional_source=True)
    qc = sub.add_parser("qc", help="QC проекта или отдельного файла")
    qc.add_argument("target")
    qc.add_argument("--json", action="store_true")
    _add_project(sub.add_parser("package-capcut", help="Создать finishing package"))
    return parser


def _add_create(parser: argparse.ArgumentParser, positional_source: bool = False) -> None:
    if positional_source:
        parser.add_argument("source")
    else:
        parser.add_argument("--source", required=True)
    parser.add_argument("--mode", choices=[item.value for item in Mode], default="fast")
    parser.add_argument("--profile", choices=[item.value for item in Profile], default="expert")
    parser.add_argument("--instruction")
    parser.add_argument("--json", action="store_true")


def _add_project(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("project_id")
    parser.add_argument("--json", action="store_true")


def namespace_to_request(args: argparse.Namespace) -> ControlRequest:
    top = args.top_command
    if top == "doctor":
        return ControlRequest(command=Command.DOCTOR)
    if top == "control":
        mapping = {
            "create": Command.CREATE_REEL,
            "status": Command.STATUS,
            "resume": Command.RESUME,
            "revise": Command.REVISE,
            "qc": Command.QC,
            "export": Command.EXPORT,
            "package-capcut": Command.PACKAGE_CAPCUT,
            "list": Command.LIST_PROJECTS,
            "info": Command.PROJECT_INFO,
            "cancel": Command.CANCEL_SAFE,
            "doctor": Command.DOCTOR,
            "import-asset": Command.IMPORT_ASSET,
        }
        parameters: dict[str, Any] = {}
        if args.control_command == "revise":
            parameters["scope"] = args.scope
        if args.control_command == "import-asset":
            parameters.update({"file": args.file, "kind": args.kind})
        return ControlRequest(
            command=mapping[args.control_command],
            project_id=getattr(args, "project_id", None),
            source=getattr(args, "source", None),
            mode=getattr(args, "mode", None),
            profile=getattr(args, "profile", None),
            instructions=getattr(args, "instruction", None),
            parameters=parameters,
        )
    if top in {"new", "analyze"}:
        parameters = {"stop_after": "transcription"} if top == "analyze" else {}
        return ControlRequest(
            command=Command.CREATE_REEL, source=args.source, mode=args.mode, profile=args.profile,
            instructions=args.instruction, parameters=parameters,
        )
    if top in {"status", "resume", "render", "package-capcut"}:
        command = {
            "status": Command.STATUS, "resume": Command.RESUME, "render": Command.RESUME,
            "package-capcut": Command.PACKAGE_CAPCUT,
        }[top]
        return ControlRequest(command=command, project_id=args.project_id)
    if top == "qc":
        if str(args.target).startswith("reel_"):
            return ControlRequest(command=Command.QC, project_id=args.target)
        return ControlRequest(command=Command.QC, parameters={"target": args.target})
    raise ValueError(f"Unknown command: {top}")


def main(argv: list[str] | None = None) -> int:
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    machine_mode = "--json" in effective_argv
    try:
        parser = build_parser()
        args = parser.parse_args(effective_argv)
        machine_mode = machine_mode or bool(getattr(args, "json", False))
        config = load_config()
        configure_logging(config.root / "logs", config.log_level, machine_mode)
        service = build_control_service(config)
        request = namespace_to_request(args)
        response = service.execute(request)
    except (ValidationError, ValueError) as exc:
        response = ControlResponse(
            request_id="invalid", success=False, status="error", message=str(exc),
            errors=[{"code": "INVALID_REQUEST", "message": str(exc)}],
        )
    except Exception as exc:
        response = ControlResponse(
            request_id="startup", success=False, status="error",
            message="Не удалось запустить приложение. Выполните setup_windows.ps1.",
            errors=[{"code": type(exc).__name__, "message": str(exc)}], requires_user_action=True,
        )
    if machine_mode:
        sys.stdout.write(json.dumps(response.model_dump(mode="json"), ensure_ascii=False) + "\n")
    else:
        _print_human(response)
    return _exit_code(response)


def _print_human(response: ControlResponse) -> None:
    print(f"Статус: {response.status}")
    if response.project_id:
        print(f"Проект: {response.project_id}")
    if response.current_stage:
        print(f"Текущий этап: {response.current_stage}")
    print(response.message)
    for warning in response.warnings:
        print(f"Предупреждение: {warning}")
    for error in response.errors:
        print(f"Ошибка [{error.get('code', 'ERROR')}]: {error.get('message', '')}")
    if response.next_action:
        print(f"Следующий шаг: {response.next_action}")
    for name, path in response.artifacts.items():
        print(f"{name}: {path}")


def _exit_code(response: ControlResponse) -> int:
    if response.status == "cancelled":
        return ExitCode.CANCELLED
    if response.status == "qc_failed":
        return ExitCode.QC_FAILED
    if response.success:
        return ExitCode.SUCCESS
    raw_code = response.errors[0].get("code") if response.errors else None
    code = str(raw_code) if raw_code is not None else ""
    mapping = {
        "VALIDATION_ERROR": ExitCode.INVALID_REQUEST,
        "INVALID_REQUEST": ExitCode.INVALID_REQUEST,
        "PROJECT_NOT_FOUND": ExitCode.PROJECT_NOT_FOUND,
        "DEPENDENCY_MISSING": ExitCode.DEPENDENCY_MISSING,
        "AI_UNAVAILABLE": ExitCode.AI_UNAVAILABLE,
        "RENDER_FAILED": ExitCode.RENDER_FAILED,
        "QC_FAILED": ExitCode.QC_FAILED,
        "CANCELLED": ExitCode.CANCELLED,
    }
    return int(mapping.get(code, ExitCode.USER_ACTION_REQUIRED if response.requires_user_action else ExitCode.GENERAL_ERROR))

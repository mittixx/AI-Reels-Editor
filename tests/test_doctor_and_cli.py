from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import cli
from core.doctor import Doctor
from core.paths import ProjectPaths
from models.contracts import ControlResponse


def test_doctor_returns_structured_checks(runtime_config, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = ProjectPaths(runtime_config.root)
    paths.ensure()
    monkeypatch.setattr("shutil.which", lambda name: f"/bin/{name}")
    result = Doctor(runtime_config, paths).run()
    assert result["schema_version"] == "1.3"
    assert all("status" in item for item in result["checks"])


def test_doctor_missing_node_and_renderers(runtime_config, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = ProjectPaths(runtime_config.root)
    paths.ensure()
    monkeypatch.setattr("shutil.which", lambda name: None if name in {"node", "npm.cmd", "npx"} else f"/bin/{name}")
    result = Doctor(runtime_config, paths).run()
    statuses = {item["name"]: item["status"] for item in result["checks"]}
    assert statuses["Node.js"] == "MISSING"
    assert statuses["HyperFrames dependencies"] == "MISSING"
    assert statuses["Motion Canvas dependencies"] == "MISSING"


def test_cli_machine_output_is_single_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], runtime_config) -> None:
    class Service:
        def execute(self, request):
            return ControlResponse(request_id=request.request_id, success=True, status="healthy", message="ok")

    monkeypatch.setattr(cli, "load_config", lambda: runtime_config)
    monkeypatch.setattr(cli, "build_control_service", lambda config: Service())
    monkeypatch.setattr(cli, "configure_logging", lambda *args, **kwargs: None)
    code = cli.main(["doctor", "--json"])
    captured = capsys.readouterr()
    assert code == 0
    assert json.loads(captured.out)["status"] == "healthy"
    assert captured.out.count("\n") == 1


def test_cli_exit_code_invalid_request() -> None:
    response = ControlResponse(
        request_id="x", success=False, status="error", message="bad",
        errors=[{"code": "INVALID_REQUEST", "message": "bad"}],
    )
    assert cli._exit_code(response) == 2


def test_help_contains_control() -> None:
    help_text = cli.build_parser().format_help()
    assert "control" in help_text
    assert "doctor" in help_text


def test_windows_scripts_present() -> None:
    root = Path(__file__).resolve().parents[1]
    setup = (root / "setup_windows.ps1").read_text(encoding="utf-8")
    launcher = (root / "start_editor.bat").read_text(encoding="utf-8")
    assert "python -m venv" in setup
    assert "Assert-ExitCode" in setup
    assert "npm ci" in setup
    assert "npm install" not in setup
    assert "main.py doctor" in setup
    assert ".venv\\Scripts\\python.exe" in launcher


def test_node_packages_are_pinned() -> None:
    root = Path(__file__).resolve().parents[1]
    hyperframes = json.loads((root / "node_tools" / "hyperframes" / "package.json").read_text())
    motion = json.loads((root / "node_tools" / "motion_canvas" / "package.json").read_text())
    assert hyperframes["dependencies"]["hyperframes"] == "0.8.12"
    assert motion["dependencies"]["@motion-canvas/core"] == "3.17.2"
    assert "remotion" not in json.dumps({"hyperframes": hyperframes, "motion": motion}).lower()

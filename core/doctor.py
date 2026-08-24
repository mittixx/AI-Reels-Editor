from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from core.config import RuntimeConfig
from core.paths import ProjectPaths
from integrations.hyperframes import HyperFramesIntegration
from integrations.process import run_process
from models.enums import CheckStatus


class Doctor:
    def __init__(self, config: RuntimeConfig, paths: ProjectPaths) -> None:
        self.config = config
        self.paths = paths

    def run(self) -> dict[str, Any]:
        checks: list[dict[str, str]] = []
        checks.append(self._check("Python 3.11+", sys.version_info >= (3, 11), sys.version.split()[0]))
        for label, binary, required in (
            ("FFmpeg", self.config.ffmpeg_bin, True),
            ("ffprobe", self.config.ffprobe_bin, True),
            ("Node.js", "node", True),
            ("npm.cmd", "npm.cmd", True),
        ):
            found = shutil.which(binary)
            checks.append(self._check(label, bool(found), found or "РЅРµ РЅР°Р№РґРµРЅ", required))
        hf_project = self.paths.node_tools / "hyperframes"
        mc_project = self.paths.node_tools / "motion_canvas"
        checks.append(self._check(
            "HyperFrames dependencies", (hf_project / "node_modules" / "hyperframes").exists(),
            "npm ci РІ node_tools/hyperframes", True,
        ))
        checks.append(self._check(
            "Motion Canvas dependencies", (mc_project / "node_modules" / "@motion-canvas").exists(),
            "npm ci РІ node_tools/motion_canvas", True,
        ))
        hf_browser, hf_browser_detail = self._hyperframes_browser(hf_project)
        checks.append(self._check(
            "HyperFrames browser",
            hf_browser,
            hf_browser_detail,
            True,
        ))
        motion_browser, motion_browser_detail = self._motion_canvas_browser(mc_project)
        checks.append(self._check(
            "Motion Canvas browser",
            motion_browser,
            motion_browser_detail,
            True,
        ))
        ai_ok = self.config.ai_provider == "mock" or (
            self.config.ai_provider == "openai" and bool(self.config.openai_api_key) and importlib.util.find_spec("openai") is not None
        )
        checks.append(self._check("AI provider", ai_ok, self.config.ai_provider, True))
        if self.config.transcription_provider == "mock":
            checks.append(self._check("Transcription provider", True, "mock", True))
        else:
            package_ok = importlib.util.find_spec("faster_whisper") is not None
            checks.append(self._check(
                "faster-whisper package",
                package_ok,
                "Python package СѓСЃС‚Р°РЅРѕРІР»РµРЅ" if package_ok else "pip install -r requirements.txt",
                True,
            ))
            model_ok, model_detail = self._whisper_model_ready(self.config.whisper_model)
            checks.append(self._check(
                "faster-whisper model",
                model_ok,
                model_detail,
                False,
            ))
        for folder in (self.paths.projects, self.paths.input, self.paths.output, self.paths.logs):
            writable = folder.is_dir() and self._writable(folder)
            checks.append(self._check(f"Write: {folder.name}", writable, str(folder), True))
        required_failed = any(item["status"] in {CheckStatus.MISSING, CheckStatus.MISCONFIGURED} for item in checks)
        return {"schema_version": "1.3", "ok": not required_failed, "checks": checks}

    @staticmethod
    def _check(name: str, ok: bool, details: str, required: bool = False) -> dict[str, str]:
        status = CheckStatus.AVAILABLE if ok else CheckStatus.MISSING if required else CheckStatus.OPTIONAL_MISSING
        return {"name": name, "status": status.value, "details": details}

    @staticmethod
    def _writable(folder: Path) -> bool:
        try:
            test = folder / ".write_test"
            test.touch(exist_ok=False)
            test.unlink()
            return True
        except OSError:
            return False

    def _hyperframes_browser(self, project: Path) -> tuple[bool, str]:
        cli = project / "node_modules" / ".bin" / "hyperframes"
        executable = HyperFramesIntegration(self.config.hyperframes_bin, local_cli=cli)._installed_cli()
        if executable is None:
            return False, "Р’С‹РїРѕР»РЅРёС‚Рµ npm ci Рё hyperframes browser ensure"
        try:
            result = run_process(
                [str(executable), "browser", "path"],
                cwd=project,
                timeout=30,
                check=False,
                env={
                    "HYPERFRAMES_NO_TELEMETRY": "1",
                    "HYPERFRAMES_NO_UPDATE_CHECK": "1",
                },
            )
        except Exception as exc:
            return False, f"browser path РЅРµРґРѕСЃС‚СѓРїРµРЅ: {type(exc).__name__}"
        path = Path(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else None
        ok = result.returncode == 0 and path is not None and path.is_file()
        return ok, str(path) if ok else "Р’С‹РїРѕР»РЅРёС‚Рµ hyperframes browser ensure"

    @staticmethod
    def _motion_canvas_browser(project: Path) -> tuple[bool, str]:
        if not (project / "node_modules" / "playwright").is_dir():
            return False, "Р’С‹РїРѕР»РЅРёС‚Рµ npm ci Рё playwright install chromium"
        try:
            result = run_process(
                [
                    "node",
                    "-e",
                    "process.stdout.write(require('playwright').chromium.executablePath())",
                ],
                cwd=project,
                timeout=30,
                check=False,
            )
        except Exception as exc:
            return False, f"Chromium path РЅРµРґРѕСЃС‚СѓРїРµРЅ: {type(exc).__name__}"
        path = Path(result.stdout.strip()) if result.stdout.strip() else None
        ok = result.returncode == 0 and path is not None and path.is_file()
        return ok, str(path) if ok else "Р’С‹РїРѕР»РЅРёС‚Рµ .\\node_modules\\.bin\\playwright.cmd install chromium"

    @staticmethod
    def _whisper_model_ready(model: str) -> tuple[bool, str]:
        explicit = Path(model).expanduser()
        if explicit.is_dir():
            return True, str(explicit.resolve())
        cache_root = Path(
            os.getenv("HF_HOME", str(Path.home() / ".cache" / "huggingface"))
        ) / "hub"
        model_dir = cache_root / f"models--Systran--faster-whisper-{model}"
        snapshots = model_dir / "snapshots"
        ready = snapshots.is_dir() and any(path.is_dir() for path in snapshots.iterdir())
        if ready:
            return True, str(model_dir)
        return (
            False,
            f"РњРѕРґРµР»СЊ {model} РЅРµ Р·Р°РєСЌС€РёСЂРѕРІР°РЅР°; РїРµСЂРІС‹Р№ Reel СЃРєР°С‡Р°РµС‚ РµС‘ Рё РїРѕС‚СЂРµР±СѓРµС‚ РёРЅС‚РµСЂРЅРµС‚",
        )

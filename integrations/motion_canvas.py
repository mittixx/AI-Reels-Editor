from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from core.errors import DependencyError, RenderError
from core.io_utils import atomic_write_json, sha256_file
from integrations.process import ProcessResult, run_process
from models.artifacts import MotionItem


@dataclass(frozen=True)
class MotionRenderJob:
    process: ProcessResult
    job_id: str
    expected_output: Path
    started_at_ns: int
    input_path: Path | None = None


class MotionCanvasIntegration:
    version = "3.17.2"

    def __init__(
        self,
        npm_bin: str = "npm.cmd",
        timeout: int = 1800,
        stability_samples: int = 3,
        stability_interval: float = 0.2,
    ) -> None:
        self.npm_bin = npm_bin
        self.timeout = timeout
        self.stability_samples = stability_samples
        self.stability_interval = stability_interval

    def available(self, node_project: Path) -> bool:
        executable = Path(self.npm_bin)
        return (executable.is_file() or shutil.which(self.npm_bin) is not None) and (node_project / "package.json").is_file()

    def render(self, node_project: Path, item: MotionItem, job_dir: Path) -> MotionRenderJob:
        if not self.available(node_project):
            raise DependencyError("Motion Canvas project/npm РЅРµРґРѕСЃС‚СѓРїРЅС‹")
        job_dir.mkdir(parents=True, exist_ok=True)
        safe_item_id = re.sub(r"[^A-Za-z0-9_-]", "_", item.id).strip("_") or "motion"
        job_id = f"{safe_item_id}-{uuid4().hex}"
        input_path = job_dir / f"{job_id}.json"
        expected_output = job_dir / "outputs" / f"{job_id}.mp4"
        atomic_write_json(input_path, {
            "schema_version": "1.3",
            "job_id": job_id,
            "component": item.component,
            "duration": item.duration,
            "data": item.data,
            "preset": item.preset,
        })
        expected_output.parent.mkdir(parents=True, exist_ok=True)
        started_at_ns = time.time_ns()
        process = run_process([
            self.npm_bin,
            "run",
            "render:asset",
            "--",
            "--input",
            str(input_path),
            "--output",
            str(expected_output),
            "--job-id",
            job_id,
        ], cwd=node_project, timeout=self.timeout, check=False)
        return MotionRenderJob(process, job_id, expected_output, started_at_ns, input_path)

    def validate_result(self, job: MotionRenderJob, output: Path) -> dict:
        result = job.process
        if result.returncode != 0:
            raise RenderError(
                f"Motion Canvas render failed: {(result.stderr or result.stdout)[-1200:]}"
            )
        expected = job.expected_output
        if not expected.is_file() or expected.stat().st_size == 0:
            raise RenderError(f"Motion Canvas РЅРµ СЃРѕР·РґР°Р» РѕР¶РёРґР°РµРјС‹Р№ output job {job.job_id}")
        if expected.stat().st_mtime_ns < job.started_at_ns - 1_000_000_000:
            raise RenderError(f"Motion Canvas output СѓСЃС‚Р°СЂРµР» РґР»СЏ job {job.job_id}")
        payload: dict = {}
        try:
            json_line = next(
                line for line in reversed(result.stdout.splitlines()) if line.strip().startswith("{")
            )
            payload = json.loads(json_line)
        except (StopIteration, json.JSONDecodeError) as exc:
            raise RenderError("Motion Canvas РЅРµ РІРµСЂРЅСѓР» job identity JSON") from exc
        if payload.get("job_id") != job.job_id:
            raise RenderError("Motion Canvas job identity РЅРµ СЃРѕРІРїР°РґР°РµС‚")
        if payload.get("success") is not True:
            raise RenderError("Motion Canvas РЅРµ РїРѕРґС‚РІРµСЂРґРёР» СѓСЃРїРµС€РЅРѕРµ Р·Р°РІРµСЂС€РµРЅРёРµ export")
        reported_output = Path(str(payload.get("output", ""))).resolve()
        if reported_output != expected.resolve():
            raise RenderError("Motion Canvas СЃРѕРѕР±С‰РёР» РЅРµРѕР¶РёРґР°РЅРЅС‹Р№ output path")
        probe = run_process([
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "json",
            str(expected),
        ], timeout=60, check=False)
        if probe.returncode != 0:
            raise RenderError("Motion Canvas output РЅРµ РїСЂРѕС€С‘Р» ffprobe validation")
        self._wait_for_stable_output(expected, job.job_id)
        if not self._decode_check(expected):
            raise RenderError("Motion Canvas output РЅРµ РїСЂРѕС€С‘Р» FFmpeg decode-check")
        expected_hash = sha256_file(expected)
        output.parent.mkdir(parents=True, exist_ok=True)
        os.replace(expected, output)
        if not output.is_file() or sha256_file(output) != expected_hash:
            raise RenderError("Motion Canvas output РїРѕРІСЂРµР¶РґС‘РЅ РїСЂРё promotion")
        self.cleanup_job(job, remove_expected=False)
        return {**payload, "output": str(output.resolve()), "sha256": expected_hash}

    @staticmethod
    def cleanup_job(job: MotionRenderJob, remove_expected: bool = True) -> None:
        if remove_expected:
            job.expected_output.unlink(missing_ok=True)
        if job.input_path:
            job.input_path.unlink(missing_ok=True)
        try:
            job.expected_output.parent.rmdir()
        except OSError:
            pass

    def _wait_for_stable_output(self, path: Path, job_id: str) -> None:
        previous: tuple[int, int] | None = None
        stable = 0
        for _ in range(self.stability_samples + 2):
            if not path.is_file() or path.stat().st_size <= 0:
                raise RenderError(f"Motion Canvas output РёСЃС‡РµР· РІРѕ РІСЂРµРјСЏ validation: {job_id}")
            current = (path.stat().st_size, path.stat().st_mtime_ns)
            stable = stable + 1 if current == previous else 0
            if stable >= self.stability_samples - 1:
                return
            previous = current
            time.sleep(self.stability_interval)
        raise RenderError(f"Motion Canvas output РЅРµ СЃС‚Р°Р±РёР»РёР·РёСЂРѕРІР°Р»СЃСЏ: {job_id}")

    @staticmethod
    def _decode_check(path: Path) -> bool:
        result = run_process([
            "ffmpeg", "-v", "error", "-xerror", "-err_detect", "explode",
            "-i", str(path), "-map", "0", "-f", "null", "-",
        ], timeout=180, check=False)
        return result.returncode == 0

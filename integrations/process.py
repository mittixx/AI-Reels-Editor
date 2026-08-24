from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from core.errors import DependencyError, ExternalProcessError


@dataclass(frozen=True)
class ProcessResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def run_process(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = 300,
    check: bool = True,
    env: Mapping[str, str] | None = None,
) -> ProcessResult:
    safe_args = [str(item) for item in args]
    launch_args = safe_args
    # cmd/bat files are not CreateProcess executables. Use a narrow cmd.exe wrapper
    # only for that file type; all ordinary processes remain shell-free.
    if os.name == "nt" and Path(safe_args[0]).suffix.lower() in {".cmd", ".bat"}:
        command_line = subprocess.list2cmdline(safe_args)
        launch_args = [os.environ.get("ComSpec", "cmd.exe"), "/d", "/s", "/c", command_line]
    try:
        result = subprocess.run(
            launch_args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            check=False,
            env={**os.environ, **env} if env is not None else None,
        )
    except FileNotFoundError as exc:
        raise DependencyError(f"Команда не найдена: {safe_args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ExternalProcessError(f"Команда превысила лимит {timeout} секунд: {safe_args[0]}") from exc
    process_result = ProcessResult(tuple(safe_args), result.returncode, result.stdout, result.stderr)
    if check and result.returncode != 0:
        tail = (result.stderr or result.stdout)[-1500:].strip()
        raise ExternalProcessError(f"Команда {safe_args[0]} завершилась с кодом {result.returncode}: {tail}")
    return process_result

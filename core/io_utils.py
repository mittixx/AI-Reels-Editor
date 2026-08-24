from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from core.errors import ValidationAppError

T = TypeVar("T", bound=BaseModel)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    if not path.is_file():
        raise ValidationAppError(f"Файл не найден: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_data(data: Any) -> str:
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def atomic_write_json(path: Path, data: BaseModel | dict[str, Any] | list[Any]) -> None:
    if isinstance(data, BaseModel):
        payload = data.model_dump(mode="json")
    else:
        payload = data
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    json.loads(serialized)
    atomic_write_text(path, serialized + "\n")


def read_json_model(path: Path, model: type[T]) -> T:
    if not path.is_file():
        raise ValidationAppError(f"JSON-файл не найден: {path}")
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise ValidationAppError(f"Некорректный JSON {path.name}: {exc}") from exc


def resolve_under(root: Path, candidate: Path) -> Path:
    root_resolved = root.resolve()
    resolved = candidate.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ValidationAppError(f"Путь выходит за разрешённую папку: {candidate}")
    return resolved

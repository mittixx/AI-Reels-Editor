from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RenderResult:
    success: bool
    output: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class BaseRenderer(ABC):
    name = "base"

    @abstractmethod
    def available(self) -> bool: ...

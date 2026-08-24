from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    root: Path

    @property
    def projects(self) -> Path:
        return self.root / "projects"

    @property
    def input(self) -> Path:
        return self.root / "input"

    @property
    def output(self) -> Path:
        return self.root / "output"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def node_tools(self) -> Path:
        return self.root / "node_tools"

    @classmethod
    def discover(cls) -> ProjectPaths:
        return cls(Path(__file__).resolve().parents[1])

    def ensure(self) -> None:
        for path in (
            self.projects,
            self.input,
            self.output / "drafts",
            self.output / "final",
            self.root / "generated" / "motion",
            self.root / "temp",
            self.logs,
        ):
            path.mkdir(parents=True, exist_ok=True)

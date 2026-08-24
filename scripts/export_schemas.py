from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def main() -> None:
    from models.artifacts import EditPlan, MotionPlan, RenderPlan, Transcript, VisualPlan
    from models.contracts import ControlRequest, ControlResponse, ProjectState

    target = ROOT / "schemas"
    target.mkdir(parents=True, exist_ok=True)
    models: list[type[BaseModel]] = [
        ControlRequest,
        ControlResponse,
        ProjectState,
        Transcript,
        EditPlan,
        VisualPlan,
        MotionPlan,
        RenderPlan,
    ]
    for model in models:
        path = target / f"{model.__name__}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

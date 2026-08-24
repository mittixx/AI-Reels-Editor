from __future__ import annotations

import shutil
from pathlib import Path

from core.io_utils import atomic_write_json, atomic_write_text
from core.subtitle_builder import SubtitleBuilder
from models.artifacts import EditPlan, MediaManifest, Transcript, VisualPlan


class CapCutBridge:
    def package(
        self,
        project_dir: Path,
        draft: Path,
        transcript: Transcript,
        edit_plan: EditPlan,
        visual_plan: VisualPlan,
        manifest: MediaManifest,
    ) -> Path:
        package = project_dir / "capcut_package"
        assets = package / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        if draft.is_file():
            shutil.copy2(draft, package / "draft.mp4")
        cues = SubtitleBuilder().build(transcript, edit_plan)
        SubtitleBuilder().write_srt(package / "subtitles.srt", cues)
        atomic_write_json(package / "visual_plan.json", visual_plan)
        atomic_write_json(package / "media_manifest.json", manifest)
        remaining = [
            item.model_dump(mode="json")
            for item in visual_plan.items
            if item.intent in {"complex_capcut_effect", "beauty_adjustment", "manual_visual_fix"}
        ]
        atomic_write_json(package / "remaining_tasks.json", {
            "schema_version": "1.3", "project_id": visual_plan.project_id, "tasks": remaining,
        })
        atomic_write_text(package / "computer_use_instructions.md", (
            "# CapCut finishing\n\n"
            "1. Откройте `draft.mp4` в новом проекте CapCut.\n"
            "2. Импортируйте `subtitles.srt`.\n"
            "3. Выполните только задачи из `remaining_tasks.json`.\n"
            "4. Не заменяйте и не удаляйте исходное пользовательское видео.\n"
            "5. Перед финальным экспортом проверьте смысл, субтитры и громкость.\n"
        ))
        return package

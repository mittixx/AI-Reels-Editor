from __future__ import annotations

import shutil
from pathlib import Path

from core.errors import QCError, ValidationAppError
from core.io_utils import sha256_file
from models.artifacts import QCReport


class Exporter:
    def export(self, project_id: str, draft: Path, source: Path, output_dir: Path, version: int, qc: QCReport) -> Path:
        if not qc.export_allowed:
            raise QCError("QC содержит critical ошибки; экспорт заблокирован")
        if not draft.is_file():
            raise ValidationAppError("Draft для экспорта не найден")
        if draft.resolve() == source.resolve():
            raise ValidationAppError("Нельзя перезаписывать исходное видео")
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"{project_id}_v{version:03d}.mp4"
        if output.resolve() == source.resolve():
            raise ValidationAppError("Export path совпадает с source")
        if output.exists() and sha256_file(output) == sha256_file(draft):
            return output
        shutil.copy2(draft, output)
        if not output.is_file() or output.stat().st_size == 0:
            raise ValidationAppError("Экспорт не создан")
        return output

# QA Report — AI Reels Editor v1.3.2

Дата: 2026-08-24. OpenAI API не вызывался, ключ не запрашивался.

## Исправления v1.3.2

- B-roll, screen recording, screenshot и logo требуют ровно один локальный `asset_id`; он должен
  находиться в `media_manifest.json`, существовать, быть непустым, соответствовать ожидаемому типу
  и SHA-256 manifest. Некорректная операция отклоняется до запуска HyperFrames.
- Motion Canvas больше не подставляет Callout при отсутствующем/некорректном `motion_input.json`.
  Job валидируется до запуска browser, использует уникальные ID/output, ждёт стабилизации размера и
  mtime, выполняет FFmpeg decode-check и только затем публикует output.
- HyperFrames рендерит в уникальный temporary job output. Старый `draft.mp4` не принимается как
  результат нового job: проверяются identity, expected path, freshness, стабилизация, FFmpeg decode
  и SHA-256; публикация в draft выполняется атомарно.
- Zoom и transition получили явный timing/animation contract: `start`, `end`, `duration`, easing,
  CSS keyframes и layer/keyframe metadata в `composition.json`.

## Regression coverage

- B-roll без asset отклоняется на validation, а не через `RenderError` внутри master render.
- Реальный B-roll asset → manifest → render plan → HyperFrames composition → lint.
- Invalid/missing Motion input fail-fast до browser.
- Partial Motion output не публикуется после decode failure; wrong output path отклоняется.
- Sequential Motion jobs остаются изолированными.
- False-success HyperFrames CLI не может принять заранее существующий старый draft.
- Отдельные zoom и transition timing/keyframe tests.
- Сохранены предыдущие проверки cache/invalidation, QC, exit codes, transcription и setup fail-fast.

## REAL PASSED

- `pytest -q`: **126 passed**.
- Python compile/import checks: passed.
- `ruff check .`: passed.
- `mypy core models integrations renderers`: passed, **47 source files**.
- FFmpeg/ffprobe integration и corrupted-video QC: passed.
- Motion Canvas TypeScript `tsc --noEmit`: passed.
- Motion Canvas invalid/missing input Node-process contracts: passed.
- HyperFrames CLI lint base template: passed.
- Реальный B-roll asset validation → HyperFrames composition/lint: passed.

## MOCK PASSED

- Mock end-to-end pipeline, resume/cache/selective invalidation.
- ControlService, JSON/exit-code и doctor contracts.
- HyperFrames stale-draft false-success regression.
- Motion stale/partial/wrong-path/sequential-job regressions.
- Zoom/transition generated timing and keyframe contracts.

## SKIPPED

- **HyperFrames real browser render:** SKIPPED. Doctor подтвердил отсутствие HyperFrames browser runtime.
- **Motion Canvas real browser render:** SKIPPED. Doctor подтвердил отсутствие Playwright Chromium.
- **faster-whisper real inference:** SKIPPED. Локальная модель `small` не загружена.
- **OpenAI semantic inference:** SKIPPED по требованию задачи.
- **Windows PowerShell setup execution:** SKIPPED в Linux QA-среде без `pwsh`; fail-fast покрыт тестами.

## Известные ограничения

- Browser-based MP4 master render нужно повторить на целевой Windows-машине после успешного
  `setup_windows.ps1` и статусов `AVAILABLE` для обоих browser checks в doctor.
- Motion Canvas wrapper зависит от текущего UI/export поведения upstream; при изменении UI он
  завершается fail-fast и не регистрирует непроверенный asset.

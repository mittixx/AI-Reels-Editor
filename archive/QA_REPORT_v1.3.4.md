# QA Report — AI Reels Editor v1.3.4

Дата: 2026-08-24. OpenAI API не вызывался, ключ не запрашивался.

## Production readiness: NO — NOT PRODUCTION READY

Release gate не пройден: текущая среда — Linux, а не Windows; browser runtime отсутствует для
HyperFrames и Motion Canvas. Поэтому настоящий Windows Motion Canvas → HyperFrames → QC render
не мог быть выполнен. Этот ZIP является диагностическим build для запуска release-gate на целевой
Windows машине после установки браузеров.

## REAL PASSED

- FFmpeg/ffprobe: реальная генерация MP4, probe и строгий полный decode-check.
- Реальный повреждённый MP4 блокируется QC и export.
- Реальный полностью чёрный H.264/AAC 1080×1920 MP4 распознан как `BLACK_OUTPUT` critical;
  `export_allowed=false`.
- Реальный valid B-roll MP4 прошёл import/manifest/render-plan/HyperFrames composition и CLI lint.
- HyperFrames local CLI lint base template и Motion Canvas `tsc --noEmit` прошли.
- Compile/import: passed. Ruff: passed. mypy: passed (48 source files). Node syntax: passed.

## MOCK PASSED

- `pytest -q`: **145 passed**.
- HyperFrames Windows selection: `.cmd` приоритетен на Windows, extensionless executable — на Linux/macOS.
- Motion Windows launcher contract: narrow `cmd.exe /d /s /c`, без `shell:true`; Python process wrapper
  использует полный `.cmd` executable, когда он настроен.
- Revalidation непосредственно перед master render: SHA, ffprobe, type, image/video decode,
  Motion MP4 integrity и B-roll duration/offset.
- Corrupt PNG, changed Motion MP4 SHA, insufficient B-roll duration, zoom across cut,
  black-output QC, schema synchronization, cache/invalidation и mock E2E.

## SKIPPED

- **Windows `.cmd` subprocess:** 1 pytest test skipped, потому что `cmd.exe` отсутствует на Linux.
  На Windows он реально создаёт и запускает temporary `.cmd`, затем запускает его через
  MotionCanvasIntegration и требует exit code 0.
- **HyperFrames Windows real render:** SKIPPED — не Windows; doctor сообщает HyperFrames browser MISSING.
- **Motion Canvas Windows real render:** SKIPPED — не Windows; Playwright Chromium отсутствует.
- **Combined Motion Canvas → HyperFrames → QC Windows render:** SKIPPED по тем же двум blockers.
- **Zoom frame/snapshot validation:** SKIPPED — нет HyperFrames browser runtime.
- faster-whisper model inference: SKIPPED; `small` не скачивалась по условиям QA.

## FAILED

- Нет упавших unit/integration/static checks.
- Не выполнен обязательный Windows browser release gate; поэтому production readiness = **NO**.

## Fixed in v1.3.4

- HyperFrames `.cmd` launcher selection и Doctor используют одну логику.
- Motion Canvas Python/Node Windows process launch hardened against incorrect `.cmd`/quoting behaviour.
- Media assets повторно валидируются именно перед master render с configured FFMPEG_BIN/FFPROBE_BIN.
- Corrupt images, modified motion assets и insufficient B-roll duration останавливают render заранее.
- Zoom через edit cut отклоняется в fallback вместо ложного continuous source interval.
- Nearly full black coverage (>=95%) является critical QC issue.
- JSON schemas regenerated; asset workflow documented as `analyze → import-asset → resume`.

## Known limitations / required release step

На целевой Windows 10/11 выполните `setup_windows.ps1`, затем реальный short technical pipeline:
Motion Canvas MP4 → HyperFrames master MP4 → ffprobe + full decode QC, а также отдельный
HyperFrames render. Только успешное прохождение всех трёх browser renders позволяет изменить
production readiness на YES.

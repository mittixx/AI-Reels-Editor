# QA Report — AI Reels Editor v1.3.1

Дата проверки: 2026-08-24. OpenAI API не вызывался.

## Исправленные дефекты

- HyperFrames composition теперь материализует B-roll, screen recording, screenshot, logo,
  hook/text/CTA overlays, zoom, transitions и все Motion Canvas assets из `render_plan.json`.
- Motion outputs включаются в `media_manifest.json` до построения master render plan.
- Каждый Motion Canvas job имеет уникальные `job_id`, input и expected output; проверяются точный
  path, identity JSON, freshness, размер, ffprobe и SHA-256. Общая output-папка не сканируется.
- Windows setup проверяет `$LASTEXITCODE` после каждого обязательного процесса и завершается с
  кодом 1 при первом failure; success-message находится только после успешного doctor.
- `VisualItem.intent` — строгий `VisualIntent` enum, экспортированный в JSON Schema и отражённый в
  AI prompt. Edit plan проверяет ranges, overlaps, source boundaries и точную итоговую duration.
- Stage input hash вычисляется до cache hit и включает upstream SHA, source, settings, prompts,
  presets и component/pipeline versions; mismatch выборочно инвалидирует stage и downstream.
- QC выполняет строгий полный FFmpeg decode (`-xerror -err_detect explode`) и не скрывает ошибки
  blackdetect. Critical issue блокирует export.
- Исправлены exit codes 8/9, machine-readable argparse errors, пустая transcription, trailing
  silence coverage, partial-cut subtitles, doctor package/model distinction и документация.
- Node setup использует `npm ci`; небезопасный runtime package fallback отсутствует;
  `HYPERFRAMES_NO_UPDATE_CHECK=1` передаётся в doctor/lint/check/render.

## Regression tests

Добавлены проверки intent allowlist и экспортированной schema, edit overlaps/duration/boundaries,
invalid transcription/trailing silence, partial subtitle cuts, decode/blackdetect failures,
exit-code/JSON contracts, B-roll и Motion manifest/master flow, всех поддерживаемых operations,
двух последовательных Motion jobs без stale output, stage ordering, setup fail-fast, HyperFrames
environment, whisper model cache, duplicate manifest IDs и render timeline boundaries. Отдельно
проверяются prompt-driven selective invalidation и блокировка semantic pipeline при неполной
transcription.

## REAL PASSED

- Full pytest: **117 passed**.
- Python compile/import checks: passed.
- Ruff: passed без замечаний.
- mypy: passed, 46 source files.
- FFmpeg/ffprobe: реальная генерация, probe и полный decode валидного 1080×1920 H.264/AAC MP4.
- Corrupted-video QC: реальный повреждённый MP4 отклонён; export заблокирован.
- Node lockfiles: `npm ci` выполнен для HyperFrames 0.8.12 и Motion Canvas 3.17.2.
- Motion Canvas TypeScript: реальный `tsc --noEmit` passed.
- HyperFrames: реальный CLI lint base template passed без errors/warnings.
- B-roll + prepared Motion MP4 → manifest → render plan → generated HyperFrames master
  composition → real HyperFrames lint: passed; выполнены operations `broll` и `motion`.
- Machine CLI: invalid/unknown argparse input дал один валидный JSON, пустой stderr и exit code 2.

## MOCK PASSED

- 13 ControlService/CLI/doctor contract tests.
- 19 mock pipeline, resume, cache/recovery и selective invalidation tests.
- 21 targeted v1.3.1 regression tests.
- Mock end-to-end pipeline through render/QC/export using deterministic fake renderers.
- Sequential Motion Canvas job identity/stale-output regression с двумя отдельными outputs.
- Setup failure regression — статическая/contract-проверка fail-fast PowerShell flow.
- B-roll и Motion asset → manifest → HyperFrames master composition assertions; все supported
  automatic operations проверены на generated HTML/composition metadata.

## SKIPPED / недоступно

- **HyperFrames real render:** SKIPPED. Установленный CLI и lint доступны, но browser runtime
  отсутствует; sandbox запрещает создание `/root/.cache/hyperframes`, необходимого CLI.
- **Motion Canvas real render:** SKIPPED. Dependencies/typecheck доступны, но Playwright Chromium
  download вернул повреждённый 0-MiB ZIP (`End of central directory record signature not found`).
- **Windows setup real execution/failure injection:** SKIPPED, в Linux-среде отсутствует `pwsh`.
  Fail-fast behavior покрыт regression test, но не обозначается как real Windows run.
- **faster-whisper real inference:** SKIPPED, модель `small` не закэширована; её внешнюю загрузку не
  подменяли mock-проверкой.
- **OpenAI semantic inference:** SKIPPED по прямому требованию; API и ключ не использовались.

## Итог browser renders

HyperFrames real render: **SKIPPED**. Motion Canvas real render: **SKIPPED**. Реальный master
composition/lint с B-roll и prepared Motion asset: **PASSED**. Полный browser-based MP4 render
следует повторить после успешной установки browser runtimes на целевой Windows-машине.

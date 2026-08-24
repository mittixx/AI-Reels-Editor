# QA Report — AI Reels Editor v1.3.3

Дата проверки: 2026-08-24. OpenAI API не вызывался, ключ не запрашивался.

## Исправления v1.3.3

- Motion Canvas Vite launcher теперь использует явный cross-platform contract: на Windows
  `cmd.exe /d /s /c` для `npm.cmd`, на Linux/macOS прямой `npm`, в обоих случаях `shell:false`.
  Запуск fail-fast, а stdout/stderr дочернего процесса сохраняются в диагностике.
- Media-backed B-roll/screen recording до HyperFrames проверяются по existence, file type, SHA-256,
  ffprobe, duration, video stream, dimensions/FPS и полному FFmpeg decode-check. Corrupt MP4 с
  совпадающим SHA отклоняется до master render.
- Добавлен deterministic input contract `control import-asset PROJECT_ID --file FILE --kind video|image`.
  Asset получает SHA-derived stable ID, project-local copy без sanitized-name collision, metadata
  catalog и запись в manifest; VisualPlanner видит и может выбрать только imported IDs.
- `simple_zoom` теперь получает `source_media_start/end` из mapping output timeline → исходный source
  через `EditPlan.keep_ranges`; HyperFrames video layer получает `data-media-start/end` и использует
  оригинальный source, а не кадр с начала base edit.
- faster-whisper больше не выставляет coverage по наличию segment. Используется provider `duration`;
  `duration_after_vad` только metadata. Конец речи с нормальной тишиной допускается при полном
  provider duration, short/missing processing блокирует semantic pipeline.
- Успешные HyperFrames/Motion Canvas jobs удаляют exact temporary identity/input/output artifacts;
  failure cleanup не затрагивает published draft. Сохранены unique job outputs, decode/SHA promotion,
  QC, cache/selective invalidation, exit codes 8/9 и shell-free subprocess policy.
- Устаревший `QA_REPORT_RU.md` v1.3.1 архивирован в `archive/QA_REPORT_v1.3.1.md`.

## Regression tests added/updated

- Windows npm.cmd launcher contract.
- Corrupt B-roll with correct manifest SHA rejected before master render.
- Missing B-roll asset rejected before renderer invocation.
- Source-offset zoom contract for a keep-range beginning at source 10 s.
- Stable asset import/catalog/manifest and VisualPlanner allowlist tests.
- Imported asset mutation changes the visual/media/render cache input hash.
- faster-whisper full coverage, trailing silence, actual truncation and empty transcription.
- Existing Motion Canvas partial/stale/wrong-path and HyperFrames stale draft regressions retained.

## REAL PASSED

- Python compile/import checks passed.
- Full `pytest -q`: **137 passed**.
- Ruff: `All checks passed!`.
- mypy: `Success: no issues found in 48 source files`.
- Motion Canvas TypeScript `tsc --noEmit` and Node syntax checks passed.
- FFmpeg/ffprobe: real generated H.264 MP4 passed probe and strict decode-check.
- Corrupted-video QC: a real truncated MP4 was rejected and export was blocked.
- Real valid B-roll MP4: import/manifest/render-plan/HyperFrames composition and real HyperFrames CLI
  lint passed. This is a real asset-validation/composition test, not a browser render.
- HyperFrames local CLI lint of its base template passed.

## MOCK PASSED

- ControlService, machine JSON/exit-code, cache/selective invalidation and mock E2E pipeline tests.
- Windows process-launch regression verifies exact `cmd.exe /d /s /c`/`npm.cmd` contract and
  Linux direct-npm contract without `shell:true`.
- Motion Canvas stale/partial/wrong-output regressions; HyperFrames stale-draft regression.
- B-roll missing-asset and corrupt-asset pre-render validation regressions.
- Zoom/transition timing contracts and non-zero source-offset zoom regression.
- Asset catalog/VisualPlanner allowlist/manifest tests and faster-whisper coverage regressions.

## SKIPPED

- **Motion Canvas Windows real render:** SKIPPED. This is a Linux environment, not Windows; the
  Windows launcher has contract-level regression coverage only. Motion Canvas browser render is
  also unavailable because Playwright Chromium download repeatedly returns a corrupt 0-MiB ZIP
  (`End of central directory record signature not found`).
- **HyperFrames real browser render:** SKIPPED. The installed CLI cannot create
  `/root/.cache/hyperframes` in this sandbox and no browser runtime is available; `browser ensure`
  therefore cannot complete.
- **B-roll real browser integration render:** SKIPPED for the same HyperFrames browser limitation.
  The real B-roll → manifest → generated master composition → CLI lint test did pass.
- **Zoom real browser/frame snapshot:** SKIPPED for the same HyperFrames browser limitation. The
  generated source-offset animation contract is covered by regression test.
- faster-whisper real inference: SKIPPED; package is installed but the `small` model is not cached,
  and its external first download was not performed.

## Known limitations

- Browser-backed MP4 rendering must be re-run on the target Windows machine after successful
  HyperFrames browser and Playwright Chromium installation.
- The Motion Canvas wrapper depends on upstream Vite/editor UI selectors; failures are fail-fast
  and retain diagnostic stdout/stderr rather than accepting stale output.

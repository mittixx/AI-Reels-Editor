# Changelog

## 1.3.4 — 2026-08-24

### Fixed

- Windows launchers prefer executable `.cmd` shims where required and invoke them via narrow `cmd.exe /d /s /c` handling;
- manifest media is revalidated immediately before master render with configured FFmpeg/ffprobe, SHA, decode, type, image and duration checks;
- zoom intervals crossing edit cuts are rejected rather than mapping across deleted source time;
- nearly fully black output is a critical QC failure;
- schemas, version markers and the documented analyze → import asset → resume workflow are synchronized.

## 1.3.2 — 2026-08-24

### Fixed

- media-required visual operations are rejected before master render when their local manifest asset is absent, changed or invalid;
- Motion Canvas no longer falls back to Callout on missing/invalid input and verifies stable, decoded expected outputs;
- HyperFrames renders to a unique job output and atomically publishes only a fresh, decoded, hashed result;
- zoom and transition operations now generate explicit timing, easing and keyframe contracts.

## 1.3.1 — 2026-08-24

### Fixed

- HyperFrames исполняет поддерживаемые B-roll, screenshot, logo, zoom/overlay и Motion Canvas operations;
- Motion Canvas jobs используют уникальные output paths и строгую проверку identity/freshness;
- Windows setup стал fail-fast и использует lockfile-driven `npm ci`;
- Visual intent и edit/transcription contracts получили строгую валидацию;
- cache hashes вычисляются до cache hit и учитывают релевантные версии/dependencies;
- QC выполняет реальный decode, не скрывает blackdetect errors и блокирует export;
- исправлены machine JSON/exit codes, subtitle partial cuts и transcription coverage;
- добавлены regression и integration tests для исправленных дефектов.

## 1.3.0 — 2026-08-24

### Added

- единый Work Control CLI/JSON contract;
- state machine, recovery, SHA-256 cache и selective invalidation;
- OpenAI/Mock AI providers и faster-whisper abstraction;
- FFmpeg technical processing/QC;
- HyperFrames master compositor 0.8.12;
- Motion Canvas asset generator 3.17.2;
- CapCut finishing package;
- Windows setup/launcher, doctor, документация и tests.

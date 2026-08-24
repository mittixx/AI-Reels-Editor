# Work Control v1.3.4

## Назначение

ChatGPT Work — control interface, а локальный AI Reels Editor — execution engine. Все команды
CLI превращаются в `ControlRequest`, выполняются одним `ControlService` и возвращают
`ControlResponse`. Обязательного HTTP-сервера нет.

## ControlRequest

```json
{
  "request_id": "uuid",
  "command": "CREATE_REEL",
  "project_id": null,
  "source": "input/video.mp4",
  "mode": "fast",
  "profile": "expert",
  "instructions": "Динамично, без перегруженных эффектов",
  "parameters": {},
  "created_at": "2026-08-24T10:00:00Z"
}
```

## ControlResponse

```json
{
  "request_id": "uuid",
  "success": true,
  "project_id": "reel_20260824_100000_a1b2c3",
  "status": "completed",
  "current_stage": "export",
  "message": "Проект создан и pipeline выполнен",
  "artifacts": {"final.mp4": "..."},
  "warnings": [],
  "errors": [],
  "next_action": "Готово",
  "requires_user_action": false,
  "data": {}
}
```

В режиме `--json` stdout содержит ровно один валидный JSON, включая ошибки разбора неизвестных или
невалидных CLI-аргументов. Обычный argparse help/error text в machine mode не выводится. Logs
пишутся отдельно.

## Команды

| Intent | CLI | Поведение |
|---|---|---|
| CREATE_REEL | `control create --source FILE --mode fast --profile expert --json` | Новый project и pipeline |
| IMPORT_ASSET | `control import-asset ID --file FILE --kind video --json` | Проверить, скопировать и зарегистрировать локальный asset; вернуть stable `asset_id` |
| STATUS | `control status ID --json` | Только state/manifest; без AI, media scan и render |
| RESUME | `control resume ID --json` | Проверка source/hash/artifacts, продолжение с первого незавершённого stage |
| REVISE | `control revise ID --scope SCOPE --instruction TEXT --json` | Только зависимые stages |
| QC | `control qc ID --json` | Повторный technical QC |
| EXPORT | `control export ID --json` | Версионный export, только после QC |
| PACKAGE_CAPCUT | `control package-capcut ID --json` | Finishing package без выдуманного CapCut API |
| LIST_PROJECTS | `control list --json` | Краткий список project state |
| PROJECT_INFO | `control info ID --json` | Полный structured state |
| CANCEL_SAFE | `control cancel ID --json` | Сохранить безопасную отмену |
| DOCTOR | `control doctor --json` или `doctor --json` | Проверка окружения |

## Stable exit codes

| Код | Значение |
|---:|---|
| 0 | SUCCESS |
| 1 | GENERAL_ERROR |
| 2 | INVALID_REQUEST |
| 3 | PROJECT_NOT_FOUND |
| 4 | DEPENDENCY_MISSING |
| 5 | AI_UNAVAILABLE |
| 6 | RENDER_FAILED |
| 7 | USER_ACTION_REQUIRED |
| 8 | QC_FAILED |
| 9 | CANCELLED |

## State, cache и recovery

Каждый project хранит `project_state.json`, stage input/output hashes, artifact hashes и status.
Перед проверкой `completed` pipeline вычисляет актуальный input hash из source, upstream artifacts,
config/preset version, prompt version и pipeline/component version. Cache hit разрешён только при
совпадении input hash и SHA-256 существующего artifact. Несовпадение выборочно переводит stage и
downstream в `pending`; после аварии `in_progress` также возвращается в `pending`.

## Selective revision

- `hook` — speech/edit/visual и downstream, но не source/audio/transcript;
- `broll`, `visual`, `subtitles` — visual и downstream;
- `motion` — motion assets и master render/QC/export;
- `render` — render plan и downstream.

Исходники и сохранённая расшифровка не пересчитываются без изменения их inputs.

## Пользовательские B-roll assets

Не передавайте путь или `asset_id` через свободный `--instruction`. Реальный workflow:
`analyze SOURCE` → `IMPORT_ASSET` в созданный project →
`RESUME`. Для video
импорт выполняет existence/type/SHA-256/ffprobe/duration/video-stream/dimensions/FPS и полный
FFmpeg decode-check, копирует файл в project и возвращает стабильный ID. ID записывается в
`project_state.json` и, если manifest уже существует, сразу в `media_manifest.json`; при следующем
pipeline run manifest пересобирается с ним снова. VisualPlanner получает только этот catalog и
media-backed intent без существующего `asset_id` не является исполнимым B-roll.

## QC и export

QC выполняет реальный FFmpeg decode и blackdetect, а также проверяет existence, duration,
1080×1920, FPS, codecs и audio. Ошибка decode/blackdetect — `critical`; любая `critical` issue
устанавливает `export_allowed=false`, команда возвращает код 8 и exporter не создаёт final MP4.
Безопасно отменённый проект возвращает статус `cancelled` и код 9.

## CapCut package

Папка содержит `draft.mp4`, `subtitles.srt`, plans, manifest, assets, `remaining_tasks.json` и
инструкцию. `remaining_tasks.json` содержит только то, что renderer не выполнил программно.

## Диагностика

Последовательность: `STATUS → DOCTOR → logs/ai_reels_editor.log → RESUME`. Source нельзя менять
внутри существующего project. Если source изменился, создайте новый Reel.

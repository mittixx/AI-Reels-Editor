# AI Reels Editor v1.3.4

Готовый локальный AI-монтажёр вертикальных видео для Windows 10/11. Он анализирует исходник,
создаёт расшифровку и structured edit/visual plans, готовит motion graphics, собирает master
timeline, проверяет MP4 и сохраняет versioned final export.

## Как устроено — простыми словами

- **Python** управляет всеми этапами, state, cache, resume и ошибками.
- **FFmpeg / ffprobe** читают характеристики видео, готовят base edit и выполняют technical QC.
- **AI** принимает только смысловые и творческие решения.
- **HyperFrames 0.8.12** — единственная master timeline: A-roll, voice, subtitles, hook, B-roll,
  overlays и Motion Canvas assets.
- **Motion Canvas 3.17.2** создаёт только отдельные motion graphics MP4.
- **CapCut** — finishing/fallback package, а не основной renderer.
- **Remotion не используется**.

Source всегда read-only: программа проверяет SHA-256, не удаляет и не перезаписывает оригинал.

## 1. Что установить

1. Windows 10/11.
2. Python 3.11 или новее: <https://www.python.org/downloads/windows/>.
3. FFmpeg + ffprobe: <https://ffmpeg.org/download.html>. Папка `bin` должна быть в `PATH`.
4. Node.js 22 или новее: <https://nodejs.org/>.
5. PyCharm — только для разработки и просмотра: <https://www.jetbrains.com/pycharm/>.

HyperFrames и Motion Canvas вручную с Python соединять не нужно: wrappers и Node subprojects
уже находятся в проекте. Официальные справки: [HyperFrames CLI](https://hyperframes.heygen.com/packages/cli),
[Motion Canvas quickstart](https://motioncanvas.io/docs/quickstart/),
[Motion Canvas FFmpeg exporter](https://motioncanvas.io/docs/rendering/video).

## 2. Распаковка и автоматическая настройка

Распакуйте ZIP, откройте PowerShell **в папке `AI_Reels_Editor`** и выполните:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup_windows.ps1
```

Скрипт безопасно создаёт `.venv`, устанавливает закреплённые Python/Node dependencies и Chromium
для Motion Canvas. Он не меняет системные настройки и не ставит отсутствующие Python/FFmpeg/Node
самостоятельно — вместо этого показывает понятную инструкцию.

Ручной вариант:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cd node_tools\hyperframes
npm ci
.\node_modules\.bin\hyperframes.cmd browser ensure
cd ..\motion_canvas
npm ci
.\node_modules\.bin\playwright.cmd install chromium
cd ..\..
python main.py doctor
```

## 3. `.env`, AI и расшифровка

`setup_windows.ps1` копирует `.env.example` в `.env`. Реальный ключ хранится только в `.env`.
Файл `.env` исключён из Git и ZIP.

Без платного API безопасный режим:

```dotenv
AI_PROVIDER=mock
TRANSCRIPTION_PROVIDER=faster_whisper
```

Он реально расшифровывает видео локально, но semantic plans создаёт консервативный MockProvider
без смысловых вырезаний. Для настоящего AI-анализа:

```dotenv
AI_PROVIDER=openai
OPENAI_API_KEY=ваш_ключ
OPENAI_MODEL=gpt-5.6-luna
```

Adapter использует официальный OpenAI Responses API и Pydantic Structured Outputs. Ключ нельзя
писать в код, сообщения, logs или ZIP. API-запросы платные; запускайте их только осознанно.

Local transcription по умолчанию — `faster-whisper`, модель `small`, CPU/int8. Doctor отдельно
показывает наличие Python package и наличие модели в локальном cache. Установленный package ещё не
означает готовность модели: первый реальный запуск явно предупреждает о возможном скачивании модели.
Для чистого технического mock-теста укажите `TRANSCRIPTION_PROVIDER=mock`.

## 4. Проверка окружения

```powershell
.\.venv\Scripts\python.exe main.py doctor
.\.venv\Scripts\python.exe main.py doctor --json
```

Статусы: `AVAILABLE`, `MISSING`, `MISCONFIGURED`, `OPTIONAL_MISSING`.

## 5. Первый Reel

Положите видео, например, сюда:

```text
input\video_01.mp4
```

FAST + EXPERT:

```powershell
.\.venv\Scripts\python.exe main.py control create --source "input\video_01.mp4" --mode fast --profile expert --json
```

DETAIL + SELLING:

```powershell
.\.venv\Scripts\python.exe main.py control create --source "input\video_01.mp4" --mode detail --profile selling --instruction "Сильный честный hook, без перегруженных эффектов" --json
```

Ответ содержит `project_id`. Сохраните его для status/resume/revise.

### Добавление собственного B-roll

Путь к медиа не передаётся через `--instruction`. Сначала импортируйте файл в нужный project:

```powershell
.\.venv\Scripts\python.exe main.py control import-asset PROJECT_ID --file "input\broll.mp4" --kind video --json
```

Ответ вернёт стабильный `asset_id`. Импорт проверяет SHA-256, ffprobe, duration, video stream,
dimensions/FPS и полный FFmpeg decode-check, затем записывает asset в project catalog и
`media_manifest.json`. VisualPlanner видит только импортированные IDs и не может выбрать
несуществующий B-roll.

## 6. FAST, DETAIL и profiles

- `fast`: один compact semantic flow, presets, минимум AI calls.
- `detail`: более глубокий hook/structure/B-roll/motion анализ.
- `expert`: чисто, профессионально, умеренный B-roll.
- `selling`: problem → value → proof → CTA.
- `lifestyle`: естественный ритм, атмосфера, мягкие переходы.

## 7. Status, resume и recovery

```powershell
python main.py control status PROJECT_ID --json
python main.py control resume PROJECT_ID --json
```

`STATUS` не вызывает AI, FFmpeg или renderer и не читает большие media. `RESUME` сначала вычисляет
актуальный input hash из source, upstream artifacts, config/preset, prompt и component versions,
затем разрешает cache hit. При несовпадении сбрасываются только stage и его downstream.

## 8. Точечная правка

```powershell
python main.py control revise PROJECT_ID --scope broll --instruction "Сделать меньше B-roll" --json
python main.py control revise PROJECT_ID --scope hook --instruction "Сделать hook короче" --json
```

Revision B-roll не запускает ffprobe, audio analysis или transcription. Dependency graph сбрасывает
только visual plan и downstream render/QC/export.

## 9. HyperFrames render

Pipeline создаёт per-project composition, выполняет bounded flow:

```text
prepare → lint → check → render → output validation
```

При первой технической ошибке composition один раз регенерируется из validated structured plans.
Второй failure сохраняется в state; бесконечных retries нет.

## 10. Motion Canvas

`motion_plan.json` создаётся всегда как контракт, но `required=false`, если motion graphics не нужны.
При `required=true` Python передаёт каждому компоненту structured job с уникальными `job_id` и
ожидаемым output path. Адаптер принимает только свежий, валидный MP4 именно текущего job; общий
output предыдущего задания не используется. Готовые assets сначала входят в `media_manifest.json`,
а затем — в HyperFrames master timeline. Доступны:
AnimatedStat, AnimatedCounter, Comparison, ProcessFlow, Timeline, Quote, CodeHighlight,
FeatureList, ProductFeature, BeforeAfter, Callout, Chart, Diagram.

Официальный Motion Canvas 3.17.2 не документирует стабильный headless render CLI. Поэтому включён
локальный Playwright wrapper: он запускает официальный Vite editor/exporter в headless Chromium и
забирает MP4. Если upstream UI изменится, stage честно остановится и сможет быть продолжен после
обновления wrapper; HyperFrames master timeline не подменяется.

## 11. QC и output

```powershell
python main.py control qc PROJECT_ID --json
python main.py control export PROJECT_ID --json
```

QC выполняет полный FFmpeg decode, затем проверяет duration, 1080×1920, FPS, H.264, audio и
black frames. Ошибка decode или blackdetect становится critical и блокирует export.
Critical issue блокирует export. Final files находятся в `output\final\` и получают версии
`_v001`, `_v002` и далее.

## 12. CapCut fallback

```powershell
python main.py control package-capcut PROJECT_ID --json
```

Создаётся `projects\PROJECT_ID\capcut_package\` с draft, SRT, plans, manifest, assets и
`remaining_tasks.json`. CapCut API не выдумывается. Автоматическое управление GUI, публикация,
замена музыки и платная генерация без отдельного разрешения не выполняются.

## 13. Запуск через `start_editor.bat`

После настройки дважды щёлкните `start_editor.bat`. Откроется PowerShell/cmd уже в папке проекта
с примерами команд. PyCharm для обычного Reel не нужен.

## 14. Work Control

Для постоянного ChatGPT Work-чата сначала достаточно прочитать:

- `WORK_CONTROL_CHEATSHEET.md`;
- `WORK_CONTROL.md`.

Исходный код нужен только для development/debugging. Machine interface — CLI + JSON; обязательного
локального HTTP-сервера нет.

## 15. Где лежат данные

- `input/` — пользователь кладёт исходники;
- `projects/PROJECT_ID/project_state.json` — state;
- `projects/PROJECT_ID/artifacts/` — validated JSON;
- `projects/PROJECT_ID/working/` — производные рабочие media;
- `projects/PROJECT_ID/renders/draft.mp4` — master draft;
- `output/final/` — versioned final MP4;
- `logs/` — structured diagnostics без secrets.

## 16. Troubleshooting

Всегда начинайте так:

```powershell
python main.py control status PROJECT_ID --json
python main.py doctor --json
```

Затем смотрите `logs\ai_reels_editor.log` и выполняйте `resume`.

- **FFmpeg not found** — установите FFmpeg и перезапустите PowerShell.
- **node/npm not found или Node < 22** — установите Node.js 22+.
- **HyperFrames dependencies missing** — `cd node_tools\hyperframes; npm ci`.
- **Motion Canvas dependencies/browser missing** — `cd node_tools\motion_canvas; npm ci; .\node_modules\.bin\playwright.cmd install chromium`.
- **OPENAI_API_KEY missing** — добавьте ключ в локальный `.env` или верните `AI_PROVIDER=mock`.
- **Source hash changed** — не продолжайте старый project; создайте новый.
- **QC failed** — исправьте critical issue, не обходите export block.

## 17. Tests для разработчика

```powershell
python -m pip install -r requirements-dev.txt
python -m compileall .
pytest
ruff check .
mypy core models integrations renderers
cd node_tools\motion_canvas
npm run typecheck
```

External integration tests автоматически skip, если соответствующая программа/Node dependency
не установлена. Unit tests не требуют реального OpenAI API и не делают платных вызовов.

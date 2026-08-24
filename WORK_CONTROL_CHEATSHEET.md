# AI Reels Editor — Work Control cheatsheet

Обычная работа идёт только через CLI/JSON и `ControlService`.

```powershell
# Проверка
.\.venv\Scripts\python.exe main.py doctor --json

# Новый Reel
.\.venv\Scripts\python.exe main.py control create --source "input\video.mp4" --mode fast --profile expert --json

# Статус / продолжение
.\.venv\Scripts\python.exe main.py control status PROJECT_ID --json
.\.venv\Scripts\python.exe main.py control resume PROJECT_ID --json

# Точечная правка
.\.venv\Scripts\python.exe main.py control revise PROJECT_ID --scope broll --instruction "Сделать меньше B-roll" --json

# QC / export / CapCut
.\.venv\Scripts\python.exe main.py control qc PROJECT_ID --json
.\.venv\Scripts\python.exe main.py control export PROJECT_ID --json
.\.venv\Scripts\python.exe main.py control package-capcut PROJECT_ID --json
```

Scopes: `hook`, `speech`, `edit`, `broll`, `visual`, `motion`, `subtitles`, `render`.

Machine mode всегда возвращает один JSON. Critical QC возвращает код 8, `CANCELLED` — код 9.

При проблеме: `STATUS → DOCTOR → logs/ai_reels_editor.log → RESUME`.
Не запускай новый проект вместо `RESUME`, если source не изменился.

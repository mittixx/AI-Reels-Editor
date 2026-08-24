@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Run setup_windows.ps1 first.
  pause
  exit /b 4
)
echo AI Reels Editor v1.3.4
echo.
echo Examples:
echo   .venv\Scripts\python.exe main.py doctor
echo   .venv\Scripts\python.exe main.py control list
echo   .venv\Scripts\python.exe main.py control create --source "input\video.mp4" --mode fast --profile expert
echo.
cmd /k

@echo off
setlocal

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" run_fullstack.py
) else (
  python run_fullstack.py
)

endlocal
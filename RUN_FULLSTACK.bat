@echo off
REM AutoSaham Backend & Frontend Launcher
REM =====================================
REM Run both backend and frontend together

setlocal enabledelayedexpansion

echo.
echo ================================================================
echo    AutoSaham Full Stack - Backend + Frontend
echo ================================================================
echo.

cd /d "%~dp0"

REM Set environment variables
set API_HOST=127.0.0.1
set API_PORT=8000
set MARKET_SYMBOLS=BBCA,USIM,KLBF,ASII,UNVR
set PYTHONUNBUFFERED=1

echo [1/2] Starting Backend (FastAPI on :8000)...
echo.

REM Start backend in new window
start "AutoSaham Backend" cmd /k "python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload"

REM Wait for backend to start
timeout /t 3 /nobreak

echo [2/2] Starting Frontend (Vite Dev Server on :5173)...
echo.

cd frontend
call npm run dev

pause

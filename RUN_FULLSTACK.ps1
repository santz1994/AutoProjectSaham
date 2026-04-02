# AutoSaham Full Stack Launcher (PowerShell)
# ==========================================
# Run both Backend + Frontend in separate processes

Write-Host "`n" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "         AutoSaham Full Stack - Backend + Frontend             " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "`n"

# Get script directory
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# Set environment variables
$env:API_HOST = "127.0.0.1"
$env:API_PORT = "8000"
$env:MARKET_SYMBOLS = "BBCA,USIM,KLBF,ASII,UNVR"
$env:PYTHONUNBUFFERED = "1"

# Backend configuration
Write-Host "[SETUP] Environment Configuration:" -ForegroundColor Yellow
Write-Host "   API Host: $($env:API_HOST):$($env:API_PORT)" -ForegroundColor Green
Write-Host "   Market Symbols: $($env:MARKET_SYMBOLS)" -ForegroundColor Green
Write-Host "`n"

# Start Backend
Write-Host "[1/2] Starting Backend (FastAPI Server)..." -ForegroundColor Cyan
Write-Host "────────────────────────────────────────────" -ForegroundColor Cyan
Write-Host "Backend URL: http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "UI URL: http://127.0.0.1:8000/ui" -ForegroundColor Green
Write-Host "Health: http://127.0.0.1:8000/health" -ForegroundColor Green
Write-Host "`n"

$BackendProcess = Start-Process powershell -ArgumentList "-NoExit", "-Command", "
    cd '$ProjectRoot'
    Write-Host 'Starting FastAPI backend...' -ForegroundColor Yellow
    python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload
" -PassThru

Write-Host "[OK] Backend process started (PID: $($BackendProcess.Id))" -ForegroundColor Green
Write-Host "[WAIT] Please wait 3 seconds for backend to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

# Start Frontend
Write-Host "`n[2/2] Starting Frontend (Vite Dev Server)..." -ForegroundColor Cyan
Write-Host "────────────────────────────────────────────" -ForegroundColor Cyan
Write-Host "Frontend URL: http://127.0.0.1:5173" -ForegroundColor Green
Write-Host "`n"

$FrontendProcess = Start-Process powershell -ArgumentList "-NoExit", "-Command", "
    cd '$ProjectRoot\frontend'
    Write-Host 'Starting Vite dev server...' -ForegroundColor Yellow
    npm run dev
" -PassThru

Write-Host "[OK] Frontend process started (PID: $($FrontendProcess.Id))" -ForegroundColor Green

Write-Host "`n" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "                  FULL STACK RUNNING                           " -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host "`n"
Write-Host "Backend:  http://127.0.0.1:8000       (FastAPI)" -ForegroundColor Green
Write-Host "Frontend: http://127.0.0.1:5173       (Vite Dev)" -ForegroundColor Green
Write-Host "UI:       http://127.0.0.1:8000/ui   (Prod Build)" -ForegroundColor Green
Write-Host "`n"
Write-Host "Backend PID:  $($BackendProcess.Id)" -ForegroundColor Yellow
Write-Host "Frontend PID: $($FrontendProcess.Id)" -ForegroundColor Yellow
Write-Host "`n"
Write-Host "Press Ctrl+C in each window to stop services" -ForegroundColor Yellow
Write-Host "`n"
Write-Host "================================================================" -ForegroundColor Cyan

# Wait for both processes
Wait-Process -Id $BackendProcess.Id, $FrontendProcess.Id

Write-Host "`n[DONE] All services stopped" -ForegroundColor Green

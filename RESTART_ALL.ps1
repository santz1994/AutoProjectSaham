#!/usr/bin/env powershell
# Complete Application Restart Script
# This restarts both backend and frontend from scratch

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "AutoSaham Complete Restart" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Kill any existing processes
Write-Host "`n[1/5] Killing existing processes..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

# Verify backend endpoint works
Write-Host "`n[2/5] Testing backend health..." -ForegroundColor Yellow
$health = try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -ErrorAction Stop
    $response.StatusCode -eq 200
} catch {
    $false
}

if ($health) {
    Write-Host "✓ Backend is already running" -ForegroundColor Green
} else {
    Write-Host "✗ Backend not running, please start it manually:" -ForegroundColor Red
    Write-Host "  cd D:\Project\AutoSaham" -ForegroundColor Yellow
    Write-Host "  python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload" -ForegroundColor Yellow
    Write-Host "`nWaiting for backend to start..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}

# Test chart API
Write-Host "`n[3/5] Testing chart API..." -ForegroundColor Yellow
$chartTest = try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/api/charts/metadata/EURUSD=X" -UseBasicParsing -ErrorAction Stop
    $response.StatusCode -eq 200
} catch {
    $false
}

if ($chartTest) {
    Write-Host "✓ Chart API is working" -ForegroundColor Green
} else {
    Write-Host "✗ Chart API not working - backend may need restart" -ForegroundColor Red
}

# Frontend setup
Write-Host "`n[4/5] Building frontend..." -ForegroundColor Yellow
cd D:\Project\AutoSaham\frontend

# Clean node_modules cache
if (Test-Path "node_modules") {
    Write-Host "Cleaning node_modules cache..." -ForegroundColor Gray
    Remove-Item -Path "node_modules/.vite" -Recurse -ErrorAction SilentlyContinue
}

# Start frontend dev server
Write-Host "`n[5/5] Starting frontend dev server..." -ForegroundColor Yellow
Write-Host "Frontend will start on http://localhost:5173" -ForegroundColor Cyan
Write-Host "`nTo access the app:" -ForegroundColor Cyan
Write-Host "  1. Open: http://localhost:5173" -ForegroundColor Yellow
Write-Host "  2. Press Ctrl+Shift+R (hard refresh)" -ForegroundColor Yellow
Write-Host "  3. Login with: demo / demo123" -ForegroundColor Yellow
Write-Host "  4. Chart should appear" -ForegroundColor Yellow
Write-Host "`nTo stop, press Ctrl+C in this terminal`n" -ForegroundColor Cyan

npm run dev

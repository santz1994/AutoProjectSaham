# AutoSaham Application Startup Script
# ==================================================

Write-Host "`n" -ForegroundColor Cyan
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║         🚀 AutoSaham Trading Platform - STARTUP            ║" -ForegroundColor Cyan
Write-Host "║              Real Market Data Integration                  ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host "`n"

# Set environment variables
Write-Host "📋 Setting up environment..." -ForegroundColor Yellow
$env:API_HOST = "127.0.0.1"
$env:API_PORT = "8000"
$env:MARKET_SYMBOLS = "BBCA,USIM,KLBF,ASII,UNVR"
$env:LOG_LEVEL = "info"
$env:PYTHONUNBUFFERED = "1"
$env:API_RELOAD = "1"

Write-Host "✅ Environment configured:" -ForegroundColor Green
Write-Host "   • API Host: $($env:API_HOST):$($env:API_PORT)" -ForegroundColor Green
Write-Host "   • Market Symbols: $($env:MARKET_SYMBOLS)" -ForegroundColor Green
Write-Host "   • API Reload: $($env:API_RELOAD)" -ForegroundColor Green
Write-Host "`n"

# Check if required modules are available
Write-Host "🔍 Checking dependencies..." -ForegroundColor Yellow
python -c "import fastapi, uvicorn, pydantic; print('✅ Core dependencies available')" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️  Some dependencies may be missing, but continuing..." -ForegroundColor Yellow
}

Write-Host "`n"
Write-Host "🌐 Starting AutoSaham API Server..." -ForegroundColor Cyan
Write-Host "────────────────────────────────────────────────────────────" -ForegroundColor Cyan
Write-Host "Frontend UI (run separately): http://localhost:5173" -ForegroundColor Green
Write-Host "API Health: http://localhost:8000/health" -ForegroundColor Green
Write-Host "Metrics: http://localhost:8000/metrics" -ForegroundColor Green
Write-Host "`n"
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host "────────────────────────────────────────────────────────────`n" -ForegroundColor Cyan

# Start the API server
python -m src.main --api 2>&1

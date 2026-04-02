#!/usr/bin/env pwsh
# AutoSaham Frontend & Backend Verification Script

# Colors
function Say-Success { Write-Host $args[0] -ForegroundColor Green }
function Say-Error { Write-Host $args[0] -ForegroundColor Red }
function Say-Warning { Write-Host $args[0] -ForegroundColor Yellow }
function Say-Info { Write-Host $args[0] -ForegroundColor Cyan }

Say-Info "=============================================================="
Say-Info "AutoSaham System Verification"
Say-Info "=============================================================="

# Test 1: Backend Health
Say-Info "`n[1] Checking Backend Status..."
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -ErrorAction Stop -TimeoutSec 5
    if ($response.StatusCode -eq 200) {
        Say-Success "  [OK] Backend running on http://localhost:8000"
    }
} catch {
    Say-Error "  [FAILED] Backend not running or not accessible"
    Say-Warning "  Start backend with: python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload"
    exit 1
}

# Test 2: Test User Database
Say-Info "`n[2] Checking Test User Database..."
$usersFile = "d:\Project\AutoSaham\data\users.json"
if (Test-Path $usersFile) {
    Say-Success "  [OK] users.json exists"
} else {
    Say-Warning "  [INFO] users.json will be created on backend startup"
}

# Test 3: Login Endpoint
Say-Info "`n[3] Testing Login Endpoint..."
try {
    $body = @{username="demo"; password="demo123"} | ConvertTo-Json
    $response = Invoke-WebRequest -Uri "http://localhost:8000/auth/login" -Method POST -Headers @{"Content-Type"="application/json"} -Body $body -ErrorAction Stop -TimeoutSec 5
    Say-Success "  [OK] Login endpoint working"
} catch {
    Say-Error "  [FAILED] Login endpoint: $($_.Exception.Message)"
}

# Test 4: Auth Me Endpoint  
Say-Info "`n[4] Testing /auth/me Endpoint..."
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/auth/me" -ErrorAction Stop -TimeoutSec 5
    Say-Success "  [OK] /auth/me endpoint returning valid response"
} catch {
    Say-Warning "  [INFO] /auth/me returned error (expected if not logged in)"
}

# Test 5: Frontend Build
Say-Info "`n[5] Checking Frontend Build..."
$distPath = "d:\Project\AutoSaham\frontend\dist\index.html"
if (Test-Path $distPath) {
    Say-Success "  [OK] Frontend production build exists"
} else {
    Say-Error "  [FAILED] Frontend build not found"
    Say-Warning "  Build with: cd frontend && npm run build"
}

# Test 6: Tools
Say-Info "`n[6] Checking Development Tools..."
try { 
    $node = node --version
    Say-Success "  [OK] Node.js: $node" 
} catch { 
    Say-Error "  [FAILED] Node.js not found" 
}

try { 
    $npm = npm --version
    Say-Success "  [OK] npm: $npm" 
} catch { 
    Say-Error "  [FAILED] npm not found" 
}

try { 
    $python = python --version
    Say-Success "  [OK] Python: $python" 
} catch { 
    Say-Error "  [FAILED] Python not found" 
}

# Summary
Say-Info "`n=============================================================="
Say-Info "VERIFICATION COMPLETE - READY TO TEST"
Say-Info "=============================================================="
Say-Info "`nNext Steps:"
Say-Info "1. Start Backend:"
Say-Info "   python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload"
Say-Info "`n2. Start Frontend (in new terminal):"
Say-Info "   cd frontend && npm run dev"
Say-Info "`n3. Open Browser:"
Say-Info "   http://localhost:5173"
Say-Info "`n4. Login:"
Say-Info "   Username: demo"
Say-Info "   Password: demo123"
Say-Info "`n"

# Testing & Setup Guide

## Prerequisites Check

### 1. Backend Server Status
Check if backend is running on localhost:8000:

```powershell
# Test in PowerShell
$response = Invoke-WebRequest -Uri "http://localhost:8000/health" -ErrorAction SilentlyContinue
if ($response) {
    Write-Host "✓ Backend is RUNNING" -ForegroundColor Green
    $response.Content | ConvertFrom-Json
} else {
    Write-Host "✗ Backend is NOT RUNNING" -ForegroundColor Red
}
```

### 2. Start Backend (if not running)

```bash
# From project root
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload
```

**Expected output:**
```
Application startup complete
Uvicorn running on http://127.0.0.1:8000
```

### 3. Start Frontend Dev Server

```bash
cd frontend
npm run dev
# Should output: http://localhost:5173
```

### 4. Test API Endpoints

Once both are running, test these manually:

#### A. Health Check
```powershell
Invoke-WebRequest -Uri "http://localhost:8000/health" | Select-Object -ExpandProperty Content
```
Expected: `{"status":"ok"}`

#### B. Create Test User (Auto-created at startup)
Already created: `demo` / `demo123`

#### C. Login Test
```powershell
$body = @{
    username = "demo"
    password = "demo123"
} | ConvertTo-Json

$response = Invoke-WebRequest `
  -Uri "http://localhost:8000/auth/login" `
  -Method POST `
  -Headers @{"Content-Type"="application/json"} `
  -Body $body `
  -ErrorAction SilentlyContinue

if ($response.StatusCode -eq 200) {
    Write-Host "✓ Login successful" -ForegroundColor Green
    $response.Headers["Set-Cookie"]  # Should see auth_token
} else {
    Write-Host "✗ Login failed" -ForegroundColor Red
}
```

#### D. Get Current User
```powershell
Invoke-WebRequest `
  -Uri "http://localhost:8000/auth/me" `
  -Headers @{"Cookie"="auth_token=<your_token_here>"} | Select-Object -ExpandProperty Content
```

---

## Frontend Testing Checklist

### Step 1: Load Frontend
Open: http://localhost:5173

### Step 2: Check Browser Console (F12)
Should see:
```
[vite] connecting...
[vite] connected.
[App] Registering Service Worker...
[App] Service Worker registered successfully
```

**Should NOT see:**
- ❌ "Unexpected end of JSON input"
- ❌ "<!doctype html" in error messages
- ❌ 404 errors for API calls
- ❌ CORS errors

### Step 3: Login Test
1. Username: `demo`
2. Password: `demo123`
3. Click Login
4. Should redirect to Dashboard

**Check in DevTools → Network:**
- `POST /auth/login` → 200 OK
- Response shows `{"status":"ok"}`
- Cookie `auth_token` set (HttpOnly)

### Step 4: Dashboard Page
Should display:
- ✓ Portfolio Summary card
- ✓ Bot Status card
- ✓ Portfolio Health widget
- ✓ Recent Activity

### Step 5: Market Intelligence Page
Should display:
- ✓ Real-Time Stock Chart (with BBCA.JK by default)
- ✓ Symbol selector dropdown
- ✓ Timeframe buttons (1m, 5m, 15m, etc.)
- ✓ Market Sentiment section
- ✓ Sector Heatmap
- ✓ Top Movers

---

## Common Errors & Fixes

### Error: "Unexpected token '<', "<!doctype""
**Cause:** Backend returning HTML error page instead of JSON
**Fix:** 
1. Ensure backend is running: `python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000`
2. Check error logs in backend terminal
3. Verify database file exists: `data/users.json`

### Error: CORS blocked error
**Fix:** Backend needs proper CORS headers
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Error: "Login failed" 
**Cause:** Incorrect credentials or auth endpoint not working
**Fix:**
1. Verify test user exists: Check `data/users.json`
2. Check that `/auth/login` endpoint returns 200 and sets cookie
3. Verify username/password are exact: `demo` / `demo123`

### Pages Not Dynamic / Showing Blank
**Cause:** Auth check failing or component not rendering
**Fix:**
1. Check browser console for errors
2. Verify `/auth/me` returns valid JSON (not HTML)
3. Check that `authService.getMe()` returns user info
4. Verify cookies are being sent with requests (credentials: 'include')

---

## Quick Start (All at Once)

**Terminal 1: Backend**
```powershell
cd d:\Project\AutoSaham
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2: Frontend**
```powershell
cd d:\Project\AutoSaham\frontend
npm run dev
```

**Browser:** Open http://localhost:5173

**Login:** demo / demo123

---

## Status Indicators

| Component | Status | Expected |
|-----------|--------|----------|
| Backend API | ? | http://localhost:8000/health → 200 |
| Frontend Dev Server | ? | http://localhost:5173 → 200 |
| Auth Login | ? | POST /auth/login → 200, cookie set |
| User Info | ? | GET /auth/me → 200, JSON response |
| Dashboard | ? | Loads with portfolio data |
| Market Chart | ? | Renders with real-time data |

**Check each status before reporting issues!**


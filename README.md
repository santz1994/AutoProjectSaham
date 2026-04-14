# AutoSaham

AutoSaham adalah platform trading automation dan AI monitoring untuk workflow Forex/Crypto global (UTC-centric), dengan frontend React + Vite dan backend FastAPI.

README ini sudah disesuaikan dengan kondisi kode saat ini: fitur frontend, kemampuan backend, daftar endpoint aktif, cara menjalankan, validasi, dan rencana next updates.

## Status Saat Ini

- Snapshot dokumen: 14 April 2026
- Progress proyek mengikuti `Progress.md` sebagai sumber status tunggal (bukan angka statis di README)
- Fokus aktif: Fase 1.5 modularisasi `src/ml/feature_store.py` (split modul core/risk/volatility/momentum)
- Fase 2.3 otomatisasi raw data -> feature dataset sudah selesai dan tervalidasi
- Frontend: React 18 + Vite + lightweight-charts
- Backend: FastAPI + pipeline data/ML + WebSocket realtime
- Timezone utama: UTC
- Market scope di UI AI Graph: Forex dan Crypto

## Arsitektur Singkat

```text
frontend/ (React + Vite)
  -> konsumsi REST + WebSocket
  -> UI pages: Dashboard, Market, Strategies, Trades, AI Monitor, AI Graph, Profile, Settings

src/api/server.py (FastAPI app)
  -> auth, system, charts, training, scheduler, metrics
  -> include router: src/api/frontend_routes.py (prefix /api)
  -> include router: src/notifications/api_routes.py (prefix /api/notifications)

src/notifications/
  -> manajemen rule + preference + history + websocket notif

src/ml, src/pipeline, src/data
  -> fitur ML, scoring/projection, ETL/market ingestion
```

## Kemampuan Aplikasi (Frontend)

### Halaman dan fitur utama

| Halaman | Kemampuan |
|---|---|
| Dashboard | Portfolio summary, refresh portfolio, bot status, kill switch state, portfolio health, top AI signals, recent activity |
| Market Intelligence | Realtime candlestick chart Forex/Crypto, symbol switch, timeframe switch, sentiment summary, sektor heatmap, top movers, live ask/bid orderbook + spread indicator, quick order ticket (BUY/SELL) |
| Strategies | Daftar strategi, deploy strategy, trigger backtest, rule display, metrik performa |
| Trade Logs | Filter/sort trades, summary analytics, export CSV, trigger report performa |
| AI Monitor | AI overview (model/dataset/pipeline), AI activity logs, auto refresh, manual checkpoint log |
| AI Graph | Live chart + projection overlay, market switch (forex/crypto/all), prediction style preset (Scalping/Daily Trader/Trader), prediction lock ON/OFF, rationale + news context |
| Profile | Edit profil, risk profile, daily report schedule, status keamanan akun, broker connection summary |
| Settings | Theme preference, notification toggles, risk settings, preferred universe, broker connect/disconnect, broker feature flags, 2FA enrollment/verify/disable |
| Auth | Login, Register, Forgot Password, Logout via secure cookie flow |

### Fitur lintas halaman

- Navbar enhanced:
  - Search shortcut (Ctrl+K)
  - Notification bell dengan history + unread count + mark-read + mark-all-read
  - Realtime notification WebSocket (/api/notifications/ws/{user_id})
  - Emergency kill switch UI
- Sidebar enhanced:
  - Navigasi cepat (Ctrl+1..8), toggle sidebar (Ctrl+B), shortcut modal (Ctrl+/)
- Toast feedback + loading skeleton + error boundary
- Responsive system:
  - Breakpoint + device detection + safe area inset
  - Mobile/tablet/desktop adaptive layout
- PWA support:
  - Manifest + service worker + install prompt + offline fallback
  - Catatan: service worker default nonaktif di localhost dev untuk menghindari cache stale

## Kemampuan Backend

### Ringkasan kemampuan

- Auth berbasis httpOnly cookie (/auth/*)
- API domain trading/frontend (/api/*) via frontend_routes
- API notifikasi realtime (/api/notifications/*)
- Chart REST + WebSocket realtime (/api/charts/*, /ws/charts/{symbol})
- ETL trigger + scheduler + training artifact endpoint
- Monitoring metrics endpoint untuk Prometheus
- Persistent encrypted app state (SQLite + encryption) untuk settings/connection/feature flags/AI logs

### Kondisi data saat ini (hybrid)

Backend saat ini menggabungkan beberapa sumber:

- Real/hampir real:
  - Chart candles/metadata/trading status
  - Market universe multi-market
  - AI projection (dengan blending model + market momentum + sentiment)
  - News context untuk projection
- Demo/fallback untuk sebagian endpoint UI:
  - Sebagian data portfolio, bot status, sectors, trades, report masih berbasis mock/fallback

Ini sengaja menjaga UX tetap stabil saat data provider atau integrasi broker tertentu belum aktif penuh.

## Endpoint Aktif

### Core server (src/api/server.py)

#### System and ops

- GET /health
- POST /run_etl
- GET /metrics
- GET /etl_runs
- POST /alert
- POST /scheduler/start
- POST /scheduler/stop

#### Auth

- POST /auth/register
- POST /auth/login
- GET /auth/me
- POST /auth/logout
- POST /auth/forgot-password

#### Training and diagnostics

- GET /api/training
- POST /api/training/trigger
- GET /api/portfolio/reconcile

#### Charts and realtime

- GET /api/charts/metadata/{symbol}
- GET /api/charts/candles/{symbol}
- GET /api/charts/timeframes
- GET /api/charts/trading-status
- WS /ws/charts/{symbol}
- WS /ws/events

### Frontend domain API (src/api/frontend_routes.py, prefix /api)

- Portfolio and bot:
  - GET /api/portfolio
  - POST /api/portfolio/refresh
  - GET /api/bot/status
  - POST /api/bot/start
  - POST /api/bot/stop
  - POST /api/bot/pause
- Signal and market:
  - GET /api/signals
  - GET /api/market/sentiment
  - GET /api/market/universe
  - GET /api/market/sectors
  - GET /api/market/movers
  - GET /api/market/news
- Strategy and trades:
  - GET /api/strategies
  - POST /api/strategies/{strategy_id}/deploy
  - POST /api/strategies/{strategy_id}/backtest
  - GET /api/trades
  - GET /api/activity
  - GET /api/reports/performance
- User settings and broker:
  - GET /api/user/settings
  - PUT /api/user/settings
  - GET /api/brokers/available
  - GET /api/brokers/feature-flags
  - PUT /api/brokers/feature-flags/{provider_id}
  - GET /api/broker/connection
  - POST /api/broker/connect
  - POST /api/broker/disconnect
  - GET /api/system/kill-switch
  - POST /api/system/kill-switch/activate
  - POST /api/system/kill-switch/deactivate
  - GET /api/system/migration-control-center
  - GET /api/system/quota/usage
  - GET /api/system/execution/pending-orders
- AI:
  - GET /api/ai/projection/{symbol}
  - GET /api/ai/overview
  - GET /api/ai/logs
  - POST /api/ai/logs

### Notification API (src/notifications/api_routes.py, prefix /api/notifications)

- Rules:
  - POST /api/notifications/rules
  - GET /api/notifications/rules
  - GET /api/notifications/rules/{rule_id}
  - PUT /api/notifications/rules/{rule_id}
  - DELETE /api/notifications/rules/{rule_id}
- Preferences:
  - POST /api/notifications/preferences
  - GET /api/notifications/preferences/{user_id}
  - PUT /api/notifications/preferences/{user_id}
  - PUT /api/notifications/preferences/{user_id}/channels
  - POST /api/notifications/preferences/{user_id}/quiet-hours
- Retrieval and stats:
  - GET /api/notifications/history/{user_id}
  - GET /api/notifications/unread/{user_id}
  - POST /api/notifications/mark-read/{notification_id}
  - GET /api/notifications/stats
  - GET /api/notifications/market-status
  - GET /api/notifications/health
- Realtime:
  - WS /api/notifications/ws/{user_id}

## AI Projection: Arti Field source

Pada endpoint GET /api/ai/projection/{symbol}, field source menunjukkan asal sinyal utama:

- transformer: sinyal utama dari model transformer
- market_realtime: fallback ke momentum market realtime
- transformer+market: hasil transformer distabilkan oleh data market realtime
- fallback: fallback non-model saat sinyal model belum memadai

Di UI AI Graph, ini tampil pada kartu confidence agar user tahu asal sinyal yang sedang dipakai.

## Teknologi Utama

### Frontend

- React 18
- Vite 5
- lightweight-charts
- Zustand
- Vitest + Testing Library

### Backend and ML

- Python 3.10+
- FastAPI + Uvicorn
- pandas, numpy, scikit-learn
- lightgbm, xgboost, transformers, torch
- stable-baselines3 (RL)
- APScheduler, aiohttp, httpx

## Menjalankan Aplikasi

### 1) Persiapan

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

cd frontend
npm install
cd ..
```

### 2) Development mode (direkomendasikan)

Terminal 1 (backend):

```bash
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload
```

Terminal 2 (frontend):

```bash
cd frontend
npm run dev
```

Akses:

- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- API Docs: http://localhost:8000/docs

### 3) One-command full stack

- PowerShell: ./RUN_FULLSTACK.ps1
- CMD: RUN_FULLSTACK.bat
- Python: python run_fullstack.py

### 4) Backend only via runner

```bash
python -m src.main --api
```

## Validasi dan Testing

### Quick regression backend API

```bash
./scripts/quick_regression.ps1
./scripts/quick_regression.ps1 -SkipMutatingActions
```

### Kill switch rehearsal drill

```powershell
./scripts/kill_switch_drill.ps1 -BaseUrl http://127.0.0.1:8000 -Actor ops-weekly-drill
```

Jika hardening auth kill-switch diaktifkan, sertakan token sesi admin dan challenge code:

```powershell
./scripts/kill_switch_drill.ps1 -BaseUrl http://127.0.0.1:8000 -Actor ops-weekly-drill -AuthToken "<session_token_cookie_value>" -ChallengeCode "123456"
```

Runbook rollback procedure tersedia di `docs/KILL_SWITCH_DRILL_RUNBOOK.md`.

Automasi jadwal mingguan (Windows Task Scheduler):

```powershell
./scripts/register_kill_switch_drill_task.ps1 -TaskName AutoSaham-KillSwitchWeeklyDrill -DayOfWeek Sunday -At 07:00 -BaseUrl http://127.0.0.1:8000 -Actor ops-weekly-drill
```

### Local exchange chaos simulation

```bash
python scripts/simulate_exchange_chaos.py --orders 20 --seed 42
```

### Frontend validation

```bash
cd frontend
npm run build
npm run test
npm run type-check
```

### Backend tests

```bash
python -m pytest tests/ -q
python -m pytest tests/test_notifications.py -q
```

## Konfigurasi Environment

Salin .env.example menjadi .env, lalu isi sesuai kebutuhan.

Variabel penting:

- Runtime: MARKET_SYMBOLS, TICKS_DB_PATH, MODELS_DIR, ML_TRAIN_INTERVAL
- Market/news: NEWSAPI_KEY, ALPHAVANTAGE_API_KEY
- ETL corporate actions: AUTOSAHAM_CORPORATE_ACTIONS_FILE (opsional, path JSON untuk backward adjustment split/dividen/rights issue pada data historis)
- Broker: BROKER_API_KEY, BROKER_API_SECRET
- Notifications: SLACK_WEBHOOK_URL, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS
- State store migration:
  - AUTOSAHAM_STATE_REDIS_URL
  - AUTOSAHAM_STATE_REDIS_PRIMARY_NAMESPACES (default: ai_regime_state,broker_connection,user_settings)
  - AUTOSAHAM_STATE_REDIS_PRIMARY_SHADOW_SQLITE (default: 1)
  - AUTOSAHAM_STATE_POSTGRES_URL (fallback ke DATABASE_URL bila kosong)
  - AUTOSAHAM_STATE_POSTGRES_AI_LOGS_ENABLED (default: 1)
  - AUTOSAHAM_STATE_POSTGRES_AI_LOGS_SHADOW_SQLITE (default: 1)
  - AUTOSAHAM_WS_BACKPLANE_ENABLED (default: 0)
  - AUTOSAHAM_WS_BACKPLANE_CHANNEL (default: autosaham:events)
  - AUTOSAHAM_INSTANCE_ID (opsional untuk identitas publisher event lintas instance)
  - AUTH_EXPOSE_RESET_TOKEN (default: 0, aktifkan 1 hanya untuk smoke test reset password di dev)
- Auth session:
  - AUTH_TTL_SECONDS (default: 86400)
  - AUTH_REMEMBER_ME_TTL_SECONDS (default: 2592000)
  - AUTOSAHAM_LOGIN_2FA_ENABLED (default: 0)
  - AUTOSAHAM_LOGIN_2FA_REQUIRED_ROLES (default: admin)
  - AUTOSAHAM_LOGIN_2FA_ISSUER (default: AutoSaham, label issuer untuk enrollment URI authenticator)
  - AUTOSAHAM_LOGIN_2FA_TOTP_SECRET (global TOTP Base32 secret)
  - AUTOSAHAM_LOGIN_2FA_TOTP_SECRET_<USERNAME> (opsional secret per user)
  - AUTOSAHAM_LOGIN_2FA_CODE (fallback static code)
- Kill switch auth hardening:
  - AUTOSAHAM_KILL_SWITCH_REQUIRE_ADMIN (default: aktif pada ENV=prod/production)
  - AUTOSAHAM_KILL_SWITCH_ADMIN_USERS (default: admin)
  - AUTOSAHAM_KILL_SWITCH_ADMIN_ROLES (default: mengikuti AUTOSAHAM_ADMIN_ROLES)
  - AUTOSAHAM_KILL_SWITCH_REQUIRE_2FA (default: aktif jika verifier tersedia)
  - AUTOSAHAM_KILL_SWITCH_TOTP_SECRET (Base32 TOTP secret, prioritas utama)
  - AUTOSAHAM_KILL_SWITCH_2FA_CODE (fallback static challenge code untuk environment terbatas)
- Authz/CSRF guard endpoint mutating:
  - AUTOSAHAM_ADMIN_GUARD_ENABLED (default: aktif pada ENV=prod/production)
  - AUTOSAHAM_ADMIN_USERS (opsional allowlist username admin global)
  - AUTOSAHAM_ADMIN_ROLES (default: admin)
  - AUTOSAHAM_CSRF_PROTECTION_ENABLED (default: aktif pada ENV=prod/production)
  - AUTOSAHAM_ROLE_GUARD_ENABLED (default: aktif pada ENV=prod/production)
  - AUTOSAHAM_ROLE_ETL_WRITE_ROLES (default: trader,developer)
  - AUTOSAHAM_ROLE_EXECUTION_WRITE_ROLES (default: trader,developer)
  - AUTOSAHAM_ROLE_SCHEDULER_WRITE_ROLES (default: developer)
  - AUTOSAHAM_ROLE_MODEL_REGISTRY_WRITE_ROLES (default: developer)
  - AUTOSAHAM_ROLE_ALERT_WRITE_ROLES (default: admin,developer)
  - AUTOSAHAM_ROLE_STRATEGY_WRITE_ROLES (default: trader,developer)
  - AUTOSAHAM_ROLE_SETTINGS_WRITE_ROLES (default: viewer,trader,developer)
  - AUTOSAHAM_ROLE_AI_LOG_WRITE_ROLES (default: trader,developer)
- Quota tier & Kong tier routing:
  - AUTOSAHAM_QUOTA_ROLE_TIERS (default: viewer=free,trader=basic,developer=pro,admin=pro)
  - AUTOSAHAM_QUOTA_FREE_PER_MINUTE, AUTOSAHAM_QUOTA_FREE_PER_HOUR
  - AUTOSAHAM_QUOTA_BASIC_PER_MINUTE, AUTOSAHAM_QUOTA_BASIC_PER_HOUR
  - AUTOSAHAM_QUOTA_PRO_PER_MINUTE, AUTOSAHAM_QUOTA_PRO_PER_HOUR
  - Frontend otomatis mengirim header X-Autosaham-Tier (free/basic/pro) dari cookie autosaham_tier.

## Docker and Observability

docker-compose.yml sudah menyiapkan stack:

- API (FastAPI)
- Redis
- PostgreSQL
- Kong API Gateway
- Prometheus
- Alertmanager
- Grafana
- Node Exporter

Jalankan:

```bash
docker-compose up -d
```

## Struktur Folder Penting

```text
src/
  api/             # FastAPI app, auth, routes, secure state store
  notifications/   # Notification manager, delivery handlers, notification API
  data/            # Data fetcher and market adapters
  ml/              # ML models, features, evaluators
  pipeline/        # ETL runner and scheduler
frontend/
  src/components/  # Pages and UI components
  src/hooks/       # useResponsive, usePWA, market feed
  src/utils/       # authService, apiService
scripts/           # utility and validation scripts
tests/             # backend test suite
monitoring/        # Prometheus and alert configuration
```

## Catatan Penting

- Saat ini backend tidak melakukan static mount frontend ke path /ui.
  Untuk akses UI, jalankan Vite dev server (localhost:5173) atau host build frontend secara terpisah.
- Notification channel WebSocket berjalan realtime. Beberapa channel lain (email/push) masih pada level handler/queue/logging dan dapat diperluas sesuai kebutuhan produksi.
- Global Kill Switch memblokir trigger eksekusi baru (bot start, deploy/backtest strategy, run ETL/training trigger) sampai status di-resume melalui endpoint kill switch.
- Aktivasi kill switch melakukan best-effort penghentian scheduler lokal dan mengembalikan ringkasan runtimeActions pada respons API untuk audit operasional cepat.
- Aktivasi kill switch juga mencoba membatalkan seluruh pending order yang sedang dilacak oleh runtime execution manager (best-effort, non-blocking), dan hasilnya dicatat pada runtimeActions.
- Aktivasi kill switch kini juga mencoba cancel semua open order pada koneksi broker live yang didukung adapter (saat ini: indopremier, stockbit, ajaib) menggunakan kredensial terenkripsi di secure state; provider lain tetap fail-safe sebagai unsupported_provider.
- Aktivasi/nonaktif kill switch kini mendukung guard admin session + challenge 2FA berbasis env flag (dengan kompatibilitas payload `actor` maupun `activatedBy` untuk klien lama).
- Endpoint operasional mutating berisiko tinggi (bot control, broker connect/disconnect, state migration, broker feature-flag update) kini mendukung guard admin session + double-submit CSRF token berbasis env flag.
- Endpoint mutating strategi/profile/log AI kini mendukung role-guard granular berbasis env (trader/developer/admin) dengan admin override dan validasi CSRF saat guard diaktifkan.
- Endpoint mutating server non-router (`/run_etl`, `/scheduler/start`, `/scheduler/stop`, `/api/training/registry/active`, `/alert`) kini ikut role-guard berbasis env + validasi CSRF saat role guard diaktifkan.
- Endpoint `/api/system/execution/orders` kini tersedia untuk submit order runtime (market/limit) dari UI Market orderbook, dijaga role-guard + CSRF saat guard aktif.
- Kong kini memiliki policy route bertingkat free/basic/pro untuk `/api`, `/api/signals|/api/ai/*`, dan jalur eksekusi; request tanpa header tier jatuh ke policy free sebagai fallback non-breaking.
- Backend memvalidasi header X-Autosaham-Tier terhadap role sesi terautentikasi untuk mencegah spoof tier lintas role.
- Login kini mendukung challenge two-factor authentication (2FA) untuk role yang dikonfigurasi (TOTP atau fallback static code), di samping opsi rememberMe TTL session.
- Endpoint auth 2FA (`/auth/2fa/status`, `/auth/2fa/enroll`, `/auth/2fa/verify`, `/auth/2fa/disable`) kini aktif untuk enrollment per-user TOTP dari Settings, dengan proteksi CSRF untuk operasi mutating.
- ETL historis mendukung corporate action backward adjustment berbasis file JSON (jika AUTOSAHAM_CORPORATE_ACTIONS_FILE dikonfigurasi) untuk membantu menjaga kontinuitas fitur ML saat stock split/dividen terjadi.

## Kontribusi

Pedoman kontribusi ada di file CONTRIBUTING.md, termasuk standar commit, validasi minimal, aturan keamanan secret, dan checklist review perubahan.

## Next Updates

Prioritas update berikutnya yang direkomendasikan:

1. Menuntaskan Fase 1.5: final wiring modular `feature_store` dan cleanup file besar (>300 baris) secara bertahap dengan regresi test ketat.
2. Melanjutkan sweep residual `.JK/IDX` di modul legacy non-core agar debugging tidak ambigu.
3. Memulai Fase 3 RL sandbox: update reward berbasis risk-adjusted return + death-penalty + simulasi fee/slippage leverage tinggi.
4. Menambah E2E test automation untuk flow kritikal (auth, strategy deploy/backtest, AI Graph controls, notifications).
5. Hardening eksekusi broker live (audit trail order, guardrail risiko tambahan, rollout feature flag per provider).
6. Penguatan observability: SLO/SLI dashboard, alert tuning berbasis error budget.
7. Packaging release yang lebih rapi (versioning, changelog, release notes otomatis).

## Lisensi

Proyek ini menggunakan lisensi MIT. Lihat file LICENSE di root repository untuk detail lengkap.

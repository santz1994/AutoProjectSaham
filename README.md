# AutoSaham

**Autonomous Crypto/Forex Reinforcement Learning Trading Bot**

AutoSaham adalah platform trading automation berbasis AI yang menggunakan Reinforcement Learning (PPO/SAC) untuk menemukan entries, exits, dan risk-management rules secara otonom — tanpa manual tweaking. Target: $100 → $10,000 melalui multiplicative scaling, dengan target winrate ~90%.

## 🎯 Vision: Fully Autonomous AI Trading

> Sistem ini dirancang 100% driven by AI. Model harus mampu menemukan entries, exits, dan risk-management rules sendiri tanpa intervensi manual yang konstan (Zero Manual Tweaking).

---

## Status Terkini

- **Update Terakhir:** 30 April 2026 (Wave 8 — Test Suite Stability + Critical Bug Fixes)
- **Test Suite:** 78 passed, 1 skipped ✅
- **Market Scope:** Forex (24/5) + Crypto (24/7) — UTC-centric
- **Frontend:** React 18 + Vite + lightweight-charts
- **Backend:** FastAPI + Stable-Baselines3 + Transformers + XAI + Ghost Machine

### Ringkasan Status Fase

| Fase | Nama | Status |
|------|------|--------|
| 1 | Cleanup & Infrastruktur Lokal | ✅ In Progress (dead modules cleaned, service extraction ongoing) |
| 2 | High-Frequency Data Pipeline | ✅ SELESAI |
| 3 | RL Sandbox Architecture | ✅ SELESAI (leverage, slippage, fees, Sharpe reward, death penalty) |
| 4 | Deep RL Training | 🟡 In Progress (training script ready, AutoML scheduler wired) |
| 5 | 24/7 Execution Server (Ghost Machine) | ✅ Backend SELESAI (Ghost Machine wired + REST API + Oracle deployment ready) |
| 6 | CEO Command Center | ✅ SELESAI (XAI + Autonomy + Ghost Machine + all frontend panels) |
| 7 | UI/UX & Performance | 🟡 Partial (Portfolio Metrics, Backtest, Risk Analytics, Heatmap done) |
| 8 | Frontend Expansion | 🟡 Partial (Multi-symbol support, Risk/Performance panels done) |

---

## Arsitektur

```text
┌──────────────────────────────────────────────────────────────┐
│                     Frontend (React 18 + Vite)                │
│  Dashboard │ Market │ AI Monitor │ AI Graph │ Settings       │
│  Portfolio Metrics │ Backtest │ Risk Analytics │ Heatmap      │
│  XAI Panel │ Autonomy Control │ Ghost Machine Control 👻      │
└──────────────────────┬───────────────────────────────────────┘
                       │ REST + WebSocket
┌──────────────────────┴───────────────────────────────────────┐
│                   FastAPI Backend (server.py)                  │
│  Auth │ Charts │ Training │ Scheduler │ Metrics              │
│  ┌─────────────────────────────────────────────────┐         │
│  │  frontend_routes.py (thinned via 9+ services)   │         │
│  │  xai_routes.py │ autonomy_routes.py             │         │
│  │  ghost_machine_routes.py │ notify_routes.py      │         │
│  └─────────────────────────────────────────────────┘         │
│                                                               │
│  ┌──────────┐  ┌───────────┐  ┌────────────┐  ┌───────────┐ │
│  │ RL Agent  │  │ Ghost     │  │ Online     │  │ Anomaly   │ │
│  │ (PPO/SAC) │  │ Machine   │  │ Learner    │  │ Detector  │ │
│  └──────────┘  └───────────┘  └────────────┘  └───────────┘ │
│                                                               │
│  ┌──────────┐  ┌───────────┐  ┌────────────┐  ┌───────────┐ │
│  │ Feature   │  │ Regime    │  │ Continuous │  │ XAI       │ │
│  │ Store     │  │ Detector  │  │ AutoML     │  │ Service   │ │
│  └──────────┘  └───────────┘  └────────────┘  └───────────┘ │
└──────────────────────────────────────────────────────────────┘
         │
    ┌────┴────┐
    │ CCXT    │  ← Binance / Bybit / Forex APIs
    │ Connect │
    └─────────┘
```

### Struktur Folder

```text
src/
  api/                  # FastAPI app, auth, routes, services (9+ extracted)
  brokers/              # Broker adapters
  data/                 # Data fetcher and market adapters
  execution/            # Order execution manager
  ml/                   # ML models, features, online learner, anomaly detector
  notifications/        # Notification manager + delivery handlers
  pipeline/             # ETL, Ghost Machine, scheduler, data connectors
  rl/                   # RL agent, trading env, policy trainer, experience replay
  strategies/           # Strategy modules
  utils/                # Logger, datetime utilities
  monitoring/           # Alert rules, monitoring
frontend/
  src/components/       # 20+ UI components (pages + panels)
  src/services/         # API client (api.js)
  src/styles/           # CSS for risk analytics, heatmap, etc.
scripts/                # Utility scripts (deploy, train, fetch, prepare)
tests/                  # 80 backend test files
docs/                   # Deployment guides, runbooks
models/                 # Saved model artifacts and checkpoints
data/dataset/           # Training datasets (e.g. hf_BTCUSDT_5m.csv)
```

---

## Fitur Utama

### 🤖 AI/ML Engine

| Fitur | Deskripsi |
|-------|-----------|
| **RL Trading Agent** | PPO/SAC via Stable-Baselines3 — 2D action space (direction + dynamic stop-loss) |
| **Asymmetric Reward** | Penalty kerugian (-10×) lebih berat dari reward kemenangan (+1×) — memaksa target winrate 90% |
| **Sharpe Ratio Reward** | Reward berbasis risk-adjusted return, bukan PnL mentah |
| **Death Penalty** | Liquidation trigger saat portfolio jatuh di bawah maintenance margin |
| **Feature Store** | RSI, MACD, Bollinger Width, dist_to_liquidation — modular (volatility, momentum, risk) |
| **Online Learning** | Concept drift detection (ADWIN/PH-test) + SRPClassifier streaming ensemble |
| **Continuous AutoML** | Optuna + Walk-Forward validation scheduler — hyperparameter optimization otonom |
| **XAI Service** | SHAP-like feature importance + MiMo narrative explanation generation |
| **Ghost Machine** | Autonomous trading loop — pull candle → compute features → predict → execute |
| **Experience Replay** | Prioritized Experience Replay dengan regime-aware boosting |
| **Anomaly Detector** | Flash-crash / black swan detection — hard-brake override pada risk sizing |

### 📊 Frontend Panels

| Panel | Kemampuan |
|-------|-----------|
| **Dashboard** | Portfolio summary, bot status, kill switch, top AI signals |
| **Market Intelligence** | Realtime candlestick chart, symbol/timeframe switch, sentiment, heatmap |
| **AI Monitor** | AI overview (model/dataset/pipeline), activity logs |
| **AI Graph** | Live chart + projection overlay, prediction style, rationale + news |
| **Portfolio Metrics** | Net Worth, Leverage, Open Positions, Win Rate — live refresh |
| **Backtest Panel** | Walk-forward backtest results, equity curve, trade statistics |
| **Risk Analytics** | VaR, CVaR, max drawdown, Sharpe/Sortino ratios, risk-adjusted metrics |
| **Performance Heatmap** | Calendar heatmap harian PnL — visual win/loss pattern |
| **XAI Panel** | Feature importance bar chart — breakdown keputusan RL agent |
| **Autonomy Control** | Slider Level 1-3 (Signal Only / Human Confirm / Full Auto) + Kill Switch |
| **Ghost Machine Control** | Start/Stop/Cycle autonomous trading loop + real-time stats |
| **Settings** | Theme, notifications, risk settings, broker connect, 2FA |

### 🔌 API Endpoints

<details>
<summary>Click to expand full endpoint list</summary>

**Core Server (server.py)**
- `GET /health` — Health check
- `POST /run_etl` — Trigger ETL
- `GET /metrics` — Prometheus metrics
- `GET/POST /scheduler/*` — Scheduler control
- `POST /auth/*` — Register, login, logout, 2FA
- `GET /api/training` — Training status
- `GET/WS /api/charts/*` — Chart REST + WebSocket
- `WS /ws/charts/{symbol}` — Real-time candlestick WS
- `WS /ws/events` — Event stream WS

**Frontend Domain (frontend_routes.py)**
- `GET /api/portfolio` — Portfolio positions
- `GET/POST /api/bot/*` — Bot start/stop/pause/status
- `GET /api/signals` — AI trading signals
- `GET /api/market/*` — Sentiment, universe, sectors, movers, news
- `GET /api/strategies` — Strategy list + deploy + backtest
- `GET /api/trades` — Trade logs
- `GET /api/ai/projection/{symbol}` — AI projection with XAI
- `GET/POST /api/system/*` — Kill switch, execution, quota

**XAI (xai_routes.py)**
- `POST /api/xai/explain` — Feature importance + narrative
- `GET /api/xai/history` — Explanation history
- `GET /api/xai/stats` — XAI service stats

**Autonomy (autonomy_routes.py)**
- `GET /api/autonomy/status` — Current autonomy level
- `POST /api/autonomy/level` — Set level (1/2/3)
- `POST /api/autonomy/kill-switch/activate` — Activate kill switch
- `POST /api/autonomy/kill-switch/deactivate` — Deactivate
- `POST /api/autonomy/order` — Submit order (routed by autonomy level)
- `POST /api/autonomy/order/{id}/approve` — Approve pending order
- `POST /api/autonomy/order/{id}/reject` — Reject pending order
- `GET /api/autonomy/pending` — List pending orders

**Ghost Machine (ghost_machine_routes.py)**
- `GET /api/v1/ghost-machine/status` — Stats (running, trades, uptime)
- `POST /api/v1/ghost-machine/start` — Start autonomous loop
- `POST /api/v1/ghost-machine/stop` — Stop loop
- `POST /api/v1/ghost-machine/cycle` — Run single cycle

**Notifications (api_routes.py)**
- `GET/POST/PUT/DELETE /api/notifications/*` — Rules, preferences, history
- `WS /api/notifications/ws/{user_id}` — Real-time notification WS

</details>

---

## Menjalankan Aplikasi

### Prerequisites

- Python 3.10+
- Node.js 18+
- Git

### 1) Setup

```bash
# Clone
git clone https://github.com/santz1994/AutoProjectSaham.git
cd AutoProjectSaham

# Backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate    # Linux/Mac
pip install -r requirements.txt

# Frontend
cd frontend && npm install && cd ..
```

### 2) Development Mode

**Terminal 1 — Backend:**
```bash
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 — Frontend:**
```bash
cd frontend && npm run dev
```

**Akses:**
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs (Swagger): http://localhost:8000/docs

### 3) Docker (Production)

```bash
docker-compose up -d
```

### 4) Oracle Cloud Deployment

Lihat [docs/ORACLE_DEPLOYMENT_GUIDE.md](docs/ORACLE_DEPLOYMENT_GUIDE.md) untuk panduan lengkap:
- Buat Oracle Cloud Free Tier account
- Provision ARM64 instance (4 OCPU, 24GB RAM)
- One-click deploy dengan `scripts/deploy_oracle_vps.sh`
- Edit kode langsung dari VSCode via Remote SSH

### 5) Data Pipeline

```bash
# Fetch 100k candle dari Binance
python scripts/fetch_hf_data.py --exchange binance --symbol BTC/USDT --timeframe 5m --candles 100000

# Prepare features
python scripts/prepare_data.py --input-csv data/dataset/hf_BTCUSDT_5m.csv --symbol BTC/USDT --timeframe 5m
```

### 6) RL Training

```bash
# Train PPO agent
python scripts/train_crypto_rl.py

# Continuous AutoML scheduler (runs in background)
# Automatically triggered on server startup
```

---

## Testing

```bash
# Full test suite (80 tests)
python -m pytest tests/ -q

# Specific test suites
python -m pytest tests/test_advanced_modules.py -q      # XAI, Autonomy, Experience Replay (39 tests)
python -m pytest tests/test_online_learner.py -q        # Online learning + ADWIN (20 tests)
python -m pytest tests/test_performance.py -q           # Performance benchmarks (22 tests)
python -m pytest tests/test_explainability.py -q        # XAI explainability (15 tests)

# Frontend
cd frontend && npm run build && npm run test
```

---

## Teknologi

### Frontend
React 18 · Vite 5 · lightweight-charts · Zustand · Vitest

### Backend & ML
Python 3.10+ · FastAPI · Uvicorn · pandas · numpy · scikit-learn
Stable-Baselines3 (PPO/SAC) · Transformers · PyTorch · LightGBM
CCXT · pandas-ta · river (online learning) · Optuna (AutoML)
Redis · PostgreSQL · Celery · APScheduler

### Deployment
Docker · Docker Compose · Nginx · Oracle Cloud ARM64 (Always Free)

---

## Program PM Multi-AI

Eksekusi proyek dijalankan dengan pola IT PM lintas 10 peran:

- **IT Expert AI/ML** — kualitas inferensi model, fallback, evaluasi sinyal
- **IT Algoritm Expert** — logika ranking, heuristic, overlay regime
- **IT Developer App** — kompatibilitas kontrak API ke frontend
- **IT Expert Python** — refactor pythonic, maintainability, test coverage
- **IT Programming Expert** — standar coding, struktur fungsi, readability
- **IT Fullstack Expert** — sinkronisasi UI ↔ backend behavior
- **IT UI/UX Expert** — keterbacaan insight AI pada UI
- **IT Architecture Expert** — pengurangan god-file, pemisahan concern
- **IT API Expert** — konsistensi schema endpoint, fallback contract
- **IT Backend Expert** — stabilitas runtime, error safety, observability

---

## Kontribusi

Lihat [CONTRIBUTING.md](CONTRIBUTING.md) untuk pedoman kontribusi, standar commit, validasi test, dan aturan keamanan.

## Lisensi

Proyek ini menggunakan lisensi MIT. Lihat [LICENSE](LICENSE) untuk detail.
# 📈 AutoSaham - Autonomous Trading Toolkit for Indonesia Stock Exchange (IDX)

## 📝 Deskripsi Proyek

**AutoSaham** adalah toolkit perdagangan otomatis dan pembelajaran mesin yang dirancang khusus untuk **Bursa Efek Indonesia (BEI) / Indonesia Stock Exchange (IDX)**. Platform ini mengintegrasikan pemrosesan data real-time, rekayasa fitur canggih, pelatihan model ML (supervised + reinforcement learning), dan eksekusi perdagangan yang aman dengan kepatuhan penuh terhadap regulasi IDX.

**Fokus Utama:**
- 🇮🇩 **Indonesia-First**: Timezone Jakarta (WIB: UTC+7), mata uang IDR, simbol IDX (*.JK), aturan BEI (jam trading 09:30-16:00 WIB)
- 🤖 **Machine Learning**: Ensemble models, online learning, meta-learning, anomaly detection, RL trading agents
- 📊 **Real-Time Data**: Integrasi resmi BEI API (RTI), WebSocket streaming, penghitungan OHLCV real-time
- 📈 **Production-Ready**: CI/CD otomatis, monitoring Prometheus+Grafana, load testing, broker integration
- 🎨 **Modern UI/UX**: TradingView charts, dashboard explainability, responsive design, PWA support
- 🔒 **Safe Execution**: Validasi order IDX, manajemen risiko, tracking settlement T+2, logging komprehensif

---

## ⭐ Fitur Utama

### Phase 1: Foundation (✅ COMPLETE)
- ✅ Triple-barrier labeling untuk kualitas label yang lebih baik
- ✅ News sentiment integration (VADER + FinBERT)
- ✅ Market microstructure features
- ✅ Interactive setup wizard untuk kemudahan onboarding
- ✅ Production-grade error handling & logging
- ✅ Model ensemble (stacking) untuk robustness

### Phase 2: Advanced ML (✅ COMPLETE)
- ✅ Online learning pipeline dengan drift detection
- ✅ Meta-learning untuk adaptasi symbol baru
- ✅ Anomaly detection (Isolation Forest + Autoencoder)
- ✅ HMM-based market regime detection
- ✅ RL policy training (PPO + SAC) dengan multi-symbol environment

### Phase 3: Production Ready (✅ COMPLETE)
- ✅ Official IDX API integration (BEI RTI WebSocket)
- ✅ Real broker integration (Stockbit, Ajaib, Indo Premier)
- ✅ Monitoring & alerting (Prometheus + Grafana + Slack)
- ✅ GitHub Actions CI/CD pipeline with Docker
- ✅ Load testing & performance optimization (Locust + pytest-benchmark)

### Phase 4: UI/UX Enhancement (🚀 IN PROGRESS - 4/5)
- ✅ TradingView charts (lightweight-charts, real-time WebSocket, 8 timeframes)
- ✅ Model explainability dashboard (SHAP TreeExplainer, feature importance, prediction explanation)
- ✅ Mobile-responsive design (PWA, Service Worker, offline support) - TASK 18 ✅
- ✅ Real-time notification system (WebSocket, Slack/email alerts) - TASK 19
- ⏳ Accessibility compliance (WCAG AA+, keyboard navigation) - TASK 20

### 🌟 Key Capabilities
```
Data Processing:
  • Real-time OHLCV aggregation dari ticks IDX
  • News sentiment analysis (multi-source)
  • Microstructure features (VWAP, order imbalance)
  • Feature caching & optimization

Machine Learning:
  • Ensemble models (LightGBM, XGBoost, Random Forest)
  • Online learning dengan concept drift detection
  • Meta-learning untuk new symbols (few-shot)
  • Anomaly detection dalam trading volume & price
  • HMM regime detection (bull/bear/sideways)

Reinforcement Learning:
  • PPO & SAC agents untuk trading
  • Multi-symbol environment
  • Risk-aware reward shaping
  • Sharpe ratio optimization

Execution & Risk:
  • IDX order validation (lot size, price limits, hours)
  • Multi-broker integration (Stockbit, Ajaib, Indo Premier)
  • Position sizing berdasarkan anomaly/regime
  • T+2 settlement tracking
  • Commission & slippage modeling

Monitoring:
  • 23+ Prometheus alert rules
  • Grafana dashboards (Trading, Broker, Strategy)
  • Slack notifications dengan color coding
  • Performance tracking (latency, accuracy, P&L)

UI/UX:
  • Professional TradingView charts (8 timeframes)
  • SHAP-based explainability dashboard
  • Progressive Web App (PWA) capabilities
    ✓ Install-to-home-screen on iOS/Android/Desktop
    ✓ Offline-first with 4 intelligent caching strategies
    ✓ Background sync for pending trades
    ✓ Push notifications for trading alerts
    ✓ 6 responsive breakpoints (320px-4K)
    ✓ Touch-optimized interface
    ✓ Safe area support for notched devices
  • Service Worker for offline functionality
  • Real-time metrics & alerts
  • Responsive design (320px to 4K)
  • Dark/light theme support
```

---

## 📋 Prasyarat (Prerequisites)

### System Requirements
- **OS**: Windows, macOS, atau Linux
- **Python**: 3.10 atau lebih baru
- **Node.js**: 16+ (untuk frontend React)
- **Git**: Untuk version control

### Software Dependencies
```bash
# Core ML & Data Processing
python -m pip install pandas numpy scikit-learn
python -m pip install lightgbm xgboost catboost
python -m pip install torch transformers vaderSentiment
python -m pip install shap optuna river

# Reinforcement Learning
python -m pip install stable-baselines3 gymnasium

# API & Web Framework
python -m pip install fastapi uvicorn pydantic
python -m pip install websockets aiohttp

# Monitoring & Logging
python -m pip install prometheus-client structlog

# Testing & Quality
python -m pip install pytest pytest-cov pytest-asyncio pytest-benchmark
python -m pip install black isort flake8 mypy bandit

# Frontend
npm install react react-dom vite lightweight-charts axios
npm install -D tailwindcss postcss autoprefixer

# Optional: Docker & Compose
docker --version
docker-compose --version
```

### External APIs & Keys (Optional)
```
# BEI Official API
- BEI RTI account & credentials

# Broker APIs
- Stockbit: API key
- Ajaib: API credentials  
- Indo Premier: Session credentials

# News & Sentiment
- NewsAPI: API key
- Financial data providers if using alternative sources
```

---

## ⚙️ Cara Instalasi (Installation)

### 1. Clone Repository
```bash
git clone https://github.com/santz1994/AutoProjectSaham.git
cd AutoProjectSaham
```

### 2. Setup Python Environment (Recommended: venv)
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 4. Setup Frontend (React)
```bash
cd frontend
npm install
npm run build  # Production build
# atau untuk development: npm run dev
```

### 5. Configure Environment Variables
```bash
# Copy template
cp .env.example .env

# Edit .env dengan credentials Anda:
# BEI_API_KEY=your_key
# STOCKBIT_API_KEY=your_key
# AJAIB_API_KEY=your_key
# NEWS_API_KEY=your_key
# SLACK_WEBHOOK_URL=your_webhook
```

### 6. Initialize Database (jika diperlukan)
```bash
python scripts/init_database.py
```

### 7. Run Tests untuk Verifikasi
```bash
pytest tests/ -v --cov=src
```

---

## 💻 Cara Penggunaan (Usage)

### Quick Start - Main CLI
```bash
# Dengan mode demo (tidak memerlukan API keys)
python -m src.main --demo

# Dengan data real (memerlukan credentials)
python -m src.main --symbols BBCA.JK,BMRI.JK,TLKM.JK
```

### Windows GUI (Tkinter)
```bash
# Buka control panel untuk menjalankan tasks secara visual
python -m src.ui.windows_app
```

### Run Scripts
```bash
# Generate demo price data
python bin/runner.py scripts/generate_demo_prices.py -- --symbols BBCA.JK TLKM.JK --n 300

# Test execution manager
python bin/runner.py scripts/test_execution_manager.py

# Train model
python bin/runner.py scripts/train_model.py -- --limit 3

# Run backtester
python bin/runner.py scripts/test_backtester.py

# Start metrics server (Prometheus)
python bin/runner.py scripts/start_metrics_server.py
```

### Python API Usage
```python
from src.pipeline.runner import AutonomousPipeline
from src.ml.ensemble import EnsembleModel
from src.execution.execution_manager import ExecutionManager

# 1. Run autonomous pipeline
runner = AutonomousPipeline()
result = runner.run(
    symbols=['BBCA.JK', 'BMRI.JK'],
    fetch_prices=True,
    news_api_key='your_key'
)

# 2. Get ensemble predictions
model = EnsembleModel()
model.load('models/ensemble_model.pkl')
predictions = model.predict(features_df)

# 3. Execute trades safely
executor = ExecutionManager(broker='stockbit')
order = executor.place_order(
    symbol='BBCA.JK',
    side='BUY',
    quantity=100,
    order_type='LIMIT',
    price=15500
)
```

### Start Development Server (Frontend + Backend)
```bash
# Terminal 1: Start FastAPI backend
python -m src.api.server

# Terminal 2: Start React development server
cd frontend && npm run dev

# Access:
# - Frontend: http://localhost:5173
# - API: http://localhost:8000
# - API Docs: http://localhost:8000/docs
```

### Docker Deployment
```bash
# Build & run dengan Docker Compose
docker-compose up -d

# Access services:
# - API: http://localhost:8000
# - Grafana: http://localhost:3000 (admin/password)
# - Prometheus: http://localhost:9090
# - AlertManager: http://localhost:9093
```

### Load Testing
```bash
# Start API server first
python -m src.api.server &

# Run Locust interactive UI
locust -f tests/load_tests/locustfile.py --host=http://localhost:8000

# Or headless testing
locust -f tests/load_tests/locustfile.py --host=http://localhost:8000 \
  --users=100 --spawn-rate=10 --run-time=5m --headless
```

### TradingView Charts API
```bash
# Get chart metadata
curl http://localhost:8000/api/charts/metadata/BBCA.JK

# Get OHLCV candles
curl "http://localhost:8000/api/charts/candles/BBCA.JK?timeframe=1d&limit=100"

# Trading status
curl http://localhost:8000/api/charts/trading-status

# WebSocket real-time updates
ws://localhost:8000/ws/charts/BBCA.JK
```

### Model Explainability API
```bash
# Top features
curl http://localhost:8000/api/explainability/features?limit=20

# Explain prediction
curl -X POST http://localhost:8000/api/explainability/explain \
  -H "Content-Type: application/json" \
  -d '{
    "features": {"BBCA_volume": 15000000, "sentiment": 0.7},
    "top_features": 10
  }'

# Feature analysis
curl http://localhost:8000/api/explainability/feature/market_sentiment

# Model metrics
curl http://localhost:8000/api/explainability/metrics
```

### React Component Usage Examples
```jsx
// TradingView Chart
import ChartComponent from './components/ChartComponent';
export default function Dashboard() {
  return <ChartComponent symbol="BBCA.JK" timeframe="1d" theme="dark" />;
}

// Model Explainability Dashboard
import ExplainabilityDashboard from './components/ExplainabilityDashboard';
export default function Analytics() {
  return <ExplainabilityDashboard theme="dark" autoRefresh={true} />;
}
```

---

## 📦 Project Structure

```
AutoProjectSaham/
├── bin/                      # Executable runners
│   └── runner.py            # Python script runner
├── src/                      # Source code
│   ├── api/                 # API routes & services
│   │   ├── chart_service.py            # TradingView charts
│   │   ├── chart_routes.py
│   │   ├── explainability_service.py   # SHAP integration
│   │   ├── explainability_routes.py
│   │   └── ... (server, auth, error_handler)
│   ├── ml/                  # Machine learning
│   │   ├── barriers.py           # Triple-barrier labeling
│   │   ├── sentiment_features.py # News sentiment
│   │   ├── microstructure.py     # Market features
│   │   ├── ensemble.py           # Model ensemble
│   │   ├── online_learner.py     # Online learning
│   │   ├── meta_learning.py      # Meta-learning
│   │   ├── anomaly_detector.py   # Anomaly detection
│   │   └── regime_detector.py    # Market regime
│   ├── rl/                  # Reinforcement learning
│   │   ├── policy_trainer.py     # PPO/SAC training
│   │   ├── agent_integration.py  # RL agent wrapper
│   │   └── ... (environments, rewards)
│   ├── execution/           # Trade execution & validation
│   │   ├── execution_manager.py  # Order execution
│   │   ├── idx_order_validator.py
│   │   └── ... (validators, settlement)
│   ├── brokers/             # Broker integrations
│   │   ├── stockbit.py      # Stockbit adapter
│   │   ├── ajaib.py         # Ajaib adapter
│   │   ├── indo_premier.py  # Indo Premier adapter
│   │   └── ... (base, manager)
│   ├── data/                # Data connectors & IDX API
│   │   ├── idx_api_client.py        # BEI RTI client
│   │   ├── idx_market_data.py       # Market data mgr
│   │   └── ... (yahoo, news, connectors)
│   ├── pipeline/            # ETL & data pipeline
│   │   ├── runner.py               # Main ETL runner
│   │   ├── idx_realtime_fetcher.py # Streaming fetcher
│   │   └── ... (scheduler, persistence)
│   ├── monitoring/          # Metrics & observability
│   │   └── metrics.py              # Prometheus metrics
│   └── utils/               # Utilities
│       └── ... (datetime, validation, performance)
├── frontend/                # React UI
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChartComponent.jsx
│   │   │   ├── ExplainabilityDashboard.jsx
│   │   │   └── ... (other components)
│   │   ├── hooks/
│   │   │   ├── useChartData.js
│   │   │   └── ... (other custom hooks)
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
├── tests/                   # Test suite
│   ├── test_*.py           # Unit tests
│   ├── integration/        # Integration tests
│   ├── load_tests/         # Locust load tests
│   └── ... (35+ test modules)
├── scripts/                # Utility scripts
│   ├── generate_demo_prices.py
│   ├── train_model.py
│   ├── train_rl.py
│   └── ... (10+ scripts)
├── docs/                   # Documentation
│   ├── PHASE1_COMPLETION_REPORT.md
│   ├── INTEGRATION_TEST_FIX.md
│   └── ... (architecture docs)
├── data/                   # Data files
│   ├── dataset/
│   ├── features/
│   └── prices/
├── models/                 # Trained models
│   ├── model.joblib
│   ├── ensemble_test.joblib
│   └── rl_ppo_config.json
├── logs/                   # Log files (gitignored)
├── requirements.txt        # Python dependencies
├── package.json           # Python project metadata
├── Dockerfile             # Docker configuration
├── docker-compose.yml     # Multi-container setup
├── .gitignore            # Git ignore patterns
├── .env.example          # Environment template
├── PROGRESS.md           # Development progress tracker
├── README.md             # This file
└── LICENSE               # MIT License
```

---

## 🤝 Kontribusi (Contributing)

### Guidelines untuk Contributors

1. **Sebelum commit:**
   ```bash
   # Run tests
   pytest tests/ -v
   
   # Check code style
   black src/ tests/
   isort src/ tests/
   flake8 src/
   mypy src/
   
   # Security check
   bandit -r src/
   ```

2. **Commit messages:**
   - Format: `[PHASE#TASK#] Short description`
   - Contoh: `[P4T18] Add PWA Service Worker`

3. **Pull request process:**
   - Create branch: `git checkout -b feature/task-description`
   - Make changes
   - Add tests untuk new features
   - Update PROGRESS.md
   - Submit PR dengan deskripsi lengkap

4. **Code standards:**
   - Type hints on all functions
   - NumPy-style docstrings
   - >80% test coverage untuk critical paths
   - Jakarta timezone awareness untuk time-related code
   - IDX compliance checks dalam order validation

### Development Workflow
```bash
# 1. Update task dalam PROGRESS.md
# 2. Create feature branch
git checkout -b p4t18-pwa-responsive

# 3. Implement changes
# 4. Add/update tests
pytest tests/ -v

# 5. Commit dengan format yang benar
git commit -m "[P4T18] Add PWA Service Worker & offline support"

# 6. Push dan create PR
git push origin p4t18-pwa-responsive
```

---

## 📄 Lisensi (License)

**AutoSaham** adalah open-source software berlisensi **MIT License**.

```
MIT License

Copyright (c) 2026 AutoSaham Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software...

[Full license text in LICENSE file]
```

---

## 📞 Kontak (Contact)

**Developer:** Daniel Rizaldy  
**Email:** danielrizaldy@gmail.com  
**Phone:** +6281287412570  
**GitHub:** [@santz1994](https://github.com/santz1994)

### Informasi Proyek
- **Repository**: [AutoProjectSaham](https://github.com/santz1994/AutoProjectSaham)
- **Status**: 🚀 Phase 4 UI/UX Enhancement (95% complete - 19/20 tasks)
- **Last Updated**: 2026-04-01 UTC+7 (JAKARTA TIME)

### Support & Feedback
- 🐛 **Issues & Bugs**: [GitHub Issues](https://github.com/santz1994/AutoProjectSaham/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/santz1994/AutoProjectSaham/discussions)
- 📧 **Email**: danielrizaldy@gmail.com

---

## 🎯 Current Phase - Phase 4 UI/UX Enhancement

**Progress:** 4/5 (80%) - 95% Overall Project Complete! 🎉

### Completed
- ✅ **Task 16:** TradingView Charts (1,150+ lines) - Real-time OHLCV, 8 timeframes, WebSocket
- ✅ **Task 17:** Model Explainability Dashboard (1,884+ lines) - SHAP, feature importance, predictions  
- ✅ **Task 18:** Mobile-Responsive Design & PWA (3,850+ lines) - Service Worker, offline support, 6 responsive breakpoints (320px-4K)
- ✅ **Task 19:** Real-time Notification System (3,700+ lines) - WebSocket, Email, Slack, Push, SMS, In-App alerts; Multi-channel delivery; Jakarta TZ (BEI 09:30-16:00 WIB)

### In Progress
- ⏳ **Task 20:** Accessibility Compliance - WCAG AAA, keyboard navigation, screen reader support

---

**Made with ❤️ for Indonesian traders | Dibangun untuk para trader Indonesia**
# AutoSaham

AutoSaham is a prototype autonomous trading toolkit focused on the Indonesia Stock Exchange (IDX).

This repository contains modular components for data ingestion, feature engineering, model training (supervised + RL), backtesting, and safe execution.

Quick overview
- `src/pipeline` — ETL connectors, batch fetcher, runner, scheduler, and persistence helpers.
- `src/ml` — feature store helpers, `PurgedTimeSeriesSplit` (purged CV), and a lightweight Optuna wrapper.
- `src/execution` — `ExecutionManager` enforcing IDX rules, pending-limit bookkeeping, and reconciliation loop.
- `src/brokers` — adapter interfaces, `PaperBrokerAdapter`, and a retry wrapper for adapters.
- `tests` — unit tests that verify core behaviors across modules.

Getting started

1. Install dependencies (recommended in a venv):

```bash
python -m pip install -r requirements.txt
```

2. Run the test suite:

```bash
python -m unittest discover -v
```

3. Run the autonomous ETL once (example):

```python
from src.pipeline.runner import AutonomousPipeline
runner = AutonomousPipeline()
res = runner.run(['BBCA.JK', 'TLKM.JK'], fetch_prices=False, news_api_key=None)
print(res)
```

Docs & next steps
- `Docs & suggestions review` is in-progress. Recommended immediate items:
  - Harden connectors (official IDX APIs) and credential handling.
  - Add CI secrets/config for external APIs used by live tests.
  - Implement a FastAPI backend to expose metrics, run jobs, and provide a safe operator UI.

Contributing
- Run tests before committing and keep changes focused (see `tests/`).

License
- MIT
# AutoSaham — Prototype trading stack

Quickstart commands and recommended runner usage.

Run the main CLI (preferred):

```bash
python -m src.main --demo
```

Run scripts using the repository runner so `src` imports resolve consistently:

```bash
python bin/runner.py scripts/generate_demo_prices.py -- --symbols BBCA.JK TLKM.JK BMRI.JK --n 300
python bin/runner.py scripts/test_execution_manager.py
python bin/runner.py scripts/test_backtester.py
python bin/runner.py scripts/train_model.py -- --limit 3

Windows GUI
--------------
There is a minimal Tkinter control panel at `src/ui/windows_app.py` that
lets you run common tasks and view logs. Launch it with:

```bash
python -m src.ui.windows_app
```

Monitoring & Alerts
-------------------
The project uses Prometheus + Grafana + AlertManager for production monitoring:

```bash
# Start monitoring stack
docker-compose up -d

# Access services
# - API: http://localhost:8000
# - Grafana: http://localhost:3000 (admin/password from .env)
# - Prometheus: http://localhost:9090
# - AlertManager: http://localhost:9093
```

Load Testing & Performance
--------------------------
Run Locust load tests to validate performance under production load:

```bash
# Install load testing dependencies
pip install locust pytest-benchmark

# Run Locust web UI (interactive)
locust -f tests/load_tests/locustfile.py --host=http://localhost:8000

# Run from command line (headless)
locust -f tests/load_tests/locustfile.py --host=http://localhost:8000 \
  --users=100 --spawn-rate=10 --run-time=5m --headless

# Run performance benchmarks
pytest tests/test_performance.py -v --benchmark-only
pytest tests/test_performance.py --benchmark-save=baseline
```

Load test validates:
- IDX compliance (*.JK symbols, IDR currency, 100 lot minimum)
- All broker integrations (Stockbit, Ajaib, Indo Premier)
- Response time thresholds (market data <100ms, orders <500ms, positions <200ms)
- Cache hit ratios (target >80%)
- Concurrent user stability (100+ users)

CI/CD Pipeline
--------------
GitHub Actions workflow automates testing, quality checks, and deployment:

```bash
# Workflow file: .github/workflows/ci-cd.yml
# Jobs: test, code-quality, security, docker-build, performance, notify

# Run locally
pytest tests/ -v --cov=src  # Run all tests with coverage
black src/ tests/           # Format code
flake8 src/                 # Lint
mypy src/                   # Type check
```

Monitoring
----------
The project exposes Prometheus metrics using `src.monitoring.metrics`. Start
the metrics HTTP endpoint with:

```bash
python bin/runner.py scripts/start_metrics_server.py
```

CI
--
A GitHub Actions CI workflow is included at `.github/workflows/ci-cd.yml` with:
- Automated testing (unit + integration)
- Code quality checks (Black, isort, Flake8, MyPy)
- Security scanning (Bandit)
- Docker build and push
- Performance benchmarking

Notes
- Use `python -m src.main` for long-running pipeline runs.
- The `bin/runner.py` wrapper inserts the project root on `sys.path` and executes a script.
- For production, deploy using Docker Compose (see `docker-compose.yml`).
- Jakarta timezone (WIB: UTC+7) used throughout. IDX/IHSG/IDR/BEI compliance enforced.


What this scaffold contains
- `src/pipeline` — data connectors (IDX, forex, news) and ETL orchestrator.
- `src/ml` — training & model utilities (placeholder).
- `src/execution` — broker interface and `PaperBroker` simulator.
- `src/strategies` — example SMA-based strategy (scalping/daily starter).
- `src/backtest` — simple backtester.

Notes
- This is a starter scaffold. Connectors include placeholders and lazy imports so you can install only what you need.
- For real trading, integrate a broker API and add risk controls and compliance checks.
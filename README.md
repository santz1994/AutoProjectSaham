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

Monitoring
----------
The project exposes Prometheus metrics using `src.monitoring.metrics`. Start
the metrics HTTP endpoint with:

```bash
python bin/runner.py scripts/start_metrics_server.py
```

CI
--
A small GitHub Actions CI workflow is included at `.github/workflows/ci.yml`.

```

Notes
- Use `python -m src.main` for long-running pipeline runs.
- The `bin/runner.py` wrapper inserts the project root on `sys.path` and executes a script.
- For production, prefer running code as packages or install the project into a virtualenv.
AutoSaham — Autonomous Trading Research & Execution

Quickstart
- Create a Python virtualenv and activate it.
- Install dependencies: `pip install -r requirements.txt` (optional for full features).
- Copy `.env.example` to `.env` and set API keys.
- Run a quick demo: `python -m src.main --demo`

What this scaffold contains
- `src/pipeline` — data connectors (IDX, forex, news) and ETL orchestrator.
- `src/ml` — training & model utilities (placeholder).
- `src/execution` — broker interface and `PaperBroker` simulator.
- `src/strategies` — example SMA-based strategy (scalping/daily starter).
- `src/backtest` — simple backtester.

Notes
- This is a starter scaffold. Connectors include placeholders and lazy imports so you can install only what you need.
- For real trading, integrate a broker API and add risk controls and compliance checks.
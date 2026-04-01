# Market data and ML trainer: configuration & run notes

This document describes how to configure and run the market-data adapter
and the ML trainer service included with the project.

Environment variables
- `MARKET_SYMBOLS` — comma-separated symbols to subscribe to (default: `AAPL,SPY`).
- `TICKS_DB_PATH` — path to the SQLite ticks DB (default: `data/ticks.db`).
- `MODELS_DIR` — directory where trained artifacts are written (default: `models`).
- `ML_TRAIN_INTERVAL` — trainer cadence in seconds (default: `86400` — 24h).
- `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_BASE_URL` — optional Alpaca credentials.

Notes
- If Alpaca libraries/credentials are not available the adapter falls back to a
  deterministic synthetic tick generator so the rest of the system (UI, trainer)
  can be exercised locally.
- Ticks are persisted to a small SQLite DB at `TICKS_DB_PATH` and used to
  construct datasets for the trainer.

Quick run

1. (Optional) create a `.env` file or export the environment variables.
2. Start the backend API:

```powershell
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8001
```

3. (Optional) trigger a one-off training run:

```powershell
curl -X POST http://127.0.0.1:8001/api/training/trigger
```

4. Inspect trained models under the `models/` directory and the persisted
   `data/ticks.db` SQLite database.

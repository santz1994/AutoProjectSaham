"""Minimal FastAPI server for AutoSaham.

Endpoints:
 - GET /health
 - POST /run_etl  (body: symbols, fetch_prices, persist_db)
 - POST /scheduler/start
 - POST /scheduler/stop

This module is safe to import when FastAPI is not installed: it provides
a helpful runtime error when the API is invoked without FastAPI.
"""
from __future__ import annotations

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel

    FASTAPI_AVAILABLE = True
except Exception:
    FASTAPI_AVAILABLE = False


if FASTAPI_AVAILABLE:
    import asyncio
    import os
    from time import time
    from typing import List, Optional

    from fastapi import WebSocket, WebSocketDisconnect, Header
    from fastapi.responses import Response, RedirectResponse
    from fastapi.staticfiles import StaticFiles

    from src.alerts.webhook import send_alert_webhook
    from src.api.event_queue import pop_events
    from src.monitoring import metrics as monitoring
    from src.pipeline.persistence import read_etl_runs
    from src.pipeline.runner import AutonomousPipeline
    from src.pipeline.scheduler import PipelineScheduler
    from src.brokers.paper_adapter import PaperBrokerAdapter
    from src.api.auth import register_user, authenticate_user, get_user_from_token

    app = FastAPI(title="AutoSaham API", version="0.1")

    # single shared pipeline instance for the server
    pipeline = AutonomousPipeline()
    _scheduler: Optional[PipelineScheduler] = None
    # Background services (initialized on application startup)
    market_service = None
    ml_service = None

    # Serve a built SPA (if present) at /ui. For development, run Vite separately.
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    frontend_dist = os.path.join(project_root, "frontend", "dist")
    if os.path.isdir(frontend_dist):
        app.mount("/ui", StaticFiles(directory=frontend_dist, html=True), name="frontend")
        # serve the build's assets also at /assets so index.html can reference
        # absolute paths like `/assets/...` produced by Vite.
        assets_dir = os.path.join(frontend_dist, "assets")
        if os.path.isdir(assets_dir):
            app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

        @app.get("/", include_in_schema=False)
        async def root():
            return RedirectResponse(url="/ui/")

    class RunPayload(BaseModel):
        symbols: List[str]
        fetch_prices: Optional[bool] = True
        persist_db: Optional[str] = None

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/run_etl")
    async def run_etl(payload: RunPayload):
        start = time()
        try:
            res = pipeline.run(
                payload.symbols,
                fetch_prices=payload.fetch_prices,
                persist_db=payload.persist_db,
            )
            duration = time() - start
            try:
                monitoring.record_etl_run(duration_seconds=duration, success=True)
            except Exception:
                pass
            return res
        except Exception as e:
            duration = time() - start
            try:
                monitoring.record_etl_run(duration_seconds=duration, success=False)
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/metrics")
    async def metrics_endpoint():
        try:
            payload, content_type = monitoring.metrics_text()
        except Exception:
            raise HTTPException(
                status_code=501, detail="prometheus_client not installed"
            )
        return Response(content=payload, media_type=content_type)

    @app.get("/etl_runs")
    async def etl_runs(limit: int = 50):
        try:
            runs = read_etl_runs(limit=limit)
            return {
                "runs": runs,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/portfolio")
    async def api_portfolio(authorization: Optional[str] = Header(None)):
        """Return a broker reconciliation snapshot.

        If the request includes a valid `Authorization: Bearer <token>` header
        that maps to a registered user, this could return a user-specific
        portfolio (when adapters are implemented). For now, we return a demo
        `PaperBroker` snapshot when unauthenticated.
        """
        try:
            user = None
            if authorization:
                token = authorization.split(" ", 1)[1] if authorization.lower().startswith("bearer ") else authorization
                user = get_user_from_token(token)

            adapter = PaperBrokerAdapter(starting_cash=10000.0)
            adapter.connect()
            snap = adapter.reconcile()
            adapter.disconnect()
            if user:
                # annotate with username for demo purposes
                return {"portfolio": snap, "user": user}
            return {"portfolio": snap}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    class UserPayload(BaseModel):
        username: str
        password: str

    @app.post("/auth/register")
    async def auth_register(payload: UserPayload):
        try:
            register_user(payload.username, payload.password)
            return {"status": "ok"}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/auth/login")
    async def auth_login(payload: UserPayload):
        token = authenticate_user(payload.username, payload.password)
        if not token:
            raise HTTPException(status_code=401, detail="invalid_credentials")
        return {"access_token": token, "token_type": "bearer"}

    @app.get("/auth/me")
    async def auth_me(authorization: Optional[str] = Header(None)):
        if not authorization:
            raise HTTPException(status_code=401, detail="missing_authorization")
        token = authorization.split(" ", 1)[1] if authorization.lower().startswith("bearer ") else authorization
        user = get_user_from_token(token)
        if not user:
            raise HTTPException(status_code=401, detail="invalid_token")
        return {"username": user}

    @app.get("/api/training")
    async def api_training(limit: int = 50):
        """Return recent training artifacts from `models/`.

        Scans the repository `models/` directory for model files and returns a
        concise metadata list (path, mtime, size). If a model file can be
        loaded with `joblib` and exposes a small metadata dict (e.g. keys
        `features`/`tuned`) those fields are included. Loading is best-effort
        and failures are ignored to keep this endpoint safe for quick inspection.
        """
        try:
            import glob

            models_dir = os.path.join(project_root, "models")
            if not os.path.isdir(models_dir):
                return {"runs": []}

            patterns = ["*.joblib", "*.pkl", "*.model"]
            matches = []
            for pat in patterns:
                matches.extend(glob.glob(os.path.join(models_dir, pat)))

            # sort by mtime desc and trim
            matches = sorted(matches, key=lambda p: os.path.getmtime(p), reverse=True)[: int(limit) if limit else 50]

            runs = []
            for p in matches:
                try:
                    st = os.stat(p)
                    item = {
                        "path": os.path.relpath(p, project_root),
                        "mtime": int(st.st_mtime),
                        "size": int(st.st_size),
                    }
                    # best-effort: attempt to read small metadata from joblib/pickle
                    try:
                        try:
                            import joblib

                            loaded = joblib.load(p)
                        except Exception:
                            # fallback to pickle load
                            import pickle

                            with open(p, "rb") as fh:
                                loaded = pickle.load(fh)

                        if isinstance(loaded, dict):
                            meta = {}
                            if "features" in loaded:
                                meta["feature_count"] = len(loaded.get("features") or [])
                            if "tuned" in loaded:
                                meta["tuned"] = bool(loaded.get("tuned"))
                            if meta:
                                item["meta"] = meta
                    except Exception:
                        # ignore load errors
                        pass

                    runs.append(item)
                except Exception:
                    continue

            return {"runs": runs}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    class AlertPayload(BaseModel):
        url: str
        message: str
        level: Optional[str] = "info"

    @app.post("/alert")
    async def alert_endpoint(payload: AlertPayload):
        try:
            payload_body = {
                "message": payload.message,
                "level": payload.level,
            }
            sent = send_alert_webhook(payload.url, payload_body)
            if not sent:
                raise HTTPException(status_code=502, detail="alert delivery failed")
            return {"status": "sent"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/scheduler/start")
    async def start_scheduler(symbols: List[str], interval_seconds: float = 3600.0):
        global _scheduler
        if (
            _scheduler
            and getattr(_scheduler, "_thread", None)
            and getattr(_scheduler, "_thread").is_alive()
        ):
            raise HTTPException(status_code=400, detail="Scheduler already running")
        _scheduler = PipelineScheduler(
            pipeline,
            symbols=symbols,
            interval_seconds=interval_seconds,
        )
        _scheduler.start()
        return {"status": "started"}

    @app.post("/scheduler/stop")
    async def stop_scheduler():
        global _scheduler
        if not _scheduler:
            raise HTTPException(status_code=400, detail="Scheduler not running")
        _scheduler.stop()
        _scheduler = None
        return {"status": "stopped"}

    @app.websocket("/ws/events")
    async def websocket_events(ws: WebSocket):
        await ws.accept()
        try:
            # poll the in-memory event queue and forward events to client
            while True:
                await asyncio.sleep(0.5)
                try:
                    evs = pop_events()
                except Exception:
                    evs = []
                for ev in evs:
                    try:
                        await ws.send_json(ev)
                    except Exception:
                        # if sending fails, the client may have disconnected
                        pass
        except WebSocketDisconnect:
            return

    @app.on_event("startup")
    async def startup_services():
        """Start optional background services: market data ingestion
        and ML trainer. These are best-effort: failures won't prevent the
        API from starting so a developer can run the server in a limited
        environment.
        """
        nonlocal_vars = globals()
        try:
            import os

            symbols_env = os.getenv("MARKET_SYMBOLS", "AAPL,SPY")
            symbols = [s.strip() for s in symbols_env.split(",") if s.strip()]
            from src.brokers.marketdata import AlpacaMarketDataAdapter
            from src.marketdata.service import MarketDataService

            adapter = AlpacaMarketDataAdapter(symbols=symbols)
            ms = MarketDataService(adapter=adapter, db_path=os.path.join(project_root, "data", "ticks.db"))
            ms.start()
            nonlocal_vars["market_service"] = ms
        except Exception:
            # do not fail startup on optional services
            pass

        try:
            from src.ml.service import MLTrainerService

            interval = int(os.getenv("ML_TRAIN_INTERVAL", str(24 * 3600)))
            mls = MLTrainerService(schedule_seconds=interval, db_path=os.path.join(project_root, "data", "ticks.db"), models_dir=os.path.join(project_root, "models"))
            mls.start()
            nonlocal_vars["ml_service"] = mls
        except Exception:
            pass

    @app.on_event("shutdown")
    async def shutdown_services():
        """Stop background services cleanly on shutdown."""
        nonlocal_vars = globals()
        try:
            ms = nonlocal_vars.get("market_service")
            if ms:
                try:
                    ms.stop()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            mls = nonlocal_vars.get("ml_service")
            if mls:
                try:
                    mls.stop()
                except Exception:
                    pass
        except Exception:
            pass

    @app.post("/api/training/trigger")
    async def api_training_trigger():
        """Trigger an immediate training run. The run is executed in a
        threadpool so the endpoint returns promptly.
        """
        try:
            import asyncio

            nonlocal_vars = globals()
            mls = nonlocal_vars.get("ml_service")
            if mls:
                await asyncio.get_event_loop().run_in_executor(None, mls.run_once)
                return {"status": "scheduled"}
            else:
                # fallback: run a single training execution synchronously in a worker
                from src.ml.service import MLTrainerService

                ms = MLTrainerService(schedule_seconds=0, db_path=os.path.join(project_root, "data", "ticks.db"), models_dir=os.path.join(project_root, "models"))
                await asyncio.get_event_loop().run_in_executor(None, ms.run_once)
                return {"status": "trained"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

else:
    # Friendly placeholders when FastAPI is not installed.
    app = None

    def _missing_fastapi(*args, **kwargs):
        raise RuntimeError(
            "FastAPI is not installed. Install with "
            "pip install fastapi[all] to enable the API server."
        )

    def health():
        return _missing_fastapi()

    def run_etl(*args, **kwargs):
        return _missing_fastapi()

    def start_scheduler(*args, **kwargs):
        return _missing_fastapi()

    def stop_scheduler(*args, **kwargs):
        return _missing_fastapi()

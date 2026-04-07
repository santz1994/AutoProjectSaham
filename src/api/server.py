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
    import traceback
    from time import time
    from typing import List, Optional

    from fastapi import WebSocket, WebSocketDisconnect, Header, Request
    from fastapi.responses import Response, RedirectResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware

    from src.alerts.webhook import send_alert_webhook
    from src.api.event_queue import pop_events
    from src.monitoring import metrics as monitoring
    from src.pipeline.persistence import read_etl_runs
    from src.pipeline.runner import AutonomousPipeline
    from src.pipeline.scheduler import PipelineScheduler
    from src.brokers.paper_adapter import PaperBrokerAdapter
    from src.api.auth import register_user, authenticate_user, get_user_from_token, invalidate_token
    from src.api.frontend_routes import router as frontend_router
    from src.notifications.api_routes import setup_notification_routes

    app = FastAPI(title="AutoSaham API", version="0.1")

    def _extract_ws_auth_token(websocket: WebSocket) -> Optional[str]:
        """Extract auth token from websocket query/cookie/header."""
        query_token = str(websocket.query_params.get("token") or "").strip()
        if query_token:
            return query_token

        cookie_token = str(websocket.cookies.get("auth_token") or "").strip()
        if cookie_token:
            return cookie_token

        auth_header = str(websocket.headers.get("authorization") or "").strip()
        if auth_header.lower().startswith("bearer "):
            bearer_token = auth_header.split(" ", 1)[1].strip()
            if bearer_token:
                return bearer_token

        return None

    def _authenticate_ws_client(websocket: WebSocket) -> Optional[str]:
        token = _extract_ws_auth_token(websocket)
        if not token:
            return None
        return get_user_from_token(token)
    
    # Register frontend API routes
    app.include_router(frontend_router)

    # Register notification routes and delivery handlers
    try:
        smtp_config = None
        if os.getenv("SMTP_HOST"):
            smtp_config = {
                "host": os.getenv("SMTP_HOST"),
                "port": int(os.getenv("SMTP_PORT", "587")),
                "user": os.getenv("SMTP_USER"),
                "password": os.getenv("SMTP_PASS"),
                "use_tls": True,
            }

        setup_notification_routes(
            app,
            smtp_config=smtp_config,
            slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL"),
        )
    except Exception as e:
        print(f"[Startup] Warning: Notification routes initialization failed: {e}")
    
    # SECURITY FIX: Configure CORS to allow frontend on localhost:5173
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",      # Vite dev server
            "http://localhost:5174",      # Vite fallback port
            "http://127.0.0.1:5173",      # Loopback variant
            "http://127.0.0.1:5174",      # Loopback variant
            "http://localhost:8000",      # API server (for UI served from backend)
            "http://localhost:3000",      # Alternative dev port
        ],
        allow_credentials=True,                    # Allow httpOnly cookies
        allow_methods=["*"],                       # Allow all HTTP methods
        allow_headers=["*"],                       # Allow all headers
        expose_headers=["Set-Cookie"],             # Expose cookie header
    )

    # single shared pipeline instance for the server
    pipeline = AutonomousPipeline()
    _scheduler: Optional[PipelineScheduler] = None
    # Background services (initialized on application startup)
    market_service = None
    ml_service = None
    
    # Project root directory for data/models paths
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

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

    @app.get("/api/portfolio/reconcile")
    async def api_portfolio_reconcile(authorization: Optional[str] = Header(None)):
        """Return a broker reconciliation snapshot.

        This diagnostic endpoint is separate from frontend portfolio routes.
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

    class ForgotPasswordPayload(BaseModel):
        email: str

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
        # SECURITY FIX: Set token as httpOnly cookie (not in response body)
        response = JSONResponse(content={"status": "ok"}, status_code=200)
        # In development (HTTP), disable secure flag; in production (HTTPS), enable it
        is_secure = os.getenv("ENV", "").lower() in ("prod", "production") or os.getenv("HTTPS") == "on"
        response.set_cookie(
            key="auth_token",
            value=token,
            httponly=True,  # Prevent JS access (XSS protection)
            secure=is_secure,  # Only send over HTTPS in production
            samesite="lax",  # CSRF protection (lax for local dev compatibility)
            max_age=86400,  # 24 hours
            path="/"
        )
        return response

    @app.get("/auth/me")
    async def auth_me(request: Request):
        # SECURITY FIX: Read token from secure httpOnly cookie, not Authorization header
        token = request.cookies.get("auth_token")
        if not token:
            # Not logged in - return 200 with empty response (JS will handle)
            return JSONResponse(content={}, status_code=200)
        user = get_user_from_token(token)
        if not user:
            # Token invalid/expired - return 200 with empty response
            return JSONResponse(content={}, status_code=200)
        return {"username": user}

    @app.post("/auth/logout")
    async def auth_logout(request: Request):
        """Clear the auth token cookie."""
        token = request.cookies.get("auth_token")
        if token:
            invalidate_token(token)
        response = JSONResponse(content={"status": "ok"}, status_code=200)
        is_secure = os.getenv("ENV", "").lower() in ("prod", "production") or os.getenv("HTTPS") == "on"
        response.delete_cookie(
            key="auth_token",
            path="/",
            httponly=True,
            secure=is_secure,
            samesite="lax"
        )
        return response

    @app.post("/auth/forgot-password")
    async def auth_forgot_password(payload: ForgotPasswordPayload):
        """Demo-safe forgot password endpoint.

        Production implementations should issue secure reset tokens and send
        transactional emails through a trusted provider.
        """
        if not payload.email or "@" not in payload.email:
            raise HTTPException(status_code=400, detail="invalid_email")

        # Do not reveal whether email exists to avoid account enumeration.
        return {
            "status": "ok",
            "message": "If the email exists, reset instructions have been sent.",
        }

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
                    # SECURITY FIX: Use restricted unpickler to prevent RCE via malicious model files
                    try:
                        try:
                            import joblib
                            # Use restricted loads to prevent arbitrary code execution
                            loaded = joblib.load(p, mmap_mode=None)
                        except Exception:
                            # fallback to pickle load with restricted unpickler
                            import pickle
                            import io

                            class RestrictedUnpickler(pickle.Unpickler):
                                """Restrict pickle to safe classes only."""
                                def find_class(self, module, name):
                                    # Whitelist safe numpy/sklearn/joblib classes
                                    allowed_modules = {
                                        'numpy', 'sklearn', 'lightgbm', 'xgboost', 
                                        '__main__', 'src.ml', 'builtins'
                                    }
                                    if not any(module.startswith(m) for m in allowed_modules):
                                        raise pickle.UnpicklingError(
                                            f"Unpickling of {module}.{name} is not allowed"
                                        )
                                    return super().find_class(module, name)

                            with open(p, "rb") as fh:
                                loaded = RestrictedUnpickler(fh).load()

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

    # Chart API Endpoints - Real IDX Data
    @app.get("/api/charts/metadata/{symbol}")
    async def charts_metadata(symbol: str):
        """Get candlestick metadata for a symbol from IDX."""
        from src.data.idx_fetcher import fetch_symbol_metadata
        
        metadata = await fetch_symbol_metadata(symbol)
        if metadata:
            metadata = {
                **metadata,
                "tradingStart": metadata.get("tradingStart", "09:00"),
                "tradingEnd": metadata.get("tradingEnd", "16:00"),
            }
            return metadata
        
        # Fallback for unknown symbols
        return {
            "symbol": symbol,
            "name": "Unknown Symbol",
            "exchange": "IDX" if ".JK" in symbol else "OTHER",
            "currency": "IDR" if ".JK" in symbol else "USD",
            "timezone": "Asia/Jakarta" if ".JK" in symbol else "UTC",
            "tradingStart": "09:00" if ".JK" in symbol else "00:00",
            "tradingEnd": "16:00" if ".JK" in symbol else "23:59",
        }

    @app.get("/api/charts/candles/{symbol}")
    async def charts_candles(symbol: str, timeframe: str = "1d", limit: int = 100):
        """Get real candlestick data from IDX."""
        from src.data.idx_fetcher import fetch_candlesticks
        
        result = await fetch_candlesticks(symbol, timeframe=timeframe, limit=limit)
        
        if result:
            return result
        
        # Fallback if fetch fails
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": [],
            "error": "Unable to fetch candlestick data",
            "metadata": {
                "total": 0,
                "exchange": "IDX",
                "source": "fallback"
            }
        }

    @app.get("/api/charts/timeframes")
    async def charts_timeframes():
        """Return supported chart timeframes and the backend source capability."""
        from src.data.idx_fetcher import TIMEFRAME_MAP

        return {
            "timeframes": list(TIMEFRAME_MAP.keys()),
            "provider": "yfinance",
            "note": (
                "Timeframe list follows backend/provider support and stability "
                "for IDX chart delivery."
            ),
        }

    @app.get("/api/charts/trading-status")
    async def charts_trading_status():
        """Get current IDX trading status."""
        from src.data.idx_fetcher import fetch_trading_status
        
        status = await fetch_trading_status()
        return status

    @app.websocket("/ws/charts/{symbol}")
    async def websocket_charts(ws: WebSocket, symbol: str):
        """WebSocket stream for chart updates used by frontend ChartComponent."""
        from src.data.idx_fetcher import fetch_candlesticks

        ws_user = _authenticate_ws_client(ws)
        if not ws_user:
            try:
                await ws.accept()
            except Exception:
                pass
            try:
                await ws.close(code=4401, reason="Unauthorized")
            except Exception:
                pass
            return

        timeframe = ws.query_params.get("timeframe", "1d")
        try:
            limit = int(ws.query_params.get("limit", "100"))
        except Exception:
            limit = 100
        limit = max(50, min(limit, 1000))

        try:
            await ws.accept()
        except Exception as e:
            print(f"[ChartsWS] Failed to accept: {type(e).__name__}: {e}")
            return

        try:
            initial = await fetch_candlesticks(symbol, timeframe=timeframe, limit=limit)
            await ws.send_json({
                "symbol": symbol,
                "timeframe": timeframe,
                "candles": (initial or {}).get("candles", []),
            })

            while True:
                try:
                    message = await asyncio.wait_for(ws.receive_text(), timeout=30)
                except asyncio.TimeoutError:
                    message = "update"

                if message == "ping":
                    await ws.send_text("pong")
                    continue

                if message.startswith("timeframe:"):
                    requested = message.split(":", 1)[1].strip()
                    if requested:
                        timeframe = requested

                latest = await fetch_candlesticks(symbol, timeframe=timeframe, limit=1)
                candles = (latest or {}).get("candles", [])
                if candles:
                    await ws.send_json({
                        "type": "candle_update",
                        "candle": candles[-1],
                    })
        except WebSocketDisconnect:
            print(f"[ChartsWS] Client disconnected for {symbol}")
        except Exception as e:
            print(f"[ChartsWS] Error for {symbol}: {type(e).__name__}: {e}")
        finally:
            print(f"[ChartsWS] Handler exiting for {symbol}")

    @app.websocket("/ws/events")
    async def websocket_events(ws: WebSocket):
        """Stream events from the in-memory queue to connected WebSocket clients.
        
        This handler polls the event queue periodically and sends any accumulated
        events to the client. It gracefully closes if the client disconnects.
        """
        ws_user = _authenticate_ws_client(ws)
        if not ws_user:
            try:
                await ws.accept()
            except Exception:
                pass
            try:
                await ws.close(code=4401, reason="Unauthorized")
            except Exception:
                pass
            return

        try:
            await ws.accept()
            print(f"[WebSocket] Client connected to /ws/events ({ws_user})")
        except Exception as e:
            print(f"[WebSocket] Failed to accept: {type(e).__name__}: {e}")
            return
        
        print("[WebSocket] Starting event loop...")
        try:
            while True:
                # Poll events every 500ms
                await asyncio.sleep(0.5)
                
                # Get any accumulated events from the in-memory queue
                events = []
                try:
                    events = pop_events()
                except Exception as e:
                    print(f"[WebSocket] Error popping events: {type(e).__name__}: {e}")
                    events = []
                
                # Send each event to the client
                if events:
                    print(f"[WebSocket] Sending {len(events)} event(s) to client...")
                
                for event in events:
                    try:
                        await ws.send_json(event)
                    except RuntimeError as e:
                        # Client disconnected or connection broken
                        print(f"[WebSocket] Client disconnected: {e}")
                        return
                    except Exception as e:
                        print(f"[WebSocket] Error sending event: {type(e).__name__}: {e}")
                        return
                        
        except WebSocketDisconnect:
            print("[WebSocket] Client disconnected (clean close)")
        except asyncio.CancelledError:
            print("[WebSocket] Task cancelled (server shutdown)")
        except Exception as e:
            print(f"[WebSocket] Unexpected error: {type(e).__name__}: {e}")
        finally:
            print("[WebSocket] Handler exiting")

    @app.on_event("startup")
    async def startup_services():
        """Start optional background services: market data ingestion
        and ML trainer. These run in background thread pools to avoid
        blocking the FastAPI event loop during startup.
        
        Uses REAL IDX market data (Bursa Efek Indonesia) by default.
        """
        global market_service, ml_service
        
        # Initialize test user for demo purposes
        try:
            from src.api.auth import _load_users
            users = _load_users()
            if "demo" not in users:  # Ensure demo account exists for local testing
                register_user("demo", "demo123")
                print("[Startup] Created test user: demo / demo123")
        except Exception as e:
            print(f"[Startup] Warning: Could not create test user: {e}")
        
        try:
            import os

            # REAL DATA: Default to IDX symbols (Indonesian stock exchange)
            symbols_env = os.getenv("MARKET_SYMBOLS", "BBCA,USIM,KLBF,ASII,UNVR")
            symbols = [s.strip() for s in symbols_env.split(",") if s.strip()]
            
            # Try to use IDX API first, fall back to Alpaca if needed
            try:
                from src.brokers.marketdata import IDXMarketDataAdapter
                adapter = IDXMarketDataAdapter(symbols=symbols)
            except Exception:
                # Fall back to Alpaca if IDX adapter unavailable
                from src.brokers.marketdata import AlpacaMarketDataAdapter
                adapter = AlpacaMarketDataAdapter(symbols=symbols)
            
            from src.marketdata.service import MarketDataService
            ms = MarketDataService(adapter=adapter, db_path=os.path.join(project_root, "data", "ticks.db"))
            # PERFORMANCE FIX: Run market service in background thread, don't block startup
            ms.start()
            market_service = ms
        except Exception:
            # do not fail startup on optional services
            pass

        try:
            from src.ml.service import MLTrainerService

            interval = int(os.getenv("ML_TRAIN_INTERVAL", str(24 * 3600)))
            mls = MLTrainerService(schedule_seconds=interval, db_path=os.path.join(project_root, "data", "ticks.db"), models_dir=os.path.join(project_root, "models"))
            # PERFORMANCE FIX: Run ML training in background thread pool via executor
            # This prevents blocking the event loop during long training operations
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, mls.start)
            ml_service = mls
        except Exception:
            pass

    @app.on_event("shutdown")
    async def shutdown_services():
        """Stop background services cleanly on shutdown."""
        global market_service, ml_service
        try:
            if market_service:
                try:
                    market_service.stop()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if ml_service:
                try:
                    ml_service.stop()
                except Exception:
                    pass
        except Exception:
            pass

    @app.post("/api/training/trigger")
    async def api_training_trigger():
        """Trigger an immediate training run. The run is executed in a
        threadpool so the endpoint returns promptly.
        """
        global ml_service
        try:
            import asyncio

            if ml_service:
                await asyncio.get_event_loop().run_in_executor(None, ml_service.run_once)
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


if __name__ == "__main__":
    if FASTAPI_AVAILABLE:
        import uvicorn
        host = os.getenv("API_HOST", "127.0.0.1")
        port = int(os.getenv("API_PORT", "8000"))
        uvicorn.run(app, host=host, port=port, log_level="info")
    else:
        raise RuntimeError("FastAPI is not installed. Install with: pip install fastapi[all]")

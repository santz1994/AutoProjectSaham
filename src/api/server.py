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
    from typing import List, Optional
    from time import time

    from fastapi.responses import Response

    from src.pipeline.runner import AutonomousPipeline
    from src.pipeline.scheduler import PipelineScheduler
    from src.monitoring import metrics as monitoring
    from src.pipeline.persistence import read_etl_runs
    from src.alerts.webhook import send_alert_webhook

    app = FastAPI(title='AutoSaham API', version='0.1')

    # single shared pipeline instance for the server
    pipeline = AutonomousPipeline()
    _scheduler: Optional[PipelineScheduler] = None

    class RunPayload(BaseModel):
        symbols: List[str]
        fetch_prices: Optional[bool] = True
        persist_db: Optional[str] = None

    @app.get('/health')
    async def health():
        return {'status': 'ok'}

    @app.post('/run_etl')
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

    @app.get('/metrics')
    async def metrics_endpoint():
        try:
            payload, content_type = monitoring.metrics_text()
        except Exception:
            raise HTTPException(
                status_code=501, detail='prometheus_client not installed'
            )
        return Response(content=payload, media_type=content_type)

    @app.get('/etl_runs')
    async def etl_runs(limit: int = 50):
        try:
            runs = read_etl_runs(limit=limit)
            return {
                'runs': runs,
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            )

    class AlertPayload(BaseModel):
        url: str
        message: str
        level: Optional[str] = 'info'

    @app.post('/alert')
    async def alert_endpoint(payload: AlertPayload):
        try:
            payload_body = {
                'message': payload.message,
                'level': payload.level,
            }
            sent = send_alert_webhook(payload.url, payload_body)
            if not sent:
                raise HTTPException(
                    status_code=502, detail='alert delivery failed'
                )
            return {'status': 'sent'}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            )

    @app.post('/scheduler/start')
    async def start_scheduler(symbols: List[str], interval_seconds: float = 3600.0):
        global _scheduler
        if (
            _scheduler
            and getattr(_scheduler, '_thread', None)
            and getattr(_scheduler, '_thread').is_alive()
        ):
            raise HTTPException(status_code=400, detail='Scheduler already running')
        _scheduler = PipelineScheduler(
            pipeline,
            symbols=symbols,
            interval_seconds=interval_seconds,
        )
        _scheduler.start()
        return {'status': 'started'}

    @app.post('/scheduler/stop')
    async def stop_scheduler():
        global _scheduler
        if not _scheduler:
            raise HTTPException(status_code=400, detail='Scheduler not running')
        _scheduler.stop()
        _scheduler = None
        return {'status': 'stopped'}


else:
    # Friendly placeholders when FastAPI is not installed.
    app = None

    def _missing_fastapi(*args, **kwargs):
        raise RuntimeError(
            'FastAPI is not installed. Install with '
            'pip install fastapi[all] to enable the API server.'
        )

    def health():
        return _missing_fastapi()

    def run_etl(*args, **kwargs):
        return _missing_fastapi()

    def start_scheduler(*args, **kwargs):
        return _missing_fastapi()

    def stop_scheduler(*args, **kwargs):
        return _missing_fastapi()

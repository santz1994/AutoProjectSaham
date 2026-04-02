"""Celery task queue configuration for AutoSaham.

Moves ML training and ETL polling from FastAPI startup to async workers.
Connect via Redis broker: CELERY_BROKER_URL=redis://redis:6379/0
"""

from celery import Celery
import os
from datetime import datetime, timedelta, timezone

# Configure Celery
app = Celery('autosaham_tasks')
app.conf.update(
    broker_url=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    result_backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'),
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Jakarta',
    enable_utc=True,
)

JAKARTA_TZ = timezone(timedelta(hours=7))


@app.task(name='autosaham.retrain_model')
def retrain_model():
    """Async model retraining task. Runs via Celery worker."""
    try:
        from src.ml.service import MLTrainerService
        from pathlib import Path
        
        project_root = Path(__file__).parent.parent
        service = MLTrainerService(
            schedule_seconds=0,
            db_path=str(project_root / 'data' / 'ticks.db'),
            models_dir=str(project_root / 'models')
        )
        service.run_once()
        return {'status': 'success', 'timestamp': datetime.now(JAKARTA_TZ).isoformat()}
    except Exception as e:
        return {'status': 'failed', 'error': str(e)}


@app.task(name='autosaham.run_etl')
def run_etl(symbols=None):
    """Async ETL pipeline task."""
    try:
        from src.pipeline.orchestrator import AutonomousPipeline
        
        symbols = symbols or ['BBCA', 'BMRI', 'ASII']
        pipeline = AutonomousPipeline(
            symbols=symbols,
            news_api_key=os.getenv('NEWSAPI_KEY'),
            interval_minutes=60
        )
        result = pipeline.run(symbols, fetch_prices=True)
        return {'status': 'success', 'result': result}
    except Exception as e:
        return {'status': 'failed', 'error': str(e)}


@app.task(name='autosaham.reconcile_orders')
def reconcile_orders():
    """Background order reconciliation task (runs every 30s)."""
    try:
        from src.execution.reconciler import TradeReconciler
        
        # Stub: Implement with actual broker client
        return {'status': 'ok', 'reconciled': 0}
    except Exception as e:
        return {'status': 'failed', 'error': str(e)}


# Celery Beat Schedule (add to FastAPI startup config)
# In your FastAPI app or docker-compose, configure:
# 
# app.conf.beat_schedule = {
#     'retrain-model-daily': {
#         'task': 'autosaham.retrain_model',
#         'schedule': crontab(hour=0, minute=0),  # Daily at midnight
#     },
#     'run-etl-hourly': {
#         'task': 'autosaham.run_etl',
#         'schedule': crontab(minute=0),  # Every hour
#         'args': (['BBCA', 'BMRI'], )
#     },
#     'reconcile-orders-every-30s': {
#         'task': 'autosaham.reconcile_orders',
#         'schedule': 30.0,
#     },
# }

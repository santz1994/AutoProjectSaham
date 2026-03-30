"""Autonomous ETL orchestrator and scheduler.

Provides a simple `AutonomousPipeline` class with `run_once()` and `start()`.
Runs `src.pipeline.etl.run_etl` and persists each run to `data/etl_<timestamp>.json`.
"""
from datetime import datetime
import json
import os

from .etl import run_etl


class AutonomousPipeline:
    def __init__(self, symbols=None, news_api_key=None, data_dir='data', interval_minutes=5):
        self.symbols = symbols or ['BBCA']
        self.news_api_key = news_api_key
        self.data_dir = data_dir
        self.interval = int(interval_minutes)
        self._scheduler = None

    def _ensure_dir(self):
        os.makedirs(self.data_dir, exist_ok=True)

    def _job(self):
        ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
        try:
            payload = {'timestamp': ts, 'symbols': self.symbols, 'data': run_etl(self.symbols, news_api_key=self.news_api_key)}
            fname = os.path.join(self.data_dir, f'etl_{ts}.json')
            with open(fname, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            print(f'ETL run saved to {fname}')
            return fname
        except Exception as e:
            err_fname = os.path.join(self.data_dir, f'etl_error_{ts}.json')
            with open(err_fname, 'w', encoding='utf-8') as fh:
                json.dump({'timestamp': ts, 'error': repr(e)}, fh, ensure_ascii=False, indent=2)
            print(f'ETL error saved to {err_fname}')
            return err_fname

    def run_once(self):
        self._ensure_dir()
        return self._job()

    def start(self):
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
        except Exception:
            raise RuntimeError('apscheduler not installed; install with `pip install apscheduler`')

        self._ensure_dir()
        if self._scheduler is not None:
            print('Scheduler already running')
            return

        self._scheduler = BackgroundScheduler()
        self._scheduler.add_job(self._job, 'interval', minutes=self.interval, max_instances=1)
        self._scheduler.start()
        print(f'AutonomousPipeline started — fetching {self.symbols} every {self.interval} minutes')

    def stop(self):
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
            print('AutonomousPipeline stopped')

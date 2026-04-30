"""Autonomous pipeline runner.

Provides a thin orchestration layer that invokes connectors (ETL) and
optionally performs batch price fetches via `BatchFetcher`.

This is intentionally small and testable; production schedulers or job
runners should call into `AutonomousPipeline.run` on a schedule.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from . import etl as etl_module
from .batch_fetcher import BatchFetcher

# backward-compatible module-level hook: tests may patch `src.pipeline.runner.run_etl`
# If set, `run()` prefers this global; otherwise it calls `etl_module.run_etl`.
run_etl = None


class AutonomousPipeline:
    def __init__(
        self,
        batch_fetcher: Optional[BatchFetcher] = None,
        batch_min_delay: float = 1.0,
        logger: Optional[logging.Logger] = None,
    ):
        self.logger = logger or logging.getLogger("autosaham.pipeline")
        self.batch_fetcher = batch_fetcher or BatchFetcher(
            min_delay=float(batch_min_delay)
        )

    def run(
        self,
        symbols: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        fetch_prices: bool = True,
        price_limit: Optional[int] = None,
        news_api_key: Optional[str] = None,
        persist_db: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run a single ETL cycle and optionally fetch per-symbol price files.

        Returns a dict containing `etl` results and optional `prices` fetch report.
        """
        if not isinstance(symbols, (list, tuple)):
            raise ValueError("symbols must be a list of tickers")

        # run connector ETL (stocks, forex, news)
        try:
            etl_func = globals().get("run_etl") or etl_module.run_etl
            etl_result = etl_func(
                symbols,
                start_date=start_date,
                end_date=end_date,
                news_api_key=news_api_key,
            )
        except Exception as e:
            self.logger.exception("ETL run failed")
            etl_result = {"error": str(e)}

        prices_report = None
        if fetch_prices and symbols:
            try:
                prices_report = self.batch_fetcher.fetch_symbols(
                    symbols, period="1y", out_dir="data/prices", limit=price_limit
                )
            except Exception as e:
                self.logger.exception("batch price fetch failed")
                prices_report = [
                    {"symbol": s, "status": "error", "error": str(e)} for s in symbols
                ]

        result = {"etl": etl_result, "prices": prices_report}

        if persist_db:
            try:
                from .persistence import save_etl_run

                rid = save_etl_run(etl_result, prices_report, db_path=persist_db)
                result["persisted_run_id"] = rid
            except Exception:
                self.logger.exception("failed to persist ETL run")

        return result

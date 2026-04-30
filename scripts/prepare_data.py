"""Prepare raw OHLCV into feature-rich dataset ready for model training.

Examples:
    python scripts/prepare_data.py \
            --input-csv data/dataset/hf_BTCUSDT_5m.csv \
            --symbol BTC/USDT --timeframe 5m \
            --features-out data/dataset/hf_BTCUSDT_5m_features.csv

  python scripts/prepare_data.py --exchange binance --symbol BTC/USDT --timeframe 5m \
      --candles 100000 --features-out data/dataset/hf_BTCUSDT_5m_features.csv
"""

from __future__ import annotations

import argparse
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.pipeline.prepare_data import prepare_training_dataset  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare high-frequency data into clean feature dataset",
    )
    parser.add_argument(
        "--input-csv",
        default="",
        help="Optional raw OHLCV CSV input (skip fetch when provided)",
    )
    parser.add_argument(
        "--exchange",
        default="binance",
        help="CCXT exchange id (used when --input-csv is not provided)",
    )
    parser.add_argument(
        "--symbol",
        default="BTC/USDT",
        help="Trading symbol (e.g., BTC/USDT, EURUSD=X)",
    )
    parser.add_argument(
        "--timeframe",
        default="5m",
        help="Candle timeframe (e.g., 1m, 5m, 1h)",
    )
    parser.add_argument(
        "--candles",
        type=int,
        default=100_000,
        help="Total candles to fetch when input-csv is not set",
    )
    parser.add_argument(
        "--batch-limit",
        type=int,
        default=1_000,
        help="Candles per API request",
    )
    parser.add_argument(
        "--market-type",
        default="spot",
        help="CCXT market type (spot, swap, future)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=True,
        help="Enable strict interval/completeness checks when fetching",
    )
    parser.add_argument(
        "--no-strict",
        dest="strict",
        action="store_false",
        help="Disable strict checks when fetching",
    )
    parser.add_argument(
        "--raw-out",
        default="",
        help="Optional output path for raw OHLCV data",
    )
    parser.add_argument(
        "--features-out",
        default="data/dataset/hf_BTCUSDT_5m_features.csv",
        help="Output path for prepared feature dataset (.csv/.parquet)",
    )
    parser.add_argument(
        "--short-window",
        type=int,
        default=5,
        help="Short SMA/momentum window",
    )
    parser.add_argument(
        "--long-window",
        type=int,
        default=20,
        help="Long SMA/volatility/Bollinger window",
    )
    parser.add_argument(
        "--horizon-bars",
        type=int,
        default=8,
        help="Horizon window for horizon_* features",
    )
    parser.add_argument(
        "--leverage",
        type=float,
        default=20.0,
        help="Leverage used in dist_to_liquidation calculation",
    )
    parser.add_argument(
        "--maintenance-margin-rate",
        type=float,
        default=0.005,
        help="Maintenance margin rate for liquidation distance feature",
    )
    parser.add_argument(
        "--position-side",
        default="long",
        choices=["long", "short"],
        help="Position side assumption for liquidation distance",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=0,
        help="Optional limit: use only latest N raw rows before feature engineering",
    )
    parser.add_argument(
        "--min-required-rows",
        type=int,
        default=1_000,
        help="Validation threshold for minimum feature rows",
    )
    parser.add_argument(
        "--disable-microstructure",
        action="store_true",
        help="Disable microstructure feature computation",
    )
    parser.add_argument(
        "--keep-nan",
        action="store_true",
        help="Do not drop rows with NaN/Inf derived features",
    )

    args = parser.parse_args()

    summary = prepare_training_dataset(
        exchange_id=args.exchange,
        symbol=args.symbol,
        timeframe=args.timeframe,
        candles=args.candles,
        batch_limit=args.batch_limit,
        market_type=args.market_type,
        strict=args.strict,
        input_csv=args.input_csv or None,
        raw_out=args.raw_out or None,
        features_out=args.features_out,
        short_window=args.short_window,
        long_window=args.long_window,
        horizon_bars=args.horizon_bars,
        leverage=args.leverage,
        maintenance_margin_rate=args.maintenance_margin_rate,
        position_side=args.position_side,
        include_microstructure=not args.disable_microstructure,
        dropna=not args.keep_nan,
        min_required_rows=args.min_required_rows,
        max_rows=args.max_rows,
    )

    print("Prepare-data pipeline completed")
    print(f"- Symbol: {summary['symbol']}")
    print(f"- Timeframe: {summary['timeframe']}")
    print(f"- Raw rows: {summary['raw_rows']}")
    print(f"- Feature rows: {summary['feature_rows']}")
    print(f"- Range: {summary['timestamp_start']} -> {summary['timestamp_end']}")
    print(f"- Features output: {summary['features_out']}")
    if "raw_out" in summary:
        print(f"- Raw output: {summary['raw_out']}")


if __name__ == "__main__":
    main()

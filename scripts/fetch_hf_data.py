"""Fetch high-frequency OHLCV data via CCXT and save to CSV.

Example:
  python scripts/fetch_hf_data.py --exchange binance --symbol BTC/USDT --timeframe 5m --candles 100000
"""

from __future__ import annotations

import argparse
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.pipeline.data_connectors.hf_connector import fetch_historical_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch high-frequency OHLCV data via CCXT")
    parser.add_argument("--exchange", default="binance", help="CCXT exchange id (e.g., binance, bybit)")
    parser.add_argument("--symbol", default="BTC/USDT", help="Exchange symbol (e.g., BTC/USDT)")
    parser.add_argument("--timeframe", default="5m", help="CCXT timeframe (default: 5m)")
    parser.add_argument("--candles", type=int, default=100_000, help="Total candles to fetch")
    parser.add_argument("--batch-limit", type=int, default=1_000, help="Candles per API request")
    parser.add_argument("--market-type", default="spot", help="CCXT defaultType (spot, swap, future)")
    parser.add_argument("--out", default="data/dataset/hf_BTCUSDT_5m.csv", help="Output CSV path")
    parser.add_argument("--strict", action="store_true", default=True, help="Enable strict completeness checks")
    parser.add_argument("--no-strict", dest="strict", action="store_false", help="Disable strict completeness checks")
    args = parser.parse_args()

    df = fetch_historical_data(
        exchange_id=args.exchange,
        symbol=args.symbol,
        timeframe=args.timeframe,
        candles=args.candles,
        batch_limit=args.batch_limit,
        market_type=args.market_type,
        strict=args.strict,
    )

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    df.to_csv(args.out, index=False)

    start_iso = df["datetime"].iloc[0].isoformat() if len(df) > 0 else "-"
    end_iso = df["datetime"].iloc[-1].isoformat() if len(df) > 0 else "-"

    print("CCXT fetch completed")
    print(f"- Exchange: {args.exchange}")
    print(f"- Symbol: {args.symbol}")
    print(f"- Timeframe: {args.timeframe}")
    print(f"- Candles: {len(df)}")
    print(f"- Range: {start_iso} -> {end_iso}")
    print(f"- Output: {args.out}")


if __name__ == "__main__":
    main()

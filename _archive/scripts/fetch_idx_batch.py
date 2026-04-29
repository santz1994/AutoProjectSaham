"""CLI script: fetch Forex/Crypto price series in batches (rate-limited).

Example:
  python scripts/fetch_idx_batch.py --symbols EURUSD=X BTC-USD ETH-USD --limit 10
"""
import argparse

from src.pipeline.batch_fetcher import BatchFetcher


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["EURUSD=X", "GBPUSD=X", "BTC-USD", "ETH-USD", "SOL-USD"],
        help="Forex/Crypto symbols to fetch",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum symbols to fetch (default 10)",
    )
    parser.add_argument(
        "--period",
        type=str,
        default="1y",
        help="History period (e.g. 1y, 6mo)",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="data/prices",
        help="Output folder for fetched JSON summaries",
    )
    args = parser.parse_args()

    symbols = [str(item or "").strip().upper() for item in args.symbols if str(item or "").strip()]
    if not symbols:
        print("No symbols provided, using fallback Forex/Crypto list")
        symbols = ["EURUSD=X", "BTC-USD", "ETH-USD"]

    fetcher = BatchFetcher(min_delay=1.0)
    results = fetcher.fetch_symbols(
        symbols,
        period=args.period,
        out_dir=args.out,
        limit=args.limit,
    )

    ok = [r for r in results if r.get("status") == "ok"]
    err = [r for r in results if r.get("status") == "error"]
    print(f"Completed: {len(ok)} ok, {len(err)} errors")
    for item in err[:10]:
        print("ERR", item["symbol"], item.get("error"))


if __name__ == "__main__":
    main()

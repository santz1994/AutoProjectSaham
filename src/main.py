import argparse
import os
import time


def main():
    parser = argparse.ArgumentParser(description="AutoSaham runner - Real Trading System")
    parser.add_argument("--run-etl", action="store_true", help="Run ETL pipeline with real market data")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run pipeline once and exit (use with --run-etl)",
    )
    parser.add_argument(
        "--symbols", nargs="+", default=["BBCA", "USIM", "KLBF"], help="IDX symbols to fetch for ETL"
    )
    parser.add_argument(
        "--interval", type=int, default=5, help="Interval minutes between ETL runs"
    )
    parser.add_argument(
        "--api", action="store_true", help="Start FastAPI server with real broker connections"
    )

    args = parser.parse_args()
    
    # Default: Start API server with real connections
    if not args.run_etl and not args.once:
        args.api = True
    
    if args.api:
        # Start the API server with real broker/market data
        import uvicorn
        host = os.getenv("API_HOST", "127.0.0.1")
        port = int(os.getenv("API_PORT", "8000"))
        reload_enabled = os.getenv("API_RELOAD", "1") == "1"

        print(
            f"🚀 Starting AutoSaham API with REAL DATA "
            f"(host={host}, port={port}, reload={'on' if reload_enabled else 'off'})"
        )

        if reload_enabled:
            uvicorn.run(
                "src.api.server:app",
                host=host,
                port=port,
                log_level="info",
                reload=True,
            )
        else:
            from .api.server import app

            uvicorn.run(app, host=host, port=port, log_level="info")
        return

    if args.run_etl:
        from .pipeline.runner import AutonomousPipeline

        news_api_key = os.getenv("NEWSAPI_KEY")
        p = AutonomousPipeline()
        if args.once:
            result = p.run(
                symbols=args.symbols,
                fetch_prices=True,
                persist_db="data/etl.db"
            )
            print("✅ ETL completed with REAL DATA:", result)
        else:
            try:
                print(f"🚀 Running ETL pipeline with REAL DATA (symbols={args.symbols}, interval={args.interval}m)")
                for symbol in args.symbols:
                    result = p.run([symbol], fetch_prices=True, persist_db="data/etl.db")
                    print(f"✅ {symbol}: {result}")
                    time.sleep(args.interval * 60)
            except KeyboardInterrupt:
                print("\n✅ ETL pipeline stopped")
        return

    parser.print_help()


if __name__ == "__main__":
    main()

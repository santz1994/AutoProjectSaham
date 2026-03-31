import argparse
import os
import time


def main():
    parser = argparse.ArgumentParser(description='AutoSaham runner')
    parser.add_argument('--demo', action='store_true', help='Run built-in demo')
    parser.add_argument('--run-etl', action='store_true', help='Run ETL pipeline')
    parser.add_argument('--once', action='store_true', help='Run pipeline once and exit (use with --run-etl)')
    parser.add_argument('--symbols', nargs='+', default=['BBCA'], help='Symbols to fetch for ETL')
    parser.add_argument('--interval', type=int, default=5, help='Interval minutes between ETL runs')

    args = parser.parse_args()
    if args.demo:
        # import the demo runner lazily to avoid heavy dependencies at import time
        from .demo import run_demo
        run_demo()
        return

    if args.run_etl:
        from .pipeline.orchestrator import AutonomousPipeline
        news_api_key = os.getenv('NEWSAPI_KEY')
        p = AutonomousPipeline(
            symbols=args.symbols,
            news_api_key=news_api_key,
            interval_minutes=args.interval,
        )
        if args.once:
            p.run_once()
        else:
            try:
                p.start()
                print('Press Ctrl-C to stop the pipeline...')
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                p.stop()
        return

    parser.print_help()


if __name__ == '__main__':
    main()

"""Quick verify which candidate modules are truly dead (unreferenced)."""
import os
import re

DEAD_CANDIDATES = [
    "src/api/idx_api_client.py",
    "src/ml/ensemble_predictor.py",
    "src/backtest/simulator.py",
    "src/ml/online_learner.py",
    "src/ml/purged_optuna.py",
    "src/strategies/buy_the_dip.py",
    "src/strategies/mean_reversion.py",
    "src/strategies/momentum_breakout.py",
    "src/strategies/momentum.py",
    "src/strategies/rsi_reversal.py",
    "src/strategies/sma_crossover.py",
    "src/execution/order_router.py",
    "src/execution/risk_manager.py",
    "src/data/news_fetcher.py",
    "src/rl/online_learner.py",
    "src/backtest/backtester.py",
    "src/brokers/local_adapter.py",
    "src/brokers/hft_adapter.py",
    "src/pipeline/runner.py",
    "src/notifications/email_notifier.py",
    "src/monitoring/metrics_collector.py",
    "src/alerts/price_alert.py",
]

def collect_imports(directory: str) -> set:
    """Collect all dotted module names imported in .py files under *directory*."""
    imports: set = set()
    if not os.path.isdir(directory):
        return imports
    for root, _dirs, files in os.walk(directory):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, encoding="utf-8") as fh:
                    for line in fh:
                        for m in re.findall(r"(?:from|import)\s+([\w.]+)", line):
                            imports.add(m)
            except Exception:
                pass
    return imports


def main() -> None:
    all_imports = collect_imports("src") | collect_imports("tests")

    dead: list = []
    alive: list = []
    total_dead_lines = 0

    for candidate in DEAD_CANDIDATES:
        if not os.path.exists(candidate):
            print(f"  SKIP (not found): {candidate}")
            continue
        mod = candidate.replace(os.sep, ".").replace("/", ".").replace("\\", ".")
        mod = mod.removesuffix(".py")
        referenced = any(mod in imp for imp in all_imports)
        lines = sum(1 for _ in open(candidate, encoding="utf-8"))
        if referenced:
            alive.append((candidate, lines))
        else:
            dead.append((candidate, lines))
            total_dead_lines += lines

    print("=" * 60)
    print("VERIFIED DEAD (safe to delete)")
    print("=" * 60)
    for path, lines in dead:
        print(f"  {path} ({lines} lines)")
    print(f"\nTotal dead modules: {len(dead)}")
    print(f"Total dead lines: {total_dead_lines}")

    print("\n" + "=" * 60)
    print("STILL REFERENCED (DO NOT DELETE)")
    print("=" * 60)
    for path, lines in alive:
        print(f"  {path} ({lines} lines)")
    print(f"\nTotal alive: {len(alive)}")


if __name__ == "__main__":
    main()
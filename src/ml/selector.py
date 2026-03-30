"""Symbol selection utilities: score symbols for a strategy and pick high-confidence names.

Functions use lazy imports for market-data libraries and fall back to raising
helpful errors if those libraries are not installed. The scoring function is
intentionally simple and designed as a starting point for more advanced models.
"""
import math
from typing import Callable, Dict, List, Optional


def _pair_trades(trades):
    # trades: list of tuples ('buy'|'sell', idx, price, qty)
    results = []
    buy_queue = []
    for typ, idx, price, qty in trades:
        if typ == 'buy':
            buy_queue.append({'qty': qty, 'price': price})
        elif typ == 'sell':
            remaining = qty
            while remaining > 0 and buy_queue:
                b = buy_queue[0]
                take = min(b['qty'], remaining)
                pnl = (price - b['price']) * take
                results.append({'buy_price': b['price'], 'sell_price': price, 'qty': take, 'pnl': pnl})
                b['qty'] -= take
                remaining -= take
                if b['qty'] == 0:
                    buy_queue.pop(0)
    return results


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def get_price_series_yf(symbol: str, period: str = '1y') -> List[float]:
    """Get daily price series for `symbol`.

    Tries the `yfinance` library first; if it's not available or fails,
    falls back to a lightweight Yahoo CSV download using `requests`.
    """
    # try yfinance first
    try:
        import yfinance as yf
        df = yf.download(symbol, period=period, interval='1d', progress=False)
        if df is not None and not df.empty:
            col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
            return [float(x) for x in df[col].tolist()]
    except Exception:
        # fall through to HTTP CSV fallback
        pass

    # Fallback: download CSV from Yahoo Finance directly
    try:
        return get_price_series_yahoo(symbol, period=period)
    except Exception as e_yahoo:
        # If Alpha Vantage key is available, try it as a last resort
        import os
        key = os.getenv('ALPHA_VANTAGE_KEY')
        if key:
            try:
                from src.pipeline.data_connectors.alpha_vantage import fetch_daily_adjusted
                return fetch_daily_adjusted(symbol, api_key=key, outputsize='compact')
            except Exception as e_av:
                # raise combined info
                raise RuntimeError(f'yfinance failed; yahoo fallback failed ({e_yahoo}); alphavantage failed ({e_av})')
        # otherwise re-raise the Yahoo error
        raise


def get_price_series_yahoo(symbol: str, period: str = '1y') -> List[float]:
    """Download historical daily prices using the robust `YahooFetcher`.

    Delegates fetching and caching to `src.pipeline.data_connectors.yahoo_fetcher.YahooFetcher`.
    """
    try:
        from src.pipeline.data_connectors.yahoo_fetcher import YahooFetcher
    except Exception as e:
        raise RuntimeError('yahoo_fetcher module not available: ' + repr(e)) from e

    fetcher = YahooFetcher()
    return fetcher.fetch(symbol, period=period)


def evaluate_strategy_on_series(prices: List[float], strategy_fn: Callable, starting_cash: float = 10000.0) -> Dict:
    from src.backtest.backtester import simple_backtest

    signals = strategy_fn(prices)
    # ensure signals length matches
    if len(signals) < len(prices):
        signals = ([0] * (len(prices) - len(signals))) + signals

    res = simple_backtest(prices, signals, starting_cash=starting_cash)
    trades = res.get('trades', [])
    final_balance = res.get('final_balance', starting_cash)

    pairs = _pair_trades(trades)
    num_trades = len(pairs)
    wins = sum(1 for p in pairs if p['pnl'] > 0)
    losses = sum(1 for p in pairs if p['pnl'] <= 0)
    total_pnl = sum(p['pnl'] for p in pairs)
    avg_pnl = (total_pnl / num_trades) if num_trades else 0.0
    win_rate = (wins / num_trades) if num_trades else 0.0
    sum_wins = sum(p['pnl'] for p in pairs if p['pnl'] > 0)
    sum_losses = -sum(p['pnl'] for p in pairs if p['pnl'] < 0)
    profit_factor = (sum_wins / sum_losses) if (sum_losses and sum_wins) else (float('inf') if sum_wins > 0 else 0.0)

    return {
        'num_trades': num_trades,
        'win_rate': win_rate,
        'avg_pnl': avg_pnl,
        'total_pnl': total_pnl,
        'profit_factor': profit_factor,
        'final_balance': final_balance,
        'trades': trades,
    }


def score_from_metrics(metrics: Dict, starting_cash: float = 10000.0) -> float:
    roi = (metrics.get('final_balance', starting_cash) - starting_cash) / starting_cash
    win_rate = metrics.get('win_rate', 0.0)
    num_trades = metrics.get('num_trades', 0)

    # map ROI to [0,1] using sigmoid sensitivity
    roi_score = _sigmoid(roi * 10.0)
    score = 0.5 * win_rate + 0.5 * roi_score

    # down-weight very low sample counts
    if num_trades < 3:
        score *= (num_trades / 3.0)

    # clamp
    return max(0.0, min(1.0, score))


def score_symbols_for_strategy(symbols: List[str], strategy_fn: Callable, period: str = '1y', starting_cash: float = 10000.0, allow_demo: bool = True) -> Dict[str, Dict]:
    """Score symbols by running the given strategy on historical prices.

    Returns a dict mapping symbol -> {metrics..., score}
    If `yfinance` is unavailable and `allow_demo` is True, the function will
    generate synthetic price series for demonstration.
    """
    out = {}
    for sym in symbols:
        # short-circuit demo symbols to avoid unnecessary network calls
        if allow_demo and isinstance(sym, str) and sym.upper().startswith('DEMO'):
            try:
                from src.demo import generate_price_series

                prices = generate_price_series(n=252, start_price=100.0, volatility_pct=1.0)
            except Exception as e:
                out[sym] = {'error': f'demo generation failed: {repr(e)}'}
                continue

            metrics = evaluate_strategy_on_series(prices, strategy_fn, starting_cash=starting_cash)
            score = score_from_metrics(metrics, starting_cash=starting_cash)
            metrics['score'] = score
            out[sym] = metrics
            continue
        try:
            prices = get_price_series_yf(sym, period=period)
        except Exception as e:
            if allow_demo:
                # fallback: generate a small synthetic series
                try:
                    from src.demo import generate_price_series
                    prices = generate_price_series(n=252, start_price=100.0, volatility_pct=1.0)
                except Exception:
                    out[sym] = {'error': f'no market data available and demo fallback failed: {repr(e)}'}
                    continue
            else:
                out[sym] = {'error': f'no market data available: {repr(e)}'}
                continue

        metrics = evaluate_strategy_on_series(prices, strategy_fn, starting_cash=starting_cash)
        score = score_from_metrics(metrics, starting_cash=starting_cash)
        metrics['score'] = score
        out[sym] = metrics

    return out


def select_high_confidence_symbols(symbols: List[str], strategy_fn: Callable, threshold: float = 0.9, **kwargs) -> List[str]:
    scored = score_symbols_for_strategy(symbols, strategy_fn, **kwargs)
    selected = [s for s, m in scored.items() if isinstance(m, dict) and m.get('score', 0) >= threshold]
    return selected


if __name__ == '__main__':
    # quick demo when run as a script
    from src.strategies.scalping import simple_sma_strategy
    syms = ['DEMO1', 'DEMO2', 'DEMO3']
    res = score_symbols_for_strategy(syms, simple_sma_strategy)
    for s, m in res.items():
        print(s, 'score=', m.get('score'), 'win_rate=', m.get('win_rate'), 'trades=', m.get('num_trades'))

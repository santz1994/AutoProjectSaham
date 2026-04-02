"""Real data trading demo using actual market data from Yahoo Finance.

This demo fetches REAL prices and runs the SMA strategy with paper trading.
"""
import logging
from typing import List, Dict, Any

from .execution.executor import PaperBroker
from .strategies.scalping import simple_sma_strategy
from .pipeline.data_connectors.yahoo_fetcher import YahooFetcher

logger = logging.getLogger(__name__)


def fetch_real_prices(symbols: List[str], period: str = "3mo") -> Dict[str, List[Dict]]:
    """Fetch REAL historical prices from Yahoo Finance."""
    fetcher = YahooFetcher(min_delay=0.5)
    prices_by_symbol = {}
    
    for symbol in symbols:
        try:
            print(f"Fetching REAL prices for {symbol} ({period})...")
            prices = fetcher.fetch(symbol, period=period, use_cache=True)
            if prices:
                prices_by_symbol[symbol] = prices
                print(f"✅ {symbol}: {len(prices)} candles")
            else:
                print(f"⚠️  {symbol}: No prices available")
        except Exception as e:
            print(f"❌ {symbol}: {e}")
    
    return prices_by_symbol


def run_demo(symbols: List[str] = None, use_real_data: bool = True):
    """Run SMA strategy with REAL market data (not mock)."""
    if symbols is None:
        symbols = ["BBCA", "USIM", "KLBF"]  # Real IDX symbols
    
    print("\n" + "="*60)
    print("🚀 AutoSaham Trading Demo - REAL MARKET DATA")
    print("="*60)
    
    if not use_real_data:
        raise ValueError("Demo now requires real data only. Mock data removed.")
    
    # Fetch REAL market data
    prices_by_symbol = fetch_real_prices(symbols, period="3mo")
    
    if not prices_by_symbol:
        print("❌ No price data available. Check network/API.")
        return
    
    # Initialize paper broker with starting capital
    broker = PaperBroker(cash=100_000_000.0)  # 100M IDR starting capital
    
    total_trades = 0
    symbol_results = []
    
    for symbol, price_list in prices_by_symbol.items():
        print(f"\n--- Trading {symbol} ---")
        
        if len(price_list) < 30:
            print(f"⚠️  Insufficient price data for {symbol} (need 30+, got {len(price_list)})")
            continue
        
        # Extract prices in order
        prices = [p["close"] for p in price_list]
        
        # Run SMA strategy on REAL data
        try:
            signals = simple_sma_strategy(prices, short=5, long=20)
        except Exception as e:
            print(f"❌ Strategy failed for {symbol}: {e}")
            continue
        
        # Execute trades
        symbol_trades = 0
        for t, (price_data, signal) in enumerate(zip(price_list, signals)):
            price = price_data["close"]
            
            if signal == 1:  # BUY signal
                try:
                    qty = int(broker.cash / price / 100) * 100  # Lot size (100 shares)
                    if qty > 0:
                        broker.place_order(symbol, "buy", qty, price)
                        symbol_trades += 1
                except Exception as e:
                    pass  # Insufficient funds
            
            elif signal == -1:  # SELL signal
                qty = broker.positions.get(symbol, 0)
                if qty > 0:
                    broker.place_order(symbol, "sell", qty, price)
                    symbol_trades += 1
        
        # Final balance after this symbol
        current_prices = {symbol: price_list[-1]["close"]}
        final_balance = broker.get_balance(current_prices)
        
        trades_log = [t for t in broker.trades if t.get("symbol") == symbol]
        profit = sum(t.get("pnl", 0) for t in trades_log)
        
        symbol_results.append({
            "symbol": symbol,
            "trades": symbol_trades,
            "profit_idr": round(profit, 2),
            "price_range": f"{min(prices):.2f} - {max(prices):.2f}",
        })
        
        print(f"  Trades: {symbol_trades}")
        print(f"  Profit: IDR {profit:,.2f}")
        print(f"  Price range: {min(prices):.2f} - {max(prices):.2f}")
        
        total_trades += symbol_trades
    
    # Final summary
    final_prices = {symbol: price_list[-1]["close"] for symbol, price_list in prices_by_symbol.items()}
    final_balance = broker.get_balance(final_prices)
    starting_capital = 100_000_000.0
    total_pnl = broker.get_balance(final_prices) - starting_capital
    
    print("\n" + "="*60)
    print("📊 DEMO COMPLETE - FINAL RESULTS")
    print("="*60)
    print(f"Starting Capital: IDR {starting_capital:,.0f}")
    print(f"Final Balance: IDR {final_balance:,.0f}")
    print(f"Total P&L: IDR {total_pnl:,.2f}")
    print(f"Total Trades: {total_trades}")
    print("\nPer-Symbol Results:")
    for r in symbol_results:
        print(f"  {r['symbol']:6} | Trades: {r['trades']:2} | P&L: {r['profit_idr']:>12,.2f} | Range: {r['price_range']}")
    print("="*60)
    print("✅ Demo with REAL market data completed successfully!")
    

if __name__ == "__main__":
    run_demo()


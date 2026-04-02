import yfinance as yf
import asyncio
from src.data.idx_fetcher import fetch_candlesticks, fetch_symbol_metadata

async def test_idx_data():
    print("=" * 60)
    print("Testing IDX Data Fetcher")
    print("=" * 60)
    
    # Test metadata
    print("\n1. Testing metadata fetch:")
    metadata = await fetch_symbol_metadata('BBCA.JK')
    print(f"   Result: {metadata}")
    
    # Test candlesticks
    print("\n2. Testing candlesticks fetch:")
    candles = await fetch_candlesticks('BBCA.JK', timeframe='1d', limit=5)
    if candles:
        print(f"   Got {len(candles.get('candles', []))} candles")
        for i, candle in enumerate(candles.get('candles', [])[:3]):
            print(f"   Candle {i}: time={candle['time']}, close={candle['close']}")
    else:
        print("   ❌ No data returned")
    
    # Test raw yfinance
    print("\n3. Testing raw yfinance:")
    ticker = yf.Ticker('BBCA.JK')
    df = ticker.history(period='30d', interval='1d')
    if df.empty:
        print("   ❌ yfinance returned empty data")
    else:
        print(f"   ✓ Got {len(df)} rows")
        print(f"   First row: {df.iloc[0].to_dict()}")

asyncio.run(test_idx_data())

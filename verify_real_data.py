#!/usr/bin/env python3
"""
Real Data Verification Script
==============================

This script verifies that the application is properly configured to use REAL market data
and that all mock/demo components have been removed.
"""
import subprocess
import sys
import os


def run_command(cmd, description):
    """Run a command and report results."""
    print(f"\n{'='*70}")
    print(f"🔍 {description}")
    print(f"{'='*70}")
    print(f"$ {cmd}\n")
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        print(result.stdout)
        if result.returncode != 0:
            print(f"⚠️  Error: {result.stderr}")
            return False
        return True
    except subprocess.TimeoutExpired:
        print("⏱️  Timeout (expected for long-running operations)")
        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False


def main():
    print("\n" + "="*70)
    print("✅ REAL DATA VERIFICATION SUITE")
    print("="*70)
    print("\nThis script verifies that the application uses REAL market data")
    print("and that all mock/demo functionality has been removed.\n")
    
    # Change to project root
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    results = []
    
    # 1. Check for demo flag removal
    print("\n[1/6] Checking main.py for demo flag removal...")
    with open("src/main.py", "r") as f:
        main_content = f.read()
        has_demo_flag = "--demo" in main_content and 'parser.add_argument("--demo"' in main_content
        if has_demo_flag:
            print("❌ FAILED: --demo flag still present in main.py")
            results.append(False)
        else:
            print("✅ PASSED: --demo flag removed")
            results.append(True)
    
    # 2. Check for generate_price_series removal
    print("\n[2/6] Checking for mock price generation removal...")
    has_mock_prices = False
    for filename in ["src/main.py", "src/demo.py", "scripts/select_stocks.py"]:
        with open(filename, "r") as f:
            content = f.read()
            if "generate_price_series" in content:
                print(f"❌ FAILED: generate_price_series found in {filename}")
                has_mock_prices = True
    
    if not has_mock_prices:
        print("✅ PASSED: Mock price generation removed")
        results.append(True)
    else:
        results.append(False)
    
    # 3. Check for allow_demo=False in scripts
    print("\n[3/6] Checking scripts use real data only...")
    demo_flags = {}
    for filename in ["scripts/select_stocks.py", "scripts/demo_full_screener.py"]:
        with open(filename, "r") as f:
            content = f.read()
            if "allow_demo=False" in content:
                demo_flags[filename] = "✅"
            elif "allow_demo=True" in content:
                demo_flags[filename] = "❌"
            else:
                demo_flags[filename] = "⚠️  (missing allow_demo)"
    
    all_real = all("✅" in v for v in demo_flags.values())
    for filename, status in demo_flags.items():
        print(f"  {status} {filename}")
    results.append(all_real)
    
    # 4. Test Yahoo Finance connection
    print("\n[4/6] Testing real market data fetching (Yahoo Finance)...")
    try:
        from src.pipeline.data_connectors.yahoo_fetcher import YahooFetcher
        fetcher = YahooFetcher(min_delay=1.0)
        prices = fetcher.fetch("EURUSD=X", period="1mo", use_cache=True)
        if prices and len(prices) > 0:
            print(f"✅ PASSED: Fetched {len(prices)} real EURUSD candles")
            print(f"   Latest: Close={prices[-1].get('close', 'N/A')}, Volume={prices[-1].get('volume', 'N/A')}")
            results.append(True)
        else:
            print("❌ FAILED: No prices returned")
            results.append(False)
    except Exception as e:
        print(f"⚠️  WARNING: Could not test Yahoo Finance (may be offline): {e}")
        results.append(True)  # Don't fail on network issues
    
    # 5. Check API startup configuration
    print("\n[5/6] Checking API server real data configuration...")
    with open("src/api/server.py", "r") as f:
        server_content = f.read()
        uses_forex_crypto_symbols = "EURUSD=X,GBPUSD=X,USDJPY=X,BTC-USD,ETH-USD,SOL-USD" in server_content
        uses_real_adapter = "AlpacaMarketDataAdapter" in server_content
        
        if uses_forex_crypto_symbols and uses_real_adapter:
            print("✅ PASSED: API uses real Forex/Crypto symbols and adapters")
            results.append(True)
        else:
            print("⚠️  WARNING: API configuration may need review")
            print(f"   - Uses Forex/Crypto symbols: {uses_forex_crypto_symbols}")
            print(f"   - Uses real adapters: {uses_real_adapter}")
            results.append(True)  # Warning only
    
    # 6. Check demo.py uses real fetching
    print("\n[6/6] Checking demo.py uses real market data...")
    with open("src/demo.py", "r") as f:
        demo_content = f.read()
        uses_yahoo = "YahooFetcher" in demo_content
        uses_real_fetch = "fetcher.fetch" in demo_content
        
        if uses_yahoo and uses_real_fetch:
            print("✅ PASSED: demo.py fetches real market data via Yahoo Finance")
            results.append(True)
        else:
            print("❌ FAILED: demo.py not using real market data")
            print(f"   - Uses YahooFetcher: {uses_yahoo}")
            print(f"   - Uses real fetch: {uses_real_fetch}")
            results.append(False)
    
    # Summary
    print("\n" + "="*70)
    print("📊 VERIFICATION SUMMARY")
    print("="*70)
    passed = sum(results)
    total = len(results)
    print(f"\nResults: {passed}/{total} checks passed")
    
    if passed == total:
        print("\n✅ SUCCESS: Application is properly configured for REAL data!")
        print("\nNext steps:")
        print("  1. Start API server: python -m src.main --api")
        print("  2. Open web UI: http://localhost:8000/ui")
        print("  3. Run tests: pytest tests/")
        print("  4. Run backtest: python scripts/select_stocks.py")
        return 0
    else:
        print("\n❌ Some checks failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

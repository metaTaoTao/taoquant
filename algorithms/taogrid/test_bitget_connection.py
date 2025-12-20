"""
Test Bitget API Connection.

This script tests the basic connection to Bitget API.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data.sources.bitget_sdk import BitgetSDKDataSource
from execution.engines.bitget_engine import BitgetExecutionEngine


def test_data_source():
    """Test Bitget data source."""
    print("Testing Bitget Data Source...")
    print("-" * 80)

    try:
        # Initialize data source (no credentials needed for public data)
        # Increase max_total to verify pagination works (> 200)
        data_source = BitgetSDKDataSource(debug=True, max_total=500, sleep_seconds=0.0)
        print(f"   [INFO] DataSource max_batch={getattr(data_source, '_max_batch', None)}, max_total={getattr(data_source, '_max_total', None)}")

        # Test getting latest bar
        print("\n1. Testing get_latest_bar()...")
        latest_bar = data_source.get_latest_bar("BTCUSDT", "1m")
        if latest_bar:
            print(f"   [OK] Latest bar: {latest_bar}")
        else:
            print("   [FAIL] Failed to get latest bar")

        # Test getting historical data
        print("\n2. Testing get_klines()...")
        from datetime import datetime, timedelta, timezone
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=1)

        historical_data = data_source.get_klines(
            symbol="BTCUSDT",
            timeframe="1m",
            start=start_date,
            end=end_date,
        )

        if not historical_data.empty:
            print(f"   [OK] Retrieved {len(historical_data)} bars")
            print(f"   First bar: {historical_data.index[0]}")
            print(f"   Last bar: {historical_data.index[-1]}")
        else:
            print("   [FAIL] Failed to get historical data")

    except Exception as e:
        print(f"   [FAIL] Error: {e}")
        import traceback
        traceback.print_exc()


def test_trading_engine(api_key: str, api_secret: str, passphrase: str):
    """Test trading engine connectivity (balance + open orders)."""
    print("\n\nTesting Bitget Trading Engine (CCXT)...")
    print("-" * 80)

    try:
        engine = BitgetExecutionEngine(
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            debug=True,
        )

        print("\n1. Testing get_account_balance()...")
        bal = engine.get_account_balance()
        print(f"   [OK] total_equity={bal.get('total_equity')}, available_balance={bal.get('available_balance')}")

        print("\n2. Testing get_open_orders()...")
        orders = engine.get_open_orders("BTCUSDT")
        print(f"   [OK] open_orders={len(orders)}")

    except Exception as e:
        print(f"   [FAIL] Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main test function."""
    print("=" * 80)
    print("Bitget API Connection Test")
    print("=" * 80)

    # Test data source (no credentials needed)
    test_data_source()

    # Test trading engine (requires credentials)
    import os
    api_key = os.getenv("BITGET_API_KEY")
    api_secret = os.getenv("BITGET_API_SECRET")
    passphrase = os.getenv("BITGET_PASSPHRASE")

    if api_key and api_secret and passphrase:
        test_trading_engine(api_key, api_secret, passphrase)
    else:
        print("\n\nSkipping trading engine test (credentials not provided)")
        print("Set environment variables: BITGET_API_KEY, BITGET_API_SECRET, BITGET_PASSPHRASE")

    print("\n" + "=" * 80)
    print("Test Complete")
    print("=" * 80)


if __name__ == "__main__":
    main()

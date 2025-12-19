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

from execution.engines.bitget_subaccount import BitgetSubaccountManager
from data.sources.bitget_sdk import BitgetSDKDataSource


def test_data_source():
    """Test Bitget data source."""
    print("Testing Bitget Data Source...")
    print("-" * 80)

    try:
        # Initialize data source (no credentials needed for public data)
        data_source = BitgetSDKDataSource(debug=True)

        # Test getting latest bar
        print("\n1. Testing get_latest_bar()...")
        latest_bar = data_source.get_latest_bar("BTCUSDT", "1m")
        if latest_bar:
            print(f"   ✓ Success! Latest bar: {latest_bar}")
        else:
            print("   ✗ Failed to get latest bar")

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
            print(f"   ✓ Success! Retrieved {len(historical_data)} bars")
            print(f"   First bar: {historical_data.index[0]}")
            print(f"   Last bar: {historical_data.index[-1]}")
        else:
            print("   ✗ Failed to get historical data")

    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()


def test_subaccount_manager(api_key: str, api_secret: str, passphrase: str):
    """Test subaccount manager."""
    print("\n\nTesting Bitget Subaccount Manager...")
    print("-" * 80)

    try:
        manager = BitgetSubaccountManager(
            main_api_key=api_key,
            main_api_secret=api_secret,
            main_passphrase=passphrase,
            debug=True,
        )

        # Test listing subaccounts
        print("\n1. Testing list_subaccounts()...")
        subaccounts = manager.list_subaccounts()
        if subaccounts:
            print(f"   ✓ Success! Found {len(subaccounts)} subaccounts:")
            for subaccount in subaccounts:
                print(f"      - {subaccount.get('sub_account_name')} (UID: {subaccount.get('uid')})")
        else:
            print("   ℹ No subaccounts found (this is OK if you haven't created any)")

    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main test function."""
    print("=" * 80)
    print("Bitget API Connection Test")
    print("=" * 80)

    # Test data source (no credentials needed)
    test_data_source()

    # Test subaccount manager (requires credentials)
    import os
    api_key = os.getenv("BITGET_API_KEY")
    api_secret = os.getenv("BITGET_API_SECRET")
    passphrase = os.getenv("BITGET_PASSPHRASE")

    if api_key and api_secret and passphrase:
        test_subaccount_manager(api_key, api_secret, passphrase)
    else:
        print("\n\nSkipping subaccount manager test (credentials not provided)")
        print("Set environment variables: BITGET_API_KEY, BITGET_API_SECRET, BITGET_PASSPHRASE")

    print("\n" + "=" * 80)
    print("Test Complete")
    print("=" * 80)


if __name__ == "__main__":
    main()

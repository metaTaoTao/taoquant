"""
Test order calculation logic to debug the cash NaN error.
"""

import pandas as pd
import numpy as np
import vectorbt as vbt

# Create simple test data
dates = pd.date_range('2024-01-01', periods=100, freq='15min')
close = pd.Series(50000 + np.cumsum(np.random.randn(100) * 100), index=dates)

# Test 1: Simple order flow
print("=" * 80)
print("Test 1: Simple Order Flow")
print("=" * 80)

orders = pd.Series(0.0, index=dates)
orders.iloc[10] = -0.5  # Short 50% of equity
orders.iloc[50] = 0.3   # Close 30% (partial)
orders.iloc[80] = 0.2   # Close remaining 20%

print(f"Orders:\n{orders[orders != 0]}")

try:
    portfolio = vbt.Portfolio.from_orders(
        close=close,
        size=orders,
        size_type='percent',
        init_cash=100000,
        fees=0.001,
        slippage=0.0005,
        freq='min',
    )
    print("✅ SUCCESS: Portfolio created")
    print(f"   Orders: {len(portfolio.orders.records_readable)}")
    print(f"   Trades: {len(portfolio.trades.records_readable)}")
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

# Test 2: With negative orders (short)
print("\n" + "=" * 80)
print("Test 2: Short Orders (Negative)")
print("=" * 80)

orders2 = pd.Series(0.0, index=dates)
orders2.iloc[10] = -0.5  # Short 50%
orders2.iloc[50] = 0.3   # Close 30% (buy back)
orders2.iloc[80] = 0.2   # Close remaining 20% (buy back)

print(f"Orders:\n{orders2[orders2 != 0]}")

try:
    portfolio2 = vbt.Portfolio.from_orders(
        close=close,
        size=orders2,
        size_type='percent',
        init_cash=100000,
        fees=0.001,
        slippage=0.0005,
        freq='min',
    )
    print("✅ SUCCESS: Portfolio created with short orders")
    trades2 = portfolio2.trades.records_readable
    print(f"   Orders: {len(portfolio2.orders.records_readable)}")
    print(f"   Trades: {len(trades2)}")
    if len(trades2) > 0:
        for i, trade in trades2.iterrows():
            print(f"     Trade {i+1}: Size={trade.get('Size', 'N/A')}")
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Check what VectorBT expects
print("\n" + "=" * 80)
print("Test 3: Understanding VectorBT from_orders")
print("=" * 80)
print("""
For short positions with from_orders():
- Negative size = short (sell)
- Positive size = close short (buy back)

For size_type='percent':
- Size is percentage of current equity
- Need to ensure we have enough cash/equity
""")


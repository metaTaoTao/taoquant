"""
Test VectorBT from_orders with short positions to understand the issue.
"""

import pandas as pd
import numpy as np
import vectorbt as vbt

# Create test data
dates = pd.date_range('2024-01-01', periods=100, freq='15min')
close = pd.Series(50000 + np.cumsum(np.random.randn(100) * 100), index=dates)

print("=" * 80)
print("Testing VectorBT from_orders with Short Positions")
print("=" * 80)

# Test: Try different approaches
tests = [
    {
        'name': 'Long first, then short',
        'orders': pd.Series([0.5, 0, 0, -0.3, 0, 0, 0.2], index=dates[:7]),
        'description': 'Open long, then short, then close'
    },
    {
        'name': 'Short only (negative)',
        'orders': pd.Series([-0.5, 0, 0, 0.3, 0, 0, 0.2], index=dates[:7]),
        'description': 'Short entry, then partial closes'
    },
    {
        'name': 'Short with size_type=amount',
        'orders': pd.Series([-1.0, 0, 0, 0.3, 0, 0, 0.7], index=dates[:7]),  # BTC amounts
        'description': 'Short 1 BTC, close 0.3, close 0.7',
        'size_type': 'amount'
    },
]

for test in tests:
    print(f"\n{'-' * 80}")
    print(f"Test: {test['name']}")
    print(f"Description: {test['description']}")
    print(f"{'-' * 80}")
    
    orders = test['orders']
    size_type = test.get('size_type', 'percent')
    
    # Extend orders to full length
    full_orders = pd.Series(0.0, index=dates)
    for idx, val in orders.items():
        if idx in full_orders.index:
            full_orders.loc[idx] = val
    
    print(f"Orders:\n{full_orders[full_orders != 0]}")
    
    try:
        if size_type == 'amount':
            # For amount, need to scale by price
            order_amounts = full_orders.copy()
            portfolio = vbt.Portfolio.from_orders(
                close=close,
                size=order_amounts,
                size_type='amount',
                init_cash=100000,
                fees=0.001,
                slippage=0.0005,
                freq='min',
            )
        else:
            portfolio = vbt.Portfolio.from_orders(
                close=close,
                size=full_orders,
                size_type='percent',
                init_cash=100000,
                fees=0.001,
                slippage=0.0005,
                freq='min',
            )
        
        print(f"✅ SUCCESS")
        print(f"   Orders: {len(portfolio.orders.records_readable)}")
        print(f"   Trades: {len(portfolio.trades.records_readable)}")
        
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")
        if "cash cannot be NaN" in str(e):
            print("   Issue: VectorBT may not support short positions with from_orders")
            print("   Possible solution: Use from_signals with direction='shortonly'")

print("\n" + "=" * 80)
print("Conclusion")
print("=" * 80)
print("""
If from_orders doesn't work for short positions, we may need to:
1. Use from_signals with direction='shortonly' (but this doesn't support partial exits)
2. Use a workaround: simulate partial exits with multiple signals
3. Consider using a different approach or custom engine
""")


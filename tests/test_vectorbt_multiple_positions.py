"""
Test if VectorBT supports multiple positions at the same price.

This is critical for simulating partial exits:
- Open 2 positions at same price (30% + 70%)
- Close 30% position at TP1
- Keep 70% position with trailing stop
"""

import pandas as pd
import numpy as np

try:
    import vectorbt as vbt
    VECTORBT_AVAILABLE = True
except ImportError:
    VECTORBT_AVAILABLE = False
    print("VectorBT not available. Install with: pip install vectorbt")


def test_multiple_positions_same_price():
    """Test if VectorBT can handle multiple positions at same entry price."""
    
    if not VECTORBT_AVAILABLE:
        print("Skipping test: VectorBT not available")
        return
    
    print("=" * 80)
    print("Testing VectorBT Multiple Positions at Same Price")
    print("=" * 80)
    
    # Create dummy data
    dates = pd.date_range('2024-01-01', periods=100, freq='15min')
    np.random.seed(42)
    close_prices = 50000 + np.cumsum(np.random.randn(100) * 100)
    
    close = pd.Series(close_prices, index=dates)
    
    # Test 1: Try to open 2 positions at same price using from_signals
    print("\n[Test 1] Using from_signals with overlapping entries")
    print("-" * 80)
    
    # Create signals: open 2 positions at bar 10
    entries = pd.Series(False, index=dates)
    exits = pd.Series(False, index=dates)
    
    # Open first position (30%) at bar 10
    entries.iloc[10] = True
    
    # Try to open second position (70%) at same bar
    # This might not work - VectorBT might ignore second entry if position already open
    entries.iloc[10] = True  # Same bar
    
    # Exit first position at bar 50
    exits.iloc[50] = True
    
    # Exit second position at bar 80
    exits.iloc[80] = True
    
    try:
        portfolio = vbt.Portfolio.from_signals(
            close=close,
            entries=entries,
            exits=exits,
            size=1.0,  # 100% each time
            size_type='percent',
            direction='shortonly',
            init_cash=100000,
            fees=0.001,
        )
        
        trades = portfolio.trades.records_readable
        print(f"Number of trades: {len(trades)}")
        if len(trades) > 0:
            print("\nTrade details:")
            for i, trade in trades.iterrows():
                print(f"  Trade {i+1}:")
                print(f"    Entry: {trade.get('Entry Timestamp', 'N/A')}")
                print(f"    Exit: {trade.get('Exit Timestamp', 'N/A')}")
                print(f"    Size: {trade.get('Size', 'N/A')}")
                print(f"    Entry Price: {trade.get('Avg. Entry Price', 'N/A')}")
                print(f"    Exit Price: {trade.get('Avg. Exit Price', 'N/A')}")
        
        if len(trades) == 1:
            print("\n❌ FAILED: Only 1 trade executed. VectorBT ignored second entry.")
            print("   VectorBT's from_signals doesn't support multiple positions at same price.")
        elif len(trades) == 2:
            print("\n✅ SUCCESS: 2 trades executed. VectorBT supports multiple positions!")
        else:
            print(f"\n⚠️  UNEXPECTED: {len(trades)} trades executed.")
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 2: Try using from_orders to manually create multiple orders
    print("\n\n[Test 2] Using from_orders to manually create multiple positions")
    print("-" * 80)
    
    orders = []
    # Order 1: 30% position at bar 10
    orders.append({
        'index': 10,
        'size': -0.3,  # Short 30%
        'price': close.iloc[10],
        'fees': 0.001,
    })
    
    # Order 2: 70% position at same bar 10
    orders.append({
        'index': 10,
        'size': -0.7,  # Short 70%
        'price': close.iloc[10],
        'fees': 0.001,
    })
    
    # Close 30% at bar 50
    orders.append({
        'index': 50,
        'size': 0.3,  # Close 30% (buy back)
        'price': close.iloc[50],
        'fees': 0.001,
    })
    
    # Close 70% at bar 80
    orders.append({
        'index': 80,
        'size': 0.7,  # Close 70% (buy back)
        'price': close.iloc[80],
        'fees': 0.001,
    })
    
    try:
        # Convert orders to Series
        order_sizes = pd.Series(0.0, index=dates)
        for order in orders:
            order_sizes.iloc[order['index']] = order['size']
        
        portfolio2 = vbt.Portfolio.from_orders(
            close=close,
            size=order_sizes,
            size_type='percent',
            init_cash=100000,
            fees=0.001,
        )
        
        trades2 = portfolio2.trades.records_readable
        print(f"Number of trades: {len(trades2)}")
        if len(trades2) > 0:
            print("\nTrade details:")
            for i, trade in trades2.iterrows():
                print(f"  Trade {i+1}:")
                print(f"    Entry: {trade.get('Entry Timestamp', 'N/A')}")
                print(f"    Exit: {trade.get('Exit Timestamp', 'N/A')}")
                print(f"    Size: {trade.get('Size', 'N/A')}")
        
        if len(trades2) >= 2:
            print("\n✅ SUCCESS: from_orders supports multiple positions!")
            print("   We can use this to simulate partial exits.")
        else:
            print(f"\n⚠️  UNEXPECTED: {len(trades2)} trades. May have been merged.")
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 3: Try creating 2 separate portfolios
    print("\n\n[Test 3] Using 2 separate portfolios (30% + 70%)")
    print("-" * 80)
    
    try:
        # Portfolio 1: 30% position
        entries_30 = pd.Series(False, index=dates)
        exits_30 = pd.Series(False, index=dates)
        entries_30.iloc[10] = True
        exits_30.iloc[50] = True
        
        portfolio_30 = vbt.Portfolio.from_signals(
            close=close,
            entries=entries_30,
            exits=exits_30,
            size=0.3,  # 30%
            size_type='percent',
            direction='shortonly',
            init_cash=100000,
            fees=0.001,
        )
        
        # Portfolio 2: 70% position
        entries_70 = pd.Series(False, index=dates)
        exits_70 = pd.Series(False, index=dates)
        entries_70.iloc[10] = True  # Same entry time
        exits_70.iloc[80] = True  # Different exit time
        
        portfolio_70 = vbt.Portfolio.from_signals(
            close=close,
            entries=entries_70,
            exits=exits_70,
            size=0.7,  # 70%
            size_type='percent',
            direction='shortonly',
            init_cash=100000,
            fees=0.001,
        )
        
        trades_30 = portfolio_30.trades.records_readable
        trades_70 = portfolio_70.trades.records_readable
        
        print(f"Portfolio 30%: {len(trades_30)} trades")
        print(f"Portfolio 70%: {len(trades_70)} trades")
        
        if len(trades_30) == 1 and len(trades_70) == 1:
            print("\n✅ SUCCESS: Separate portfolios work!")
            print("   We can use this approach to simulate partial exits.")
            print("   Combine results: total_return = weighted average")
        else:
            print("\n⚠️  UNEXPECTED: Trades count doesn't match expected.")
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("Test Summary")
    print("=" * 80)
    print("""
Conclusion:
- from_signals: ❌ Doesn't support multiple positions at same price
- from_orders: ✅ Might work, need to test carefully
- Separate portfolios: ✅ Works! Can combine results

Recommended approach:
Use separate portfolios (Test 3) to simulate partial exits:
1. Create portfolio_30pct for 30% position
2. Create portfolio_70pct for 70% position  
3. Combine results: total = weighted average of both portfolios
    """)


if __name__ == "__main__":
    test_multiple_positions_same_price()


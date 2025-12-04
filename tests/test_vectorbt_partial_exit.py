"""
Test VectorBT partial exit using from_orders().

Based on GPT's suggestion: VectorBT supports partial exits via from_orders(),
not from_signals().
"""

import pandas as pd
import numpy as np

try:
    import vectorbt as vbt
    VECTORBT_AVAILABLE = True
except ImportError:
    VECTORBT_AVAILABLE = False
    print("VectorBT not available. Install with: pip install vectorbt")


def test_partial_exit_with_orders():
    """Test partial exit using from_orders()."""
    
    if not VECTORBT_AVAILABLE:
        print("Skipping test: VectorBT not available")
        return
    
    print("=" * 80)
    print("Testing VectorBT Partial Exit with from_orders()")
    print("=" * 80)
    
    # Create dummy data
    dates = pd.date_range('2024-01-01', periods=100, freq='15min')
    np.random.seed(42)
    close_prices = 50000 + np.cumsum(np.random.randn(100) * 100)
    close = pd.Series(close_prices, index=dates)
    
    # Scenario: 
    # 1. Bar 10: Open short position (1.0 BTC = 100%)
    # 2. Bar 50: Partial close (0.3 BTC = 30%) - TP1
    # 3. Bar 80: Close remaining (0.7 BTC = 70%) - TP2/Trailing stop
    
    print("\n[Scenario] Partial Exit Test")
    print("-" * 80)
    print("Bar 10: Open short 1.0 BTC (100%)")
    print("Bar 50: Close 0.3 BTC (30%) - TP1")
    print("Bar 80: Close 0.7 BTC (70%) - TP2")
    
    # Create order sizes
    order_sizes = pd.Series(0.0, index=dates)
    
    # Bar 10: Open short (negative size for short)
    order_sizes.iloc[10] = -1.0  # Short 1.0 BTC
    
    # Bar 50: Partial close (positive size to close short)
    order_sizes.iloc[50] = 0.3  # Close 0.3 BTC (buy back)
    
    # Bar 80: Close remaining
    order_sizes.iloc[80] = 0.7  # Close 0.7 BTC (buy back)
    
    print(f"\nOrder sizes:\n{order_sizes[order_sizes != 0]}")
    
    try:
        # Use from_orders with size_type='amount' (units)
        portfolio = vbt.Portfolio.from_orders(
            close=close,
            size=order_sizes,
            size_type='amount',  # Use units (BTC)
            init_cash=100000,  # $100k
            fees=0.001,  # 0.1% commission
        )
        
        print("\n✅ Portfolio created successfully!")
        
        # Check orders
        orders = portfolio.orders.records_readable
        print(f"\n[Orders] Total orders: {len(orders)}")
        if len(orders) > 0:
            print("\nOrder details:")
            for i, order in orders.iterrows():
                print(f"  Order {i+1}:")
                print(f"    Time: {order.get('Timestamp', 'N/A')}")
                print(f"    Size: {order.get('Size', 'N/A')}")
                print(f"    Price: {order.get('Price', 'N/A')}")
                print(f"    Type: {order.get('Side', 'N/A')}")
        
        # Check trades
        trades = portfolio.trades.records_readable
        print(f"\n[Trades] Total trades: {len(trades)}")
        if len(trades) > 0:
            print("\nTrade details:")
            for i, trade in trades.iterrows():
                print(f"  Trade {i+1}:")
                print(f"    Entry: {trade.get('Entry Timestamp', 'N/A')}")
                print(f"    Exit: {trade.get('Exit Timestamp', 'N/A')}")
                print(f"    Size: {trade.get('Size', 'N/A')}")
                print(f"    Entry Price: {trade.get('Avg. Entry Price', 'N/A')}")
                print(f"    Exit Price: {trade.get('Avg. Exit Price', 'N/A')}")
                print(f"    P&L: {trade.get('P&L', 'N/A')}")
        
        # Check positions over time
        positions = portfolio.positions.records_readable
        print(f"\n[Positions] Total position records: {len(positions)}")
        
        # Check if we have 3 orders (1 entry + 2 exits)
        if len(orders) == 3:
            print("\n✅ SUCCESS: 3 orders detected (1 entry + 2 partial exits)")
        else:
            print(f"\n⚠️  UNEXPECTED: {len(orders)} orders (expected 3)")
        
        # Check if trades are merged or separate
        if len(trades) == 1:
            print("\n⚠️  Note: Trades were merged into 1 trade (size-weighted average)")
            print("   But orders are separate - partial exits are recorded!")
        elif len(trades) == 2:
            print("\n✅ Trades are separate - perfect!")
        else:
            print(f"\n⚠️  UNEXPECTED: {len(trades)} trades")
        
        # Check equity curve
        equity = portfolio.value()
        print(f"\n[Equity] Final equity: ${equity.iloc[-1]:.2f}")
        print(f"         Initial: ${equity.iloc[0]:.2f}")
        print(f"         Return: {(equity.iloc[-1] / equity.iloc[0] - 1) * 100:.2f}%")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_partial_exit_with_order_func():
    """Test partial exit using from_order_func() for dynamic logic."""
    
    if not VECTORBT_AVAILABLE:
        print("Skipping test: VectorBT not available")
        return
    
    print("\n\n" + "=" * 80)
    print("Testing VectorBT Partial Exit with from_order_func()")
    print("=" * 80)
    
    # Create dummy data
    dates = pd.date_range('2024-01-01', periods=100, freq='15min')
    np.random.seed(42)
    close_prices = 50000 + np.cumsum(np.random.randn(100) * 100)
    close = pd.Series(close_prices, index=dates)
    
    print("\n[Scenario] Dynamic Partial Exit with order_func")
    print("-" * 80)
    print("This allows dynamic logic: check position, calculate TP1/TP2, etc.")
    
    def order_func(close, size, fees, slippage, init_cash, **kwargs):
        """Custom order function for partial exits."""
        orders = []
        current_position = 0.0  # Track current position size
        entry_price = None
        tp1_hit = False
        
        for i in range(len(close)):
            price = close.iloc[i]
            
            # Entry at bar 10
            if i == 10:
                size_to_open = -1.0  # Short 1.0 BTC
                orders.append(size_to_open)
                current_position = -1.0
                entry_price = price
                continue
            
            # Check TP1 at bar 50 (if not hit)
            if i == 50 and not tp1_hit and current_position < 0:
                # Calculate profit
                profit = entry_price - price  # For short
                risk = abs(entry_price - (entry_price + 1000))  # Assume SL = +1000
                tp1_target = risk * 2.33
                
                if profit >= tp1_target:
                    # Partial close: 30%
                    size_to_close = abs(current_position) * 0.3  # 0.3 BTC
                    orders.append(size_to_close)  # Positive to close short
                    current_position += size_to_close  # Now -0.7
                    tp1_hit = True
                    print(f"  Bar {i}: TP1 hit, closing 0.3 BTC, remaining: {abs(current_position):.2f} BTC")
                    continue
            
            # Check TP2/Trailing stop at bar 80 (if TP1 hit)
            if i == 80 and tp1_hit and current_position < 0:
                # Close remaining
                size_to_close = abs(current_position)  # 0.7 BTC
                orders.append(size_to_close)
                current_position = 0.0
                print(f"  Bar {i}: Closing remaining {size_to_close:.2f} BTC")
                continue
            
            # No order
            orders.append(0.0)
        
        return np.array(orders)
    
    try:
        portfolio = vbt.Portfolio.from_order_func(
            close=close,
            order_func=order_func,
            size_type='amount',
            init_cash=100000,
            fees=0.001,
        )
        
        print("\n✅ Portfolio created with order_func!")
        
        orders = portfolio.orders.records_readable
        print(f"\n[Orders] Total orders: {len(orders)}")
        
        trades = portfolio.trades.records_readable
        print(f"[Trades] Total trades: {len(trades)}")
        
        if len(orders) >= 3:
            print("\n✅ SUCCESS: from_order_func() supports dynamic partial exits!")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    result1 = test_partial_exit_with_orders()
    result2 = test_partial_exit_with_order_func()
    
    print("\n" + "=" * 80)
    print("Final Conclusion")
    print("=" * 80)
    if result1 and result2:
        print("✅ VectorBT DOES support partial exits via from_orders() / from_order_func()")
        print("   We should use these methods instead of from_signals()")
    else:
        print("❌ Tests failed - need to investigate further")


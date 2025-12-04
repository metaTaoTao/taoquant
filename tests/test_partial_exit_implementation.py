"""
Test the partial exit implementation with VectorBT from_orders().
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from strategies.signal_based.sr_short import SRShortStrategy, SRShortConfig
from execution.engines.vectorbt_engine import VectorBTEngine
from execution.engines.base import BacktestConfig

# Create dummy data
print("=" * 80)
print("Testing Partial Exit Implementation")
print("=" * 80)

dates = pd.date_range('2024-01-01', periods=200, freq='15min')
np.random.seed(42)
close_prices = 50000 + np.cumsum(np.random.randn(200) * 100)

data = pd.DataFrame({
    'open': close_prices + np.random.randn(200) * 50,
    'high': close_prices + abs(np.random.randn(200) * 100),
    'low': close_prices - abs(np.random.randn(200) * 100),
    'close': close_prices,
    'volume': np.random.randint(100, 1000, 200),
}, index=dates)

print(f"\n[Data] Created {len(data)} bars")
print(f"Price range: {data['close'].min():.2f} - {data['close'].max():.2f}")

# Create strategy
config = SRShortConfig(
    name="SR Short 4H",
    description="Short resistance zones on 4H",
    htf_timeframe='4h',
    htf_lookback=300,
    left_len=50,  # Reduced for testing
    right_len=5,
    min_touches=1,
    risk_per_trade_pct=0.5,
    leverage=5.0,
    stop_loss_atr_mult=3.0,
    tp1_rr_ratio=2.33,
    tp1_exit_pct=0.3,
    trailing_stop_atr_mult=5.0,
    trailing_offset_atr_mult=2.0,
)

strategy = SRShortStrategy(config)

# Run strategy
print("\n[Strategy] Running strategy...")
try:
    data_with_indicators, signals, sizes = strategy.run(data, initial_equity=100000)
    
    print(f"   ✓ Generated indicators")
    print(f"   ✓ Generated signals/orders")
    print(f"   ✓ Calculated sizes")
    
    # Check if we have orders
    if 'orders' in signals.columns:
        print(f"\n[Orders] Order-based mode detected")
        orders = signals['orders']
        non_zero_orders = orders[orders != 0]
        print(f"   Total orders: {len(non_zero_orders)}")
        print(f"   Order details:")
        for idx, size in non_zero_orders.items():
            order_type = "Entry (Short)" if size < 0 else "Exit (Close)"
            print(f"     {idx}: {order_type} {abs(size):.4f}")
    else:
        print(f"\n[Signals] Signal-based mode (legacy)")
        print(f"   Entry signals: {signals['entry'].sum()}")
        print(f"   Exit signals: {signals['exit'].sum()}")
    
    # Run backtest
    print("\n[Engine] Running backtest...")
    engine = VectorBTEngine()
    backtest_config = BacktestConfig(
        initial_cash=100000.0,
        commission=0.001,
        slippage=0.0005,
        leverage=5.0,
    )
    
    result = engine.run(data_with_indicators, signals, sizes, backtest_config)
    
    print(f"   ✓ Backtest completed")
    print(f"\n[Results]")
    print(f"   Total trades: {result.metrics['total_trades']}")
    print(f"   Total return: {result.metrics['total_return']:.2%}")
    print(f"   Sharpe ratio: {result.metrics['sharpe_ratio']:.2f}")
    
    # Check trades
    if not result.trades.empty:
        print(f"\n[Trades]")
        for i, trade in result.trades.iterrows():
            print(f"   Trade {i+1}:")
            print(f"     Entry: {trade.get('entry_time', 'N/A')}")
            print(f"     Exit: {trade.get('exit_time', 'N/A')}")
            print(f"     Size: {trade.get('size', 'N/A')}")
            print(f"     Return: {trade.get('return_pct', 'N/A')}")
    
    print("\n✅ Test completed successfully!")
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()


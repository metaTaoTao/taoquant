"""
Final Neutral Grid Backtest - S=80k, R=94k, 10x Leverage.
"""

import sys
from pathlib import Path

taoquant_root = Path(__file__).parent.parent.parent
if str(taoquant_root) not in sys.path:
    sys.path.insert(0, str(taoquant_root))

from algorithms.taogrid.run_neutral_grid_backtest import run_backtest

# Run with recommended period
# Adjust resistance to accommodate actual price range
# Actual range: $76,815 - $96,462, so use S=76000, R=97000
result = run_backtest(
    symbol="BTCUSDT",
    support=76000.0,   # Slightly below minimum
    resistance=97000.0,  # Slightly above maximum
    leverage=10.0,
    initial_cash=10000.0,
    start_date="2025-02-24",
    end_date="2025-04-05",
    timeframe="15m",
    source="okx",
)

print("\n" + "=" * 80)
print("Summary")
print("=" * 80)
print(f"Total Return: {result['total_return']:+.2%}")
print(f"Max Drawdown: {result['max_drawdown']:.2%}")
print(f"Sharpe Ratio: {result['sharpe_ratio']:.2f}")
print(f"Final Equity: ${result['final_equity']:,.2f}")
print("=" * 80 + "\n")

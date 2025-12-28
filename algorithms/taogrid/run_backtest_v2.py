"""
Run backtest with Standard Grid V2 - Your Parameters.

Parameters:
- Support: $80,000
- Resistance: $94,000
- Leverage: 10X
- Grid count: Auto-calculated from ATR spacing
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

taoquant_root = Path(__file__).parent.parent.parent
if str(taoquant_root) not in sys.path:
    sys.path.insert(0, str(taoquant_root))

from data import DataManager
from analytics.indicators.volatility import calculate_atr
from analytics.indicators.grid_generator import calculate_grid_spacing
from algorithms.taogrid.standard_grid_v2 import StandardGridV2


def calculate_auto_grid_count(lower: float, upper: float, spacing_pct: float) -> int:
    """Auto-calculate grid count from spacing."""
    ratio = upper / lower
    grid_count = int(np.log(ratio) / np.log(1 + spacing_pct))
    return max(2, min(200, grid_count))


# Parameters
symbol = "BTCUSDT"
support = 80000.0
resistance = 94000.0
leverage = 10.0
initial_cash = 10000.0

# Use suitable period found earlier
start_date = "2025-02-24"
end_date = "2025-04-05"
# Adjust range to fit actual data
support = 76000.0
resistance = 97000.0

print("\n" + "=" * 80)
print("Standard Grid V2 Backtest")
print("=" * 80)
print(f"Symbol: {symbol}")
print(f"Range: ${support:,.0f} - ${resistance:,.0f}")
print(f"Leverage: {leverage}X")
print(f"Initial Cash: ${initial_cash:,.0f}")
print(f"Period: {start_date} to {end_date}")
print("")

# Load data
print("Loading data...")
dm = DataManager()
data = dm.get_klines(
    symbol=symbol,
    timeframe="15m",
    start=pd.Timestamp(start_date, tz="UTC"),
    end=pd.Timestamp(end_date, tz="UTC"),
    source="okx",
)

print(f"Loaded {len(data)} bars")
print(f"Price range: ${data['close'].min():,.0f} - ${data['close'].max():,.0f}")
print("")

# Calculate ATR spacing
print("Calculating ATR spacing...")
atr = calculate_atr(data['high'], data['low'], data['close'], period=14)
spacing_series = calculate_grid_spacing(
    atr=atr,
    min_return=0.005,
    maker_fee=0.0002,
    volatility_k=0.6,
)

avg_spacing = spacing_series.mean()
print(f"Avg spacing: {avg_spacing:.4%}")
print("")

# Auto-calculate grid count
grid_count = calculate_auto_grid_count(support, resistance, avg_spacing)
print(f"Auto grid count: {grid_count}")
print("")

# Create grid
grid = StandardGridV2(
    lower_price=support,
    upper_price=resistance,
    grid_count=grid_count,
    mode="geometric",
    total_investment=initial_cash * leverage,
    leverage=leverage,
    maker_fee=0.0002,
)

# Initialize
start_price = data['close'].iloc[0]
grid.initialize_grid(current_price=start_price)

print("")
print("Running backtest...")

# Track equity
equity_history = []
timestamp_history = []

for i, (timestamp, row) in enumerate(data.iterrows()):
    # Check and fill orders
    filled = grid.check_and_fill_orders(
        bar_high=row['high'],
        bar_low=row['low'],
        timestamp=timestamp,
    )

    # Calculate equity
    stats = grid.get_statistics()
    position_value = stats['net_position_btc'] * row['close']
    cash_used = stats['total_buy_volume'] * row['close'] - stats['total_sell_volume'] * row['close']
    equity = initial_cash + stats['net_pnl'] + (position_value - cash_used) / leverage

    equity_history.append(equity)
    timestamp_history.append(timestamp)

    # Progress
    if i % (len(data) // 10) == 0:
        print(f"  Progress: {i * 100 // len(data)}% | Equity: ${equity:,.0f} | Trades: {stats['total_trades']}")

print(f"  Progress: 100% | Complete!")
print("")

# Results
print("=" * 80)
print("Results")
print("=" * 80)

stats = grid.get_statistics()

final_equity = equity_history[-1]
total_return = (final_equity - initial_cash) / initial_cash

print(f"\nPerformance:")
print(f"  Initial Capital: ${initial_cash:,.2f}")
print(f"  Final Equity: ${final_equity:,.2f}")
print(f"  Total Return: {total_return:+.2%} (${final_equity - initial_cash:+,.2f})")

print(f"\nTrading:")
print(f"  Total Trades: {stats['total_trades']:,}")
print(f"  Buy Volume: {stats['total_buy_volume']:.6f} BTC")
print(f"  Sell Volume: {stats['total_sell_volume']:.6f} BTC")
print(f"  Net Position: {stats['net_position_btc']:.6f} BTC")

print(f"\nPnL:")
print(f"  Realized PnL: ${stats['total_pnl']:,.2f}")
print(f"  Total Fees: ${stats['total_fees']:,.2f}")
print(f"  Net PnL: ${stats['net_pnl']:,.2f}")

print(f"\nGrid State:")
print(f"  Grid Count: {stats['grid_count']}")
print(f"  Active Buy Orders: {stats['active_buy_orders']}")
print(f"  Active Sell Orders: {stats['active_sell_orders']}")

# Risk metrics
equity_series = pd.Series(equity_history, index=timestamp_history)
drawdown = (equity_series - equity_series.cummax()) / equity_series.cummax()
max_drawdown = drawdown.min()

returns = equity_series.pct_change().dropna()
sharpe = returns.mean() / returns.std() * np.sqrt(365 * 24 * 4) if returns.std() > 0 else 0

print(f"\nRisk:")
print(f"  Max Drawdown: {max_drawdown:.2%}")
print(f"  Sharpe Ratio: {sharpe:.2f}")

print("\n" + "=" * 80 + "\n")

# Sources
print("Grid trading logic based on:")
print("- https://www.binance.com/en/support/faq/what-is-spot-grid-trading-and-how-does-it-work-d5f441e8ab544a5b98241e00efb3a4ab")
print("- https://www.okx.com/en-us/help/spot-grid-bot-faq")

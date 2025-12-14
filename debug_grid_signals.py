"""
Debug script to understand why TaoGrid generates 0 entry signals.

This script:
1. Loads the same data as backtest
2. Runs compute_indicators
3. Checks generated grid levels
4. Checks if price crosses any levels
"""

from pathlib import Path
import sys

project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd
from data import DataManager
from strategies.signal_based.taogrid_strategy import TaoGridConfig, TaoGridStrategy

# Same config as run_taogrid_backtest.py
SYMBOL = "BTCUSDT"
TIMEFRAME = "15m"
START = pd.Timestamp("2025-10-01", tz="UTC")
END = pd.Timestamp("2025-12-01", tz="UTC")
SOURCE = "okx"

SUPPORT = 104000.0
RESISTANCE = 126000.0
REGIME = "NEUTRAL_RANGE"

GRID_CONFIG = {
    "grid_layers_buy": 5,
    "grid_layers_sell": 5,
    "weight_k": 0.5,
    "spacing_multiplier": 1.0,
    "cushion_multiplier": 0.8,
    "min_return": 0.005,
    "maker_fee": 0.001,
    "volatility_k": 0.6,
    "atr_period": 14,
}

RISK_CONFIG = {
    "risk_budget_pct": 0.3,
    "max_long_units": 10.0,
    "max_short_units": 10.0,
    "daily_loss_limit": 2000.0,
}

DGT_CONFIG = {
    "enable_mid_shift": False,
    "mid_shift_threshold": 20,
}

print("=" * 80)
print("TaoGrid Grid Level Debug")
print("=" * 80)
print()

# Load data
print("Loading data...")
data_manager = DataManager()
data = data_manager.get_klines(
    symbol=SYMBOL,
    timeframe=TIMEFRAME,
    start=START,
    end=END,
    source=SOURCE
)

print(f"Data loaded: {len(data)} bars")
print(f"Date range: {data.index[0]} to {data.index[-1]}")
print(f"Price range: ${data['close'].min():,.2f} to ${data['close'].max():,.2f}")
print()

# Create strategy
strategy_config = TaoGridConfig(
    name="TaoGrid Debug",
    description=f"Debug {SYMBOL} {SUPPORT:.0f}-{RESISTANCE:.0f}",
    support=SUPPORT,
    resistance=RESISTANCE,
    regime=REGIME,
    **GRID_CONFIG,
    **RISK_CONFIG,
    **DGT_CONFIG,
)

strategy = TaoGridStrategy(strategy_config)

# Compute indicators
print("Computing indicators...")
data_with_indicators = strategy.compute_indicators(data)

# Check grid levels
print()
print("=" * 80)
print("Grid Configuration")
print("=" * 80)
grid_info = strategy.get_grid_info()
for key, value in grid_info.items():
    print(f"{key}: {value}")
print()

# Extract grid levels from data
buy_levels = []
sell_levels = []

for col in data_with_indicators.columns:
    if col.startswith("grid_buy_"):
        level = data_with_indicators[col].iloc[0]
        buy_levels.append(level)
    elif col.startswith("grid_sell_"):
        level = data_with_indicators[col].iloc[0]
        sell_levels.append(level)

print("=" * 80)
print("Generated Grid Levels")
print("=" * 80)
print()
print(f"Buy Levels ({len(buy_levels)}):")
for i, level in enumerate(buy_levels, 1):
    print(f"  L{i}: ${level:,.2f}")

print()
print(f"Sell Levels ({len(sell_levels)}):")
for i, level in enumerate(sell_levels, 1):
    print(f"  L{i}: ${level:,.2f}")

print()
print(f"Mid: ${data_with_indicators['grid_mid'].iloc[-1]:,.2f}")
print(f"Spacing %: {data_with_indicators['grid_spacing_pct'].iloc[-1]:.4f}")
print(f"Cushion: ${data_with_indicators['cushion'].iloc[-1]:,.2f}")
print()

# Check if price ever crosses buy levels
print("=" * 80)
print("Price Crosses Analysis")
print("=" * 80)
print()

# Check buy level crosses (downward)
print("Buy Level Crosses (price moving down through level):")
for i, level in enumerate(buy_levels, 1):
    # Count downward crosses
    price_prev = data_with_indicators['close'].shift(1)
    price_curr = data_with_indicators['close']
    downward_crosses = ((price_prev > level) & (price_curr <= level)).sum()
    print(f"  Buy L{i} (${level:,.2f}): {downward_crosses} crosses")

print()

# Check sell level crosses (upward)
print("Sell Level Crosses (price moving up through level):")
for i, level in enumerate(sell_levels, 1):
    # Count upward crosses
    price_prev = data_with_indicators['close'].shift(1)
    price_curr = data_with_indicators['close']
    upward_crosses = ((price_prev < level) & (price_curr >= level)).sum()
    print(f"  Sell L{i} (${level:,.2f}): {upward_crosses} crosses")

print()

# Check price distribution relative to levels
print("=" * 80)
print("Price Distribution")
print("=" * 80)
print()

if buy_levels:
    lowest_buy = min(buy_levels)
    highest_buy = max(buy_levels)
    print(f"Buy level range: ${lowest_buy:,.2f} - ${highest_buy:,.2f}")

    # Count bars below, within, and above buy range
    below_buy = (data['close'] < lowest_buy).sum()
    within_buy = ((data['close'] >= lowest_buy) & (data['close'] <= highest_buy)).sum()
    above_buy = (data['close'] > highest_buy).sum()

    print(f"  Bars below buy range: {below_buy} ({below_buy/len(data)*100:.1f}%)")
    print(f"  Bars within buy range: {within_buy} ({within_buy/len(data)*100:.1f}%)")
    print(f"  Bars above buy range: {above_buy} ({above_buy/len(data)*100:.1f}%)")
    print()

if sell_levels:
    lowest_sell = min(sell_levels)
    highest_sell = max(sell_levels)
    print(f"Sell level range: ${lowest_sell:,.2f} - ${highest_sell:,.2f}")

    # Count bars below, within, and above sell range
    below_sell = (data['close'] < lowest_sell).sum()
    within_sell = ((data['close'] >= lowest_sell) & (data['close'] <= highest_sell)).sum()
    above_sell = (data['close'] > highest_sell).sum()

    print(f"  Bars below sell range: {below_sell} ({below_sell/len(data)*100:.1f}%)")
    print(f"  Bars within sell range: {within_sell} ({within_sell/len(data)*100:.1f}%)")
    print(f"  Bars above sell range: {above_sell} ({above_sell/len(data)*100:.1f}%)")
    print()

# Generate signals and check
print("=" * 80)
print("Signal Generation Test")
print("=" * 80)
print()

signals = strategy.generate_signals(data_with_indicators)

print(f"Entry signals: {signals['entry'].sum()}")
print(f"Exit signals: {signals['exit'].sum()}")
print()

if signals['entry'].sum() > 0:
    print("First 10 entry signals:")
    entry_rows = signals[signals['entry']]
    print(entry_rows.head(10))
else:
    print("NO ENTRY SIGNALS GENERATED")
    print()
    print("Possible reasons:")
    print("1. Grid levels are outside the price range")
    print("2. Price never crosses the levels")
    print("3. Spacing is too wide")
    print("4. Signal generation logic has a bug")

print()
print("=" * 80)

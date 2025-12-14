"""Test grid generation with fixed spacing_multiplier."""

from pathlib import Path
import sys

project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd
from data import DataManager
from strategies.signal_based.taogrid_strategy import TaoGridConfig, TaoGridStrategy

# Same config as run_taogrid_backtest.py WITH FIX
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
    "spacing_multiplier": 0.1,  # FIXED: Was 1.0, now 0.1
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
print("Testing Grid Generation with spacing_multiplier = 0.1")
print("=" * 80)
print()

# Load data
data_manager = DataManager()
data = data_manager.get_klines(
    symbol=SYMBOL,
    timeframe=TIMEFRAME,
    start=START,
    end=END,
    source=SOURCE
)

print(f"Data: {len(data)} bars")
print(f"Price range: ${data['close'].min():,.2f} - ${data['close'].max():,.2f}")
print()

# Create strategy
strategy_config = TaoGridConfig(
    name="TaoGrid Test",
    description=f"Test {SYMBOL} {SUPPORT:.0f}-{RESISTANCE:.0f}",
    support=SUPPORT,
    resistance=RESISTANCE,
    regime=REGIME,
    **GRID_CONFIG,
    **RISK_CONFIG,
    **DGT_CONFIG,
)

strategy = TaoGridStrategy(strategy_config)

# Compute indicators
data_with_indicators = strategy.compute_indicators(data)

# Check grid levels
print("=" * 80)
print("Grid Info")
print("=" * 80)
grid_info = strategy.get_grid_info()
for key, value in grid_info.items():
    print(f"{key}: {value}")
print()

# Extract grid levels
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
print(f"Base spacing (ATR-based): {data_with_indicators['grid_spacing_pct'].iloc[-1]*10:.4f} (after 0.1x)")
print(f"Mid: ${data_with_indicators['grid_mid'].iloc[-1]:,.2f}")
print()

print(f"Buy Levels ({len(buy_levels)}):")
for i, level in enumerate(buy_levels, 1):
    print(f"  L{i}: ${level:,.2f}")

print()
print(f"Sell Levels ({len(sell_levels)}):")
for i, level in enumerate(sell_levels, 1):
    print(f"  L{i}: ${level:,.2f}")

print()

# Generate signals
signals = strategy.generate_signals(data_with_indicators)

print("=" * 80)
print("Signal Generation")
print("=" * 80)
print(f"Entry signals: {signals['entry'].sum()}")
print(f"Exit signals: {signals['exit'].sum()}")
print()

if signals['entry'].sum() > 0:
    print("✓ SUCCESS: Signals generated!")
    print()
    print("First 5 entry signals:")
    entry_rows = data_with_indicators[signals['entry']].head(5)
    for idx in entry_rows.index:
        price = data_with_indicators.loc[idx, 'close']
        reason = signals.loc[idx, 'reason']
        print(f"  {idx}: price=${price:,.2f}, reason={reason}")
else:
    print("✗ FAILED: Still no signals")

print()
print("=" * 80)

"""Debug ATR and spacing calculation."""

from pathlib import Path
import sys

project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd
from data import DataManager
from analytics.indicators.volatility import calculate_atr
from analytics.indicators.grid_generator import calculate_grid_spacing

# Load data
SYMBOL = "BTCUSDT"
TIMEFRAME = "15m"
START = pd.Timestamp("2025-10-01", tz="UTC")
END = pd.Timestamp("2025-12-01", tz="UTC")
SOURCE = "okx"

print("Loading data...")
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

# Calculate ATR
atr = calculate_atr(data['high'], data['low'], data['close'], period=14)

# Calculate spacing
spacing_pct = calculate_grid_spacing(
    atr=atr,
    min_return=0.005,
    maker_fee=0.001,
    volatility_k=0.6
)

print("=" * 80)
print("ATR Analysis")
print("=" * 80)
print(f"ATR min: ${atr.min():,.2f}")
print(f"ATR max: ${atr.max():,.2f}")
print(f"ATR mean: ${atr.mean():,.2f}")
print(f"ATR last: ${atr.iloc[-1]:,.2f}")
print()

# ATR as % of price
atr_pct_of_price = (atr / data['close']) * 100
print(f"ATR % of price (last): {atr_pct_of_price.iloc[-1]:.2f}%")
print()

print("=" * 80)
print("Spacing Analysis")
print("=" * 80)
print(f"Spacing min: {spacing_pct.min():.4f} ({spacing_pct.min()*100:.2f}%)")
print(f"Spacing max: {spacing_pct.max():.4f} ({spacing_pct.max()*100:.2f}%)")
print(f"Spacing mean: {spacing_pct.mean():.4f} ({spacing_pct.mean()*100:.2f}%)")
print(f"Spacing last: {spacing_pct.iloc[-1]:.4f} ({spacing_pct.iloc[-1]*100:.2f}%)")
print()

# Calculate how many layers we can fit
mid = 115000
support = 104000
resistance = 126000

range_below = mid - support  # 11,000
range_above = resistance - mid  # 11,000

last_spacing = spacing_pct.iloc[-1]

# With geometric spacing, how many layers can we fit?
# price[i] = mid / (1 + spacing)^i
# We need: mid / (1 + spacing)^n >= support
# => (1 + spacing)^n <= mid / support
# => n <= log(mid / support) / log(1 + spacing)

import numpy as np

max_layers_buy = np.log(mid / support) / np.log(1 + last_spacing)
max_layers_sell = np.log(resistance / mid) / np.log(1 + last_spacing)

print("=" * 80)
print("Grid Fitting Analysis")
print("=" * 80)
print(f"S/R Range: ${support:,.0f} - ${resistance:,.0f}")
print(f"Mid: ${mid:,.0f}")
print(f"Range below mid: ${range_below:,.0f} ({range_below/mid*100:.2f}%)")
print(f"Range above mid: ${range_above:,.0f} ({range_above/mid*100:.2f}%)")
print()
print(f"With spacing of {last_spacing*100:.2f}%:")
print(f"  Max buy layers: {max_layers_buy:.1f}")
print(f"  Max sell layers: {max_layers_sell:.1f}")
print()

# Test with smaller spacing
test_spacing_values = [0.005, 0.01, 0.015, 0.02, 0.03]
print("=" * 80)
print("How many layers can fit with different spacing?")
print("=" * 80)
for test_spacing in test_spacing_values:
    layers_buy = np.log(mid / support) / np.log(1 + test_spacing)
    layers_sell = np.log(resistance / mid) / np.log(1 + test_spacing)
    print(f"Spacing {test_spacing*100:.1f}%: buy={layers_buy:.1f}, sell={layers_sell:.1f}")

print()
print("=" * 80)
print("Recommendation")
print("=" * 80)
print()
print("The ATR-based spacing (11%) is too wide for the S/R range (9.6%).")
print()
print("Options:")
print("1. Reduce volatility_k from 0.6 to 0.1 (less sensitive to volatility)")
print("2. Use spacing_multiplier to scale down the spacing")
print("3. Widen the S/R range")
print("4. Use fixed spacing instead of ATR-based")
print()
print("Recommended: Use spacing_multiplier = 0.1 to get ~1.1% spacing")
print("This would allow ~9-10 layers on each side.")

"""
Analyze SR zone detection to understand why so few signals are generated.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from data import DataManager
from strategies.signal_based.sr_short import SRShortStrategy, SRShortConfig
from analytics.indicators.sr_zones import detect_pivot_highs, compute_sr_zones
from utils.resample import resample_ohlcv

print("=" * 80)
print("SR Zone Detection Analysis")
print("=" * 80)

# Load data
data_manager = DataManager()
data = data_manager.get_klines('BTCUSDT', '15m', '2025-10-01', '2025-12-01', source='okx')

# Create strategy with optimized parameters
config = SRShortConfig(
    name="SR Short 4H",
    description="SR Short strategy with 4H HTF",
    left_len=30,  # Optimized: more sensitive
    right_len=5,  # Optimized: faster confirmation
    merge_atr_mult=3.5,
)
strategy = SRShortStrategy(config)

print(f"\n[Data] Loaded {len(data)} bars from {data.index[0]} to {data.index[-1]}")

# Step 1: Resample to HTF
print(f"\n[HTF] Resampling to {config.htf_timeframe}...")
data_htf = resample_ohlcv(data, config.htf_timeframe)
print(f"  HTF bars: {len(data_htf)}")

# Step 2: Detect pivot highs
print(f"\n[Pivots] Detecting pivot highs with left_len={config.left_len}, right_len={config.right_len}...")
pivots = detect_pivot_highs(
    data_htf['high'],
    left_len=config.left_len,
    right_len=config.right_len
)
pivot_count = pivots.notna().sum()
print(f"  Total pivot highs detected: {pivot_count}")
print(f"  Pivot rate: {pivot_count / len(data_htf) * 100:.2f}% of bars")

# Show some pivot prices
pivot_prices = pivots.dropna()
if len(pivot_prices) > 0:
    print(f"\n  Sample pivot prices (first 10):")
    for idx, price in pivot_prices.head(10).items():
        print(f"    {idx}: {price:.2f}")

# Step 3: Compute zones
print(f"\n[Zones] Computing zones with merge_atr_mult={config.merge_atr_mult}...")
zones_htf = compute_sr_zones(
    data_htf,
    left_len=config.left_len,
    right_len=config.right_len,
    merge_atr_mult=config.merge_atr_mult,
)

# Count zones
has_zone = zones_htf['zone_top'].notna() & zones_htf['zone_bottom'].notna()
zone_bars = has_zone.sum()
print(f"  Bars with zones: {zone_bars} ({zone_bars / len(zones_htf) * 100:.2f}%)")

# Count unique zones (by tracking zone_top changes)
zone_tops = zones_htf['zone_top'].dropna()
if len(zone_tops) > 0:
    # Count zone changes (new zone when zone_top changes significantly)
    zone_changes = (zone_tops.diff().abs() > 1.0).sum()
    unique_zones = zone_changes + 1
    print(f"  Estimated unique zones: {unique_zones}")

# Count active zones (not broken)
active_zones = zones_htf[~zones_htf['zone_is_broken'].fillna(True)]
active_zone_bars = (active_zones['zone_top'].notna()).sum()
print(f"  Active (not broken) zone bars: {active_zone_bars} ({active_zone_bars / len(zones_htf) * 100:.2f}%)")

# Count zones with min_touches
qualified_zones = zones_htf[
    (zones_htf['zone_touches'] >= config.min_touches) &
    (~zones_htf['zone_is_broken'].fillna(True))
]
qualified_zone_bars = (qualified_zones['zone_top'].notna()).sum()
print(f"  Qualified zones (touches>={config.min_touches}, not broken): {qualified_zone_bars} ({qualified_zone_bars / len(zones_htf) * 100:.2f}%)")

# Step 4: Align zones to 15m timeframe
print(f"\n[Alignment] Aligning zones to 15m timeframe...")
zone_columns = ['zone_top', 'zone_bottom', 'zone_touches', 'zone_is_broken']
zones_aligned = zones_htf[zone_columns].reindex(
    data.index,
    method='ffill'
)

aligned_has_zone = zones_aligned['zone_top'].notna() & zones_aligned['zone_bottom'].notna()
aligned_zone_bars = aligned_has_zone.sum()
print(f"  15m bars with zones: {aligned_zone_bars} ({aligned_zone_bars / len(data) * 100:.2f}%)")

# Step 5: Check entry conditions
print(f"\n[Entry Conditions] Checking entry conditions...")
has_zone_15m = zones_aligned['zone_top'].notna() & zones_aligned['zone_bottom'].notna()
zone_is_broken_15m = zones_aligned['zone_is_broken'].fillna(False).astype(bool)
zone_active_15m = has_zone_15m & (~zone_is_broken_15m)
zone_qualified_15m = zone_active_15m & (zones_aligned['zone_touches'] >= config.min_touches)

zone_bottom_15m = zones_aligned['zone_bottom'].fillna(-np.inf)
zone_top_15m = zones_aligned['zone_top'].fillna(np.inf)
inside_zone_15m = (
    (data['close'] >= zone_bottom_15m) &
    (data['close'] <= zone_top_15m) &
    has_zone_15m
)

entry_condition = zone_qualified_15m & inside_zone_15m
entry_count = entry_condition.sum()
print(f"  Bars with entry condition: {entry_count} ({entry_count / len(data) * 100:.2f}%)")

# Show entry opportunities
if entry_count > 0:
    entry_times = data.index[entry_condition]
    print(f"\n  Entry opportunities (first 20):")
    for i, entry_time in enumerate(entry_times[:20], 1):
        idx = data.index.get_loc(entry_time)
        zone_top = zones_aligned['zone_top'].iloc[idx]
        zone_bottom = zones_aligned['zone_bottom'].iloc[idx]
        close_price = data['close'].iloc[idx]
        touches = zones_aligned['zone_touches'].iloc[idx]
        print(f"    {i}. {entry_time}: price={close_price:.2f}, zone=[{zone_bottom:.2f}, {zone_top:.2f}], touches={touches}")

# Step 6: Summary
print("\n" + "=" * 80)
print("Summary & Recommendations")
print("=" * 80)
print(f"\nCurrent Parameters:")
print(f"  left_len: {config.left_len}")
print(f"  right_len: {config.right_len}")
print(f"  merge_atr_mult: {config.merge_atr_mult}")
print(f"  min_touches: {config.min_touches}")
print(f"  htf_lookback: {config.htf_lookback}")

print(f"\nDetection Results:")
print(f"  Pivot highs: {pivot_count} ({pivot_count / len(data_htf) * 100:.2f}% of HTF bars)")
print(f"  Unique zones: ~{unique_zones if len(zone_tops) > 0 else 0}")
print(f"  Qualified zone bars (HTF): {qualified_zone_bars} ({qualified_zone_bars / len(zones_htf) * 100:.2f}%)")
print(f"  Entry opportunities (15m): {entry_count} ({entry_count / len(data) * 100:.2f}%)")

print(f"\nPotential Issues:")
if pivot_count < 10:
    print(f"  [WARNING] Very few pivot highs ({pivot_count}). Consider reducing left_len/right_len.")
if unique_zones < 5:
    print(f"  [WARNING] Very few unique zones (~{unique_zones}). Consider reducing merge_atr_mult.")
if entry_count < 10:
    print(f"  [WARNING] Very few entry opportunities ({entry_count}). Consider:")
    print(f"      - Reducing min_touches (currently {config.min_touches})")
    print(f"      - Reducing left_len/right_len to detect more pivots")
    print(f"      - Reducing merge_atr_mult to create more zones")


"""
Debug script to analyze zone detection and signal generation.
"""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd
from data import DataManager
from strategies.signal_based.sr_short import SRShortConfig, SRShortStrategy
from utils.resample import resample_ohlcv
from analytics.indicators.sr_zones import compute_sr_zones

# Configuration
SYMBOL = "BTCUSDT"
TIMEFRAME = "15m"
START = pd.Timestamp("2025-7-01", tz="UTC")
END = pd.Timestamp("2025-10-01", tz="UTC")
SOURCE = "okx"

# Load data
print("=" * 80)
print("ZONE DETECTION DEBUG")
print("=" * 80)
print(f"\n[1] Loading {TIMEFRAME} data...")
data_manager = DataManager()
data = data_manager.get_klines(
    symbol=SYMBOL,
    timeframe=TIMEFRAME,
    start=START,
    end=END,
    source=SOURCE,
)
print(f"    Loaded {len(data)} bars from {data.index[0]} to {data.index[-1]}")

# Resample to 4H
print(f"\n[2] Resampling to 4H...")
data_4h = resample_ohlcv(data, '4h')
print(f"    Resampled to {len(data_4h)} 4H bars")

# Detect zones on 4H
print(f"\n[3] Detecting zones on 4H data...")
zones_4h = compute_sr_zones(
    data_4h,
    left_len=30,
    right_len=5,
    merge_atr_mult=3.5,
)

# Analyze zone activity
print(f"\n[4] Analyzing zone activity...")
active_zones = zones_4h[
    (zones_4h['zone_top'].notna()) &
    (zones_4h['zone_is_broken'] == False)
]
print(f"    Total bars with zones: {(zones_4h['zone_top'].notna()).sum()}")
print(f"    Active zones: {len(active_zones)}")
print(f"    Broken zones: {(zones_4h['zone_is_broken'] == True).sum()}")

if len(active_zones) > 0:
    print(f"\n[5] Active zone examples:")
    print(active_zones[['zone_top', 'zone_bottom', 'zone_touches', 'zone_is_broken']].head(10))

    # Show zone touches distribution
    print(f"\n[6] Zone touches distribution:")
    touches_dist = zones_4h[zones_4h['zone_top'].notna()]['zone_touches'].value_counts().sort_index()
    print(touches_dist)
else:
    print(f"\n[5] NO ACTIVE ZONES FOUND!")
    print(f"    This is the root cause of 0 orders.")

# Check strategy signals
print(f"\n[7] Testing strategy signal generation...")
strategy = SRShortStrategy(SRShortConfig(
    name="SR Short 4H",
    description="Short-only strategy based on 4H resistance zones",
    left_len=30,
    right_len=5,
    merge_atr_mult=3.5,
    min_touches=1,
    max_retries=3,
    risk_per_trade_pct=0.5,
    leverage=5.0,
    stop_loss_atr_mult=3.0,
))

# Run strategy
data_with_indicators = strategy.compute_indicators(data)
signals = strategy.generate_signals(data_with_indicators)

# Analyze signals
entry_signals = (signals['orders'] < 0).sum()
exit_signals = (signals['orders'] > 0).sum()
print(f"    Entry signals: {entry_signals}")
print(f"    Exit signals: {exit_signals}")

if entry_signals > 0:
    print(f"\n[8] Entry signal examples:")
    entry_bars = data_with_indicators[signals['orders'] < 0].head(5)
    print(entry_bars[['close', 'zone_top', 'zone_bottom', 'zone_touches']])
else:
    print(f"\n[8] NO ENTRY SIGNALS!")
    print(f"    Checking entry conditions...")

    # Check zone alignment
    zones_aligned = data_with_indicators['zone_top'].notna()
    print(f"    Bars with zones: {zones_aligned.sum()}/{len(data)}")

    if zones_aligned.sum() > 0:
        # Show some bars with zones
        print(f"\n    Sample bars with zones:")
        sample = data_with_indicators[zones_aligned].head(10)
        print(sample[['close', 'zone_top', 'zone_bottom', 'zone_touches', 'zone_is_broken']])

        # Check if price is inside zone
        inside_zone = (
            (data_with_indicators['close'] >= data_with_indicators['zone_bottom']) &
            (data_with_indicators['close'] <= data_with_indicators['zone_top']) &
            zones_aligned
        )
        print(f"\n    Bars where price is inside zone: {inside_zone.sum()}")

        if inside_zone.sum() > 0:
            print(f"\n    Sample bars with price inside zone:")
            sample2 = data_with_indicators[inside_zone].head(5)
            print(sample2[['close', 'zone_top', 'zone_bottom', 'zone_touches', 'zone_is_broken']])

print("\n" + "=" * 80)
print("DEBUG COMPLETE")
print("=" * 80)

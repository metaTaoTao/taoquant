"""
Detailed zone lifecycle debug script.
"""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from data import DataManager
from utils.resample import resample_ohlcv
from analytics.indicators.sr_zones import detect_pivot_highs, calculate_atr, Zone

# Configuration
SYMBOL = "BTCUSDT"
TIMEFRAME = "15m"
START = pd.Timestamp("2025-7-01", tz="UTC")
END = pd.Timestamp("2025-10-01", tz="UTC")
SOURCE = "okx"

# Load data
print("=" * 80)
print("DETAILED ZONE LIFECYCLE DEBUG")
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

# Resample to 4H
data_4h = resample_ohlcv(data, '4h')
print(f"    4H data: {len(data_4h)} bars")

# Manually run zone detection with detailed logging
print(f"\n[2] Running zone detection manually...")

# Detect pivots
left_len = 30
right_len = 5
merge_atr_mult = 3.5
pivots = detect_pivot_highs(data_4h['high'], left_len, right_len)
pivot_indices = np.where(~np.isnan(pivots.values))[0]
print(f"    Detected {len(pivot_indices)} pivot highs")

# Calculate ATR
atr = calculate_atr(data_4h['high'], data_4h['low'], data_4h['close'], period=14)

# Manually process first few pivots
print(f"\n[3] Processing first 5 pivots:")
zones = []

for idx, pivot_real_idx in enumerate(pivot_indices[:10]):  # Process first 10
    p_high = pivots.iloc[pivot_real_idx]
    confirmation_idx = pivot_real_idx + right_len

    if confirmation_idx >= len(data_4h):
        continue

    # Body top
    p_body = max(
        data_4h['open'].iloc[pivot_real_idx],
        data_4h['close'].iloc[pivot_real_idx]
    )

    # Add minimum thickness
    current_atr = atr.iloc[confirmation_idx]
    if (p_high - p_body) < (current_atr * 0.2):
        p_body = p_high - (current_atr * 0.2)

    print(f"\n  Pivot #{idx+1}:")
    print(f"    Pivot idx: {pivot_real_idx}, Confirmation idx: {confirmation_idx}")
    print(f"    Pivot time: {data_4h.index[pivot_real_idx]}")
    print(f"    Confirmation time: {data_4h.index[confirmation_idx]}")
    print(f"    Zone: top={p_high:.1f}, bottom={p_body:.1f}")

    # Check if zone was already broken before confirmation
    # This is the key check!
    broken_before_conf = False
    for check_idx in range(pivot_real_idx, confirmation_idx + 1):
        check_close = data_4h['close'].iloc[check_idx]
        check_atr = atr.iloc[check_idx]
        break_threshold = p_high + (check_atr * 0.5)
        if check_close > break_threshold:
            broken_before_conf = True
            print(f"    [!] Zone broken BEFORE confirmation at idx {check_idx} ({data_4h.index[check_idx]})")
            print(f"        close={check_close:.1f} > break_threshold={break_threshold:.1f}")
            break

    if not broken_before_conf:
        print(f"    [OK] Zone valid at confirmation")

    # Create zone (using my fixed logic)
    new_zone = Zone(
        top=p_high,
        bottom=p_body,
        start_time=data_4h.index[confirmation_idx],  # My fix: use confirmation time
        end_time=None,  # My fix: None until broken
        touches=1,
        is_broken=broken_before_conf,  # Mark as broken if already broken
    )
    zones.append(new_zone)

    # Simulate what happens after confirmation
    if not broken_before_conf:
        # Check when it gets broken
        for future_idx in range(confirmation_idx + 1, min(confirmation_idx + 100, len(data_4h))):
            future_close = data_4h['close'].iloc[future_idx]
            future_atr = atr.iloc[future_idx]
            break_threshold = p_high + (future_atr * 0.5)
            if future_close > break_threshold:
                print(f"    [X] Zone broken AFTER confirmation at idx {future_idx} ({data_4h.index[future_idx]})")
                print(f"        close={future_close:.1f} > break_threshold={break_threshold:.1f}")
                print(f"        Lifetime: {future_idx - confirmation_idx} bars")
                break

print(f"\n[4] Summary:")
print(f"    Total pivots detected: {len(pivot_indices)}")
broken_before_conf_count = sum(1 for z in zones if z.is_broken)
print(f"    Zones broken BEFORE confirmation: {broken_before_conf_count}/{len(zones)}")
print(f"    Valid zones at confirmation: {len(zones) - broken_before_conf_count}/{len(zones)}")

print("\n" + "=" * 80)

"""
Analyze entry logic to verify:
1. Only one entry per zone
2. Can enter immediately after position closes
3. No multiple positions
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd
from data import DataManager
from strategies.signal_based.sr_short import SRShortStrategy, SRShortConfig

print("=" * 80)
print("Entry Logic Analysis")
print("=" * 80)

# Load data
data_manager = DataManager()
data = data_manager.get_klines('BTCUSDT', '15m', '2025-10-01', '2025-12-01', source='okx')

# Create strategy
config = SRShortConfig(
    name="SR Short 4H",
    description="SR Short strategy with 4H HTF",
    left_len=30,
    right_len=5,
    merge_atr_mult=3.5,
)
strategy = SRShortStrategy(config)

# Compute indicators and generate signals
print("\n[Strategy] Computing indicators and generating signals...")
data_with_indicators = strategy.compute_indicators(data)
signals = strategy.generate_signals(data_with_indicators)
orders = signals['orders']

# Analyze orders
entry_orders = orders[orders < 0]
exit_orders = orders[orders > 0]

print(f"\n[Orders]")
print(f"  Total entry orders: {len(entry_orders)}")
print(f"  Total exit orders: {len(exit_orders)}")

# Show entry times and zones
print(f"\n[Entry Analysis]")
for i, (entry_time, order_size) in enumerate(entry_orders.items(), 1):
    idx = data_with_indicators.index.get_loc(entry_time)
    zone_bottom = data_with_indicators['zone_bottom'].iloc[idx]
    zone_top = data_with_indicators['zone_top'].iloc[idx]
    close_price = data_with_indicators['close'].iloc[idx]
    
    print(f"\n  Entry {i}: {entry_time}")
    print(f"    Price: {close_price:.2f}")
    print(f"    Zone: [{zone_bottom:.2f}, {zone_top:.2f}]")
    
    # Check if there are more entry opportunities in this zone before this entry
    zone_mask = (
        (data_with_indicators['zone_bottom'] == zone_bottom) &
        (data_with_indicators['zone_top'] == zone_top) &
        (data_with_indicators.index < entry_time)
    )
    earlier_opportunities = zone_mask.sum()
    print(f"    Earlier opportunities in same zone: {earlier_opportunities}")

# Check exit times and next entry
print(f"\n[Exit-Entry Gap Analysis]")
exit_times = exit_orders.index
entry_times = entry_orders.index

for i, exit_time in enumerate(exit_times):
    # Find next entry after this exit
    next_entries = entry_times[entry_times > exit_time]
    if len(next_entries) > 0:
        next_entry = next_entries[0]
        gap = (next_entry - exit_time).total_seconds() / 60  # minutes
        print(f"  Exit {i+1}: {exit_time} -> Next entry: {next_entry} (gap: {gap:.0f} minutes)")
    else:
        print(f"  Exit {i+1}: {exit_time} -> No next entry")

# Check for multiple entries in same zone
print(f"\n[Zone Reuse Check]")
zone_entries = {}
for entry_time in entry_orders.index:
    idx = data_with_indicators.index.get_loc(entry_time)
    zone_bottom = data_with_indicators['zone_bottom'].iloc[idx]
    zone_top = data_with_indicators['zone_top'].iloc[idx]
    zone_key = (float(zone_bottom), float(zone_top))
    
    if zone_key not in zone_entries:
        zone_entries[zone_key] = []
    zone_entries[zone_key].append(entry_time)

print(f"  Unique zones used: {len(zone_entries)}")
for zone_key, entry_times in zone_entries.items():
    if len(entry_times) > 1:
        print(f"  [WARNING] Zone {zone_key} has {len(entry_times)} entries: {entry_times}")
    else:
        print(f"  Zone {zone_key}: 1 entry (OK)")

print("\n" + "=" * 80)
print("Summary")
print("=" * 80)
print(f"✅ Total entries: {len(entry_orders)}")
print(f"✅ Unique zones: {len(zone_entries)}")
print(f"✅ Each zone used only once: {all(len(entries) == 1 for entries in zone_entries.values())}")


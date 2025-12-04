"""
Analyze partial exit trades to verify TP1 and TP2 logic.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd

# Load trades
from utils.paths import get_results_dir
trades_path = get_results_dir() / "SR Short 4H_BTCUSDT_15m_trades.csv"
if not trades_path.exists():
    print(f"Trades file not found: {trades_path}")
    exit(1)

trades = pd.read_csv(trades_path)
trades['entry_time'] = pd.to_datetime(trades['entry_time'])
trades['exit_time'] = pd.to_datetime(trades['exit_time'])

print("=" * 80)
print("Partial Exit Analysis")
print("=" * 80)

print(f"\nTotal trades: {len(trades)}")

# Group by entry_time to see partial exits
print("\n" + "-" * 80)
print("Trades grouped by entry time:")
print("-" * 80)

entry_groups = trades.groupby('entry_time')

for entry_time, group in entry_groups:
    print(f"\nEntry: {entry_time}")
    print(f"  Total exits: {len(group)}")
    print(f"  Total size: {group['size'].sum():.6f} BTC")
    
    # Check if sizes match expected pattern (30% + 70% or similar)
    sizes = group['size'].values
    total_size = sizes.sum()
    
    if len(sizes) >= 2:
        # Check if first exit is ~30% of total
        first_exit_pct = sizes[0] / total_size if total_size > 0 else 0
        remaining_pct = (total_size - sizes[0]) / total_size if total_size > 0 else 0
        
        print(f"  First exit: {sizes[0]:.6f} BTC ({first_exit_pct*100:.1f}% of total)")
        print(f"  Remaining: {remaining_pct*100:.1f}% of total")
        
        if 0.25 <= first_exit_pct <= 0.35:
            print(f"  ✅ First exit is ~30% (TP1 partial exit)")
        else:
            print(f"  ⚠️  First exit is {first_exit_pct*100:.1f}% (expected ~30%)")
    
    # Show all exits
    for i, (idx, trade) in enumerate(group.iterrows(), 1):
        duration = trade['exit_time'] - entry_time
        print(f"    Exit {i}: {trade['exit_time']} | Size: {trade['size']:.6f} BTC | "
              f"Return: {trade['return_pct']*100:.2f}% | Duration: {duration}")

# Check if we have multiple exits from same entry (partial exits)
multi_exit_entries = entry_groups.filter(lambda x: len(x) > 1)
if len(multi_exit_entries) > 0:
    print("\n" + "=" * 80)
    print("✅ PARTIAL EXITS DETECTED!")
    print("=" * 80)
    print(f"Found {len(multi_exit_entries)} trades with multiple exits from same entry")
    print("This confirms that partial exit logic is working!")
else:
    print("\n" + "=" * 80)
    print("⚠️  No partial exits detected")
    print("=" * 80)
    print("All trades have single exit (may be normal if TP1/TP2 not triggered)")


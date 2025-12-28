"""
Find suitable backtest period for given S/R range.
"""

import sys
from pathlib import Path
import pandas as pd

taoquant_root = Path(__file__).parent.parent.parent
if str(taoquant_root) not in sys.path:
    sys.path.insert(0, str(taoquant_root))

from data import DataManager

# Target range
support = 80000.0
resistance = 94000.0

print(f"\nSearching for period where price is in range ${support:,.0f} - ${resistance:,.0f}")
print("=" * 80)

# Load recent data
dm = DataManager()
data = dm.get_klines(
    symbol="BTCUSDT",
    timeframe="1d",  # Daily data for faster search
    start=pd.Timestamp("2024-01-01", tz="UTC"),
    end=pd.Timestamp("2025-12-26", tz="UTC"),
    source="okx",
)

print(f"\nLoaded {len(data)} days of data")
print(f"Overall range: ${data['close'].min():,.0f} - ${data['close'].max():,.0f}")

# Find periods where price is within range
in_range = (data['close'] >= support) & (data['close'] <= resistance)
data['in_range'] = in_range

# Find continuous periods
periods = []
start_idx = None

for i in range(len(data)):
    if in_range.iloc[i]:
        if start_idx is None:
            start_idx = i
    else:
        if start_idx is not None:
            # Period ended
            periods.append({
                'start': data.index[start_idx],
                'end': data.index[i - 1],
                'days': i - start_idx,
                'price_start': data['close'].iloc[start_idx],
                'price_end': data['close'].iloc[i - 1],
            })
            start_idx = None

# Check if still in range at end
if start_idx is not None:
    periods.append({
        'start': data.index[start_idx],
        'end': data.index[-1],
        'days': len(data) - start_idx,
        'price_start': data['close'].iloc[start_idx],
        'price_end': data['close'].iloc[-1],
    })

# Sort by duration
periods = sorted(periods, key=lambda x: x['days'], reverse=True)

print(f"\nFound {len(periods)} periods where price was in range:")
print("-" * 80)

for i, p in enumerate(periods[:10], 1):  # Show top 10
    print(f"{i}. {p['start'].date()} to {p['end'].date()} ({p['days']} days)")
    print(f"   Price: ${p['price_start']:,.0f} -> ${p['price_end']:,.0f}")
    if p['days'] >= 30:
        print(f"   [GOOD] Long enough for backtest")
    print()

if len(periods) > 0 and periods[0]['days'] >= 30:
    best = periods[0]
    print("=" * 80)
    print("RECOMMENDED PERIOD:")
    print(f"  Start: {best['start'].date()}")
    print(f"  End: {best['end'].date()}")
    print(f"  Duration: {best['days']} days")
    print("=" * 80)
else:
    print("=" * 80)
    print("NO SUITABLE PERIOD FOUND!")
    print(f"\nAlternative: Adjust S/R to match recent price range")
    recent_30d = data.tail(30)
    recent_low = recent_30d['low'].min()
    recent_high = recent_30d['high'].max()
    print(f"  Recent 30-day range: ${recent_low:,.0f} - ${recent_high:,.0f}")
    print("=" * 80)

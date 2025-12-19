"""
Quick data reload verification script
"""
from datetime import datetime, timezone
from pathlib import Path
import sys
import io

# Add project root
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data import DataManager

def main():
    # Set UTF-8 encoding for stdout
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
    print("=" * 80)
    print("Data Reload Verification")
    print("=" * 80)
    print()
    
    # Test parameters (same as backtest)
    symbol = "BTCUSDT"
    timeframe = "1m"
    start = datetime(2025, 7, 10, tzinfo=timezone.utc)
    end = datetime(2025, 8, 10, tzinfo=timezone.utc)
    
    print(f"Symbol: {symbol}")
    print(f"Timeframe: {timeframe}")
    print(f"Start: {start}")
    print(f"End: {end}")
    print()
    
    dm = DataManager()
    
    print("Fetching fresh data from API (cache cleared)...")
    data = dm.get_klines(
        symbol=symbol,
        timeframe=timeframe,
        start=start,
        end=end,
        source="okx",
        use_cache=True,  # Will recreate cache
    )
    
    print()
    print("=" * 80)
    print("Data Loaded Successfully")
    print("=" * 80)
    print(f"Bars: {len(data)}")
    print(f"Time range: {data.index[0]} to {data.index[-1]}")
    print(f"Columns: {list(data.columns)}")
    print()
    print("First 5 bars:")
    print(data.head())
    print()
    print("Last 5 bars:")
    print(data.tail())
    print()
    print("Statistics:")
    print(data.describe())
    print()
    print("OK: Data reloaded, ready for backtest!")

if __name__ == "__main__":
    main()


"""
诊断数据差异的详细工具
"""
from pathlib import Path
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import io

# Add project root
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data import DataManager

# Set UTF-8 encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def check_cache_files():
    """检查所有缓存文件"""
    print("=" * 80)
    print("Cache Files Check")
    print("=" * 80)
    
    cache_paths = [
        Path("data/cache"),
        Path("algorithms/taogrid/data/cache"),
        Path("run/data/cache"),
        Path("notebooks/data/cache"),
        Path("scripts/data/cache"),
        Path("strategies/grid/data/cache"),
    ]
    
    for cache_dir in cache_paths:
        if cache_dir.exists():
            parquet_files = list(cache_dir.glob("okx_btcusdt*.parquet"))
            if parquet_files:
                print(f"\n{cache_dir}:")
                for f in parquet_files:
                    try:
                        df = pd.read_parquet(f)
                        print(f"  {f.name}: {len(df)} bars, {df.index[0]} to {df.index[-1]}")
                    except Exception as e:
                        print(f"  {f.name}: Error reading - {e}")

def compare_data_sources():
    """对比不同数据源的数据"""
    print()
    print("=" * 80)
    print("Data Source Comparison")
    print("=" * 80)
    
    symbol = "BTCUSDT"
    timeframe = "1m"
    start = datetime(2025, 7, 10, tzinfo=timezone.utc)
    end = datetime(2025, 8, 10, tzinfo=timezone.utc)
    
    print(f"Symbol: {symbol}")
    print(f"Timeframe: {timeframe}")
    print(f"Start: {start}")
    print(f"End: {end}")
    print()
    
    # Load data with cache disabled to force fresh fetch
    print("Loading data (cache disabled)...")
    dm = DataManager()
    
    # First, check if cache exists
    cache_path = dm._cache_path("okx", symbol, timeframe)
    print(f"Cache path: {cache_path}")
    print(f"Cache exists: {cache_path.exists()}")
    
    if cache_path.exists():
        print("\nReading cached data...")
        cached_data = pd.read_parquet(cache_path)
        print(f"Cached: {len(cached_data)} bars from {cached_data.index[0]} to {cached_data.index[-1]}")
        print(f"First 5 bars:")
        print(cached_data.head())
        print(f"\nLast 5 bars:")
        print(cached_data.tail())
    
    # Load fresh data
    print("\nFetching fresh data from API...")
    fresh_data = dm.get_klines(
        symbol=symbol,
        timeframe=timeframe,
        start=start,
        end=end,
        source="okx",
        use_cache=False,  # Force fresh fetch
    )
    
    print(f"Fresh: {len(fresh_data)} bars from {fresh_data.index[0]} to {fresh_data.index[-1]}")
    print(f"First 5 bars:")
    print(fresh_data.head())
    print(f"\nLast 5 bars:")
    print(fresh_data.tail())
    
    # Compare if cache exists
    if cache_path.exists():
        print("\n" + "=" * 80)
        print("Cache vs Fresh Comparison")
        print("=" * 80)
        
        # Find overlapping period
        common_start = max(cached_data.index[0], fresh_data.index[0])
        common_end = min(cached_data.index[-1], fresh_data.index[-1])
        
        cached_trimmed = cached_data.loc[common_start:common_end]
        fresh_trimmed = fresh_data.loc[common_start:common_end]
        
        if len(cached_trimmed) != len(fresh_trimmed):
            print(f"⚠️  Length mismatch: cached={len(cached_trimmed)}, fresh={len(fresh_trimmed)}")
        else:
            print(f"✅ Length match: {len(cached_trimmed)} bars")
            
            # Compare values
            for col in ['open', 'high', 'low', 'close']:
                if col in cached_trimmed.columns and col in fresh_trimmed.columns:
                    diff = (cached_trimmed[col] - fresh_trimmed[col]).abs()
                    max_diff = diff.max()
                    mean_diff = diff.mean()
                    
                    if max_diff > 1e-6:
                        print(f"⚠️  {col}: max_diff={max_diff:.10f}, mean_diff={mean_diff:.10f}")
                        # Find where max diff occurs
                        max_idx = diff.idxmax()
                        print(f"     Max diff at: {max_idx}")
                        print(f"     Cached: {cached_trimmed.loc[max_idx, col]}")
                        print(f"     Fresh: {fresh_trimmed.loc[max_idx, col]}")
                    else:
                        print(f"✅ {col}: matches (max_diff={max_diff:.15f})")

def check_data_consistency():
    """检查数据一致性"""
    print()
    print("=" * 80)
    print("Data Consistency Check")
    print("=" * 80)
    
    symbol = "BTCUSDT"
    timeframe = "1m"
    start = datetime(2025, 7, 10, tzinfo=timezone.utc)
    end = datetime(2025, 8, 10, tzinfo=timezone.utc)
    
    dm = DataManager()
    data = dm.get_klines(
        symbol=symbol,
        timeframe=timeframe,
        start=start,
        end=end,
        source="okx",
        use_cache=True,
    )
    
    print(f"Data loaded: {len(data)} bars")
    print(f"Time range: {data.index[0]} to {data.index[-1]}")
    print()
    
    # Check for duplicates
    duplicates = data.index.duplicated()
    if duplicates.any():
        print(f"⚠️  Found {duplicates.sum()} duplicate timestamps")
    else:
        print("✅ No duplicate timestamps")
    
    # Check for gaps
    expected_interval = pd.Timedelta(minutes=1)
    time_diffs = data.index.to_series().diff()
    gaps = time_diffs[time_diffs > expected_interval * 1.5]  # Allow 50% tolerance
    
    if len(gaps) > 0:
        print(f"⚠️  Found {len(gaps)} time gaps:")
        for gap_time, gap_size in gaps.head(10).items():
            print(f"   {gap_time}: gap of {gap_size}")
    else:
        print("✅ No significant time gaps")
    
    # Check data quality
    print("\nData quality checks:")
    for col in ['open', 'high', 'low', 'close']:
        if col in data.columns:
            null_count = data[col].isnull().sum()
            if null_count > 0:
                print(f"⚠️  {col}: {null_count} null values")
            else:
                print(f"✅ {col}: no null values")
            
            # Check for negative values (shouldn't happen for prices)
            if (data[col] < 0).any():
                print(f"⚠️  {col}: found negative values")
            
            # Check high >= low
            if col == 'high':
                if (data['high'] < data['low']).any():
                    print(f"⚠️  high < low found in {((data['high'] < data['low']).sum())} bars")

def main():
    print("Data Difference Diagnostic Tool")
    print("=" * 80)
    print()
    
    check_cache_files()
    compare_data_sources()
    check_data_consistency()
    
    print()
    print("=" * 80)
    print("Diagnostic Complete")
    print("=" * 80)
    print()
    print("Next steps:")
    print("1. Run backtest and save results")
    print("2. Compare results with home computer using compare_backtest_results.py")
    print("3. If differences persist, check:")
    print("   - Python version")
    print("   - Package versions (pandas, numpy)")
    print("   - System timezone settings")
    print("   - Data source API responses (may vary slightly)")

if __name__ == "__main__":
    main()


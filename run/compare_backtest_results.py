"""
对比两台机器的回测结果，找出差异原因
"""
from pathlib import Path
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import io

# Add project root
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Set UTF-8 encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def load_results(result_dir: Path):
    """加载回测结果"""
    metrics_path = result_dir / "metrics.json"
    trades_path = result_dir / "trades.csv"
    orders_path = result_dir / "orders.csv"
    equity_path = result_dir / "equity_curve.csv"
    
    results = {}
    
    if metrics_path.exists():
        with open(metrics_path, 'r', encoding='utf-8') as f:
            results['metrics'] = json.load(f)
    
    if trades_path.exists():
        results['trades'] = pd.read_csv(trades_path, parse_dates=True)
        if 'timestamp' in results['trades'].columns:
            results['trades']['timestamp'] = pd.to_datetime(results['trades']['timestamp'], utc=True)
    
    if orders_path.exists():
        results['orders'] = pd.read_csv(orders_path, parse_dates=True)
        if 'timestamp' in results['orders'].columns:
            results['orders']['timestamp'] = pd.to_datetime(results['orders']['timestamp'], utc=True)
    
    if equity_path.exists():
        results['equity'] = pd.read_csv(equity_path, parse_dates=True)
        if 'timestamp' in results['equity'].columns:
            results['equity']['timestamp'] = pd.to_datetime(results['equity']['timestamp'], utc=True)
    
    return results

def compare_metrics(metrics1: dict, metrics2: dict):
    """对比指标"""
    print("=" * 80)
    print("Metrics Comparison")
    print("=" * 80)
    
    all_keys = set(metrics1.keys()) | set(metrics2.keys())
    
    differences = []
    for key in sorted(all_keys):
        val1 = metrics1.get(key, None)
        val2 = metrics2.get(key, None)
        
        if val1 != val2:
            if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                diff_pct = abs(val1 - val2) / max(abs(val1), abs(val2), 1e-10) * 100
                print(f"{key:30s}: {val1:15.6f} vs {val2:15.6f} (diff: {diff_pct:.4f}%)")
                if diff_pct > 0.01:  # > 0.01% difference
                    differences.append((key, val1, val2, diff_pct))
            else:
                print(f"{key:30s}: {val1} vs {val2}")
                differences.append((key, val1, val2, None))
        else:
            print(f"{key:30s}: {val1:15.6f} (match)")
    
    return differences

def compare_trades(trades1: pd.DataFrame, trades2: pd.DataFrame):
    """对比交易记录"""
    print()
    print("=" * 80)
    print("Trades Comparison")
    print("=" * 80)
    
    print(f"Trades count: {len(trades1)} vs {len(trades2)}")
    
    if len(trades1) != len(trades2):
        print(f"⚠️  Trade count mismatch!")
        print(f"   First 10 trades from result 1:")
        print(trades1.head(10).to_string())
        print(f"\n   First 10 trades from result 2:")
        print(trades2.head(10).to_string())
        return
    
    # Compare by timestamp
    if 'timestamp' in trades1.columns and 'timestamp' in trades2.columns:
        trades1_sorted = trades1.sort_values('timestamp').reset_index(drop=True)
        trades2_sorted = trades2.sort_values('timestamp').reset_index(drop=True)
        
        # Compare each trade
        mismatches = []
        for i in range(min(len(trades1_sorted), len(trades2_sorted))):
            t1 = trades1_sorted.iloc[i]
            t2 = trades2_sorted.iloc[i]
            
            # Compare key fields
            if abs(t1['timestamp'] - t2['timestamp']).total_seconds() > 60:
                mismatches.append((i, 'timestamp', t1['timestamp'], t2['timestamp']))
            
            for col in ['size', 'price', 'pnl']:
                if col in t1 and col in t2:
                    if abs(t1[col] - t2[col]) > 1e-6:
                        mismatches.append((i, col, t1[col], t2[col]))
        
        if mismatches:
            print(f"⚠️  Found {len(mismatches)} trade mismatches:")
            for idx, col, v1, v2 in mismatches[:10]:  # Show first 10
                print(f"   Trade {idx}, {col}: {v1} vs {v2}")
        else:
            print("✅ All trades match!")

def compare_data(data1_path: str, data2_path: str):
    """对比原始数据"""
    print()
    print("=" * 80)
    print("Data Comparison")
    print("=" * 80)
    
    # Try to load cached data
    cache_paths = [
        Path("data/cache/okx_btcusdt_1m.parquet"),
        Path("run/data/cache/okx_btcusdt_1m.parquet"),
        Path("algorithms/taogrid/data/cache/okx_btcusdt_1m.parquet"),
    ]
    
    data1 = None
    data2 = None
    
    for cache_path in cache_paths:
        if cache_path.exists():
            print(f"Found cache: {cache_path}")
            if data1 is None:
                data1 = pd.read_parquet(cache_path)
                print(f"  Loaded {len(data1)} bars from {data1.index[0]} to {data1.index[-1]}")
            elif data2 is None:
                data2 = pd.read_parquet(cache_path)
                print(f"  Loaded {len(data2)} bars from {data2.index[0]} to {data2.index[-1]}")
                break
    
    if data1 is not None and data2 is not None:
        # Compare data
        if len(data1) != len(data2):
            print(f"⚠️  Data length mismatch: {len(data1)} vs {len(data2)}")
        else:
            # Compare overlapping period
            common_start = max(data1.index[0], data2.index[0])
            common_end = min(data1.index[-1], data2.index[-1])
            
            data1_trimmed = data1.loc[common_start:common_end]
            data2_trimmed = data2.loc[common_start:common_end]
            
            if len(data1_trimmed) != len(data2_trimmed):
                print(f"⚠️  Trimmed data length mismatch: {len(data1_trimmed)} vs {len(data2_trimmed)}")
            else:
                # Compare values
                for col in ['open', 'high', 'low', 'close']:
                    if col in data1_trimmed.columns and col in data2_trimmed.columns:
                        diff = (data1_trimmed[col] - data2_trimmed[col]).abs()
                        max_diff = diff.max()
                        if max_diff > 1e-6:
                            print(f"⚠️  {col} max difference: {max_diff:.6f}")
                            print(f"   First difference at: {data1_trimmed.index[diff.argmax()]}")
                        else:
                            print(f"✅ {col} matches (max diff: {max_diff:.10f})")

def main():
    print("Backtest Results Comparison Tool")
    print("=" * 80)
    print()
    
    # Default result directories
    result_dir1 = Path("run/results_lean_taogrid")
    result_dir2 = Path("run/results_lean_taogrid")  # Same for now, user can specify
    
    if len(sys.argv) > 1:
        result_dir1 = Path(sys.argv[1])
    if len(sys.argv) > 2:
        result_dir2 = Path(sys.argv[2])
    
    print(f"Result 1: {result_dir1}")
    print(f"Result 2: {result_dir2}")
    print()
    
    # Load results
    print("Loading results...")
    results1 = load_results(result_dir1)
    results2 = load_results(result_dir2)
    
    if not results1 or not results2:
        print("⚠️  Could not load results. Please check paths.")
        return
    
    # Compare metrics
    if 'metrics' in results1 and 'metrics' in results2:
        differences = compare_metrics(results1['metrics'], results2['metrics'])
        if differences:
            print(f"\n⚠️  Found {len(differences)} significant metric differences")
        else:
            print("\n✅ All metrics match!")
    
    # Compare trades
    if 'trades' in results1 and 'trades' in results2:
        compare_trades(results1['trades'], results2['trades'])
    
    # Compare data
    compare_data(str(result_dir1), str(result_dir2))
    
    print()
    print("=" * 80)
    print("Comparison Complete")
    print("=" * 80)

if __name__ == "__main__":
    main()


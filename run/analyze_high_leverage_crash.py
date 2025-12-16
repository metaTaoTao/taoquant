"""分析高杠杆下的暴跌表现 - 查找560x杠杆的结果"""
import pandas as pd
import json
from pathlib import Path

print("=" * 80)
print("查找560x杠杆配置的回测结果")
print("=" * 80)
print()

# 检查所有结果目录的metrics
results_base = Path("run")
for result_dir in sorted(results_base.glob("results*")):
    if not result_dir.is_dir():
        continue
    
    metrics_file = result_dir / "metrics.json"
    if not metrics_file.exists():
        continue
    
    try:
        with open(metrics_file, 'r') as f:
            metrics = json.load(f)
        
        max_dd = metrics.get('max_drawdown', 0) * 100
        total_return = metrics.get('total_return', 0) * 100
        
        # 检查是否是我们要找的结果（高杠杆，回撤约11%）
        if abs(max_dd - 11.37) < 1.0 or max_dd > 10:
            print(f"目录: {result_dir.name}")
            print(f"  最大回撤: {max_dd:.2f}%")
            print(f"  总收益率: {total_return:.2f}%")
            print(f"  交易数: {metrics.get('total_trades', 0)}")
            print()
            
            # 检查equity_curve是否包含10.10-10.11
            equity_file = result_dir / "equity_curve.csv"
            if equity_file.exists():
                df = pd.read_csv(equity_file)
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                
                crash_data = df[
                    (df['timestamp'] >= '2025-10-10') & 
                    (df['timestamp'] <= '2025-10-11 23:59:59')
                ]
                if len(crash_data) > 0:
                    print(f"  包含10.10-10.11数据: 是 ({len(crash_data)} 个数据点)")
                    print(f"  数据范围: {df['timestamp'].min()} 至 {df['timestamp'].max()}")
                    print()
                    
                    # 详细分析这个结果
                    print("  详细分析:")
                    peak_before = df[df['timestamp'] < '2025-10-10']['equity'].max()
                    min_during = crash_data['equity'].min()
                    crash_dd = (min_during - peak_before) / peak_before * 100 if peak_before > 0 else 0
                    print(f"    暴跌期间最大回撤: {crash_dd:.2f}%")
                    print()
    except:
        continue

print("=" * 80)
print()
print("提示: 如果未找到560x杠杆的结果，请确认:")
print("1. 结果目录名称")
print("2. 最大回撤是否确实是11.37%")
print("3. 杠杆倍数配置")

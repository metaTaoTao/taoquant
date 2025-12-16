"""查找包含10.10-10.11暴跌数据的回测结果"""
import pandas as pd
from pathlib import Path

target_start = pd.Timestamp("2025-10-10 00:00:00", tz='UTC')
target_end = pd.Timestamp("2025-10-11 23:59:59", tz='UTC')

print("=" * 80)
print("查找包含10.10-10.11暴跌数据的回测结果")
print("=" * 80)
print()

results_base = Path("run")
found_results = []

for result_dir in results_base.glob("results*"):
    if not result_dir.is_dir():
        continue
    
    equity_file = result_dir / "equity_curve.csv"
    if not equity_file.exists():
        continue
    
    try:
        df = pd.read_csv(equity_file)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        data_start = df['timestamp'].min()
        data_end = df['timestamp'].max()
        
        # 检查是否包含目标时间段
        if data_start <= target_end and data_end >= target_start:
            crash_data = df[
                (df['timestamp'] >= target_start) & 
                (df['timestamp'] <= target_end)
            ]
            
            if len(crash_data) > 0:
                found_results.append({
                    'dir': result_dir.name,
                    'data_start': data_start,
                    'data_end': data_end,
                    'crash_points': len(crash_data),
                    'total_points': len(df)
                })
    except Exception as e:
        continue

if found_results:
    print(f"找到 {len(found_results)} 个包含暴跌数据的结果目录:")
    print()
    for r in found_results:
        print(f"目录: {r['dir']}")
        print(f"  数据范围: {r['data_start']} 至 {r['data_end']}")
        print(f"  暴跌期间数据点: {r['crash_points']}")
        print(f"  总数据点: {r['total_points']}")
        print()
else:
    print("未找到包含10.10-10.11暴跌数据的结果目录")
    print()
    print("请确认:")
    print("1. 回测时间范围是否包含 2025-10-10 至 2025-10-11")
    print("2. 结果文件是否已生成")
    print()

print("=" * 80)

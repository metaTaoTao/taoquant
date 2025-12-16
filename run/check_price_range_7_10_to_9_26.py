"""
检查7.10-9.26期间的价格范围，确认是否在网格范围内
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
from data.data_manager import DataManager

print("=" * 80)
print("检查7.10-9.26期间的价格范围")
print("=" * 80)

dm = DataManager()

# 网格范围
grid_support = 107000
grid_resistance = 123000

# 检查7.10-9.26期间的价格
start = pd.Timestamp('2025-07-10', tz='UTC')
end = pd.Timestamp('2025-09-26', tz='UTC')

print(f"\n时间范围: {start} 至 {end}")
print(f"网格范围: ${grid_support:,} - ${grid_resistance:,}")

try:
    data = dm.get_klines('BTCUSDT', '1m', start=start, end=end, use_cache=True)
    
    print(f"\n数据统计:")
    print(f"  总K线数: {len(data)}")
    print(f"  最低价: ${data['low'].min():,.0f}")
    print(f"  最高价: ${data['high'].max():,.0f}")
    print(f"  开盘价: ${data['open'].iloc[0]:,.0f}")
    print(f"  收盘价: ${data['close'].iloc[-1]:,.0f}")
    
    # 检查价格在网格范围内的时间比例
    # 价格在网格范围内：low >= support 且 high <= resistance
    in_range = ((data['low'] >= grid_support) & (data['high'] <= grid_resistance)).sum()
    total = len(data)
    in_range_pct = (in_range / total * 100) if total > 0 else 0
    
    print(f"\n价格在网格范围内的时间:")
    print(f"  {in_range}/{total} ({in_range_pct:.1f}%)")
    
    # 检查价格低于网格底部的时间
    below_support = (data['low'] < grid_support).sum()
    below_support_pct = (below_support / total * 100) if total > 0 else 0
    print(f"\n价格低于网格底部(${grid_support:,})的时间:")
    print(f"  {below_support}/{total} ({below_support_pct:.1f}%)")
    
    # 检查价格高于网格顶部的时间
    above_resistance = (data['high'] > grid_resistance).sum()
    above_resistance_pct = (above_resistance / total * 100) if total > 0 else 0
    print(f"\n价格高于网格顶部(${grid_resistance:,})的时间:")
    print(f"  {above_resistance}/{total} ({above_resistance_pct:.1f}%)")
    
    # 检查价格穿越网格的时间
    crosses_grid = ((data['low'] < grid_support) | (data['high'] > grid_resistance)).sum()
    crosses_grid_pct = (crosses_grid / total * 100) if total > 0 else 0
    print(f"\n价格穿越网格边界的时间:")
    print(f"  {crosses_grid}/{total} ({crosses_grid_pct:.1f}%)")
    
    # 分析价格分布
    print(f"\n价格分布分析:")
    print(f"  价格中位数: ${data['close'].median():,.0f}")
    print(f"  价格均值: ${data['close'].mean():,.0f}")
    print(f"  价格标准差: ${data['close'].std():,.0f}")
    
    # 检查价格是否大部分时间在网格范围内
    if in_range_pct < 50:
        print(f"\n警告: 价格在网格范围内的时间只有 {in_range_pct:.1f}%")
        print(f"   这可能是交易次数减少的主要原因！")
        if below_support_pct > 30:
            print(f"   价格大部分时间低于网格底部 ({below_support_pct:.1f}%)")
        if above_resistance_pct > 30:
            print(f"   价格大部分时间高于网格顶部 ({above_resistance_pct:.1f}%)")
    else:
        print(f"\n价格在网格范围内的时间: {in_range_pct:.1f}%")
        print(f"  如果交易次数仍然减少，可能是其他原因（因子过滤、库存限制等）")
    
    # 对比9.26-10.26期间的价格范围
    print(f"\n" + "=" * 80)
    print("对比：9.26-10.26期间的价格范围")
    print("=" * 80)
    
    start2 = pd.Timestamp('2025-09-26', tz='UTC')
    end2 = pd.Timestamp('2025-10-26', tz='UTC')
    
    data2 = dm.get_klines('BTCUSDT', '1m', start=start2, end=end2, use_cache=True)
    
    print(f"\n时间范围: {start2} 至 {end2}")
    print(f"  总K线数: {len(data2)}")
    print(f"  最低价: ${data2['low'].min():,.0f}")
    print(f"  最高价: ${data2['high'].max():,.0f}")
    
    in_range2 = ((data2['low'] >= grid_support) & (data2['high'] <= grid_resistance)).sum()
    total2 = len(data2)
    in_range_pct2 = (in_range2 / total2 * 100) if total2 > 0 else 0
    
    print(f"\n价格在网格范围内的时间:")
    print(f"  {in_range2}/{total2} ({in_range_pct2:.1f}%)")
    
    print(f"\n对比结果:")
    print(f"  7.10-9.26: {in_range_pct:.1f}% 时间在网格范围内")
    print(f"  9.26-10.26: {in_range_pct2:.1f}% 时间在网格范围内")
    print(f"  差异: {in_range_pct2 - in_range_pct:.1f}%")
    
    if in_range_pct < in_range_pct2:
        print(f"\n确认: 7.10-9.26期间价格在网格范围内的时间更少")
        print(f"  这解释了为什么延长回测时间后交易次数反而减少")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()

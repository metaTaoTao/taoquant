"""
分析7.10-9.26和9.26-10.26期间的交易频率差异
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from data import DataManager

print("=" * 80)
print("分析交易频率差异")
print("=" * 80)

dm = DataManager()

# 网格参数
grid_support = 107000
grid_resistance = 123000
min_return = 0.0012  # 0.12%
grid_layers = 40

print(f"\n网格参数:")
print(f"  支撑: ${grid_support:,}")
print(f"  阻力: ${grid_resistance:,}")
print(f"  最小回报: {min_return:.4f} ({min_return*100:.2f}%)")
print(f"  网格层级: {grid_layers}")

# 分析7.10-9.26期间
print(f"\n" + "=" * 80)
print("7.10-9.26期间分析")
print("=" * 80)

start1 = pd.Timestamp('2025-07-10', tz='UTC')
end1 = pd.Timestamp('2025-09-26', tz='UTC')

data1 = dm.get_klines('BTCUSDT', '1m', start=start1, end=end1, use_cache=True)

print(f"\n价格统计:")
print(f"  价格范围: ${data1['low'].min():,.0f} - ${data1['high'].max():,.0f}")
print(f"  价格中位数: ${data1['close'].median():,.0f}")
print(f"  价格均值: ${data1['close'].mean():,.0f}")

# 计算价格波动率
price_range1 = data1['high'].max() - data1['low'].min()
price_range_pct1 = (price_range1 / data1['close'].mean()) * 100
print(f"\n价格波动:")
print(f"  价格范围: ${price_range1:,.0f} ({price_range_pct1:.2f}%)")

# 计算每日价格变化
data1['price_change'] = data1['close'].pct_change()
data1['abs_price_change'] = data1['price_change'].abs()
daily_volatility1 = data1['abs_price_change'].mean() * 100
print(f"  平均每分钟波动率: {daily_volatility1:.4f}%")

# 估算网格间距
grid_range = grid_resistance - grid_support
estimated_spacing = grid_range / grid_layers
estimated_spacing_pct = (estimated_spacing / data1['close'].mean()) * 100
print(f"\n估算网格间距:")
print(f"  网格范围: ${grid_range:,.0f}")
print(f"  估算间距: ${estimated_spacing:,.0f} ({estimated_spacing_pct:.4f}%)")
print(f"  最小回报要求: {min_return*100:.2f}%")

# 分析价格穿越网格层级的频率
# 简化：计算价格变化超过网格间距的频率
price_changes = data1['close'].pct_change().abs()
spacing_threshold = estimated_spacing_pct / 100
crosses_level = (price_changes >= spacing_threshold).sum()
total_bars1 = len(data1)
crosses_level_pct = (crosses_level / total_bars1 * 100) if total_bars1 > 0 else 0
print(f"\n价格穿越网格层级的频率:")
print(f"  穿越次数: {crosses_level}/{total_bars1} ({crosses_level_pct:.2f}%)")

# 分析9.26-10.26期间
print(f"\n" + "=" * 80)
print("9.26-10.26期间分析")
print("=" * 80)

start2 = pd.Timestamp('2025-09-26', tz='UTC')
end2 = pd.Timestamp('2025-10-26', tz='UTC')

data2 = dm.get_klines('BTCUSDT', '1m', start=start2, end=end2, use_cache=True)

print(f"\n价格统计:")
print(f"  价格范围: ${data2['low'].min():,.0f} - ${data2['high'].max():,.0f}")
print(f"  价格中位数: ${data2['close'].median():,.0f}")
print(f"  价格均值: ${data2['close'].mean():,.0f}")

price_range2 = data2['high'].max() - data2['low'].min()
price_range_pct2 = (price_range2 / data2['close'].mean()) * 100
print(f"\n价格波动:")
print(f"  价格范围: ${price_range2:,.0f} ({price_range_pct2:.2f}%)")

data2['price_change'] = data2['close'].pct_change()
data2['abs_price_change'] = data2['price_change'].abs()
daily_volatility2 = data2['abs_price_change'].mean() * 100
print(f"  平均每分钟波动率: {daily_volatility2:.4f}%")

estimated_spacing2 = grid_range / grid_layers
estimated_spacing_pct2 = (estimated_spacing2 / data2['close'].mean()) * 100
print(f"\n估算网格间距:")
print(f"  估算间距: ${estimated_spacing2:,.0f} ({estimated_spacing_pct2:.4f}%)")

price_changes2 = data2['close'].pct_change().abs()
spacing_threshold2 = estimated_spacing_pct2 / 100
crosses_level2 = (price_changes2 >= spacing_threshold2).sum()
total_bars2 = len(data2)
crosses_level_pct2 = (crosses_level2 / total_bars2 * 100) if total_bars2 > 0 else 0
print(f"\n价格穿越网格层级的频率:")
print(f"  穿越次数: {crosses_level2}/{total_bars2} ({crosses_level_pct2:.2f}%)")

# 对比分析
print(f"\n" + "=" * 80)
print("对比分析")
print("=" * 80)

print(f"\n时间长度:")
print(f"  7.10-9.26: {total_bars1} 根K线 ({total_bars1/1440:.1f} 天)")
print(f"  9.26-10.26: {total_bars2} 根K线 ({total_bars2/1440:.1f} 天)")
print(f"  比例: {total_bars1/total_bars2:.2f}x")

print(f"\n价格波动率对比:")
print(f"  7.10-9.26: {daily_volatility1:.4f}%")
print(f"  9.26-10.26: {daily_volatility2:.4f}%")
print(f"  差异: {daily_volatility2 - daily_volatility1:.4f}%")
if daily_volatility1 < daily_volatility2:
    print(f"  9.26-10.26期间波动率更高，理论上应该有更多交易")

print(f"\n价格穿越网格层级频率对比:")
print(f"  7.10-9.26: {crosses_level_pct:.2f}%")
print(f"  9.26-10.26: {crosses_level_pct2:.2f}%")
print(f"  差异: {crosses_level_pct2 - crosses_level_pct:.2f}%")

print(f"\n" + "=" * 80)
print("可能的原因")
print("=" * 80)

if crosses_level_pct < crosses_level_pct2:
    print(f"\n1. 价格波动率较低（最可能）")
    print(f"   7.10-9.26期间价格波动率较低 ({daily_volatility1:.4f}%)")
    print(f"   导致网格订单触发频率降低")
    print(f"   即使时间更长，交易次数也可能更少")
    
    print(f"\n2. 因子过滤可能更严格")
    print(f"   7.10-9.26期间，Breakout Risk 或 Trend Score 可能一直不利")
    print(f"   导致大部分买入订单被阻止")
    
    print(f"\n3. 库存限制可能更严格")
    print(f"   7.10-9.26期间，库存比率可能一直很高")
    print(f"   导致买入订单被持续阻止")
else:
    print(f"\n价格波动率不是主要原因")
    print(f"   可能是因子过滤或库存限制导致的")

print(f"\n建议:")
print(f"  1. 检查回测日志，查看7.10-9.26期间是否有大量订单被阻止")
print(f"  2. 对比两个时间段的因子状态（Breakout Risk, Trend Score等）")
print(f"  3. 对比两个时间段的库存状态")

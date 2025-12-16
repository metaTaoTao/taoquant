"""对比修复前后的压力测试结果"""
import pandas as pd
from pathlib import Path

v1_metrics = Path("run/results_lean_taogrid_stress_test_2025_09_26/metrics.json")
v2_metrics = Path("run/results_lean_taogrid_stress_test_2025_09_26_v2/metrics.json")

import json

print("=" * 80)
print("压力测试结果对比 (修复前后)")
print("=" * 80)
print()

v1 = json.load(open(v1_metrics))
v2 = json.load(open(v2_metrics))

print("修复前 (v1):")
print(f"  总收益率: {v1['total_return']:.2%}")
print(f"  最大回撤: {v1['max_drawdown']:.2%}")
print(f"  夏普比率: {v1['sharpe_ratio']:.2f}")
print(f"  总交易数: {v1['total_trades']}")
print(f"  胜率: {v1['win_rate']:.2%}")
print()

print("修复后 (v2):")
print(f"  总收益率: {v2['total_return']:.2%}")
print(f"  最大回撤: {v2['max_drawdown']:.2%}")
print(f"  夏普比率: {v2['sharpe_ratio']:.2f}")
print(f"  总交易数: {v2['total_trades']}")
print(f"  胜率: {v2['win_rate']:.2%}")
print()

print("改善:")
print(f"  交易数: {v2['total_trades'] / v1['total_trades']:.1f}x")
print(f"  收益率: {v2['total_return'] / v1['total_return']:.1f}x")
print(f"  夏普比率: {v2['sharpe_ratio'] / v1['sharpe_ratio']:.1f}x")
print()

# 查看v2的交易统计
v2_trades = pd.read_csv("run/results_lean_taogrid_stress_test_2025_09_26_v2/trades.csv")
print(f"v2 交易明细:")
print(f"  总交易数: {len(v2_trades)}")
print(f"  盈利交易: {(v2_trades['pnl'] > 0).sum()}")
print(f"  亏损交易: {(v2_trades['pnl'] < 0).sum()}")
print(f"  平均持仓时间: {v2_trades['holding_period'].mean():.1f} 小时")
print()

print("=" * 80)

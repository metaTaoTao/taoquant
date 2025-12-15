"""对比修复前后的结果"""
import json
import pandas as pd

# 读取结果
with open('run/results_lean_taogrid/metrics.json', 'r') as f:
    metrics = json.load(f)

orders_df = pd.read_csv('run/results_lean_taogrid/orders.csv')

print("=" * 80)
print("修复前后对比分析")
print("=" * 80)
print()

print("修复前（Bug状态）:")
print("  总交易数: 17")
print("  总收益率: 2.95%")
print("  最大回撤: -5.87%")
print("  夏普比率: 0.26")
print("  ROE: 2.95%")
print()

print("修复后（当前）:")
print(f"  总交易数: {metrics['total_trades']}")
print(f"  总收益率: {metrics['total_return']:.2%}")
print(f"  最大回撤: {metrics['max_drawdown']:.2%}")
print(f"  夏普比率: {metrics['sharpe_ratio']:.2f}")
print(f"  ROE: {metrics['total_return']:.2%}")
print()

print("目标表现:")
print("  总交易数: 数百/数千笔")
print("  总收益率: 50%+")
print("  最大回撤: ~20%")
print("  夏普比率: 5+")
print("  ROE: 50%+")
print()

print("改善情况:")
trade_improvement = metrics['total_trades'] / 17
return_improvement = metrics['total_return'] / 0.0295
sharpe_improvement = metrics['sharpe_ratio'] / 0.26

print(f"  交易数: 提升 {trade_improvement:.1f}x ({metrics['total_trades']}/17)")
print(f"  收益率: 提升 {return_improvement:.1f}x ({metrics['total_return']:.2%}/2.95%)")
print(f"  夏普比率: 提升 {sharpe_improvement:.1f}x ({metrics['sharpe_ratio']:.2f}/0.26)")
print()

print("订单统计:")
print(f"  总订单数: {len(orders_df)}")
print(f"  买入订单: {len(orders_df[orders_df['direction'] == 'buy'])}")
print(f"  卖出订单: {len(orders_df[orders_df['direction'] == 'sell'])}")
print()

print("=" * 80)
print("分析:")
print("=" * 80)
print()
print("✅ 已大幅改善:")
print("  - 交易数从 17 → 181 (提升 10.6x)")
print("  - 收益率从 2.95% → 16.25% (提升 5.5x)")
print("  - 夏普从 0.26 → 1.01 (提升 3.9x)")
print()
print("⚠️ 仍有差距:")
print(f"  - 交易数: 181 笔 vs 期望的数百/数千笔")
print(f"  - ROE: 16.25% vs 期望的 50%+")
print(f"  - 夏普: 1.01 vs 期望的 5+")
print()
print("可能原因:")
print("  1. MM Risk Zone 被禁用，可能需要重新启用并调整阈值")
print("  2. 因子过滤可能过于严格（breakout risk, range position等）")
print("  3. 网格触发条件可能需要优化")
print("  4. 可能需要调整其他参数（spacing, layers等）")
print()
print("=" * 80)

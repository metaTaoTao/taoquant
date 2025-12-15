"""
分析修复后的未实现亏损计算是否正确
"""
import sys
from pathlib import Path
import pandas as pd

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 读取权益曲线和订单数据
equity_df = pd.read_csv("run/results_lean_taogrid/equity_curve.csv")
equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'], utc=True)
equity_df = equity_df.set_index('timestamp').sort_index()

orders_df = pd.read_csv("run/results_lean_taogrid/orders.csv")
orders_df['timestamp'] = pd.to_datetime(orders_df['timestamp'], utc=True)

# 找到触发风控关闭的时间点
shutdown_time = pd.Timestamp("2025-07-10 16:20:00", tz="UTC")

print("=" * 80)
print("未实现亏损分析（修复后）")
print("=" * 80)
print()

# 获取关闭时的权益曲线数据
shutdown_idx = equity_df.index.get_indexer([shutdown_time], method='nearest')[0]
shutdown_row = equity_df.iloc[shutdown_idx]

print(f"风控关闭时间: {shutdown_time}")
print(f"权益: ${shutdown_row['equity']:,.2f}")
print(f"现金: ${shutdown_row['cash']:,.2f}")
print(f"持仓: {shutdown_row['holdings']:.4f} BTC")
print(f"持仓价值: ${shutdown_row['holdings_value']:,.2f}")
print()

# 计算成本基础（从买入订单累计）
buy_orders = orders_df[orders_df['direction'] == 'buy']
sell_orders = orders_df[orders_df['direction'] == 'sell']

# 计算到关闭时的成本基础
cost_basis = 0.0
holdings_count = 0.0

# 按时间顺序处理买入和卖出
all_orders = pd.concat([
    buy_orders[['timestamp', 'direction', 'size', 'price']],
    sell_orders[['timestamp', 'direction', 'size', 'price']]
]).sort_values('timestamp')

for _, order in all_orders.iterrows():
    if order['timestamp'] > shutdown_time:
        break
    
    if order['direction'] == 'buy':
        cost_basis += order['size'] * order['price']
        holdings_count += order['size']
    elif order['direction'] == 'sell':
        # 使用 FIFO 方式减少成本基础
        # 简化计算：假设按平均成本卖出
        if holdings_count > 0:
            avg_cost = cost_basis / holdings_count if holdings_count > 0 else 0
            cost_basis -= order['size'] * avg_cost
            holdings_count -= order['size']
            cost_basis = max(0.0, cost_basis)
            holdings_count = max(0.0, holdings_count)

print(f"计算出的成本基础: ${cost_basis:,.2f}")
print(f"计算出的持仓数量: {holdings_count:.4f} BTC")
print()

# 计算未实现亏损
current_value = shutdown_row['holdings_value']
unrealized_pnl = current_value - cost_basis

print(f"当前持仓价值: ${current_value:,.2f}")
print(f"成本基础: ${cost_basis:,.2f}")
print(f"未实现盈亏: ${unrealized_pnl:,.2f}")
print(f"未实现盈亏百分比 (相对权益): {(unrealized_pnl / shutdown_row['equity']) * 100:.2f}%")
print()

# 检查是否应该触发风控
max_loss_pct = 0.30  # 30%
max_loss_amount = shutdown_row['equity'] * max_loss_pct

print(f"风控阈值 (30%): ${max_loss_amount:,.2f}")
print(f"是否应该触发: {unrealized_pnl < -max_loss_amount}")
print()

# 对比修复前后的差异
print("=" * 80)
print("修复前 vs 修复后对比")
print("=" * 80)
print()

# 修复前：成本基础不会被卖出减少（Bug）
cost_basis_bug = 0.0
for _, order in buy_orders.iterrows():
    if order['timestamp'] <= shutdown_time:
        cost_basis_bug += order['size'] * order['price']

unrealized_pnl_bug = current_value - cost_basis_bug

print(f"修复前（Bug）:")
print(f"  成本基础: ${cost_basis_bug:,.2f}")
print(f"  未实现盈亏: ${unrealized_pnl_bug:,.2f}")
print(f"  未实现盈亏百分比: {(unrealized_pnl_bug / shutdown_row['equity']) * 100:.2f}%")
print()

print(f"修复后:")
print(f"  成本基础: ${cost_basis:,.2f}")
print(f"  未实现盈亏: ${unrealized_pnl:,.2f}")
print(f"  未实现盈亏百分比: {(unrealized_pnl / shutdown_row['equity']) * 100:.2f}%")
print()

print("=" * 80)
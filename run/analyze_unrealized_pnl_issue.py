"""分析未实现亏损计算问题 - 检查 00:55 时的状态"""
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

# 读取订单和权益曲线
orders_file = Path("run/results_lean_taogrid_stress_test_2025_09_26/orders.csv")
equity_file = Path("run/results_lean_taogrid_stress_test_2025_09_26/equity_curve.csv")

orders_df = pd.read_csv(orders_file)
equity_df = pd.read_csv(equity_file)
equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'])

# 筛选 00:55 之前的数据
shutdown_time = pd.Timestamp("2025-09-26 00:55:00", tz='UTC')
before_shutdown_orders = orders_df[orders_df['timestamp'] <= '2025-09-26 00:55:00']
before_shutdown_equity = equity_df[equity_df['timestamp'] <= shutdown_time]

print("=" * 80)
print("未实现亏损计算问题诊断")
print("=" * 80)
print()

# 分析 00:55 之前的订单
print("00:55 之前的订单:")
print("-" * 80)
for idx, row in before_shutdown_orders.iterrows():
    direction = row['direction']
    size = row['size']
    price = row['price']
    market_price = row.get('market_price', 'N/A')
    print(f"{row['timestamp']} | {direction.upper():4s} | Size: {size:.4f} BTC | Price: ${price:,.2f} | Market: ${market_price if market_price != 'N/A' else 'N/A'}")
print()

# 计算到 00:55 时的持仓状态
print("00:55 时的持仓状态计算:")
print("-" * 80)

# 模拟计算 cost basis 和 holdings
total_cost_basis = 0.0
holdings = 0.0
cash = 100000.0

buy_orders = before_shutdown_orders[before_shutdown_orders['direction'] == 'buy']
sell_orders = before_shutdown_orders[before_shutdown_orders['direction'] == 'sell']

print("买入订单:")
for idx, row in buy_orders.iterrows():
    size = row['size']
    price = row['price']
    cost = row.get('cost', size * price * 1.0002)  # 含手续费
    total_cost_basis += size * price  # cost basis 只用价格，不含手续费
    holdings += size
    cash -= cost
    print(f"  {row['timestamp']} | BUY {size:.4f} @ ${price:,.2f} | Cost basis += ${size * price:,.2f} | Holdings: {holdings:.4f}")

print()
print("卖出订单:")
for idx, row in sell_orders.iterrows():
    size = row['size']
    price = row['price']
    proceeds = row.get('proceeds', size * price * 0.9998)  # 扣除手续费
    # 使用 FIFO 匹配：每次卖出按比例减少 cost basis
    if holdings > 0:
        reduction_ratio = min(size / holdings, 1.0)
        cost_basis_reduction = total_cost_basis * reduction_ratio
        total_cost_basis -= cost_basis_reduction
        holdings -= size
        cash += proceeds
        print(f"  {row['timestamp']} | SELL {size:.4f} @ ${price:,.2f} | Cost basis -= ${cost_basis_reduction:,.2f} | Holdings: {holdings:.4f}")
    else:
        print(f"  {row['timestamp']} | SELL {size:.4f} @ ${price:,.2f} | WARNING: No holdings to sell!")

print()
print("00:55 时的状态:")
print("-" * 80)
shutdown_state = equity_df[equity_df['timestamp'] <= shutdown_time].iloc[-1]
current_price_0055 = shutdown_state['holdings_value'] / shutdown_state['holdings'] if shutdown_state['holdings'] > 0 else 109000
print(f"持仓数量: {holdings:.4f} BTC")
print(f"Cost Basis: ${total_cost_basis:,.2f}")
print(f"当前价格 (估算): ${current_price_0055:,.2f}")
print(f"当前市值: ${holdings * current_price_0055:,.2f}")
print(f"未实现盈亏: ${holdings * current_price_0055 - total_cost_basis:,.2f}")
print(f"权益 (从equity_curve): ${shutdown_state['equity']:,.2f}")
print()

# 计算未实现亏损百分比
if shutdown_state['equity'] > 0:
    unrealized_pnl = holdings * current_price_0055 - total_cost_basis
    unrealized_pnl_pct = unrealized_pnl / shutdown_state['equity']
    print(f"未实现盈亏占权益比例: {unrealized_pnl_pct:.2%}")
    print(f"阈值 (30%): -30.00%")
    print(f"触发条件: {unrealized_pnl_pct:.2%} < -30.00% ? {unrealized_pnl_pct < -0.30}")

print()
print("=" * 80)

"""追踪 cost_basis 计算问题 - 检查卖出时是否正确匹配"""
import pandas as pd
from pathlib import Path

orders_file = Path("run/results_lean_taogrid_stress_test_2025_09_26_v2/orders.csv")
trades_file = Path("run/results_lean_taogrid_stress_test_2025_09_26_v2/trades.csv")

orders_df = pd.read_csv(orders_file)
trades_df = pd.read_csv(trades_file) if trades_file.exists() else pd.DataFrame()

print("=" * 80)
print("Cost Basis 计算问题追踪")
print("=" * 80)
print()

# 查看00:53-00:57之间的订单
period_orders = orders_df[orders_df['timestamp'] >= '2025-09-26 00:53:00']
period_orders = period_orders[period_orders['timestamp'] <= '2025-09-26 00:57:00']

print("00:53-00:57 期间的订单:")
print("-" * 80)
for idx, row in period_orders.iterrows():
    direction = row['direction']
    size = row['size']
    price = row['price']
    matched_trades = row.get('matched_trades', 0)
    print(f"{row['timestamp']} | {direction.upper():4s} | Size: {size:.4f} | Price: ${price:,.2f} | Matched: {matched_trades}")
print()

# 查看对应的交易
if not trades_df.empty:
    period_trades = trades_df[trades_df['entry_timestamp'] >= '2025-09-26 00:53:00']
    period_trades = period_trades[period_trades['exit_timestamp'] <= '2025-09-26 00:57:00']
    
    print("对应的交易记录:")
    print("-" * 80)
    for idx, row in period_trades.iterrows():
        print(f"Entry: {row['entry_timestamp']} @ ${row['entry_price']:,.2f} | "
              f"Exit: {row['exit_timestamp']} @ ${row['exit_price']:,.2f} | "
              f"Size: {row['size']:.4f} | PnL: ${row['pnl']:,.2f}")
print()

print("=" * 80)
print()
print("关键观察:")
print("- 如果 sell 订单的 matched_trades=0，说明没有成功匹配到 buy 位置")
print("- 这会导致 cost_basis 不被减少，从而产生错误的未实现亏损计算")

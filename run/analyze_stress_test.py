"""分析压力测试回测结果"""
import pandas as pd
from pathlib import Path

equity_file = Path("run/results_lean_taogrid_stress_test_2025_09_26/equity_curve.csv")
df = pd.read_csv(equity_file)
df['timestamp'] = pd.to_datetime(df['timestamp'])

print("=" * 80)
print("压力测试结果分析")
print("=" * 80)
print()

# 基本统计
initial_equity = df['equity'].iloc[0]
final_equity = df['equity'].iloc[-1]
max_equity = df['equity'].max()
min_equity = df['equity'].min()

print(f"初始权益: ${initial_equity:,.2f}")
print(f"最终权益: ${final_equity:,.2f}")
print(f"最高权益: ${max_equity:,.2f} (发生在: {df.loc[df['equity'].idxmax(), 'timestamp']})")
print(f"最低权益: ${min_equity:,.2f} (发生在: {df.loc[df['equity'].idxmin(), 'timestamp']})")
print()

# 回撤分析
df['cummax'] = df['equity'].cummax()
df['drawdown'] = (df['equity'] - df['cummax']) / df['cummax']
max_dd = df['drawdown'].min()
max_dd_time = df.loc[df['drawdown'].idxmin(), 'timestamp']
print(f"最大回撤: {max_dd:.2%} (发生在: {max_dd_time})")
print()

# 10/11 插针期间
oct_11_start = pd.Timestamp("2025-10-11 00:00:00", tz='UTC')
oct_11_end = pd.Timestamp("2025-10-12 00:00:00", tz='UTC')
oct_11_data = df[(df['timestamp'] >= oct_11_start) & (df['timestamp'] < oct_11_end)]
if len(oct_11_data) > 0:
    oct_11_min = oct_11_data['equity'].min()
    oct_11_min_time = oct_11_data.loc[oct_11_data['equity'].idxmin(), 'timestamp']
    print(f"10/11 当日最低权益: ${oct_11_min:,.2f} (发生在: {oct_11_min_time})")
    print(f"10/11 当日权益范围: ${oct_11_data['equity'].min():,.2f} ~ ${oct_11_data['equity'].max():,.2f}")
    print()

# 网格关闭后的权益变化
shutdown_time = pd.Timestamp("2025-09-26 00:55:00", tz='UTC')
after_shutdown = df[df['timestamp'] > shutdown_time]
if len(after_shutdown) > 0:
    print(f"网格关闭后 (00:55 之后) 权益变化:")
    print(f"  关闭时权益: ${after_shutdown['equity'].iloc[0]:,.2f}")
    print(f"  最终权益: ${after_shutdown['equity'].iloc[-1]:,.2f}")
    print(f"  关闭后最低: ${after_shutdown['equity'].min():,.2f}")
    print()

print("=" * 80)

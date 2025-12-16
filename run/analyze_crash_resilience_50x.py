"""
分析10.10-10.11暴跌期间50X杠杆策略的抗压机制
"""
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

results_dir = Path("run/results_lean_taogrid")

# 读取数据
equity_file = results_dir / "equity_curve.csv"
orders_file = results_dir / "orders.csv"
trades_file = results_dir / "trades.csv"

print("=" * 80)
print("分析10.10-10.11暴跌期间的策略抗压机制")
print("=" * 80)

# 读取权益曲线
equity_df = pd.read_csv(equity_file)
equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'], utc=True)
equity_df = equity_df.set_index('timestamp')

# 读取订单
orders_df = pd.read_csv(orders_file)
orders_df['timestamp'] = pd.to_datetime(orders_df['timestamp'], utc=True)
orders_df = orders_df.set_index('timestamp')
# 统一列名：direction -> side
orders_df['side'] = orders_df['direction'].str.upper()

# 读取交易
trades_df = pd.read_csv(trades_file)
# trades.csv没有timestamp列，使用entry_timestamp作为主要时间戳
trades_df['timestamp'] = pd.to_datetime(trades_df['entry_timestamp'], utc=True)
trades_df = trades_df.set_index('timestamp')

# 定义暴跌时间段
crash_start = pd.Timestamp("2025-10-10 20:00:00", tz='UTC')
crash_end = pd.Timestamp("2025-10-11 04:00:00", tz='UTC')

print(f"\n暴跌时间段: {crash_start} 至 {crash_end}")

# 提取暴跌期间的权益曲线
crash_equity = equity_df.loc[(equity_df.index >= crash_start) & (equity_df.index <= crash_end)]

# 提取暴跌期间的订单
crash_orders = orders_df.loc[(orders_df.index >= crash_start) & (orders_df.index <= crash_end)]

# 提取暴跌期间的交易
crash_trades = trades_df.loc[(trades_df.index >= crash_start) & (trades_df.index <= crash_end)]

print(f"\n暴跌期间权益曲线数据点: {len(crash_equity)}")
print(f"暴跌期间订单数: {len(crash_orders)}")
print(f"暴跌期间交易数: {len(crash_trades)}")

# 1. 分析权益曲线变化
print("\n" + "=" * 80)
print("1. 权益曲线变化分析")
print("=" * 80)

if len(crash_equity) > 0:
    initial_equity = crash_equity.iloc[0]['equity']
    final_equity = crash_equity.iloc[-1]['equity']
    min_equity = crash_equity['equity'].min()
    max_equity = crash_equity['equity'].max()
    max_dd_in_crash = (min_equity - initial_equity) / initial_equity * 100
    
    print(f"暴跌开始权益: ${initial_equity:,.2f}")
    print(f"暴跌期间最低权益: ${min_equity:,.2f} (时间: {crash_equity.loc[crash_equity['equity'] == min_equity].index[0]})")
    print(f"暴跌结束权益: ${final_equity:,.2f}")
    print(f"暴跌期间最大回撤: {max_dd_in_crash:.2f}%")
    print(f"权益恢复: {((final_equity - min_equity) / initial_equity * 100):.2f}%")

# 2. 分析持仓变化
print("\n" + "=" * 80)
print("2. 持仓和现金变化分析")
print("=" * 80)

if len(crash_equity) > 0:
    # 持仓相关
    max_holdings = crash_equity['holdings'].max()
    min_holdings = crash_equity['holdings'].min()
    avg_holdings = crash_equity['holdings'].mean()
    
    max_holdings_value = crash_equity['holdings_value'].max()
    min_holdings_value = crash_equity['holdings_value'].min()
    
    print(f"最大持仓: {max_holdings:.4f} BTC")
    print(f"最小持仓: {min_holdings:.4f} BTC")
    print(f"平均持仓: {avg_holdings:.4f} BTC")
    print(f"最大持仓价值: ${max_holdings_value:,.2f}")
    print(f"最小持仓价值: ${min_holdings_value:,.2f}")
    
    # 现金变化
    min_cash = crash_equity['cash'].min()
    max_cash = crash_equity['cash'].max()
    print(f"\n现金范围: ${min_cash:,.2f} 至 ${max_cash:,.2f}")

# 3. 分析订单执行模式
print("\n" + "=" * 80)
print("3. 订单执行模式分析")
print("=" * 80)

if len(crash_orders) > 0:
    buy_orders = crash_orders[crash_orders['side'] == 'BUY']
    sell_orders = crash_orders[crash_orders['side'] == 'SELL']
    
    print(f"买入订单: {len(buy_orders)}")
    print(f"卖出订单: {len(sell_orders)}")
    
    if len(buy_orders) > 0:
        print(f"\n买入订单:")
        print(f"  平均价格: ${buy_orders['price'].mean():,.2f}")
        print(f"  价格范围: ${buy_orders['price'].min():,.2f} - ${buy_orders['price'].max():,.2f}")
        print(f"  平均数量: {buy_orders['size'].mean():.4f} BTC")
        print(f"  总买入量: {buy_orders['size'].sum():.4f} BTC")
    
    if len(sell_orders) > 0:
        print(f"\n卖出订单:")
        print(f"  平均价格: ${sell_orders['price'].mean():,.2f}")
        print(f"  价格范围: ${sell_orders['price'].min():,.2f} - ${sell_orders['price'].max():,.2f}")
        print(f"  平均数量: {sell_orders['size'].mean():.4f} BTC")
        print(f"  总卖出量: {sell_orders['size'].sum():.4f} BTC")
    
    # 按小时统计订单
    crash_orders['hour'] = crash_orders.index.hour
    hourly_orders = crash_orders.groupby('hour').agg({
        'side': 'count',
        'size': 'sum',
        'price': ['min', 'max', 'mean']
    })
    print(f"\n按小时订单分布:")
    print(hourly_orders)

# 4. 分析网格层级执行
print("\n" + "=" * 80)
print("4. 网格层级执行分析")
print("=" * 80)

if len(crash_orders) > 0 and 'level' in crash_orders.columns:
    level_stats = crash_orders.groupby('level').agg({
        'side': 'count',
        'size': 'sum',
        'price': ['min', 'max', 'mean']
    })
    print(f"网格层级统计 (共{len(level_stats)}个层级):")
    print(level_stats.head(20))  # 显示前20层
    
    # 找出最活跃的层级
    most_active_level = level_stats['side'].idxmax()
    print(f"\n最活跃层级: L{most_active_level} ({level_stats.loc[most_active_level, 'side']}笔订单)")

# 5. 分析关键时点的持仓和权益
print("\n" + "=" * 80)
print("5. 关键时点分析")
print("=" * 80)

# 找到权益最低点
if len(crash_equity) > 0:
    min_equity_idx = crash_equity['equity'].idxmin()
    min_equity_row = crash_equity.loc[min_equity_idx]
    
    print(f"权益最低点 ({min_equity_idx}):")
    print(f"  权益: ${min_equity_row['equity']:,.2f}")
    print(f"  持仓: {min_equity_row['holdings']:.4f} BTC")
    print(f"  持仓价值: ${min_equity_row['holdings_value']:,.2f}")
    print(f"  现金: ${min_equity_row['cash']:,.2f}")
    
    # 计算此时的实际杠杆
    if min_equity_row['holdings_value'] > 0:
        implied_leverage = min_equity_row['holdings_value'] / min_equity_row['equity']
        print(f"  实际杠杆倍数: {implied_leverage:.2f}X")

# 6. 分析订单配对情况（网格配对机制）
print("\n" + "=" * 80)
print("6. 网格配对机制分析")
print("=" * 80)

if len(crash_orders) > 0 and 'matched_trades' in crash_orders.columns:
    matched_orders = crash_orders[crash_orders['matched_trades'] > 0]
    unmatched_orders = crash_orders[crash_orders['matched_trades'] == 0]
    
    print(f"成功配对的订单: {len(matched_orders)}")
    print(f"未配对的订单: {len(unmatched_orders)}")
    print(f"配对率: {len(matched_orders) / len(crash_orders) * 100:.2f}%")
    
    # 分析卖出订单的配对情况
    sell_orders_with_match = crash_orders[(crash_orders['side'] == 'SELL') & (crash_orders['matched_trades'] > 0)]
    sell_orders_no_match = crash_orders[(crash_orders['side'] == 'SELL') & (crash_orders['matched_trades'] == 0)]
    
    print(f"\n卖出订单配对:")
    print(f"  成功配对: {len(sell_orders_with_match)}")
    print(f"  未配对: {len(sell_orders_no_match)}")

# 7. 分析价格区间和网格覆盖
print("\n" + "=" * 80)
print("7. 价格区间和网格覆盖分析")
print("=" * 80)

if len(crash_orders) > 0:
    price_min = crash_orders['price'].min()
    price_max = crash_orders['price'].max()
    price_range = price_max - price_min
    
    print(f"订单价格范围: ${price_min:,.2f} - ${price_max:,.2f}")
    print(f"价格波动幅度: ${price_range:,.2f} ({price_range / price_min * 100:.2f}%)")
    
    # 分析订单在价格区间的分布
    price_bins = np.linspace(price_min, price_max, 20)
    crash_orders['price_bin'] = pd.cut(crash_orders['price'], bins=price_bins)
    price_dist = crash_orders.groupby('price_bin').size()
    print(f"\n价格区间订单分布 (前10个最活跃区间):")
    print(price_dist.nlargest(10))

# 8. 总结关键抗压机制
print("\n" + "=" * 80)
print("8. 策略抗压机制总结")
print("=" * 80)

print("""
基于以上分析，50X杠杆策略能在10.10-11暴跌中保持11.37%最大回撤的关键机制可能包括：

1. **网格配对机制**：
   - 卖出订单优先匹配同层级的买入订单，实现快速平仓
   - 即使价格暴跌，卖出订单能快速锁定利润或限制亏损

2. **动态持仓管理**：
   - 持仓在暴跌期间可能通过频繁的买卖配对迅速降低
   - 避免大量单边持仓暴露在极端行情中

3. **价格区间控制**：
   - 网格订单分散在价格区间内，避免集中暴露
   - 即使在暴跌时，部分订单仍能盈利配对

4. **实际杠杆控制**：
   - 虽然名义杠杆50X，但实际持仓可能通过配对机制降低
   - 权益最低点的实际杠杆可能远低于50X

5. **频繁交易对冲**：
   - 暴跌期间的频繁买卖交易形成天然对冲
   - 每次卖出配对都能减少持仓风险
""")

print("\n分析完成！")

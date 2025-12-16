"""深入分析10.10-10.11暴跌期间的表现 - 560x杠杆下的风险控制"""
import pandas as pd
import numpy as np
from pathlib import Path

results_dir = Path("run/results_lean_taogrid_stress_test_2025_09_26_v2")

print("=" * 80)
print("10.10-10.11暴跌期间深度分析")
print("=" * 80)
print()

# 读取数据
equity_df = pd.read_csv(results_dir / "equity_curve.csv")
equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'])

orders_df = pd.read_csv(results_dir / "orders.csv")
orders_df['timestamp'] = pd.to_datetime(orders_df['timestamp'])

trades_df = pd.read_csv(results_dir / "trades.csv")
trades_df['entry_timestamp'] = pd.to_datetime(trades_df['entry_timestamp'])
trades_df['exit_timestamp'] = pd.to_datetime(trades_df['exit_timestamp'])

# 定义暴跌时间段
crash_start = pd.Timestamp("2025-10-10 00:00:00", tz='UTC')
crash_end = pd.Timestamp("2025-10-11 23:59:59", tz='UTC')

# 1. 权益曲线分析
print("1. 权益曲线分析")
print("-" * 80)

# 找到暴跌前的峰值
before_crash = equity_df[equity_df['timestamp'] < crash_start]
peak_equity = before_crash['equity'].max()
peak_idx = before_crash['equity'].idxmax()
peak_time = before_crash.loc[peak_idx, 'timestamp']

# 暴跌期间的数据
crash_equity = equity_df[
    (equity_df['timestamp'] >= crash_start) & 
    (equity_df['timestamp'] <= crash_end)
].copy()

# 找到最低点
min_equity = crash_equity['equity'].min()
min_idx = crash_equity['equity'].idxmin()
min_time = crash_equity.loc[min_idx, 'timestamp']

# 计算最大回撤
max_dd = (min_equity - peak_equity) / peak_equity * 100

print(f"峰值权益: ${peak_equity:,.2f} (时间: {peak_time})")
print(f"最低权益: ${min_equity:,.2f} (时间: {min_time})")
print(f"最大回撤: {max_dd:.2f}%")
print()

# 查看暴跌期间的持仓变化
if 'holdings' in crash_equity.columns:
    peak_holdings = before_crash.loc[peak_idx, 'holdings'] if peak_idx in before_crash.index else 0
    min_holdings = crash_equity.loc[min_idx, 'holdings']
    
    print(f"峰值持仓: {peak_holdings:.4f} BTC")
    print(f"最低点持仓: {min_holdings:.4f} BTC")
    print(f"持仓变化: {min_holdings - peak_holdings:.4f} BTC")
    print()

# 2. 订单分析
print("2. 订单分析")
print("-" * 80)

crash_orders = orders_df[
    (orders_df['timestamp'] >= crash_start) & 
    (orders_df['timestamp'] <= crash_end)
].copy()

print(f"暴跌期间订单总数: {len(crash_orders)} 笔")

if len(crash_orders) > 0:
    buy_orders = crash_orders[crash_orders['direction'] == 'buy']
    sell_orders = crash_orders[crash_orders['direction'] == 'sell']
    
    print(f"  买入: {len(buy_orders)} 笔, 总量: {buy_orders['size'].sum():.4f} BTC")
    print(f"  卖出: {len(sell_orders)} 笔, 总量: {sell_orders['size'].sum():.4f} BTC")
    print()
    
    # 分析价格和时间分布
    if 'market_price' in crash_orders.columns:
        prices = crash_orders['market_price'].dropna()
        print(f"价格统计:")
        print(f"  最低价: ${prices.min():,.2f}")
        print(f"  最高价: ${prices.max():,.2f}")
        print(f"  价格跌幅: {((prices.min() - prices.max()) / prices.max() * 100):.2f}%")
        print()
        
        # 按小时统计订单
        crash_orders['hour'] = crash_orders['timestamp'].dt.hour
        hourly_orders = crash_orders.groupby('hour').agg({
            'size': 'count',
            'market_price': ['min', 'max']
        })
        print(f"每小时订单分布 (前5小时):")
        for hour in sorted(crash_orders['hour'].unique())[:5]:
            hour_data = crash_orders[crash_orders['hour'] == hour]
            print(f"  {hour:02d}:00 - {len(hour_data)} 笔订单, 价格范围: ${hour_data['market_price'].min():,.0f} - ${hour_data['market_price'].max():,.0f}")
        print()

# 3. 交易分析
print("3. 交易分析")
print("-" * 80)

crash_trades = trades_df[
    ((trades_df['entry_timestamp'] >= crash_start) & (trades_df['entry_timestamp'] <= crash_end)) |
    ((trades_df['exit_timestamp'] >= crash_start) & (trades_df['exit_timestamp'] <= crash_end))
].copy()

print(f"暴跌期间相关交易: {len(crash_trades)} 笔")

if len(crash_trades) > 0:
    winning = crash_trades[crash_trades['pnl'] > 0]
    losing = crash_trades[crash_trades['pnl'] < 0]
    
    print(f"  盈利交易: {len(winning)} 笔, 总盈利: ${winning['pnl'].sum():,.2f}")
    print(f"  亏损交易: {len(losing)} 笔, 总亏损: ${losing['pnl'].sum():,.2f}")
    print(f"  净盈亏: ${crash_trades['pnl'].sum():,.2f}")
    print(f"  胜率: {len(winning) / len(crash_trades) * 100:.1f}%")
    print()

# 4. 关键时间点分析
print("4. 关键时间点分析")
print("-" * 80)

# 找到暴跌开始时的权益和持仓
start_equity_row = crash_equity.iloc[0]
end_equity_row = crash_equity.iloc[-1]

print(f"10.10 00:00 状态:")
print(f"  权益: ${start_equity_row['equity']:,.2f}")
if 'holdings' in start_equity_row:
    print(f"  持仓: {start_equity_row['holdings']:.4f} BTC")
    if start_equity_row['holdings'] > 0:
        print(f"  持仓价值: ${start_equity_row.get('holdings_value', 0):,.2f}")
print()

print(f"10.11 23:59 状态:")
print(f"  权益: ${end_equity_row['equity']:,.2f}")
if 'holdings' in end_equity_row:
    print(f"  持仓: {end_equity_row['holdings']:.4f} BTC")
    if end_equity_row['holdings'] > 0:
        print(f"  持仓价值: ${end_equity_row.get('holdings_value', 0):,.2f}")
print()

# 5. 推断杠杆倍数
print("5. 杠杆倍数推断")
print("-" * 80)

# 从持仓和权益推断杠杆
if 'holdings' in crash_equity.columns and 'holdings_value' in crash_equity.columns:
    # 找一个有持仓的时间点
    sample_row = crash_equity[crash_equity['holdings'] > 0.001].iloc[0] if len(crash_equity[crash_equity['holdings'] > 0.001]) > 0 else None
    if sample_row is not None:
        holdings = sample_row['holdings']
        holdings_value = sample_row['holdings_value']
        equity = sample_row['equity']
        
        # 估算杠杆: holdings_value / equity
        estimated_leverage = holdings_value / equity if equity > 0 else 0
        
        print(f"基于持仓推断:")
        print(f"  持仓: {holdings:.4f} BTC")
        print(f"  持仓价值: ${holdings_value:,.2f}")
        print(f"  权益: ${equity:,.2f}")
        print(f"  推断杠杆: {estimated_leverage:.1f}x")
        print()

# 6. 风险控制机制分析
print("6. 风险控制机制分析")
print("-" * 80)

# 查看是否有订单被阻止
if 'matched_trades' in orders_df.columns:
    zero_match_orders = orders_df[orders_df['matched_trades'] == 0]
    crash_zero_match = zero_match_orders[
        (zero_match_orders['timestamp'] >= crash_start) & 
        (zero_match_orders['timestamp'] <= crash_end)
    ]
    print(f"未匹配的订单 (可能被风控阻止): {len(crash_zero_match)} 笔")
    print()

# 查看持仓是否在暴跌期间被大幅减少
if 'holdings' in crash_equity.columns:
    holdings_series = crash_equity['holdings'].values
    max_holdings = holdings_series.max()
    min_holdings = holdings_series.min()
    holdings_reduction = (max_holdings - min_holdings) / max_holdings * 100 if max_holdings > 0 else 0
    
    print(f"持仓变化:")
    print(f"  最大持仓: {max_holdings:.4f} BTC")
    print(f"  最小持仓: {min_holdings:.4f} BTC")
    print(f"  持仓减少: {holdings_reduction:.1f}%")
    print()

print("=" * 80)
print()
print("关键发现:")
print(f"- 最大回撤: {max_dd:.2f}%")
print(f"- 暴跌期间订单: {len(crash_orders)} 笔")
print(f"- 暴跌期间交易: {len(crash_trades)} 笔")
if len(crash_equity) > 0:
    equity_change = (end_equity_row['equity'] - start_equity_row['equity']) / start_equity_row['equity'] * 100
    print(f"- 期间权益变化: {equity_change:.2f}%")
print()

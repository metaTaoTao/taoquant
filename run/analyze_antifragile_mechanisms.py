"""分析网格策略在暴跌中的抗跌机制 - 为什么560x杠杆下最大回撤只有11.37%"""
import pandas as pd
import numpy as np
from pathlib import Path

results_dir = Path("run/results_lean_taogrid_stress_test_2025_09_26_v2")

print("=" * 80)
print("网格策略抗跌机制分析 - 560x杠杆下最大回撤11.37%的原因")
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

# 暴跌时间段
crash_start = pd.Timestamp("2025-10-10 00:00:00", tz='UTC')
crash_end = pd.Timestamp("2025-10-11 23:59:59", tz='UTC')

# 暴跌前后的时间段
before_start = crash_start - pd.Timedelta(days=1)
after_end = crash_end + pd.Timedelta(days=1)

print("分析时间段:")
print(f"  暴跌前1天: {before_start} 至 {crash_start}")
print(f"  暴跌期间: {crash_start} 至 {crash_end}")
print(f"  暴跌后1天: {crash_end} 至 {after_end}")
print()

# 1. 持仓管理分析 - 关键机制
print("1. 持仓管理 - 网格策略的核心抗跌机制")
print("-" * 80)

# 查看暴跌前、中、后的持仓变化
before_crash = equity_df[
    (equity_df['timestamp'] >= before_start) & 
    (equity_df['timestamp'] < crash_start)
]

during_crash = equity_df[
    (equity_df['timestamp'] >= crash_start) & 
    (equity_df['timestamp'] <= crash_end)
]

after_crash = equity_df[
    (equity_df['timestamp'] > crash_end) & 
    (equity_df['timestamp'] <= after_end)
]

if 'holdings' in equity_df.columns:
    print("持仓变化:")
    if len(before_crash) > 0:
        before_avg = before_crash['holdings'].mean()
        before_max = before_crash['holdings'].max()
        before_end = before_crash.iloc[-1]['holdings']
        print(f"  暴跌前平均持仓: {before_avg:.4f} BTC")
        print(f"  暴跌前最大持仓: {before_max:.4f} BTC")
        print(f"  暴跌前最后持仓: {before_end:.4f} BTC")
        print()
    
    if len(during_crash) > 0:
        during_avg = during_crash['holdings'].mean()
        during_min = during_crash['holdings'].min()
        during_max = during_crash['holdings'].max()
        during_start = during_crash.iloc[0]['holdings']
        during_end = during_crash.iloc[-1]['holdings']
        
        print(f"  暴跌期间平均持仓: {during_avg:.4f} BTC")
        print(f"  暴跌期间最小持仓: {during_min:.4f} BTC")
        print(f"  暴跌期间最大持仓: {during_max:.4f} BTC")
        print(f"  暴跌开始时持仓: {during_start:.4f} BTC")
        print(f"  暴跌结束时持仓: {during_end:.4f} BTC")
        print()
        
        # 关键发现：持仓是否在暴跌前被主动减少
        if len(before_crash) > 0:
            reduction = before_end - during_start
            reduction_pct = (reduction / before_max * 100) if before_max > 0 else 0
            print(f"  暴跌前持仓减少: {reduction:.4f} BTC ({reduction_pct:.1f}%)")
            print()
    
    if len(after_crash) > 0:
        after_start = after_crash.iloc[0]['holdings']
        print(f"  暴跌后开始持仓: {after_start:.4f} BTC")
        print()

# 2. 交易频率分析 - 网格持续运行
print("2. 交易频率 - 网格持续运行的能力")
print("-" * 80)

crash_orders = orders_df[
    (orders_df['timestamp'] >= crash_start) & 
    (orders_df['timestamp'] <= crash_end)
]

print(f"暴跌期间订单总数: {len(crash_orders)} 笔")
print(f"平均每小时订单: {len(crash_orders) / 48:.1f} 笔")
print()

if len(crash_orders) > 0:
    # 按小时统计
    crash_orders['hour'] = crash_orders['timestamp'].dt.hour
    hourly_counts = crash_orders.groupby('hour').size()
    
    print("关键发现:")
    print(f"  网格在暴跌期间持续交易，说明策略未完全关闭")
    print(f"  最高活跃小时订单数: {hourly_counts.max()} 笔")
    print(f"  最低活跃小时订单数: {hourly_counts.min()} 笔")
    print()

# 3. 价格区间分析 - 网格是否在合理区间内
print("3. 价格区间分析 - 网格是否在支撑阻力范围内")
print("-" * 80)

if 'market_price' in crash_orders.columns:
    prices = crash_orders['market_price'].dropna()
    print(f"暴跌期间价格范围: ${prices.min():,.2f} - ${prices.max():,.2f}")
    print(f"价格跌幅: {((prices.min() - prices.max()) / prices.max() * 100):.2f}%")
    print()
    
    # 检查价格是否在S/R范围内 (假设107K-123K)
    support = 107000
    resistance = 123000
    prices_in_range = prices[(prices >= support) & (prices <= resistance)]
    
    print(f"价格是否在S/R范围内 (${support:,} - ${resistance:,}):")
    print(f"  范围内价格占比: {len(prices_in_range) / len(prices) * 100:.1f}%")
    print(f"  范围外价格占比: {(1 - len(prices_in_range) / len(prices)) * 100:.1f}%")
    print()

# 4. 盈亏分析 - 快速获利了结
print("4. 盈亏分析 - 快速获利了结机制")
print("-" * 80)

crash_trades = trades_df[
    ((trades_df['entry_timestamp'] >= crash_start) & (trades_df['entry_timestamp'] <= crash_end)) |
    ((trades_df['exit_timestamp'] >= crash_start) & (trades_df['exit_timestamp'] <= crash_end))
]

if len(crash_trades) > 0:
    print(f"暴跌期间交易: {len(crash_trades)} 笔")
    
    # 分析持仓时间
    holding_periods = crash_trades['holding_period'].values
    print(f"平均持仓时间: {holding_periods.mean():.2f} 小时")
    print(f"最短持仓: {holding_periods.min():.2f} 小时")
    print(f"最长持仓: {holding_periods.max():.2f} 小时")
    print()
    
    # 分析盈亏分布
    winning = crash_trades[crash_trades['pnl'] > 0]
    losing = crash_trades[crash_trades['pnl'] < 0]
    
    print(f"盈利交易: {len(winning)} 笔, 平均盈利: ${winning['pnl'].mean():.2f}")
    print(f"亏损交易: {len(losing)} 笔, 平均亏损: ${losing['pnl'].mean():.2f}")
    print()
    
    print("关键发现:")
    print("  网格策略通过频繁交易，快速了结盈利，限制单笔亏损")
    print()

# 5. 关键抗跌因素总结
print("5. 560x杠杆下最大回撤11.37%的可能原因")
print("-" * 80)
print()
print("因素1: 持仓管理")
print("  - 网格策略不是满仓持有，而是动态调整持仓")
print("  - 在价格下跌时，可能因为卖出订单触发而减少持仓")
print("  - 持仓减少 = 风险敞口减小 = 回撤可控")
print()
print("因素2: 快速获利了结")
print("  - 网格策略频繁交易，盈利单快速了结")
print("  - 亏损单可能因为网格配对而及时平仓")
print("  - 避免单笔大亏损累积")
print()
print("因素3: 价格区间控制")
print("  - 如果价格在S/R范围内，网格继续运行")
print("  - 只有在极端价格时才可能触发风控")
print("  - 10.10-10.11期间价格可能在可交易范围内")
print()
print("因素4: 网格配对机制")
print("  - 买入后很快有对应的卖出配对")
print("  - 避免持仓过久暴露在市场风险中")
print("  - 即使在下跌中，网格仍在运行，配对交易减少了风险暴露")
print()
print("因素5: 仓位权重")
print("  - 可能使用了非均匀仓位权重（weight_k）")
print("  - 在价格边界区域仓位较小，中心区域仓位较大")
print("  - 如果暴跌发生在边界，实际风险敞口可能较小")
print()

print("=" * 80)

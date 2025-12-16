"""分析10.10-10.11暴跌期间的表现"""
import pandas as pd
from pathlib import Path

results_dir = Path("run/results_lean_taogrid")
equity_file = results_dir / "equity_curve.csv"
orders_file = results_dir / "orders.csv"
trades_file = results_dir / "trades.csv"

print("=" * 80)
print("10.10-10.11暴跌期间表现分析")
print("=" * 80)
print()

# 读取权益曲线
equity_df = pd.read_csv(equity_file)
equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'])
print(f"权益曲线时间范围: {equity_df['timestamp'].min()} 至 {equity_df['timestamp'].max()}")
print(f"总数据点: {len(equity_df)}")
print()

# 定义暴跌时间段
crash_start = pd.Timestamp("2025-10-10 00:00:00", tz='UTC')
crash_end = pd.Timestamp("2025-10-11 23:59:59", tz='UTC')

# 获取暴跌前后的数据点
before_crash = equity_df[equity_df['timestamp'] < crash_start]
during_crash = equity_df[
    (equity_df['timestamp'] >= crash_start) & 
    (equity_df['timestamp'] <= crash_end)
]
after_crash = equity_df[equity_df['timestamp'] > crash_end]

print(f"暴跌前数据点: {len(before_crash)}")
print(f"暴跌期间数据点: {len(during_crash)}")
print(f"暴跌后数据点: {len(after_crash)}")
print()

if len(before_crash) > 0 and len(during_crash) > 0:
    # 找到暴跌前的峰值
    peak_equity = before_crash['equity'].max()
    peak_time = before_crash[before_crash['equity'] == peak_equity].iloc[0]['timestamp']
    
    # 找到暴跌期间的最低点
    crash_min_equity = during_crash['equity'].min()
    crash_min_time = during_crash[during_crash['equity'] == crash_min_equity].iloc[0]['timestamp']
    
    # 计算最大回撤
    max_dd = (crash_min_equity - peak_equity) / peak_equity * 100
    
    print(f"峰值权益: ${peak_equity:,.2f} (时间: {peak_time})")
    print(f"暴跌期间最低权益: ${crash_min_equity:,.2f} (时间: {crash_min_time})")
    print(f"最大回撤: {max_dd:.2f}%")
    print()
    
    # 查看暴跌期间的持仓
    if 'holdings' in during_crash.columns:
        crash_holdings = during_crash['holdings'].values
        print(f"暴跌期间持仓:")
        print(f"  初始持仓: {crash_holdings[0]:.4f} BTC")
        print(f"  最低点持仓: {during_crash[during_crash['equity'] == crash_min_equity]['holdings'].iloc[0]:.4f} BTC")
        print(f"  平均持仓: {crash_holdings.mean():.4f} BTC")
        print()

# 读取订单数据
if orders_file.exists():
    orders_df = pd.read_csv(orders_file)
    orders_df['timestamp'] = pd.to_datetime(orders_df['timestamp'])
    
    crash_orders = orders_df[
        (orders_df['timestamp'] >= crash_start) & 
        (orders_df['timestamp'] <= crash_end)
    ]
    
    print(f"暴跌期间订单: {len(crash_orders)} 笔")
    if len(crash_orders) > 0:
        print(f"  买入: {len(crash_orders[crash_orders['direction'] == 'buy'])} 笔")
        print(f"  卖出: {len(crash_orders[crash_orders['direction'] == 'sell'])} 笔")
        print()
        
        # 查看价格
        if 'market_price' in crash_orders.columns:
            prices = crash_orders['market_price'].dropna()
            print(f"价格信息:")
            print(f"  最低价: ${prices.min():,.2f}")
            print(f"  最高价: ${prices.max():,.2f}")
            print(f"  价格跌幅: {((prices.min() - prices.max()) / prices.max() * 100):.2f}%")
            print()

print("=" * 80)

"""分析10.10-10.11暴跌期间的表现 - 560x杠杆下的风险控制"""
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

# 读取数据
results_dir = Path("run/results_lean_taogrid")
orders_file = results_dir / "orders.csv"
equity_file = results_dir / "equity_curve.csv"
trades_file = results_dir / "trades.csv"

if not orders_file.exists():
    # 尝试其他可能的结果目录
    results_dir = Path("run/results_lean_taogrid_stress_test_2025_09_26_v2")
    orders_file = results_dir / "orders.csv"
    equity_file = results_dir / "equity_curve.csv"
    trades_file = results_dir / "trades.csv"

print("=" * 80)
print("10.10-10.11暴跌期间分析 - 高杠杆风险控制")
print("=" * 80)
print(f"结果目录: {results_dir}")
print()

# 读取订单
if orders_file.exists():
    orders_df = pd.read_csv(orders_file)
    orders_df['timestamp'] = pd.to_datetime(orders_df['timestamp'])
    print(f"订单数据: {len(orders_df)} 笔")
else:
    print(f"未找到订单文件: {orders_file}")
    orders_df = pd.DataFrame()

# 读取权益曲线
if equity_file.exists():
    equity_df = pd.read_csv(equity_file)
    equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'])
    print(f"权益曲线: {len(equity_df)} 个数据点")
else:
    print(f"未找到权益曲线文件: {equity_file}")
    equity_df = pd.DataFrame()

# 读取交易
if trades_file.exists():
    trades_df = pd.read_csv(trades_file)
    trades_df['entry_timestamp'] = pd.to_datetime(trades_df['entry_timestamp'])
    trades_df['exit_timestamp'] = pd.to_datetime(trades_df['exit_timestamp'])
    print(f"交易记录: {len(trades_df)} 笔")
else:
    print(f"未找到交易文件: {trades_file}")
    trades_df = pd.DataFrame()

print()

# 筛选10.10-10.11期间的数据
crash_start = pd.Timestamp("2025-10-10 00:00:00", tz='UTC')
crash_end = pd.Timestamp("2025-10-11 23:59:59", tz='UTC')

print(f"暴跌期间: {crash_start} 至 {crash_end}")
print()

# 分析权益曲线
if not equity_df.empty:
    crash_equity = equity_df[
        (equity_df['timestamp'] >= crash_start) & 
        (equity_df['timestamp'] <= crash_end)
    ].copy()
    
    if len(crash_equity) > 0:
        initial_equity = crash_equity.iloc[0]['equity']
        final_equity = crash_equity.iloc[-1]['equity']
        min_equity = crash_equity['equity'].min()
        max_equity = crash_equity['equity'].max()
        
        # 计算最大回撤
        peak = equity_df[equity_df['timestamp'] <= crash_start]['equity'].max() if len(equity_df[equity_df['timestamp'] <= crash_start]) > 0 else initial_equity
        max_dd_during_crash = (min_equity - peak) / peak if peak > 0 else 0
        
        print("权益变化 (10.10-10.11):")
        print(f"  期初权益: ${initial_equity:,.2f}")
        print(f"  期末权益: ${final_equity:,.2f}")
        print(f"  最低权益: ${min_equity:,.2f}")
        print(f"  最高权益: ${max_equity:,.2f}")
        print(f"  期间盈亏: ${final_equity - initial_equity:,.2f} ({(final_equity - initial_equity) / initial_equity * 100:.2f}%)")
        print(f"  从峰值回撤: ${min_equity - peak:,.2f} ({max_dd_during_crash * 100:.2f}%)")
        print()
        
        # 查找最低点的时间
        min_equity_row = crash_equity[crash_equity['equity'] == min_equity].iloc[0]
        print(f"  最低点时间: {min_equity_row['timestamp']}")
        print(f"  最低点持仓: {min_equity_row.get('holdings', 'N/A')}")
        print()

# 分析订单
if not orders_df.empty:
    crash_orders = orders_df[
        (orders_df['timestamp'] >= crash_start) & 
        (orders_df['timestamp'] <= crash_end)
    ].copy()
    
    print(f"暴跌期间订单: {len(crash_orders)} 笔")
    
    if len(crash_orders) > 0:
        buy_orders = crash_orders[crash_orders['direction'] == 'buy']
        sell_orders = crash_orders[crash_orders['direction'] == 'sell']
        
        print(f"  买入: {len(buy_orders)} 笔")
        print(f"  卖出: {len(sell_orders)} 笔")
        print()
        
        # 查看价格范围
        if 'market_price' in crash_orders.columns:
            prices = crash_orders['market_price'].dropna()
            if len(prices) > 0:
                print(f"价格范围:")
                print(f"  最低价: ${prices.min():,.2f}")
                print(f"  最高价: ${prices.max():,.2f}")
                print(f"  价格变化: ${(prices.max() - prices.min()):,.2f} ({(prices.max() - prices.min()) / prices.min() * 100:.2f}%)")
                print()

# 分析交易
if not trades_df.empty:
    crash_trades = trades_df[
        (trades_df['entry_timestamp'] >= crash_start) | 
        (trades_df['exit_timestamp'] >= crash_start)
    ].copy()
    crash_trades = crash_trades[
        (crash_trades['entry_timestamp'] <= crash_end) | 
        (crash_trades['exit_timestamp'] <= crash_end)
    ]
    
    print(f"暴跌期间交易: {len(crash_trades)} 笔")
    
    if len(crash_trades) > 0:
        winning = crash_trades[crash_trades['pnl'] > 0]
        losing = crash_trades[crash_trades['pnl'] < 0]
        
        print(f"  盈利交易: {len(winning)} 笔")
        print(f"  亏损交易: {len(losing)} 笔")
        if len(crash_trades) > 0:
            print(f"  胜率: {len(winning) / len(crash_trades) * 100:.1f}%")
        print(f"  总盈亏: ${crash_trades['pnl'].sum():,.2f}")
        print()

# 分析持仓变化
if not equity_df.empty:
    # 查看暴跌前后的持仓
    before_crash = equity_df[equity_df['timestamp'] < crash_start].iloc[-1] if len(equity_df[equity_df['timestamp'] < crash_start]) > 0 else None
    after_crash = equity_df[equity_df['timestamp'] > crash_end].iloc[0] if len(equity_df[equity_df['timestamp'] > crash_end]) > 0 else None
    
    if before_crash is not None and 'holdings' in before_crash:
        print("持仓变化:")
        print(f"  暴跌前持仓: {before_crash['holdings']:.4f} BTC")
        if after_crash is not None and 'holdings' in after_crash:
            print(f"  暴跌后持仓: {after_crash['holdings']:.4f} BTC")
            print(f"  持仓变化: {after_crash['holdings'] - before_crash['holdings']:.4f} BTC")
        print()

print("=" * 80)

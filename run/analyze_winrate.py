"""
分析 winrate 为什么是 100% 的问题
"""
import pandas as pd
from pathlib import Path

# 读取数据
results_dir = Path(__file__).parent.parent / "run" / "results"
trades_file = results_dir / "SR Short 4H_BTCUSDT_15m_trades.csv"
orders_file = results_dir / "SR Short 4H_BTCUSDT_15m_orders.csv"

trades = pd.read_csv(trades_file)
orders = pd.read_csv(orders_file)

print("=" * 60)
print("TRADES ANALYSIS")
print("=" * 60)
print(f"Total trades: {len(trades)}")
print(f"Positive returns: {(trades['return_pct'] > 0).sum()}")
print(f"Negative returns: {(trades['return_pct'] < 0).sum()}")
print(f"Zero returns: {(trades['return_pct'] == 0).sum()}")
print("\nAll trades:")
print(trades[['entry_time', 'exit_time', 'return_pct']].to_string())

print("\n" + "=" * 60)
print("ORDERS ANALYSIS")
print("=" * 60)
print(f"Total orders: {len(orders)}")
print(f"Entries: {(orders['order_type'] == 'ENTRY').sum()}")
print(f"TP1: {(orders['order_type'] == 'TP1').sum()}")
print(f"TP2: {(orders['order_type'] == 'TP2').sum()}")
print(f"SL: {(orders['order_type'] == 'SL').sum()}")

print("\nAll orders:")
print(orders[['timestamp', 'order_type', 'price', 'size', 'direction']].to_string())

print("\n" + "=" * 60)
print("CHECK SL TRADE")
print("=" * 60)
sl_orders = orders[orders['order_type'] == 'SL']
print(f"SL orders found: {len(sl_orders)}")
if len(sl_orders) > 0:
    print("\nSL order details:")
    print(sl_orders[['timestamp', 'price', 'size', 'direction']].to_string())
    
    # 检查 SL 是否在 trades 中
    sl_time = pd.to_datetime(sl_orders.iloc[0]['timestamp'])
    print(f"\nLooking for SL exit time: {sl_time}")
    
    # 尝试匹配
    trades['exit_time_parsed'] = pd.to_datetime(trades['exit_time'])
    matching = trades[trades['exit_time_parsed'] == sl_time]
    print(f"Matching trades: {len(matching)}")
    if len(matching) > 0:
        print("\nMatching trade:")
        print(matching[['entry_time', 'exit_time', 'return_pct']].to_string())
    else:
        print("\n⚠️  WARNING: SL order exists but no matching trade found!")
        print("This means the SL trade was not included in trades.csv")
        print("This is why winrate is 100% - the losing trade is missing!")

print("\n" + "=" * 60)
print("CHECK ENTRY-EXIT MATCHING")
print("=" * 60)
# 检查每个 entry 对应的 exits
for entry_time in orders[orders['order_type'] == 'ENTRY']['timestamp']:
    entry_time_parsed = pd.to_datetime(entry_time)
    print(f"\nEntry: {entry_time}")
    
    # 找到这个 entry 之后的所有 exits
    entry_orders = orders[orders['timestamp'] == entry_time]
    entry_size = entry_orders.iloc[0]['size']
    
    # 找到这个 entry 之后的所有 exits（直到下一个 entry）
    next_entry_idx = orders[(orders['order_type'] == 'ENTRY') & (orders['timestamp'] > entry_time)]
    if len(next_entry_idx) > 0:
        next_entry_time = pd.to_datetime(next_entry_idx.iloc[0]['timestamp'])
        exits = orders[
            (orders['order_type'].isin(['TP1', 'TP2', 'SL'])) &
            (pd.to_datetime(orders['timestamp']) > entry_time_parsed) &
            (pd.to_datetime(orders['timestamp']) < next_entry_time)
        ]
    else:
        exits = orders[
            (orders['order_type'].isin(['TP1', 'TP2', 'SL'])) &
            (pd.to_datetime(orders['timestamp']) > entry_time_parsed)
        ]
    
    print(f"  Entry size: {entry_size}")
    print(f"  Exits found: {len(exits)}")
    total_exit_size = exits['size'].sum()
    print(f"  Total exit size: {total_exit_size}")
    print(f"  Size match: {abs(entry_size - total_exit_size) < 0.01}")
    
    if len(exits) > 0:
        print("  Exit details:")
        for _, exit_order in exits.iterrows():
            exit_time_parsed = pd.to_datetime(exit_order['timestamp'])
            # 检查这个 exit 是否在 trades 中
            matching_trades = trades[trades['exit_time_parsed'] == exit_time_parsed]
            if len(matching_trades) > 0:
                print(f"    {exit_order['order_type']} at {exit_order['timestamp']}: "
                      f"size={exit_order['size']}, return={matching_trades.iloc[0]['return_pct']:.4f}")
            else:
                print(f"    {exit_order['order_type']} at {exit_order['timestamp']}: "
                      f"size={exit_order['size']} ⚠️ NOT IN TRADES")


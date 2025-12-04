"""
检查 SL 交易的计算是否正确
"""
import pandas as pd
from pathlib import Path

results_dir = Path(__file__).parent.parent / "run" / "results"
orders_file = results_dir / "SR Short 4H_BTCUSDT_15m_orders.csv"
trades_file = results_dir / "SR Short 4H_BTCUSDT_15m_trades.csv"

orders = pd.read_csv(orders_file)
trades = pd.read_csv(trades_file)

# 找到 SL 订单
sl_order = orders[orders['order_type'] == 'SL'].iloc[0]
print("=" * 60)
print("SL ORDER DETAILS")
print("=" * 60)
print(f"Timestamp: {sl_order['timestamp']}")
print(f"Price: {sl_order['price']}")
print(f"Size: {sl_order['size']}")
print(f"Direction: {sl_order['direction']}")

# 找到对应的 entry
entry_order = orders[
    (orders['order_type'] == 'ENTRY') &
    (pd.to_datetime(orders['timestamp']) < pd.to_datetime(sl_order['timestamp']))
].iloc[-1]  # 最后一个 entry（应该是对应的）

print("\n" + "=" * 60)
print("CORRESPONDING ENTRY")
print("=" * 60)
print(f"Timestamp: {entry_order['timestamp']}")
print(f"Price: {entry_order['price']}")
print(f"Size: {entry_order['size']}")
print(f"Direction: {entry_order['direction']}")

# 计算正确的 return（对于做空）
entry_price = entry_order['price']
exit_price = sl_order['price']
print("\n" + "=" * 60)
print("CALCULATION")
print("=" * 60)
print(f"Entry price (SHORT): {entry_price}")
print(f"Exit price (LONG to close): {exit_price}")
print(f"Price change: {exit_price - entry_price}")

# 对于做空：return = (entry_price - exit_price) / entry_price
correct_return = (entry_price - exit_price) / entry_price
print(f"\nCorrect return (for SHORT): {correct_return:.6f} ({correct_return*100:.2f}%)")

# 检查 trades.csv 中的记录
trades['exit_time_parsed'] = pd.to_datetime(trades['exit_time'])
sl_time = pd.to_datetime(sl_order['timestamp'])
matching_trade = trades[trades['exit_time_parsed'] == sl_time]

if len(matching_trade) > 0:
    print("\n" + "=" * 60)
    print("TRADES.CSV RECORD")
    print("=" * 60)
    trade = matching_trade.iloc[0]
    print(f"Entry time in trades.csv: {trade['entry_time']}")
    print(f"Exit time: {trade['exit_time']}")
    print(f"Return in trades.csv: {trade['return_pct']:.6f} ({trade['return_pct']*100:.2f}%)")
    
    print("\n" + "=" * 60)
    print("⚠️  PROBLEM DETECTED!")
    print("=" * 60)
    print(f"Correct return should be: {correct_return:.6f} ({correct_return*100:.2f}%)")
    print(f"Return in trades.csv is: {trade['return_pct']:.6f} ({trade['return_pct']*100:.2f}%)")
    
    if correct_return < 0 and trade['return_pct'] > 0:
        print("\n❌ ERROR: SL trade shows positive return but should be negative!")
        print("This is why winrate is 100% - the losing trade is counted as winning!")
        
        # 检查 entry_time 是否正确
        entry_time_parsed = pd.to_datetime(entry_order['timestamp'])
        trade_entry_time_parsed = pd.to_datetime(trade['entry_time'])
        
        if entry_time_parsed != trade_entry_time_parsed:
            print(f"\n⚠️  Entry time mismatch!")
            print(f"  Actual entry time: {entry_time_parsed}")
            print(f"  Entry time in trades.csv: {trade_entry_time_parsed}")
            print("  This suggests VectorBT merged trades incorrectly!")


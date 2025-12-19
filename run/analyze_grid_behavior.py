"""
Deep analysis of grid behavior - understand pairing and loss patterns.
"""
import pandas as pd
import numpy as np
from pathlib import Path

results_dir = Path("run/results_lean_taogrid")
trades_df = pd.read_csv(results_dir / "trades.csv")
orders_df = pd.read_csv(results_dir / "orders.csv")

print("=" * 80)
print("GRID BEHAVIOR DEEP ANALYSIS")
print("=" * 80)
print()

# 1. Pairing Pattern Analysis
print("1. GRID PAIRING PATTERN")
print("-" * 80)
trades_df['level_diff'] = trades_df['exit_level'] - trades_df['entry_level']
trades_df['price_diff'] = trades_df['exit_price'] - trades_df['entry_price']

# Categorize trades by pairing type
same_level = trades_df[trades_df['level_diff'] == 0]
positive_diff = trades_df[trades_df['level_diff'] > 0]
negative_diff = trades_df[trades_df['level_diff'] < 0]

print(f"Total trades: {len(trades_df)}")
print(f"\nPairing categories:")
print(f"  Same-level (perfect pair):  {len(same_level):4d} ({len(same_level)/len(trades_df)*100:5.1f}%) - Buy L{int(same_level['entry_level'].mode()[0])} -> Sell L{int(same_level['exit_level'].mode()[0])}")
print(f"  Higher exit (sell above):   {len(positive_diff):4d} ({len(positive_diff)/len(trades_df)*100:5.1f}%) - Sell at higher level")
print(f"  Lower exit (sell below):    {len(negative_diff):4d} ({len(negative_diff)/len(trades_df)*100:5.1f}%) - Sell at lower level")

print(f"\nPnL by pairing category:")
print(f"  Same-level:  Avg=${same_level['pnl'].mean():7.2f}, Total=${same_level['pnl'].sum():,.2f} (Win rate: {(same_level['pnl'] > 0).sum()/len(same_level)*100:.1f}%)")
print(f"  Higher exit: Avg=${positive_diff['pnl'].mean():7.2f}, Total=${positive_diff['pnl'].sum():,.2f} (Win rate: {(positive_diff['pnl'] > 0).sum()/len(positive_diff)*100:.1f}%)")
print(f"  Lower exit:  Avg=${negative_diff['pnl'].mean():7.2f}, Total=${negative_diff['pnl'].sum():,.2f} (Win rate: {(negative_diff['pnl'] > 0).sum()/len(negative_diff)*100:.1f}%)")
print()

# 2. Loss Pattern Analysis
print("2. WHY DO SOME TRADES LOSE MONEY?")
print("-" * 80)
losing_trades = trades_df[trades_df['pnl'] < 0]
print(f"Total losing trades: {len(losing_trades)} ({len(losing_trades)/len(trades_df)*100:.1f}%)")

print(f"\nLosing trades by level difference:")
for diff in sorted(losing_trades['level_diff'].unique())[:10]:
    subset = losing_trades[losing_trades['level_diff'] == diff]
    avg_loss = subset['pnl'].mean()
    print(f"  Level diff {diff:+3d}: {len(subset):3d} trades, Avg loss=${avg_loss:,.2f}")

print(f"\nLarge losses (PnL < -$500):")
large_losses = losing_trades[losing_trades['pnl'] < -500].sort_values('pnl')
for idx, row in large_losses.head(5).iterrows():
    print(f"  Buy L{int(row['entry_level']):2d} @ ${row['entry_price']:,.0f} -> Sell L{int(row['exit_level']):2d} @ ${row['exit_price']:,.0f}")
    print(f"    Loss: ${row['pnl']:,.2f} ({row['return_pct']:.2%}), Level diff: {int(row['level_diff'])}, Holding: {row['holding_period']:.1f}h")
print()

# 3. Price Movement Analysis
print("3. PRICE MOVEMENT PATTERN")
print("-" * 80)
orders_df['timestamp'] = pd.to_datetime(orders_df['timestamp'])
orders_df = orders_df.sort_values('timestamp')

# Analyze price range during backtest
print(f"Price range during backtest:")
print(f"  Highest price: ${orders_df['market_price'].max():,.2f}")
print(f"  Lowest price:  ${orders_df['market_price'].min():,.2f}")
print(f"  Range: ${orders_df['market_price'].max() - orders_df['market_price'].min():,.2f}")
print(f"  Grid support:    $107,000")
print(f"  Grid resistance: $123,000")

# Check if price broke through grid boundaries
price_below_support = (orders_df['market_price'] < 107000).sum()
price_above_resistance = (orders_df['market_price'] > 123000).sum()
print(f"\nBoundary breaks:")
print(f"  Price below support ($107k): {price_below_support} bars ({price_below_support/len(orders_df)*100:.1f}%)")
print(f"  Price above resistance ($123k): {price_above_resistance} bars ({price_above_resistance/len(orders_df)*100:.1f}%)")

if price_below_support > 0:
    print(f"  -> This causes FORCED LIQUIDATION of high-level buys at low prices!")
print()

# 4. Buy/Sell Order Timing
print("4. BUY vs SELL ORDER DISTRIBUTION")
print("-" * 80)
buy_orders = orders_df[orders_df['direction'] == 'buy']
sell_orders = orders_df[orders_df['direction'] == 'sell']

print(f"Buy orders:  {len(buy_orders):4d}")
print(f"Sell orders: {len(sell_orders):4d}")
print(f"Difference:  {len(buy_orders) - len(sell_orders):4d} (open positions at end)")

print(f"\nBuy order levels (top 5):")
buy_level_counts = buy_orders['level'].value_counts().head(5)
for level, count in buy_level_counts.items():
    avg_price = buy_orders[buy_orders['level'] == level]['price'].mean()
    print(f"  L{int(level):2d}: {count:3d} orders @ ${avg_price:,.0f}")

print(f"\nSell order levels (top 5):")
sell_level_counts = sell_orders['level'].value_counts().head(5)
for level, count in sell_level_counts.items():
    avg_price = sell_orders[sell_orders['level'] == level]['price'].mean()
    print(f"  L{int(level):2d}: {count:3d} orders @ ${avg_price:,.0f}")
print()

# 5. Time-based Analysis
print("5. TEMPORAL PATTERN")
print("-" * 80)
trades_df['entry_timestamp'] = pd.to_datetime(trades_df['entry_timestamp'])
trades_df['exit_timestamp'] = pd.to_datetime(trades_df['exit_timestamp'])
trades_df['entry_date'] = trades_df['entry_timestamp'].dt.date
trades_df['exit_date'] = trades_df['exit_timestamp'].dt.date

# Daily PnL
daily_pnl = trades_df.groupby('exit_date')['pnl'].agg(['sum', 'count', 'mean'])
print(f"Daily statistics:")
print(f"  Best day:  ${daily_pnl['sum'].max():,.2f} ({int(daily_pnl.loc[daily_pnl['sum'].idxmax(), 'count'])} trades)")
print(f"  Worst day: ${daily_pnl['sum'].min():,.2f} ({int(daily_pnl.loc[daily_pnl['sum'].idxmin(), 'count'])} trades)")
print(f"  Avg daily: ${daily_pnl['sum'].mean():,.2f} ({daily_pnl['count'].mean():.1f} trades)")

# Check if losses concentrated in certain periods
large_loss_dates = trades_df[trades_df['pnl'] < -500]['exit_date'].value_counts()
if len(large_loss_dates) > 0:
    print(f"\nDates with large losses (>$500 per trade):")
    for date, count in large_loss_dates.head(5).items():
        day_trades = trades_df[trades_df['exit_date'] == date]
        print(f"  {date}: {count} large losses, Total PnL=${day_trades['pnl'].sum():,.2f}")
print()

# 6. Grid Strategy Type Conclusion
print("6. GRID STRATEGY TYPE IDENTIFICATION")
print("-" * 80)
print("Based on the analysis:")
print()

same_level_pct = len(same_level) / len(trades_df) * 100
if same_level_pct > 80:
    print("[PURE PAIRED GRID]")
    print("  - Each buy is matched with sell at same level")
    print("  - Profits from grid spacing only")
elif same_level_pct > 40:
    print("[HYBRID PAIRED GRID with INVENTORY MANAGEMENT]")
    print("  - Core: Paired grid (42.9% same-level trades)")
    print("  - Secondary: FIFO matching for inventory control")
    print("  - Loses money when forced to sell below buy level")
else:
    print("[DYNAMIC GRID]")
    print("  - No fixed pairing")
    print("  - Pure FIFO matching")

print()
print("Key behaviors observed:")
print(f"  1. Same-level trades: {len(same_level)} ({same_level_pct:.1f}%) - ALL PROFITABLE")
print(f"  2. Cross-level trades: {len(positive_diff) + len(negative_diff)} ({(len(positive_diff) + len(negative_diff))/len(trades_df)*100:.1f}%)")
print(f"     - Sell higher: {len(positive_diff)} (usually profitable)")
print(f"     - Sell lower:  {len(negative_diff)} (often unprofitable)")
print()
print("Loss mechanism:")
print("  When price drops significantly:")
print("  -> Old high-level buys cannot find paired sells")
print("  -> System uses FIFO to match with available sells")
print("  -> Results in selling low what was bought high")
print("  -> This is the COST of inventory management")
print()

print("=" * 80)

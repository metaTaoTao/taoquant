"""Show actual grid structure with paired buy/sell prices."""
import pandas as pd

orders_df = pd.read_csv('run/results_lean_taogrid/orders.csv')

buy_orders = orders_df[orders_df['direction'] == 'buy']
sell_orders = orders_df[orders_df['direction'] == 'sell']

print("=" * 80)
print("ACTUAL GRID STRUCTURE (Paired Levels)")
print("=" * 80)
print()
print("Each level has a BUY price (trigger) and a SELL price (trigger):")
print()

# Show L28-L35 as examples (around the active trading area)
for level in range(28, 36):
    buy_at_level = buy_orders[buy_orders['level'] == level]
    sell_at_level = sell_orders[sell_orders['level'] == level]

    if len(buy_at_level) > 0 and len(sell_at_level) > 0:
        buy_price = buy_at_level['price'].iloc[0]
        sell_price = sell_at_level['price'].iloc[0]
        spread = sell_price - buy_price
        spread_pct = (spread / buy_price) * 100

        print(f"Level {level:2d}:")
        print(f"  BUY  trigger @ ${buy_price:10,.2f}")
        print(f"  SELL trigger @ ${sell_price:10,.2f}")
        print(f"  Grid spread:   ${spread:7.2f} ({spread_pct:.3f}%)")
        print()

print()
print("=" * 80)
print("HOW PAIRING WORKS")
print("=" * 80)
print()

# Find a specific paired trade
trades_df = pd.read_csv('run/results_lean_taogrid/trades.csv')
paired_trade = trades_df[(trades_df['entry_level'] == 33) & (trades_df['exit_level'] == 33)].iloc[0]

entry_level = int(paired_trade['entry_level'])
buy_trigger = buy_orders[buy_orders['level'] == entry_level]['price'].iloc[0]
sell_trigger = sell_orders[sell_orders['level'] == entry_level]['price'].iloc[0]

print(f"Example: Perfect Pair at Level {entry_level}")
print()
print("Step 1: Price drops to ${:.2f}".format(buy_trigger))
print(f"  -> Triggers BUY order at Level {entry_level}")
print(f"  -> Buy executed @ ${paired_trade['entry_price']:,.2f}")
print()
print("Step 2: Price rises to ${:.2f}".format(sell_trigger))
print(f"  -> Triggers SELL order at Level {entry_level}")
print(f"  -> Sell executed @ ${paired_trade['exit_price']:,.2f}")
print()
print(f"Result: Profit = ${paired_trade['pnl']:.2f}")
print()

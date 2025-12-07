"""
Verify PnL calculation from trades and orders.
"""

import pandas as pd

print("=" * 80)
print("PnL VERIFICATION")
print("=" * 80)

# Read trades and orders
trades = pd.read_csv("run/results/SR Short 4H_BTCUSDT_15m_trades.csv")
orders = pd.read_csv("run/results/SR Short 4H_BTCUSDT_15m_orders.csv")

print(f"\n[Orders Analysis]")
print(f"Total orders: {len(orders)}")
print("\nOrders breakdown:")
print(orders[['timestamp', 'price', 'size', 'direction', 'order_type']])

print(f"\n[Trades Analysis]")
print(f"Total trades: {len(trades)}")

# Calculate PnL manually from trades.csv
total_pnl_from_trades = trades['pnl'].sum()
print(f"\nTotal PnL (from trades.csv): ${total_pnl_from_trades:,.2f}")

# Calculate PnL manually from orders
print(f"\n[Manual PnL Calculation from Orders]")

# Find matching entry-exit pairs
entries = orders[orders['order_type'] == 'ENTRY'].copy()
exits = orders[orders['order_type'].isin(['SL', 'TP1', 'TP2'])].copy()

print(f"\nEntries: {len(entries)}")
print(f"Exits: {len(exits)}")

# Check for unmatched orders
print(f"\n[Order Matching Check]")
entry_sizes = entries['size'].sum()
exit_sizes = exits['size'].sum()
print(f"Total entry size: {entry_sizes:.4f} BTC")
print(f"Total exit size: {exit_sizes:.4f} BTC")
print(f"Difference: {abs(entry_sizes - exit_sizes):.4f} BTC")

if abs(entry_sizes - exit_sizes) > 0.001:
    print("\n[WARNING] Entry and exit sizes don't match!")
    print("This means there are unmatched positions (still open or incorrectly closed)")

# Reconstruct trades from orders
print(f"\n[Reconstructing Trades from Orders]")

reconstructed_pnl = 0.0
open_positions = []

for idx, order in orders.iterrows():
    if order['order_type'] == 'ENTRY':
        # Open new position
        open_positions.append({
            'entry_time': order['timestamp'],
            'entry_price': order['price'],
            'entry_size': order['size'],
            'remaining_size': order['size'],
        })
        print(f"\n[{order['timestamp']}] ENTRY: {order['size']:.4f} BTC @ ${order['price']:.2f}")

    elif order['order_type'] in ['SL', 'TP1', 'TP2']:
        # Close position (partial or full)
        if open_positions:
            pos = open_positions[-1]  # Get most recent position
            exit_size = order['size']

            # Calculate PnL for this exit
            # For short: PnL = (entry_price - exit_price) * size
            pnl = (pos['entry_price'] - order['price']) * exit_size
            reconstructed_pnl += pnl

            print(f"[{order['timestamp']}] {order['order_type']}: {exit_size:.4f} BTC @ ${order['price']:.2f}")
            print(f"  → PnL: ${pnl:,.2f}")

            # Update remaining size
            pos['remaining_size'] -= exit_size

            # If fully closed, remove position
            if pos['remaining_size'] < 0.001:
                open_positions.pop()
                print(f"  → Position fully closed")
            else:
                print(f"  → Remaining: {pos['remaining_size']:.4f} BTC")

print(f"\n[Summary]")
print(f"Total PnL (from trades.csv): ${total_pnl_from_trades:,.2f}")
print(f"Total PnL (reconstructed from orders): ${reconstructed_pnl:,.2f}")
print(f"Difference: ${abs(total_pnl_from_trades - reconstructed_pnl):.2f}")

if open_positions:
    print(f"\n[WARNING] {len(open_positions)} position(s) still open!")
    for pos in open_positions:
        print(f"  - Entry: {pos['entry_time']}, Size: {pos['remaining_size']:.4f} BTC @ ${pos['entry_price']:.2f}")

# Calculate return percentage
initial_capital = 100000
return_pct_from_pnl = (reconstructed_pnl / initial_capital) * 100

# Account for commission and slippage
commission_rate = 0.001  # 0.1%
slippage_rate = 0.0005  # 0.05%
total_friction = commission_rate + slippage_rate  # 0.15% per trade

# Calculate total commission/slippage cost
total_entries = len(entries)
total_exits = len(exits)
total_trades_count = total_entries + total_exits

# Estimate total notional value traded
total_entry_value = (entries['price'] * entries['size']).sum()
total_exit_value = (exits['price'] * exits['size']).sum()
total_notional = total_entry_value + total_exit_value

# Estimate friction cost
estimated_friction_cost = total_notional * total_friction
expected_return_with_friction = ((reconstructed_pnl - estimated_friction_cost) / initial_capital) * 100

print(f"\n[Return Calculation]")
print(f"Initial Capital: ${initial_capital:,.2f}")
print(f"Total PnL (price difference): ${reconstructed_pnl:,.2f}")
print(f"Estimated Commission/Slippage: ${estimated_friction_cost:,.2f}")
print(f"Expected Net PnL: ${reconstructed_pnl - estimated_friction_cost:,.2f}")

# Load actual metrics from file
import json
with open("run/results/SR Short 4H_BTCUSDT_15m_metrics.json", "r") as f:
    metrics = json.load(f)
reported_return_pct = metrics['total_return'] * 100

print(f"\nExpected Return (without friction): {return_pct_from_pnl:.2f}%")
print(f"Expected Return (with friction): {expected_return_with_friction:.2f}%")
print(f"Reported Return (from VectorBT): {reported_return_pct:.2f}%")
print(f"Discrepancy: {abs(expected_return_with_friction - reported_return_pct):.2f}%")

if abs(expected_return_with_friction - reported_return_pct) > 0.5:
    print("\n[DISCREPANCY DETECTED]")
    print(f"Expected: {expected_return_with_friction:.2f}%, Got: {reported_return_pct:.2f}%")
    print("This is likely due to rounding differences or VectorBT's calculation method.")
else:
    print("\n[OK] Returns match within acceptable tolerance (< 0.5%)")

print("\n" + "=" * 80)

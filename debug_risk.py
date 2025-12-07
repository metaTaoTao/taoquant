"""
Debug position sizing and risk calculation.
"""

import pandas as pd

# Read trades
trades = pd.read_csv("run/results/SR Short 4H_BTCUSDT_15m_trades.csv")

print("=" * 80)
print("RISK CALCULATION ANALYSIS")
print("=" * 80)

initial_capital = 100000
target_risk_pct = 0.5  # 0.5%
target_risk_amount = initial_capital * (target_risk_pct / 100)  # 500

print(f"\n[Configuration]")
print(f"  Initial Capital: ${initial_capital:,.2f}")
print(f"  Target Risk: {target_risk_pct}% = ${target_risk_amount:,.2f}")
print(f"  Leverage: 5x")

print(f"\n[Trade Analysis]")
for idx, trade in trades.iterrows():
    entry_price = trade['entry_price']
    exit_price = trade['exit_price']
    size = trade['size']  # BTC
    pnl = trade['pnl']

    # Calculate price movement
    price_move = abs(exit_price - entry_price)

    # Calculate actual risk (what position size SHOULD have been for $500 risk)
    theoretical_size = target_risk_amount / price_move

    # Calculate actual risk
    actual_risk = abs(pnl)
    actual_risk_pct = (actual_risk / initial_capital) * 100

    # Calculate size multiplier
    size_multiplier = size / theoretical_size if theoretical_size > 0 else 0

    print(f"\n  Trade #{idx + 1}:")
    print(f"    Entry: ${entry_price:,.2f}")
    print(f"    Exit: ${exit_price:,.2f}")
    print(f"    Price Move: ${price_move:,.2f}")
    print(f"    ---")
    print(f"    Theoretical Size (for $500 risk): {theoretical_size:.4f} BTC")
    print(f"    Actual Size: {size:.4f} BTC")
    print(f"    Size Multiplier: {size_multiplier:.2f}x")
    print(f"    ---")
    print(f"    Target Risk: ${target_risk_amount:,.2f} ({target_risk_pct}%)")
    print(f"    Actual Risk: ${actual_risk:,.2f} ({actual_risk_pct:.2f}%)")
    print(f"    Risk Multiplier: {actual_risk / target_risk_amount:.2f}x")

print("\n" + "=" * 80)
print("DIAGNOSIS")
print("=" * 80)

avg_size_multiplier = trades.apply(
    lambda row: (row['size'] / (target_risk_amount / abs(row['exit_price'] - row['entry_price']))),
    axis=1
).mean()

avg_risk_multiplier = trades.apply(
    lambda row: (abs(row['pnl']) / target_risk_amount),
    axis=1
).mean()

print(f"\nAverage Size Multiplier: {avg_size_multiplier:.2f}x")
print(f"Average Risk Multiplier: {avg_risk_multiplier:.2f}x")

print("\nPROBLEM:")
print("  Position sizes are being multiplied by leverage (5x),")
print("  which also multiplies the risk by 5x!")
print("\nCURRENT BEHAVIOR:")
print("  - Target risk: 0.5% = $500")
print("  - Leverage applied: 5x")
print("  - Actual risk: ~2.5% = $2,500 (5x the target)")
print("\nEXPECTED BEHAVIOR:")
print("  - Target risk: 0.5% = $500")
print("  - Leverage should NOT increase risk")
print("  - Actual risk should be: 0.5% = $500")
print("\nSOLUTION:")
print("  Remove leverage from position size calculation.")
print("  Leverage only affects margin requirement, not position size.")

print("\n" + "=" * 80)

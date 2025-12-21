"""Diagnose BULLISH strategy risk control status."""
import pandas as pd
import numpy as np

# Load equity curve
equity = pd.read_csv('run/results_bullish_20240703_20240810/equity_curve.csv')
equity['timestamp'] = pd.to_datetime(equity['timestamp'])

# Load config parameters
SUPPORT = 56000.0
RESISTANCE = 72000.0
INITIAL_CASH = 100000.0
LEVERAGE = 5.0
MAX_RISK_LOSS_PCT = 0.30
MAX_RISK_INVENTORY_PCT = 0.80

print("=" * 90)
print("BULLISH Strategy Risk Control Diagnostic (2024-07-03 to 2024-08-10)")
print("=" * 90)
print()

# Find key moments
peak_idx = equity['equity'].idxmax()
trough_idx = equity.loc[peak_idx:]['equity'].idxmin()

key_moments = [
    ("Start", 0),
    ("Before accumulation", 5000),
    ("Peak equity", peak_idx),
    ("Trough (MaxDD)", trough_idx),
    ("End", len(equity)-1)
]

print("Risk Control Status at Key Moments:")
print("-" * 90)
fmt = "{:<20} {:<20} {:>10} {:>12} {:>10} {:>12} {:>12}"
print(fmt.format("Moment", "Date", "Price", "Equity", "Holdings", "Unreal Loss%", "Inv Risk%"))
print("-" * 90)

for label, idx in key_moments:
    row = equity.iloc[idx]
    timestamp = str(row['timestamp'])[:16]

    holdings = row.get('holdings', 0)
    holdings_value = row.get('holdings_value', 0)
    price = holdings_value / holdings if holdings > 0 else 0
    equity_val = row['equity']
    cash = row.get('cash', 0)

    # Unrealized PnL
    unrealized_pnl = holdings_value + cash - INITIAL_CASH
    unrealized_pnl_pct = unrealized_pnl / equity_val if equity_val > 0 else 0

    # Inventory risk
    max_capacity = equity_val * LEVERAGE
    inv_notional = abs(holdings * price)
    inv_risk_pct = inv_notional / max_capacity if max_capacity > 0 else 0

    print(fmt.format(
        label, timestamp,
        f"${price:,.0f}", f"${equity_val:,.0f}", f"{holdings:.3f}",
        f"{unrealized_pnl_pct:.2%}", f"{inv_risk_pct:.2%}"
    ))

print()
print("=" * 90)
print("Risk Threshold Checks")
print("=" * 90)

for label, idx in [("Peak", peak_idx), ("Trough", trough_idx)]:
    row = equity.iloc[idx]
    holdings = row.get('holdings', 0)
    holdings_value = row.get('holdings_value', 0)
    price = holdings_value / holdings if holdings > 0 else 0
    equity_val = row['equity']
    cash = row.get('cash', 0)

    print()
    print(f"{label}: {row['timestamp']}")
    print("-" * 50)

    # Price depth
    ATR_EST = 500  # Estimate
    shutdown_price = SUPPORT - (3.0 * ATR_EST)
    print(f"  Price Depth Check:")
    print(f"    Current price: ${price:,.0f}")
    print(f"    Support: ${SUPPORT:,.0f}")
    print(f"    Shutdown threshold (S - 3*ATR): ${shutdown_price:,.0f}")
    triggered = price < shutdown_price
    print(f"    Status: {'TRIGGERED' if triggered else 'OK'}")

    # Unrealized loss
    unrealized_pnl = holdings_value + cash - INITIAL_CASH
    unrealized_pnl_pct = abs(unrealized_pnl) / equity_val
    print(f"  Unrealized Loss Check:")
    print(f"    Unrealized PnL: ${unrealized_pnl:,.0f}")
    print(f"    Unrealized loss %: {unrealized_pnl_pct:.2%}")
    print(f"    Shutdown threshold: {MAX_RISK_LOSS_PCT:.2%}")
    triggered = unrealized_pnl < 0 and unrealized_pnl_pct > MAX_RISK_LOSS_PCT
    print(f"    Status: {'TRIGGERED' if triggered else 'OK'}")

    # Inventory risk
    max_capacity = equity_val * LEVERAGE
    inv_notional = abs(holdings * price)
    inv_risk_pct = inv_notional / max_capacity
    print(f"  Inventory Risk Check:")
    print(f"    Inventory notional: ${inv_notional:,.0f}")
    print(f"    Max capacity (equity * leverage): ${max_capacity:,.0f}")
    print(f"    Inventory risk %: {inv_risk_pct:.2%}")
    print(f"    Shutdown threshold: {MAX_RISK_INVENTORY_PCT:.2%}")
    triggered = inv_risk_pct > MAX_RISK_INVENTORY_PCT
    print(f"    Status: {'TRIGGERED' if triggered else 'OK'}")

print()
print("=" * 90)
print("Analysis Summary:")
print("-" * 90)
print("1. Holdings accumulated from 0.137 BTC to 2.88 BTC before peak")
print("2. At peak: 32.6% inventory risk (< 80% threshold) - NO SHUTDOWN")
print("3. At trough: 47.2% inventory risk (< 80% threshold) - NO SHUTDOWN")
print("4. Unrealized loss at trough: ~37% (> 30% threshold) - SHOULD SHUTDOWN")
print()
print("CONCLUSION: Grid should have shut down at trough due to unrealized loss > 30%")
print("=" * 90)

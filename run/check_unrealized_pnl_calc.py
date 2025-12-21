"""Check how unrealized PnL is calculated vs wind-down threshold."""
import pandas as pd

equity = pd.read_csv('run/results_bullish_20240703_20240810/equity_curve.csv')
equity['timestamp'] = pd.to_datetime(equity['timestamp'])

# Config
INITIAL_CASH = 100000.0
MAX_RISK_LOSS_PCT = 0.30

# At trough
trough_idx = equity['equity'].idxmin()
trough = equity.iloc[trough_idx]

print("=" * 80)
print("Unrealized PnL Calculation Check at Trough")
print("=" * 80)
print()
print(f"Timestamp: {trough['timestamp']}")
print(f"Price: ${trough.get('holdings_value', 0) / trough.get('holdings', 1):,.0f}")
print()

# Method 1: SimpleLeanRunner's calculation (line 409)
# unrealized_pnl = (long_value - cost_basis) + (short_entry_value - short_value)
holdings = trough['holdings']
holdings_value = trough.get('holdings_value', 0)
cash = trough['cash']
equity_val = trough['equity']

# Assume all holdings are long, no shorts
long_value = holdings_value
# cost_basis estimation: cash changed from initial
# equity = cash + holdings_value
# Initial: cash = $100K, holdings = 0
# Current: cash = negative (borrowed), holdings = positive
# cost_basis = ???

# Try to reverse engineer from equity curve
# equity = cash + holdings_value
#  initial_cash = 100000
#  net_cash_spent = initial_cash - current_cash
net_cash_spent = INITIAL_CASH - cash

print(f"Method 1: Based on SimpleLeanRunner logic")
print(f"  Holdings value: ${holdings_value:,.0f}")
print(f"  Cash: ${cash:,.0f}")
print(f"  Net cash spent: ${net_cash_spent:,.0f}")
print(f"  Estimated cost basis: ~${net_cash_spent:,.0f}")
print(f"  Unrealized PnL = holdings_value - cost_basis")
print(f"                 = ${holdings_value:,.0f} - ${net_cash_spent:,.0f}")
unrealized_pnl_method1 = holdings_value - net_cash_spent
print(f"                 = ${unrealized_pnl_method1:,.0f}")
print(f"  Unrealized PnL % of equity: {unrealized_pnl_method1 / equity_val:.2%}")
print()

# Method 2: Total return based
total_return = (equity_val - INITIAL_CASH)
print(f"Method 2: Total return method")
print(f"  Total return: ${total_return:,.0f} ({total_return / INITIAL_CASH:.2%})")
print()

# Method 3: My diagnostic method
# unrealized_pnl = holdings_value + cash - initial_cash
unrealized_pnl_method3 = holdings_value + cash - INITIAL_CASH
print(f"Method 3: My diagnostic method")
print(f"  Unrealized PnL = ${unrealized_pnl_method3:,.0f}")
print(f"  Unrealized PnL % of equity: {abs(unrealized_pnl_method3) / equity_val:.2%}")
print()

# Check threshold
print("=" * 80)
print("Threshold Check")
print("=" * 80)
print(f"Max risk loss threshold: {MAX_RISK_LOSS_PCT:.0%}")
print()

for method_name, unreal_pnl in [
    ("Method 1 (SimpleLeanRunner)", unrealized_pnl_method1),
    ("Method 3 (Diagnostic)", unrealized_pnl_method3),
]:
    pct = abs(unreal_pnl) / equity_val
    triggered = unreal_pnl < 0 and pct > MAX_RISK_LOSS_PCT
    print(f"{method_name:30s}: ${unreal_pnl:>10,.0f} ({pct:>6.2%}) - {'TRIGGERED' if triggered else 'OK'}")

print()
print("=" * 80)
print("CONCLUSION:")
if unrealized_pnl_method1 > -MAX_RISK_LOSS_PCT * equity_val:
    print("If SimpleLeanRunner uses Method 1, the shutdown threshold was NOT triggered")
    print(f"because unrealized PnL ${unrealized_pnl_method1:,.0f} > threshold ${-MAX_RISK_LOSS_PCT * equity_val:,.0f}")
else:
    print("The threshold SHOULD have been triggered")
print("=" * 80)

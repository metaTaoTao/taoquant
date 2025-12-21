"""诊断BULLISH策略在2024-07期间的风控状态."""
import pandas as pd
import numpy as np

# Load equity curve
equity = pd.read_csv('run/results_bullish_20240703_20240810/equity_curve.csv')
equity['timestamp'] = pd.to_datetime(equity['timestamp'])

# Load config parameters (from base config)
SUPPORT = 56000.0
RESISTANCE = 72000.0
INITIAL_CASH = 100000.0
LEVERAGE = 5.0
MAX_RISK_LOSS_PCT = 0.30  # 30% threshold
MAX_RISK_INVENTORY_PCT = 0.80  # 80% threshold

print("=" * 80)
print("BULLISH策略风控状态诊断 (2024-07-03 to 2024-08-10)")
print("=" * 80)
print()

# Find key moments
peak_idx = equity['equity'].idxmax()
trough_idx = equity.loc[peak_idx:]['equity'].idxmin()
end_idx = len(equity) - 1

key_moments = [
    ("初始状态", 0),
    ("累积开始前", 5000),
    ("峰值", peak_idx),
    ("谷底", trough_idx),
    ("结束", end_idx)
]

print("关键时刻风控检查：")
print("-" * 80)
print(f"{'时刻':<15} {'日期':<20} {'价格':<10} {'权益':<12} {'持仓':<10} {'未实现亏损%':<12} {'库存风险%':<12}")
print("-" * 80)

for label, idx in key_moments:
    row = equity.iloc[idx]
    timestamp = str(row['timestamp'])[:16]

    # Estimate price from holdings_value and holdings
    holdings = row.get('holdings', 0)
    holdings_value = row.get('holdings_value', 0)
    price = holdings_value / holdings if holdings > 0 else 0

    equity_val = row['equity']
    cash = row.get('cash', 0)

    # Calculate unrealized PnL percentage
    unrealized_pnl = equity_val - INITIAL_CASH - (equity_val - holdings_value - cash)
    unrealized_pnl_pct = unrealized_pnl / INITIAL_CASH if INITIAL_CASH > 0 else 0

    # Calculate inventory risk
    max_capacity = equity_val * LEVERAGE
    inv_notional = abs(holdings * price)
    inv_risk_pct = inv_notional / max_capacity if max_capacity > 0 else 0

    print(f"{label:<15} {timestamp:<20} ${price:<9,.0f} ${equity_val:<11,.0f} {holdings:<9.3f} {unrealized_pnl_pct:<11.2%} {inv_risk_pct:<11.2%}")

print()
print("=" * 80)
print("风控阈值检查")
print("=" * 80)

# Check at peak and trough
for label, idx in [("峰值", peak_idx), ("谷底", trough_idx)]:
    row = equity.iloc[idx]
    holdings = row.get('holdings', 0)
    holdings_value = row.get('holdings_value', 0)
    price = holdings_value / holdings if holdings > 0 else 0
    equity_val = row['equity']
    cash = row.get('cash', 0)

    print()
    print(f"{label} ({row['timestamp']})")
    print("-" * 40)

    # Price depth check
    shutdown_price = SUPPORT - (3.0 * 500)  # Estimate ATR ~500
    print(f"  价格深度检查:")
    print(f"    当前价格: ${price:,.0f}")
    print(f"    支撑线: ${SUPPORT:,.0f}")
    print(f"    关闭阈值 (S - 3×ATR): ${shutdown_price:,.0f}")
    print(f"    {'✓ 触发' if price < shutdown_price else '✗ 未触发'}")

    # Unrealized loss check
    unrealized_pnl = holdings_value + cash - INITIAL_CASH
    unrealized_pnl_pct = abs(unrealized_pnl) / equity_val
    adjusted_threshold = MAX_RISK_LOSS_PCT  # No profit buffer for simplicity
    print(f"  未实现亏损检查:")
    print(f"    未实现PnL: ${unrealized_pnl:,.0f}")
    print(f"    未实现亏损%: {unrealized_pnl_pct:.2%}")
    print(f"    关闭阈值: {adjusted_threshold:.2%}")
    print(f"    {'✓ 触发' if unrealized_pnl_pct > adjusted_threshold else '✗ 未触发'}")

    # Inventory risk check
    max_capacity = equity_val * LEVERAGE
    inv_notional = abs(holdings * price)
    inv_risk_pct = inv_notional / max_capacity
    print(f"  库存风险检查:")
    print(f"    库存名义值: ${inv_notional:,.0f}")
    print(f"    最大容量: ${max_capacity:,.0f}")
    print(f"    库存风险%: {inv_risk_pct:.2%}")
    print(f"    关闭阈值: {MAX_RISK_INVENTORY_PCT:.2%}")
    print(f"    {'✓ 触发' if inv_risk_pct > MAX_RISK_INVENTORY_PCT else '✗ 未触发'}")

print()
print("=" * 80)

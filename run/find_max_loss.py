"""Find maximum unrealized loss point in equity curve."""
import pandas as pd

df = pd.read_csv('run/results_bullish_20240703_20240810/equity_curve.csv')
df['timestamp'] = pd.to_datetime(df['timestamp'])

# Find min unrealized_pnl (most negative)
min_idx = df['unrealized_pnl'].idxmin()
min_row = df.loc[min_idx]

print('='*80)
print('MAXIMUM UNREALIZED LOSS POINT')
print('='*80)
print(f'Timestamp: {min_row["timestamp"]}')
print(f'Equity: ${min_row["equity"]:,.2f}')
print(f'Unrealized PnL: ${min_row["unrealized_pnl"]:,.2f}')
print(f'Unrealized PnL %: {min_row["unrealized_pnl"] / min_row["equity"]:.2%}')
print(f'Long holdings: {min_row["long_holdings"]:.4f} BTC')
print(f'Cost basis: ${min_row["cost_basis"]:,.2f}')
print(f'Grid enabled: {min_row["grid_enabled"]}')
print(f'Risk level: {int(min_row["risk_level"])}')
print()

# Check if risk control should have triggered
threshold = 0.30
profit_buffer_pct = 0.50
realized_profit = df['equity'].max() - 100000
profit_buffer = max(0, realized_profit * profit_buffer_pct)
adjusted_threshold = threshold + (profit_buffer / min_row['equity'])

print(f'Risk Control Threshold Check:')
print(f'  Base threshold: {threshold:.0%}')
print(f'  Peak equity: ${df["equity"].max():,.2f}')
print(f'  Realized profit: ${realized_profit:,.2f}')
print(f'  Profit buffer (50%): ${profit_buffer:,.2f}')
print(f'  Adjusted threshold: {adjusted_threshold:.2%}')
print(f'  Actual unrealized loss %: {abs(min_row["unrealized_pnl"]) / min_row["equity"]:.2%}')
print(f'  Should shutdown: {abs(min_row["unrealized_pnl"]) / min_row["equity"] > adjusted_threshold}')
print()

# Show 10 worst moments
print('Top 10 Worst Unrealized Loss Moments:')
print('-'*80)
worst = df.nsmallest(10, 'unrealized_pnl')[['timestamp','equity','unrealized_pnl','grid_enabled','risk_level']]
worst['unreal_pct'] = worst['unrealized_pnl'] / worst['equity']
print(worst.to_string(index=False))

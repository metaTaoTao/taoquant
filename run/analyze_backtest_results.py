"""
Analyze backtest results for order fill logic and potential issues.
"""
import pandas as pd
import numpy as np
from pathlib import Path

# Load results
results_dir = Path("run/results_lean_taogrid")
orders_df = pd.read_csv(results_dir / "orders.csv")
trades_df = pd.read_csv(results_dir / "trades.csv")
equity_df = pd.read_csv(results_dir / "equity_curve.csv")

print("=" * 80)
print("BACKTEST RESULTS ANALYSIS")
print("=" * 80)
print()

# 1. Order Statistics
print("1. ORDER STATISTICS")
print("-" * 80)
print(f"Total orders: {len(orders_df)}")
print(f"Buy orders: {(orders_df['direction'] == 'buy').sum()}")
print(f"Sell orders: {(orders_df['direction'] == 'sell').sum()}")
print()

# Check matched_trades distribution
if 'matched_trades' in orders_df.columns:
    print("Matched trades per sell order:")
    matched_counts = orders_df[orders_df['direction'] == 'sell']['matched_trades'].value_counts().sort_index()
    for count, freq in matched_counts.items():
        print(f"  {int(count)} matches: {freq} orders ({freq/len(orders_df)*100:.1f}%)")
    print()

# 2. Trade Statistics
print("2. TRADE STATISTICS")
print("-" * 80)
print(f"Total trades: {len(trades_df)}")
print(f"Winning trades: {(trades_df['pnl'] > 0).sum()} ({(trades_df['pnl'] > 0).sum()/len(trades_df)*100:.1f}%)")
print(f"Losing trades: {(trades_df['pnl'] < 0).sum()} ({(trades_df['pnl'] < 0).sum()/len(trades_df)*100:.1f}%)")
print()

# Check grid pairing: entry_level vs exit_level
print("Grid pairing analysis:")
trades_df['level_diff'] = trades_df['exit_level'] - trades_df['entry_level']
level_diff_counts = trades_df['level_diff'].value_counts().sort_index()
print("  Level difference distribution (exit_level - entry_level):")
for diff, count in level_diff_counts.head(10).items():
    print(f"    {int(diff):+3d} levels: {count:4d} trades ({count/len(trades_df)*100:5.1f}%)")
print()

# 3. PnL Analysis
print("3. PNL ANALYSIS")
print("-" * 80)
print(f"Total PnL: ${trades_df['pnl'].sum():,.2f}")
print(f"Average PnL per trade: ${trades_df['pnl'].mean():.2f}")
print(f"Median PnL per trade: ${trades_df['pnl'].median():.2f}")
print()

# Check for anomalies: large losses
large_losses = trades_df[trades_df['pnl'] < -500].sort_values('pnl')
if len(large_losses) > 0:
    print(f"WARNING: Found {len(large_losses)} trades with PnL < -$500:")
    for idx, row in large_losses.head(5).iterrows():
        print(f"  [{row['entry_timestamp']} -> {row['exit_timestamp']}] "
              f"L{int(row['entry_level'])} to L{int(row['exit_level'])}: "
              f"${row['pnl']:.2f} ({row['return_pct']:.2%})")
    print()

# 4. Return Analysis
print("4. RETURN ANALYSIS")
print("-" * 80)
print(f"Average return per trade: {trades_df['return_pct'].mean():.4%}")
print(f"Median return per trade: {trades_df['return_pct'].median():.4%}")
print()

# Check for negative return on same-level trades (should be impossible)
same_level_trades = trades_df[trades_df['level_diff'] == 0]
if len(same_level_trades) > 0:
    print(f"Same-level trades (entry_level == exit_level): {len(same_level_trades)}")
    negative_same_level = same_level_trades[same_level_trades['pnl'] < 0]
    if len(negative_same_level) > 0:
        print(f"  WARNING: {len(negative_same_level)} same-level trades with negative PnL!")
        for idx, row in negative_same_level.head(5).iterrows():
            print(f"    [{row['entry_timestamp']} -> {row['exit_timestamp']}] "
                  f"L{int(row['entry_level'])} to L{int(row['exit_level'])}: "
                  f"${row['pnl']:.2f} ({row['return_pct']:.4%})")
    else:
        print("  All same-level trades have positive PnL (expected)")
    print()

# 5. Holding Period Analysis
print("5. HOLDING PERIOD ANALYSIS")
print("-" * 80)
print(f"Average holding period: {trades_df['holding_period'].mean():.2f} hours")
print(f"Median holding period: {trades_df['holding_period'].median():.2f} hours")
print(f"Max holding period: {trades_df['holding_period'].max():.2f} hours")
print(f"Min holding period: {trades_df['holding_period'].min():.2f} hours")
print()

# 6. Level Distribution
print("6. GRID LEVEL DISTRIBUTION")
print("-" * 80)
print("Buy levels (entry):")
entry_levels = trades_df['entry_level'].value_counts().sort_index()
for level, count in entry_levels.head(10).items():
    print(f"  L{int(level)}: {count:4d} trades ({count/len(trades_df)*100:5.1f}%)")
print()

print("Sell levels (exit):")
exit_levels = trades_df['exit_level'].value_counts().sort_index()
for level, count in exit_levels.head(10).items():
    print(f"  L{int(level)}: {count:4d} trades ({count/len(trades_df)*100:5.1f}%)")
print()

# 7. Consistency Check: Orders vs Trades
print("7. CONSISTENCY CHECK")
print("-" * 80)
total_matched_from_orders = orders_df[orders_df['direction'] == 'sell']['matched_trades'].sum()
print(f"Total matched trades from orders.csv: {int(total_matched_from_orders)}")
print(f"Total trades in trades.csv: {len(trades_df)}")
if abs(total_matched_from_orders - len(trades_df)) < 5:
    print("✓ Orders and trades are consistent")
else:
    print(f"✗ WARNING: Mismatch of {abs(total_matched_from_orders - len(trades_df))} trades!")
print()

# 8. Equity Curve Analysis
print("8. EQUITY CURVE ANALYSIS")
print("-" * 80)
equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'])
initial_equity = equity_df['equity'].iloc[0]
final_equity = equity_df['equity'].iloc[-1]
max_equity = equity_df['equity'].max()
min_equity = equity_df['equity'].min()
print(f"Initial equity: ${initial_equity:,.2f}")
print(f"Final equity: ${final_equity:,.2f}")
print(f"Max equity: ${max_equity:,.2f}")
print(f"Min equity: ${min_equity:,.2f}")
print(f"Total return: {(final_equity - initial_equity) / initial_equity:.2%}")
print()

# Check for negative equity
negative_equity_count = (equity_df['equity'] < 0).sum()
if negative_equity_count > 0:
    print(f"WARNING: {negative_equity_count} bars with negative equity!")
    first_negative = equity_df[equity_df['equity'] < 0].iloc[0]
    print(f"  First occurrence: {first_negative['timestamp']} @ ${first_negative['equity']:,.2f}")
else:
    print("✓ No negative equity detected")
print()

print("=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)

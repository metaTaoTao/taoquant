"""Analyze trading patterns correctly."""
import pandas as pd

trades_df = pd.read_csv('run/results_lean_taogrid/trades.csv')
trades_df['level_diff'] = trades_df['exit_level'] - trades_df['entry_level']

# Three patterns
same = trades_df[trades_df['level_diff'] == 0]
negative_diff = trades_df[trades_df['level_diff'] < 0]  # Sell UP
positive_diff = trades_df[trades_df['level_diff'] > 0]  # Sell DOWN

print("=" * 80)
print("THREE TRADING PATTERNS")
print("=" * 80)
print()

print("Pattern 1: Same-level (Perfect Pair)")
print(f"  Level diff: 0")
print(f"  Count: {len(same)} ({len(same)/len(trades_df)*100:.1f}%)")
print(f"  Avg PnL: ${same['pnl'].mean():.2f}")
print(f"  Win rate: {(same['pnl'] > 0).sum()/len(same)*100:.1f}%")
print()

print("Pattern 2: Sell HIGHER (exit_level < entry_level)")
print(f"  Level diff: NEGATIVE (sell at higher price)")
print(f"  Count: {len(negative_diff)} ({len(negative_diff)/len(trades_df)*100:.1f}%)")
print(f"  Avg PnL: ${negative_diff['pnl'].mean():.2f}")
print(f"  Win rate: {(negative_diff['pnl'] > 0).sum()/len(negative_diff)*100:.1f}%")
print()

print("Pattern 3: Sell LOWER (exit_level > entry_level)")
print(f"  Level diff: POSITIVE (sell at lower price)")
print(f"  Count: {len(positive_diff)} ({len(positive_diff)/len(trades_df)*100:.1f}%)")
print(f"  Avg PnL: ${positive_diff['pnl'].mean():.2f}")
print(f"  Win rate: {(positive_diff['pnl'] > 0).sum()/len(positive_diff)*100:.1f}%")
print()

print("=" * 80)
print("REAL EXAMPLES")
print("=" * 80)
print()

print("Example 1: Same-level (Perfect Pair)")
ex1 = same[same['pnl'] > 90].iloc[0]
print(f"  Buy  L{int(ex1['entry_level']):2d} @ ${ex1['entry_price']:,.0f}")
print(f"  Sell L{int(ex1['exit_level']):2d} @ ${ex1['exit_price']:,.0f}")
print(f"  PnL: ${ex1['pnl']:.2f}, Return: {ex1['return_pct']:.2%}")
print(f"  Price diff: ${ex1['exit_price'] - ex1['entry_price']:,.0f}")
print()

print("Example 2: Sell HIGHER (Earn MORE)")
ex2 = negative_diff.nlargest(1, 'pnl').iloc[0]
print(f"  Buy  L{int(ex2['entry_level']):2d} @ ${ex2['entry_price']:,.0f}")
print(f"  Sell L{int(ex2['exit_level']):2d} @ ${ex2['exit_price']:,.0f}")
print(f"  Level diff: {int(ex2['level_diff'])}")
print(f"  PnL: ${ex2['pnl']:.2f}, Return: {ex2['return_pct']:.2%}")
print(f"  Price diff: ${ex2['exit_price'] - ex2['entry_price']:,.0f}")
print()

print("Example 3: Sell LOWER (Loss)")
ex3 = positive_diff.nsmallest(1, 'pnl').iloc[0]
print(f"  Buy  L{int(ex3['entry_level']):2d} @ ${ex3['entry_price']:,.0f}")
print(f"  Sell L{int(ex3['exit_level']):2d} @ ${ex3['exit_price']:,.0f}")
print(f"  Level diff: {int(ex3['level_diff'])}")
print(f"  PnL: ${ex3['pnl']:.2f}, Return: {ex3['return_pct']:.2%}")
print(f"  Price diff: ${ex3['exit_price'] - ex3['entry_price']:,.0f}")
print()

print("=" * 80)
print("UNDERSTANDING LEVEL NUMBERING")
print("=" * 80)
print()
print("KEY INSIGHT: Level number is INVERSE to price!")
print()
print("  L1  = HIGHEST price = Top of grid")
print("  L40 = LOWEST price  = Bottom of grid")
print()
print("Therefore:")
print("  exit_level < entry_level = Sell at HIGHER price = PROFIT")
print("  exit_level > entry_level = Sell at LOWER price  = LOSS")
print()

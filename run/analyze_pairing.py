import pandas as pd

# Load trades
trades = pd.read_csv('run/results_stage1_extended/trades.csv')

# Analyze pairing
correct_pairing = (trades['entry_level'] == trades['exit_level']).sum()
wrong_pairing = (trades['entry_level'] != trades['exit_level']).sum()
total_trades = len(trades)

print('=' * 80)
print('配对分析 (Pairing Analysis)')
print('=' * 80)
print(f'总交易数: {total_trades}')
print(f'正确配对 (entry_level == exit_level): {correct_pairing} ({correct_pairing/total_trades*100:.1f}%)')
print(f'错误配对 (entry_level != exit_level): {wrong_pairing} ({wrong_pairing/total_trades*100:.1f}%)')
print()

# Calculate average returns for each type
correct_returns = trades[trades['entry_level'] == trades['exit_level']]['return_pct']
wrong_returns = trades[trades['entry_level'] != trades['exit_level']]['return_pct']

print('平均回报率分析:')
print(f'  正确配对平均回报: {correct_returns.mean()*100:.4f}%')
if len(wrong_returns) > 0:
    print(f'  错误配对平均回报: {wrong_returns.mean()*100:.4f}%')
else:
    print('  错误配对平均回报: N/A')
print(f'  总体平均回报: {trades["return_pct"].mean()*100:.4f}%')
print()

# Show wrong pairing examples
if wrong_pairing > 0:
    print(f'错误配对示例 (前10个):')
    wrong_trades = trades[trades['entry_level'] != trades['exit_level']].head(10)
    for idx, row in wrong_trades.iterrows():
        print(f'  L{int(row["entry_level"])} -> L{int(row["exit_level"])}: return={row["return_pct"]*100:.2f}%, pnl=${row["pnl"]:.2f}')
    print()

    # Count level differences
    print('错误配对层级差异统计:')
    level_diff = trades[trades['entry_level'] != trades['exit_level']].copy()
    level_diff['diff'] = level_diff['exit_level'] - level_diff['entry_level']
    print(level_diff['diff'].value_counts().sort_index())

print('=' * 80)

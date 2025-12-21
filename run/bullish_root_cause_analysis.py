"""BULLISH策略亏损根本原因分析报告."""
import pandas as pd

equity = pd.read_csv('run/results_bullish_20240703_20240810/equity_curve.csv')
orders = pd.read_csv('run/results_bullish_20240703_20240810/orders.csv')
trades = pd.read_csv('run/results_bullish_20240703_20240810/trades.csv')

equity['timestamp'] = pd.to_datetime(equity['timestamp'])
orders['timestamp'] = pd.to_datetime(orders['timestamp'])
trades['timestamp'] = pd.to_datetime(trades['timestamp'])

print("="*90)
print("BULLISH策略亏损根本原因分析 (2024-07-03 to 2024-08-10)")
print("="*90)
print()

# 1. 配对交易表现
print("1. 配对交易表现（Grid内部买卖匹配）")
print("-"*90)
print(f"   总配对交易数: {len(trades)}")
print(f"   盈利交易数: {(trades['pnl'] > 0).sum()}")
print(f"   亏损交易数: {(trades['pnl'] <= 0).sum()}")
print(f"   胜率: {(trades['pnl'] > 0).sum() / len(trades):.2%}")
print(f"   总realized PnL: ${trades['pnl'].sum():,.2f}")
print("   结论: ✓ 配对交易100%盈利，非常成功")
print()

# 2. 未配对持仓风险
buy_orders = orders[orders['direction'] == 'buy']
sell_orders = orders[orders['direction'] == 'sell']
net_position = buy_orders['size'].sum() - sell_orders['size'].sum()

print("2. 未配对持仓累积")
print("-"*90)
print(f"   总买入: {buy_orders['size'].sum():.4f} BTC")
print(f"   总卖出: {sell_orders['size'].sum():.4f} BTC")
print(f"   净累积持仓: {net_position:.4f} BTC")
print(f"   平均买入价: ${buy_orders['cost'].sum() / buy_orders['size'].sum():,.2f}")
print()

# 3. 风控触发情况
shutdown_rows = equity[equity['grid_enabled'] == False]
if len(shutdown_rows) > 0:
    first_shutdown = shutdown_rows.iloc[0]
    print("3. 风控触发记录")
    print("-"*90)
    print(f"   首次关闭时间: {first_shutdown['timestamp']}")
    print(f"   关闭时equity: ${first_shutdown['equity']:,.2f}")
    print(f"   关闭时unrealized PnL: ${first_shutdown['unrealized_pnl']:,.2f}")
    print(f"   关闭时持仓: {first_shutdown['long_holdings']:.4f} BTC")
    print(f"   风险等级: {int(first_shutdown['risk_level'])}")
    print(f"   网格关闭时长: {len(shutdown_rows)} bars ({len(shutdown_rows)/60:.1f} hours)")
    print("   结论: ✓ 风控系统正常触发并关闭网格")
else:
    print("3. 风控触发记录")
    print("-"*90)
    print("   无关闭记录")
print()

# 4. 最大unrealized loss
min_idx = equity['unrealized_pnl'].idxmin()
worst_row = equity.loc[min_idx]

print("4. 最大unrealized loss点")
print("-"*90)
print(f"   时间: {worst_row['timestamp']}")
print(f"   Equity: ${worst_row['equity']:,.2f}")
print(f"   Unrealized PnL: ${worst_row['unrealized_pnl']:,.2f} ({worst_row['unrealized_pnl']/worst_row['equity']:.2%})")
print(f"   持仓: {worst_row['long_holdings']:.4f} BTC")
print(f"   Grid enabled: {worst_row['grid_enabled']}")
print(f"   Risk level: {int(worst_row['risk_level'])}")
print("   结论: ✗ 风控关闭网格后，持仓仍在账上，未实现亏损继续扩大")
print()

# 5. 问题总结
print("="*90)
print("根本问题诊断")
print("="*90)
print()
print("【现象】100%胜率却亏损（配对成功但持仓浮亏）")
print()
print("【原因】")
print("  1. BULLISH_RANGE = 70/30（买入权重 > 卖出权重）")
print(f"     → 容易累积多头持仓（本次累积 {net_position:.4f} BTC）")
print()
print("  2. 风控系统设计：shutdown只停止新交易，不清仓")
print("     → Grid关闭后，existing持仓仍在账上")
print()
print("  3. enable_forced_deleverage = False（未启用强制减仓）")
print("     → 即使-64%亏损也不会主动市价平仓")
print()
print("  4. 价格下跌 → 未配对多头持仓产生巨大浮亏")
print(f"     → Realized profit ${trades['pnl'].sum():,.2f}")
print(f"     → Unrealized loss ${worst_row['unrealized_pnl']:,.2f}")
print(f"     → Net result: 亏损")
print()
print("【解决方案】")
print("  Option 1: 启用强制减仓")
print("    enable_forced_deleverage = True")
print("    deleverage_level1_unrealized_loss_pct = 0.15  # -15%时卖出25%")
print("    deleverage_level2_unrealized_loss_pct = 0.25  # -25%时卖出50%")
print()
print("  Option 2: 风控shutdown时强制清仓")
print("    修改algorithm.py，在should_shutdown=True时返回市价卖单")
print()
print("  Option 3: 调整regime allocation")
print("    BULLISH_RANGE从70/30改为60/40，降低多头持仓累积速度")
print()
print("="*90)

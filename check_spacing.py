"""
检查当前TaoGrid的Spacing配置和计算结果
"""

# 当前配置参数
min_return = 0.005          # 0.5% - 目标净利润
maker_fee = 0.001           # 0.1% - 单边手续费
slippage = 0.0              # 0% - 限价单无滑点
spacing_multiplier = 1.0    # 标准倍数（不扩大不缩小）

# 计算
trading_costs = 2 * maker_fee + 2 * slippage
base_spacing = min_return + trading_costs
final_spacing = base_spacing * spacing_multiplier

# 在BTC=$117,000时的实际金额
btc_price = 117000
spacing_usd = btc_price * final_spacing

print("=" * 70)
print("TaoGrid Spacing 计算详情")
print("=" * 70)
print()

print("[Formula]")
print("  spacing = (min_return + 2×maker_fee + 2×slippage) × spacing_multiplier")
print()

print("[Parameters]")
print(f"  min_return         = {min_return:.3%}  (目标净利润)")
print(f"  maker_fee          = {maker_fee:.3%}   (单边手续费)")
print(f"  slippage           = {slippage:.3%}   (限价单无滑点)")
print(f"  spacing_multiplier = {spacing_multiplier:.1f}      (标准倍数)")
print()

print("[Calculation]")
print(f"  Step 1: trading_costs = 2×{maker_fee:.2%} + 2×{slippage:.2%}")
print(f"          = {trading_costs:.3%}")
print()
print(f"  Step 2: base_spacing = min_return + trading_costs")
print(f"          = {min_return:.3%} + {trading_costs:.3%}")
print(f"          = {base_spacing:.3%}")
print()
print(f"  Step 3: final_spacing = base_spacing × spacing_multiplier")
print(f"          = {base_spacing:.3%} × {spacing_multiplier}")
print(f"          = {final_spacing:.3%}")
print()

print("[Result]")
print(f"  网格间距(%)    : {final_spacing:.3%}")
print(f"  网格间距($)    : ${spacing_usd:,.0f}  (假设BTC=${btc_price:,})")
print(f"  单笔毛利       : {final_spacing:.3%}")
print(f"  单笔成本       : {trading_costs:.3%}")
print(f"  单笔净利润     : {final_spacing - trading_costs:.3%} [OK]")
print()

print("[Profit Analysis]")
net_profit_pct = final_spacing - trading_costs
profit_ratio = net_profit_pct / final_spacing * 100

print(f"  毛利润占比     : {final_spacing / final_spacing * 100:.1f}%")
print(f"  成本占比       : {trading_costs / final_spacing * 100:.1f}%")
print(f"  净利润占比     : {profit_ratio:.1f}%")
print()

print("[Important]")
print(f"  - spacing_multiplier 必须 >= 1.0 (当前: {spacing_multiplier})")
print(f"  - 当前设置保证每笔交易净利润 >= {min_return:.2%}")
print(f"  - 若要提高turnover，可增加网格层数，不要降低spacing_multiplier")
print()

print("[Tuning Suggestions]")
print()
print("  提高单笔利润:")
print("    → min_return = 0.01 (1.0%)    # spacing变为1.2%")
print()
print("  扩大网格间距:")
print("    → spacing_multiplier = 1.5    # spacing变为1.05%")
print()
print("  提高交易频率:")
print("    → grid_layers_buy = 15-20     # 增加网格层数")
print("    → risk_budget_pct = 0.8       # 增加资金占比")
print()

print("=" * 70)

"""诊断网格关闭原因 - 使用订单中的实际价格"""
import pandas as pd
from pathlib import Path

# 读取订单数据
orders_file = Path("run/results_lean_taogrid_stress_test_2025_09_26/orders.csv")
orders_df = pd.read_csv(orders_file)

# 配置
support = 107000.0
atr = 63.69  # 从初始化日志中获取
cushion_multiplier = 0.8
max_risk_atr_mult = 3.0

# 计算阈值
risk_zone_threshold = support + (atr * cushion_multiplier)
level3_threshold = support - (2.0 * atr)
shutdown_price_threshold = support - (max_risk_atr_mult * atr)

print("=" * 80)
print("网格关闭触发原因诊断")
print("=" * 80)
print()

print(f"支撑: ${support:,.0f}")
print(f"ATR: ${atr:,.2f}")
print(f"Shutdown 价格阈值: ${shutdown_price_threshold:,.2f} (support - {max_risk_atr_mult} × ATR)")
print(f"Level3 价格阈值: ${level3_threshold:,.2f} (support - 2.0 × ATR)")
print(f"Risk Zone 价格阈值: ${risk_zone_threshold:,.2f} (support + cushion)")
print()

# 查看00:53-00:55之间的订单和市场价
print("00:53-00:55 期间的订单:")
print("-" * 80)
period_orders = orders_df[orders_df['timestamp'] >= '2025-09-26 00:53:00']
for idx, row in period_orders.iterrows():
    direction = row['direction']
    price = row['price']
    market_price = row.get('market_price', 'N/A')
    print(f"{row['timestamp']} | {direction.upper():4s} | Grid Price: ${price:,.2f} | Market Price: ${market_price if market_price != 'N/A' else 'N/A':,.2f}")
    
    if market_price != 'N/A':
        # 检查是否触发价格阈值
        if market_price < shutdown_price_threshold:
            print(f"  ⚠️ 市场价 ${market_price:,.2f} < Shutdown阈值 ${shutdown_price_threshold:,.2f} - 触发关闭！")
        elif market_price < level3_threshold:
            print(f"  ⚠️ 市场价 ${market_price:,.2f} < Level3阈值 ${level3_threshold:,.2f}")
        elif market_price < risk_zone_threshold:
            print(f"  ⚠️ 市场价 ${market_price:,.2f} < Risk Zone阈值 ${risk_zone_threshold:,.2f}")

print()
print("=" * 80)
print()
print("结论:")
print(f"- 如果市场价在 00:53-00:55 期间低于 ${shutdown_price_threshold:,.2f}，会触发价格条件关闭")
print(f"- 如果市场价低于 ${level3_threshold:,.2f}，会触发 Level3 风险")
print(f"- 未实现亏损触发条件：未实现亏损 < -30% × 权益")

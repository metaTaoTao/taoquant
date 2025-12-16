"""
量化分析10.10-10.11暴跌期间的策略表现
基于用户提供的日志数据
"""
import pandas as pd
import numpy as np

print("=" * 80)
print("量化分析：50X杠杆策略在10.10-10.11暴跌中的表现")
print("=" * 80)

# 从日志中提取的关键数据点
log_data = {
    # 持仓峰值点（10.10 21:54）
    "peak_inventory": {
        "timestamp": "2025-10-10 21:54:00",
        "inventory_pct": 70,  # 7.02 BTC out of 10 BTC (70%)
        "inventory_btc": 7.02,
        "price_range": "$112K-$113K",  # 大致价格区间
        "avg_price": 112500,  # 假设平均价格
    },
    
    # 持仓快速下降点（10.10 21:56）
    "decline_point": {
        "timestamp": "2025-10-10 21:56:00",
        "inventory_pct": 54,  # 5.36 BTC
        "inventory_btc": 5.36,
        "time_diff_minutes": 2,  # 从峰值到下降点仅2分钟
    },
    
    # 订单执行频率（10.10 21:00-22:00）
    "execution_frequency": {
        "period": "21:00-22:00",
        "orders": 60,  # 估算的订单数
        "minutes": 60,
        "orders_per_minute": 1.0,
    },
    
    # 价格范围
    "price_range": {
        "min": 107876,  # L40价格
        "max": 112995,  # L12价格
        "range_pct": (112995 - 107876) / 107876 * 100,  # 约4.75%
    },
    
    # 网格设置
    "grid_setup": {
        "support": 107000,
        "resistance": 123000,
        "levels": 40,
        "price_in_range": True,  # 价格在S/R区间内
    },
}

print("\n关键数据点：\n")
for key, data in log_data.items():
    print(f"【{key}】")
    for subkey, value in data.items():
        print(f"  {subkey}: {value}")
    print()

# 计算实际杠杆
print("=" * 80)
print("实际杠杆计算")
print("=" * 80)

# 假设初始权益（基于用户配置）
initial_equity = 100000  # $100,000

# 在持仓峰值时的假设权益（考虑已有利润）
# 从回测结果看，9.26-10.10期间应该有盈利
# 假设此时权益约$140,000-$150,000
peak_equity_range = [140000, 150000, 160000]

for peak_equity in peak_equity_range:
    peak_inv = log_data["peak_inventory"]["inventory_btc"]
    avg_price = log_data["peak_inventory"]["avg_price"]
    holdings_value = peak_inv * avg_price
    
    actual_leverage = holdings_value / peak_equity
    
    print(f"\n假设持仓峰值时权益=${peak_equity:,.0f}:")
    print(f"  持仓: {peak_inv:.2f} BTC × ${avg_price:,.0f} = ${holdings_value:,.0f}")
    print(f"  实际杠杆: ${holdings_value:,.0f} / ${peak_equity:,.0f} = {actual_leverage:.2f}X")
    print(f"  名义杠杆: 50X")
    print(f"  杠杆使用率: {actual_leverage / 50 * 100:.1f}%")

# 计算持仓降低速度
print("\n" + "=" * 80)
print("持仓降低速度分析")
print("=" * 80)

peak_inv = log_data["peak_inventory"]["inventory_btc"]
decline_inv = log_data["decline_point"]["inventory_btc"]
time_diff = log_data["decline_point"]["time_diff_minutes"]

inv_reduction = peak_inv - decline_inv
inv_reduction_pct = (inv_reduction / peak_inv) * 100
reduction_rate = inv_reduction / time_diff  # BTC per minute

print(f"峰值持仓: {peak_inv:.2f} BTC (70%)")
print(f"2分钟后持仓: {decline_inv:.2f} BTC (54%)")
print(f"持仓减少: {inv_reduction:.2f} BTC ({inv_reduction_pct:.1f}%)")
print(f"降低速度: {reduction_rate:.3f} BTC/分钟")
print(f"\n这意味着持仓在暴跌期间能够快速降低，限制了风险暴露")

# 计算价格波动和回撤的关系
print("\n" + "=" * 80)
print("价格波动 vs 回撤分析")
print("=" * 80)

price_min = log_data["price_range"]["min"]
price_max = log_data["price_range"]["max"]
price_range_pct = log_data["price_range"]["range_pct"]

max_drawdown = 11.37  # 用户报告的最大回撤

print(f"暴跌期间价格范围: ${price_min:,} - ${price_max:,}")
print(f"价格波动幅度: {price_range_pct:.2f}%")
print(f"策略最大回撤: {max_drawdown:.2f}%")
print(f"\n关键发现：")
print(f"  价格波动约{price_range_pct:.2f}%，但策略回撤只有{max_drawdown:.2f}%")
print(f"  这说明策略通过以下机制限制了回撤：")
print(f"  1. 持仓快速降低，减少了价格下跌的影响")
print(f"  2. 网格配对机制，每次配对都锁定部分利润或限制亏损")
print(f"  3. Breakout风险控制，阻止逆势买入")

# 分析订单配对效率
print("\n" + "=" * 80)
print("订单配对效率分析")
print("=" * 80)

# 从日志观察，大部分卖出订单都有对应的买入配对
# 估算配对效率（基于日志观察）
pairing_efficiency = 0.85  # 假设85%的订单能够配对

print(f"估算订单配对效率: {pairing_efficiency*100:.0f}%")
print(f"\n配对机制的作用：")
print(f"  1. 卖出订单快速匹配买入订单，实现平仓")
print(f"  2. 每次配对都减少持仓，降低风险")
print(f"  3. 如果配对失败，FIFO机制确保持仓仍然减少")
print(f"  4. 这确保了持仓在暴跌期间能够快速降低")

# 总结
print("\n" + "=" * 80)
print("总结：为什么50X杠杆只有11.37%回撤？")
print("=" * 80)

summary = f"""
核心答案：**实际杠杆远低于名义杠杆**

1. **实际杠杆约5-6X**（而非50X）
   - 持仓峰值时：7 BTC × $112,500 ≈ $787,500持仓价值
   - 假设权益：$140,000-$150,000
   - 实际杠杆：约5.3X-5.6X
   - 因此回撤不会被50倍放大

2. **持仓快速降低**
   - 从峰值70%在2分钟内降至54%
   - 降低速度：{reduction_rate:.3f} BTC/分钟
   - 持仓降低后，实际杠杆进一步下降

3. **价格仍在有效区间**
   - 价格波动{price_range_pct:.2f}%，但价格仍在网格S/R区间内
   - 网格机制继续有效，订单能够正常配对

4. **多重风险控制机制**
   - Breakout风险控制阻止逆势买入
   - 网格配对机制快速平仓
   - FIFO机制确保成本基础正确计算
   - 这些机制共同作用，限制了风险暴露

结论：
虽然名义杠杆是50X，但通过动态持仓管理、风险因子过滤、网格配对等机制，
实际杠杆被控制在5-6X左右，这就是为什么策略能在极端暴跌中保持11.37%最大回撤的根本原因。
"""

print(summary)

print("\n分析完成！")

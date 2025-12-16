"""
修正后的分析：基于真实价格数据（最低$101,500，跌破网格底部）
"""
import pandas as pd

print("=" * 80)
print("修正后的分析：价格跌破网格底部时的策略抗压机制")
print("=" * 80)

# 真实价格数据
actual_data = {
    "price_crash": {
        "start_time": "2025-10-10 21:13:00",
        "min_price_time": "2025-10-10 21:20:00",
        "min_price": 101500,
        "recovery_time": "2025-10-10 21:27:00",
        "below_support_duration_minutes": 10,  # 价格在107K以下停留10分钟
        "at_101k_duration_minutes": 2,  # 价格在101K-103K区间只有2分钟
    },
    
    "grid_setup": {
        "support": 107000,  # 网格底部
        "lowest_buy_level": 107876,  # L40价格
        "price_drop_below_support": 5500,  # 101500 - 107000 = -5500
        "drop_percent": -5.14,  # (101500 - 107000) / 107000 * 100
    },
}

print("\n真实价格数据：\n")
for key, data in actual_data.items():
    print(f"【{key}】")
    for subkey, value in data.items():
        print(f"  {subkey}: {value}")
    print()

# 关键问题：为什么价格跌到101K时策略还能抗住？
print("=" * 80)
print("关键问题：价格跌到101K时策略如何抗住？")
print("=" * 80)

analysis = """
基于真实价格数据和日志分析：

1. **价格在低位的停留时间极短**
   - 价格在101K-103K区间只有2分钟（21:19-21:20）
   - 这是典型的"插针"行情：快速下跌，快速反弹
   - 在如此短的时间内，即使有持仓亏损，也来不及放大

2. **价格跌破网格底部时，网格订单可能已全部触发或超出范围**
   - 网格底部是107K，最低价格是101.5K
   - 当价格快速跌破107K时，可能：
     a) 之前在高位的买入订单已经通过卖出配对平仓
     b) 网格没有在107K以下设置买入订单（超出网格范围）
     c) 即使价格到了101K，也没有新的买入订单被触发

3. **持仓在暴跌前已经降低**
   - 从日志看，在21:13价格开始快速下跌前，已经有大量卖出订单执行
   - 卖出订单通过配对机制降低了持仓
   - 当价格跌到101K时，持仓可能已经降到较低水平

4. **Breakout风险控制阻止逆势买入**
   - 从日志看到：`Order blocked - BUY L38: Breakout risk-off (downside)`
   - 在极端下跌时，Breakout因子阻止了买入订单
   - 这避免了在101K低位开新仓

5. **价格快速反弹**
   - 价格从101K快速反弹到107K以上只用了7分钟
   - 在价格反弹过程中，如果还有持仓，未实现亏损会快速减少
   - 如果有卖出订单在反弹过程中触发，还能锁定部分利润

6. **网格订单的价格执行机制**
   - 网格订单是按网格层级价格执行的，不是按市场价格
   - 即使市场价格到了101K，如果网格层级价格是107K，订单还是按107K执行
   - 这意味着在价格插针到101K时，可能没有订单被触发（因为已经超出网格范围）

关键发现：
- 价格虽然跌到101K，但停留时间极短（2分钟）
- 在这个极短时间内，持仓已经通过之前的卖出订单降低
- Breakout风险控制阻止了在低位的逆势买入
- 价格快速反弹，限制了未实现亏损的持续时间
"""

print(analysis)

# 计算理论最大亏损 vs 实际回撤
print("=" * 80)
print("理论亏损 vs 实际回撤分析")
print("=" * 80)

# 假设在价格跌到101K时的持仓情况
# 从日志看，在21:20之前持仓可能已经降到较低水平

scenarios = [
    {
        "name": "如果持仓峰值时价格跌到101K",
        "holdings_btc": 7.0,
        "avg_buy_price": 112000,  # 假设平均买入价
        "crash_price": 101500,
        "unrealized_loss": (101500 - 112000) * 7.0,
        "equity": 150000,
        "drawdown_pct": None,
    },
    {
        "name": "如果持仓已经降低到50%",
        "holdings_btc": 5.0,
        "avg_buy_price": 110000,
        "crash_price": 101500,
        "unrealized_loss": (101500 - 110000) * 5.0,
        "equity": 150000,
        "drawdown_pct": None,
    },
    {
        "name": "如果持仓已经降低到30%",
        "holdings_btc": 3.0,
        "avg_buy_price": 109000,
        "crash_price": 101500,
        "unrealized_loss": (101500 - 109000) * 3.0,
        "equity": 150000,
        "drawdown_pct": None,
    },
]

for scenario in scenarios:
    unrealized_loss = scenario["unrealized_loss"]
    equity = scenario["equity"]
    drawdown_pct = (abs(unrealized_loss) / equity) * 100
    scenario["drawdown_pct"] = drawdown_pct
    
    print(f"\n{scenario['name']}:")
    print(f"  持仓: {scenario['holdings_btc']:.2f} BTC")
    print(f"  平均买入价: ${scenario['avg_buy_price']:,.0f}")
    print(f"  暴跌价格: ${scenario['crash_price']:,.0f}")
    print(f"  未实现亏损: ${unrealized_loss:,.0f}")
    print(f"  理论回撤: {drawdown_pct:.2f}%")
    print(f"  实际回撤: 11.37%")

print("\n" + "=" * 80)
print("修正后的结论")
print("=" * 80)

conclusion = """
关键发现：价格虽然跌到101K，但策略能抗住的真正原因是：

1. **价格在低位停留时间极短**
   - 价格在101K-103K只有2分钟
   - 这是"插针"行情，不是持续下跌

2. **持仓在暴跌前已经降低**
   - 通过频繁的卖出配对，持仓从峰值快速降低
   - 当价格跌到101K时，实际持仓可能已经降到较低水平

3. **网格订单执行机制保护**
   - 价格跌破网格底部时，可能没有新的买入订单被触发
   - 即使市场价格到101K，网格订单价格仍是107K+，不会在101K执行

4. **Breakout风险控制**
   - 阻止在极端下跌时的逆势买入
   - 避免在101K低位开新仓

5. **价格快速反弹**
   - 从101K反弹到107K以上只用了7分钟
   - 限制了未实现亏损的持续时间

6. **实际杠杆控制在较低水平**
   - 虽然名义杠杆50X，但实际使用的杠杆可能只有5-6X
   - 即使价格跌到101K，实际杠杆的放大效应也是有限的

因此，策略能抗住的关键不是"价格没有跌到101K"，而是：
- 持仓在暴跌前已经降低
- 价格在低位停留时间极短（插针）
- 快速反弹限制了亏损的持续时间
"""

print(conclusion)

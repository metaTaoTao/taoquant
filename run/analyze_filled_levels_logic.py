"""
分析 filled_levels 的逻辑问题
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("=" * 80)
print("filled_levels 逻辑分析")
print("=" * 80)

print("\n关键发现：")
print("=" * 80)

finding = """
1. 【filled_levels 的设置逻辑已被移除】

   代码位置: grid_manager.py:787
   ```python
   # self.filled_levels[level_key] = True  # REMOVED: allow continuous orders
   ```
   
   这意味着：
   - filled_levels 永远不会被设置为 True
   - 但是检查逻辑还在：if self.filled_levels.get(level_key, False)
   - 所以 filled_levels.get() 应该总是返回 False
   - 不应该阻止任何订单！

2. 【filled_levels 只在卖出匹配时被删除】

   代码位置: grid_manager.py:852-853
   ```python
   if buy_level_key in self.filled_levels:
       del self.filled_levels[buy_level_key]
   ```
   
   这意味着：
   - filled_levels 只在卖出订单匹配后，且所有持仓被清空时才被删除
   - 但 filled_levels 从未被设置为 True，所以这个删除操作实际上不会执行
   - 除非有其他代码路径设置了 filled_levels

3. 【问题可能不在 filled_levels】

   如果 filled_levels 一直是空的，那么：
   - 不应该阻止任何订单
   - 不应该影响交易数量
   
   那么问题可能在于：
   - 其他因子过滤（Breakout Risk, Trend Score等）
   - 库存限制
   - 订单触发逻辑
   - 卖出订单匹配逻辑
"""

print(finding)

print("\n" + "=" * 80)
print("可能的问题")
print("=" * 80)

possible_issues = """
1. 【filled_levels 可能在其他地方被设置】

   需要检查：
   - 是否有其他代码路径设置了 filled_levels
   - 是否有遗留代码或未清理的状态
   - 是否有初始化时设置了 filled_levels

2. 【订单触发逻辑问题】

   可能的问题：
   - pending_limit_orders 的状态管理
   - 订单触发条件（touched, inventory check等）
   - 订单大小计算（可能返回0，导致订单不执行）

3. 【卖出订单匹配问题】

   可能的问题：
   - match_sell_order 可能返回 None
   - 导致卖出订单无法匹配，持仓无法减少
   - 进而影响后续买入订单的执行

4. 【状态累积问题】

   可能的问题：
   - 7.10-9.26期间，某些状态（如 pending_orders, buy_positions）累积
   - 导致9.26-10.26期间的订单触发逻辑异常
   - 或者订单大小计算异常
"""

print(possible_issues)

print("\n" + "=" * 80)
print("建议的检查方法")
print("=" * 80)

suggestions = """
1. 【运行回测并查看日志】

   运行回测后，检查日志输出：
   - 是否有 [FILLED_LEVELS] BUY L... blocked 的日志？
   - 如果有，说明 filled_levels 确实在阻止订单
   - 如果没有，说明问题不在 filled_levels

2. 【检查 filled_levels 的状态】

   查看定期汇总日志：
   - filled_levels 的数量是否一直为0？
   - 如果一直为0，说明 filled_levels 不是问题
   - 如果数量很高，说明有其他代码设置了 filled_levels

3. 【检查订单触发情况】

   需要添加更多日志来检查：
   - 订单是否被触发？
   - 订单大小是否为0？
   - 订单是否被其他因子阻止？

4. 【检查卖出订单匹配】

   需要添加日志来检查：
   - 卖出订单是否成功匹配？
   - match_sell_order 是否返回 None？
   - 如果匹配失败，为什么？
"""

print(suggestions)

print("\n" + "=" * 80)
print("需要添加的额外日志")
print("=" * 80)

additional_logs = """
1. 【订单触发日志】
   - 当订单被触发时，记录触发原因
   - 当订单被阻止时，记录阻止原因（filled_levels, inventory, factor等）

2. 【订单大小计算日志】
   - 记录订单大小的计算过程
   - 记录各个因子的影响（Breakout Risk, Trend Score等）
   - 记录最终订单大小是否为0

3. 【卖出订单匹配日志】
   - 记录 match_sell_order 的调用和返回结果
   - 记录匹配成功/失败的原因

4. 【pending_orders 状态日志】
   - 记录 pending_orders 的数量变化
   - 记录订单的添加和移除
"""

print(additional_logs)

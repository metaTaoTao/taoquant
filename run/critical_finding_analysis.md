# 关键发现：filled_levels 逻辑分析

## 关键发现

### 1. filled_levels 的设置逻辑已被移除

**代码位置**: `grid_manager.py:787`
```python
# self.filled_levels[level_key] = True  # REMOVED: allow continuous orders
```

**影响**：
- `filled_levels` 永远不会被设置为 `True`
- 但是检查逻辑还在：`if self.filled_levels.get(level_key, False)`
- 所以 `filled_levels.get()` 应该总是返回 `False`
- **理论上不应该阻止任何订单**

### 2. 但是初始化时检查 filled_levels

**代码位置**: `grid_manager.py:267`
```python
# Only place if not already filled
if not self.filled_levels.get(level_key, False):
    self.pending_limit_orders.append({...})
```

**问题**：
- 初始化时，如果 `filled_levels` 中有某个层级，就不会放置该层级的订单
- 如果 `filled_levels` 在某个时候被设置了（可能是遗留代码或其他路径），那么：
  1. 初始化时，这些层级不会放置订单
  2. 后续也不会触发这些层级的订单
  3. **导致交易数量减少**

### 3. 真正的问题可能在其他地方

如果 `filled_levels` 一直是空的，那么问题可能在于：

1. **订单触发逻辑**
   - `check_limit_order_triggers` 中的其他条件
   - 价格是否触及限价单价格
   - 是否有持仓（对于卖出订单）

2. **订单大小计算**
   - `calculate_order_size` 可能返回 0
   - 因子过滤（Breakout Risk, Trend Score等）可能阻止订单
   - 库存限制可能阻止买入

3. **卖出订单匹配**
   - `match_sell_order` 可能返回 `None`
   - 导致卖出订单无法匹配，持仓无法减少
   - 进而影响后续买入订单的执行

4. **状态累积问题**
   - 7.10-9.26期间，某些状态（如 `pending_orders`, `buy_positions`）累积
   - 导致9.26-10.26期间的订单触发逻辑异常

## 建议的检查步骤

### 1. 运行回测并查看日志

运行回测后，检查日志输出：
- **是否有 `[FILLED_LEVELS] BUY L... blocked` 的日志？**
  - 如果有，说明 `filled_levels` 确实在阻止订单（可能是遗留代码设置了它）
  - 如果没有，说明问题不在 `filled_levels`

### 2. 检查 filled_levels 的状态

查看定期汇总日志：
- `filled_levels` 的数量是否一直为 0？
  - 如果一直为 0，说明 `filled_levels` 不是问题
  - 如果数量很高，说明有其他代码设置了 `filled_levels`

### 3. 需要添加更多诊断日志

如果 `filled_levels` 不是问题，需要添加日志来检查：
- 订单是否被触发？
- 订单大小是否为 0？
- 订单是否被其他因子阻止？
- 卖出订单是否成功匹配？

## 下一步行动

1. **运行回测**，查看日志输出
2. **分析日志**，确认 `filled_levels` 是否真的在阻止订单
3. **如果 filled_levels 不是问题**，添加更多日志来诊断其他可能的原因

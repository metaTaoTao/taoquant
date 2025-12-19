# 根本原因和修复

## 根本原因

**买入订单执行后，没有立即重新放置买入订单，导致买入pending订单数逐渐减少到0，无法继续买入！**

### 问题流程

1. 初始状态：40个买入pending订单
2. 买入订单执行后：
   - 移除买入订单
   - 放置卖出订单
   - **不重新放置买入订单**（等待卖出后再重新进入）
3. 如果卖出订单长时间未触发：
   - 买入订单已经被移除
   - 买入订单不会重新放置
   - 买入pending订单数逐渐减少
4. 最终状态：买入pending订单数为0，无法继续买入

### 证据

从 `run/find_root_cause.py` 的输出：
- 初始pending订单数: 40
- 最终pending订单数: 40（但都是卖出订单）
- 买入pending订单数: 0
- 买入持仓数: 29（有持仓但没有对应的买入订单）

## 修复

在 `algorithms/taogrid/algorithm.py` 的 `on_order_filled` 方法中：

**修改前：**
```python
# IMPORTANT (inventory-aware grid):
# Do NOT immediately re-place the same buy order after a buy fill.
# We wait until the corresponding sell is filled, then re-enter.
```

**修改后：**
```python
# IMPORTANT: Re-place the buy order immediately to maintain grid density
# This ensures continuous trading opportunities and prevents order count from decreasing
# The original logic (waiting for sell to re-enter) was causing order count to drop to zero
if self.grid_manager.buy_levels is not None and level < len(self.grid_manager.buy_levels):
    buy_level_price = self.grid_manager.buy_levels[level]
    self.grid_manager.place_pending_order('buy', level, buy_level_price)
    self._log(f"  Re-placed buy limit order at L{level+1} @ ${buy_level_price:,.0f} (immediate re-entry)")
```

## 预期效果

修复后：
- 买入订单执行后，立即重新放置买入订单
- 买入pending订单数保持在40个
- 可以持续买入，增加交易频率
- 交易数应该大幅增加

## 其他已修复的问题

1. ✅ `volatility_k=0.0` - 网格间距从5%降至0.16%
2. ✅ 移除 `filled_levels` 检查 - 允许价格重复触发
3. ✅ 修复 `execute_order` 返回值 - 买入被拒绝时返回False
4. ✅ 修复 `on_order_filled` 调用逻辑 - 只在订单执行成功时调用
5. ✅ 修复卖出订单大小计算 - 使用 `long_exposure` 而不是 `holdings_btc`
6. ✅ 修复订单执行失败后的 `triggered` 标志重置


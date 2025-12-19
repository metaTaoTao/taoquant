# 交易笔数少的问题诊断报告

## 关键发现

1. **网格价格被触及19,882次，但只有16笔交易**
   - 交易触发率：0.08%
   - 说明订单被大量阻止

2. **网格设置正常**
   - 网格间距：0.16%（volatility_k=0.0）
   - 买入层数：40层
   - 卖出层数：40层
   - 56%的价格在买入网格范围内

3. **可能的原因**

### 原因1: filled_levels阻止重复触发
- `check_pending_order_trigger` (grid_manager.py:353) 检查 `filled_levels`
- 如果 `filled_levels.get(level_key, False) == True`，订单被阻止
- `filled_levels` 只在卖出匹配后重置（grid_manager.py:898）
- 如果卖出匹配失败，`filled_levels` 永远不会重置

### 原因2: 卖出订单需要long_exposure > 0
- `check_pending_order_trigger` (grid_manager.py:377) 检查 `long_exposure`
- 如果没有持仓，卖出订单无法触发
- 这可能导致买入后无法卖出，形成死锁

### 原因3: 订单大小被限制为0
- `calculate_order_size` 可能返回0
- 原因包括：库存限制、风险控制、因子调整等

### 原因4: 网格被关闭
- 如果价格跌破support - 3×ATR，网格会被关闭
- 或者未实现亏损超过30% equity

## 建议的修复方案

1. **移除或修复filled_levels检查**
   - 既然 `add_buy_position` 已经允许连续订单（第823行注释掉），`check_pending_order_trigger` 也不应该检查 `filled_levels`
   - 或者确保 `filled_levels` 在买入后立即重置

2. **检查卖出匹配逻辑**
   - 确保卖出订单能正确匹配买入持仓
   - 如果匹配失败，应该允许自由卖出（不强制配对）

3. **启用详细日志**
   - 设置 `enable_console_log=True` 查看具体哪些订单被阻止
   - 检查 `[ORDER_BLOCKED]` 和 `[FILLED_LEVELS]` 日志

4. **检查订单大小计算**
   - 查看 `[ORDER_SIZE]` 日志，确认订单大小是否为0
   - 检查 `throttle_status.reason`


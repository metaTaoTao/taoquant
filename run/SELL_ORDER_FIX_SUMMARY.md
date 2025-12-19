# 卖出订单触发和执行逻辑修复总结

## 核心问题

**价格触及卖出网格250次，但卖出订单触发次数为0**

## 已修复的问题

1. ✅ 修复 `long_exposure` 计算错误 - `long_exposure` 已经是BTC数量，不需要除以价格
2. ✅ 修复 `last_checked_bar` 逻辑 - 只在订单被实际触发且执行成功时才设置
3. ✅ 修复订单执行失败后的重置逻辑 - 重置 `triggered` 和 `last_checked_bar`

## 关键发现

### 1. 订单放置情况
- 买入订单执行次数: 40次
- 卖出订单放置次数: 20次（只有买入订单的一半）
- 原因：`place_pending_order` 检查订单是否已存在，如果已存在就不放置
- 这是正常的，因为同一level的多个买入订单共享同一个卖出订单

### 2. 订单触发情况
- 价格触及卖出网格次数: 250次
- 卖出订单触发次数: 0次
- 价格触及率: 0.00%

### 3. 应该触发但未触发的情况
- 有4次价格触及且应该触发（价格触及、long_exposure > 0）
- 但卖出订单没有被触发

## 问题根源

**`check_limit_order_triggers` 只返回第一个被触发的订单**

如果同一根K线中有多个订单被触发（买入和卖出），只会返回第一个。虽然我们在 `simple_lean_runner` 中循环调用 `on_data`，但问题是：
1. 第一次调用时，如果买入订单先被触发，就返回买入订单
2. 第二次调用时，卖出订单可能因为 `last_checked_bar` 被跳过

## 解决方案

### 方案1: 修改 `check_limit_order_triggers` 返回所有被触发的订单列表（推荐）
- 优点：可以处理同一根K线中的所有订单
- 缺点：需要修改 `on_data` 的逻辑

### 方案2: 修改 `last_checked_bar` 的逻辑（已部分实现）
- 只在订单被实际触发且执行成功时才设置 `last_checked_bar`
- 如果订单被触发但执行失败，重置 `last_checked_bar` 以允许重新检查

### 方案3: 分别检查买入和卖出订单
- 在 `check_limit_order_triggers` 中，先检查所有买入订单，再检查所有卖出订单
- 或者，分别调用 `check_buy_triggers` 和 `check_sell_triggers`

## 当前状态

- ✅ 已修复 `long_exposure` 计算错误
- ✅ 已修复 `last_checked_bar` 逻辑
- ⚠️ 仍需要修复 `check_limit_order_triggers` 返回所有订单的问题

## 下一步

1. **修改 `check_limit_order_triggers` 返回所有被触发的订单列表**
   - 这样可以确保同一根K线中的所有订单都能被处理

2. **测试修复效果**
   - 运行回测，检查交易数是否增加
   - 检查卖出订单是否被正确触发和执行


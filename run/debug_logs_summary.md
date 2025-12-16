# 调试日志总结

## 已添加的调试日志

### 1. 订单触发日志 (`grid_manager.py:check_limit_order_triggers`)

- **订单触发时**: `[ORDER_TRIGGER] BUY/SELL L... TRIGGERED`
- **订单未触发（价格未触及）**: `[ORDER_TRIGGER] BUY/SELL L... not triggered - price not touched`
- **卖出订单未触发（无持仓）**: `[ORDER_TRIGGER] SELL L... not triggered - no long positions`

### 2. 订单大小计算日志 (`grid_manager.py:calculate_order_size`)

- **初始大小**: `[ORDER_SIZE] BUY/SELL L... - base_size=... BTC`
- **最终大小=0（被阻止）**: `[ORDER_SIZE] BUY/SELL L... - FINAL SIZE=0 (blocked: ...)`
- **最终大小被节流**: `[ORDER_SIZE] BUY/SELL L... - FINAL SIZE=... BTC (throttled: ...)`
- **最终大小正常**: `[ORDER_SIZE] BUY/SELL L... - FINAL SIZE=... BTC`

### 3. 卖出订单匹配日志 (`grid_manager.py:match_sell_order`)

- **匹配尝试**: `[SELL_MATCH] Attempting to match SELL L...`
- **匹配成功**: `[SELL_MATCH] SUCCESS: SELL L... matched with BUY L...`
- **匹配失败**: `[SELL_MATCH] FAILED: SELL L... - no matching buy position found`
- **显示可用持仓**: 匹配失败时显示可用的买入持仓

### 4. FIFO匹配日志 (`simple_lean_runner.py:execute_order`)

- **Grid配对失败，回退到FIFO**: `[SELL_MATCH_FIFO] Grid pairing failed for SELL L..., falling back to FIFO`
- **FIFO匹配成功**: `[SELL_MATCH_FIFO] FIFO match: SELL L... matched with BUY L...`
- **无持仓可匹配**: `[SELL_MATCH_FIFO] No long positions available for FIFO matching`

### 5. 订单执行日志 (`simple_lean_runner.py:execute_order`)

- **买入执行成功**: `[BUY_EXECUTED] L... @ $..., size=... BTC, holdings=..., long_positions_count=..., cost_basis=$...`
- **买入被拒绝（杠杆限制）**: `[BUY_REJECTED] L... - leverage constraint: ...`
- **卖出执行成功**: `[SELL_EXECUTED] L... @ $..., size=... BTC, holdings=..., long_positions_count=..., cost_basis=$...`

### 6. 交易记录日志 (`simple_lean_runner.py:execute_order`)

- **交易匹配**: `[TRADE_MATCHED] BUY L... -> SELL L..., size=..., PnL=..., holding=...h`
- **交易记录**: `[TRADE_RECORD] SELL L... - recorded ... matched trades (total trades now: ...)`
- **警告（卖出执行但无交易记录）**: `[WARNING] SELL L... executed but no trades recorded!`

### 7. 订单创建日志 (`algorithm.py:on_data`)

- **订单创建**: `[ORDER_CREATED] BUY/SELL L... @ $..., size=... BTC, inventory: long=..., holdings=...`
- **订单接收**: `[ORDER_EXECUTE] Received BUY/SELL L... @ $..., size=... BTC`
- **订单执行成功**: `[ORDER_EXECUTE] BUY/SELL L... EXECUTED successfully`
- **订单执行失败**: `[ORDER_EXECUTE] BUY/SELL L... FAILED to execute`

### 8. 订单阻止日志 (`algorithm.py:on_data`)

- **订单被阻止**: `[ORDER_BLOCKED] BUY/SELL L... - reason: ..., inventory: long=..., holdings=...`

### 9. 待处理订单日志 (`grid_manager.py`)

- **放置待处理订单**: `[PENDING_ORDER] Placed BUY/SELL L... @ $... (pending_orders count: ...)`
- **移除待处理订单**: `[PENDING_ORDER] Removed BUY/SELL L... (pending_orders: ... -> ...)`
- **订单已存在**: `[PENDING_ORDER] BUY/SELL L... already exists, skipping`

### 10. 定期汇总日志 (`simple_lean_runner.py`)

- **每1000根K线**: `[FILLED_LEVELS_SUMMARY] Bar ... @ ...: filled_levels=..., pending_orders=..., buy_positions=..., samples=[...]`

### 11. 无订单触发日志 (`algorithm.py:on_data`)

- **每1000根K线（如果无订单触发）**: `[ORDER_TRIGGER] Bar ... @ ...: No order triggered (pending_orders=..., price=$...)`

## 日志标签说明

- `[ORDER_TRIGGER]` - 订单触发相关
- `[ORDER_SIZE]` - 订单大小计算
- `[ORDER_BLOCKED]` - 订单被阻止
- `[ORDER_CREATED]` - 订单创建
- `[ORDER_EXECUTE]` - 订单执行
- `[SELL_MATCH]` - 卖出订单匹配（Grid配对）
- `[SELL_MATCH_FIFO]` - 卖出订单匹配（FIFO回退）
- `[BUY_EXECUTED]` - 买入执行
- `[SELL_EXECUTED]` - 卖出执行
- `[TRADE_MATCHED]` - 交易匹配
- `[TRADE_RECORD]` - 交易记录
- `[PENDING_ORDER]` - 待处理订单
- `[FILLED_LEVELS]` - filled_levels 状态
- `[FILLED_LEVELS_SUMMARY]` - filled_levels 汇总

## 注意事项

1. **日志可能很多** - 如果不需要，可以设置 `enable_console_log=False`
2. **所有日志都是只读的** - 只是 `print()` 语句，不修改任何业务逻辑
3. **定期汇总日志** - 每1000根K线输出一次，不会太频繁
4. **关键事件日志** - 订单触发、执行、匹配等关键事件都会记录

## 使用方法

运行回测后，日志会输出到控制台。可以使用以下方法分析：

1. **搜索特定标签** - 例如搜索 `[SELL_MATCH]` 查看卖出匹配情况
2. **统计日志数量** - 统计各种日志的数量，找出问题
3. **对比两个时间段** - 对比7.10-10.26和9.26-10.26期间的日志差异

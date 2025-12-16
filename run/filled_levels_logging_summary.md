# filled_levels 状态诊断日志总结

## 已添加的日志点

### 1. 买入订单被 filled_levels 阻止时
**位置**: `algorithms/taogrid/helpers/grid_manager.py:353-355`

```python
if self.filled_levels.get(level_key, False):
    triggered = False
    # Log when order is blocked due to filled_levels
    if getattr(self.config, "enable_console_log", False):
        print(f"[FILLED_LEVELS] BUY L{level_index+1} @ ${limit_price:,.0f} blocked - level already filled (filled_levels count: {len(self.filled_levels)})")
```

**输出示例**:
```
[FILLED_LEVELS] BUY L15 @ $110,500.00 blocked - level already filled (filled_levels count: 12)
```

### 2. 卖出订单匹配后重置 filled_levels 时
**位置**: `algorithms/taogrid/helpers/grid_manager.py:841-844`

```python
if buy_level_key in self.filled_levels:
    del self.filled_levels[buy_level_key]
    # Log when filled_levels is reset
    if getattr(self.config, "enable_console_log", False):
        print(f"[FILLED_LEVELS] Reset BUY L{buy_level_idx+1} after sell match (filled_levels count: {len(self.filled_levels)})")
```

**输出示例**:
```
[FILLED_LEVELS] Reset BUY L15 after sell match (filled_levels count: 11)
```

### 3. 添加买入持仓时显示 filled_levels 状态
**位置**: `algorithms/taogrid/helpers/grid_manager.py:782-787`

```python
# Log filled_levels state when adding buy position
if getattr(self.config, "enable_console_log", False):
    filled_count = len(self.filled_levels)
    is_filled = self.filled_levels.get(level_key, False)
    print(f"[FILLED_LEVELS] Add BUY L{buy_level_index+1} @ ${buy_price:,.0f} - filled_levels count: {filled_count}, this level filled: {is_filled}")
```

**输出示例**:
```
[FILLED_LEVELS] Add BUY L15 @ $110,500.00 - filled_levels count: 12, this level filled: False
```

### 4. 定期汇总日志（每1000根K线）
**位置**: `algorithms/taogrid/simple_lean_runner.py:252-257`

```python
# Periodic filled_levels summary log (every 1000 bars)
if i > 0 and i % 1000 == 0 and getattr(self.algorithm.config, "enable_console_log", False):
    filled_levels = self.algorithm.grid_manager.filled_levels
    filled_count = len(filled_levels)
    filled_keys = list(filled_levels.keys())[:10]  # Show first 10
    pending_orders_count = len(self.algorithm.grid_manager.pending_limit_orders)
    buy_positions_count = sum(len(positions) for positions in self.algorithm.grid_manager.buy_positions.values())
    print(f"\n[FILLED_LEVELS_SUMMARY] Bar {i} @ {timestamp}: filled_levels={filled_count}, pending_orders={pending_orders_count}, buy_positions={buy_positions_count}, samples={filled_keys}")
```

**输出示例**:
```
[FILLED_LEVELS_SUMMARY] Bar 1000 @ 2025-07-10 16:40:00+00:00: filled_levels=5, pending_orders=40, buy_positions=8, samples=['buy_L10', 'buy_L15', 'buy_L20', 'buy_L25', 'buy_L30']
```

## 如何使用这些日志

### 1. 运行回测
```bash
python algorithms/taogrid/simple_lean_runner.py
```

### 2. 查看日志输出
在回测过程中，您会看到：
- 哪些买入订单被 `filled_levels` 阻止
- 哪些层级被重置
- `filled_levels` 的定期汇总状态

### 3. 分析问题
- 如果看到大量 `[FILLED_LEVELS] BUY L... blocked`，说明 `filled_levels` 确实在阻止订单
- 如果 `filled_levels` 数量一直很高且很少被重置，说明卖出订单匹配有问题
- 对比7.10-9.26和9.26-10.26期间的 `filled_levels` 状态，找出差异

## 关键指标

1. **filled_levels 数量**: 应该保持在较低水平（< 10），如果一直很高，说明重置逻辑有问题
2. **被阻止的订单数**: 如果很多订单被阻止，说明 `filled_levels` 确实影响了交易
3. **重置频率**: 卖出订单匹配后应该立即重置对应的买入层级

## 注意事项

- 日志可能会产生大量输出，如果不需要，可以设置 `enable_console_log=False`
- 定期汇总日志每1000根K线输出一次，不会太频繁
- 如果需要更详细的日志，可以调整日志输出频率

# 分析：为什么延长回测时间后交易次数反而减少？

## 关键发现

- **9.26-10.26（30天）**：1274笔交易
- **7.10-10.26（108天）**：1179笔交易
- **7.10-9.26（78天）**：1179 - 1274 = **-95笔交易**（不可能！）

这说明：**9.26-10.26期间的交易数量在7.10-10.26回测中减少了95笔**

## 可能的原因

### 1. **filled_levels 状态累积问题**（最可能）★★★★★

**代码逻辑**（`grid_manager.py:105, 267, 353, 783-844`）：

```python
# filled_levels 用于跟踪已触发的层级，避免重复触发
self.filled_levels: Dict[str, bool] = {}

# 检查层级是否已填充
if self.filled_levels.get(level_key, False):
    # 跳过，不触发订单
    continue

# 订单执行后，标记层级为已填充
self.filled_levels[level_key] = True
```

**问题**：
- `filled_levels` 在整个回测过程中会累积状态
- 如果7.10-9.26期间某些层级被标记为 `filled = True`
- 这些层级在9.26-10.26期间可能无法再次触发
- 导致订单触发频率降低，交易数量减少

**影响**：
- 7.10-9.26期间：某些层级被标记为 filled
- 9.26-10.26期间：这些层级无法再次触发，订单减少
- 结果：9.26-10.26期间的交易数量在7.10-10.26回测中减少了

### 2. **pending_limit_orders 状态累积问题**★★★★

**代码逻辑**（`grid_manager.py:122, 212, 252-270`）：

```python
# pending_limit_orders 用于跟踪待触发的限价单
self.pending_limit_orders: List[dict] = []

# 初始化时，在所有买入层级放置限价单
def _initialize_pending_orders(self):
    self.pending_limit_orders = []
    for level_index, level_price in enumerate(self.buy_levels):
        if not self.filled_levels.get(level_key, False):
            self.pending_limit_orders.append({...})
```

**问题**：
- `pending_limit_orders` 在 `setup_grid()` 时初始化
- 但在整个回测过程中，订单可能被触发、移除、重新添加
- 如果7.10-9.26期间订单状态异常，可能影响后续订单触发

### 3. **网格重置逻辑问题**★★★

**代码逻辑**（`grid_manager.py:841-844`）：

```python
# 卖出订单匹配后，重置买入层级
if buy_level_key in self.filled_levels:
    del self.filled_levels[buy_level_key]
```

**问题**：
- 卖出订单匹配后，应该重置买入层级，允许再次触发
- 但如果7.10-9.26期间卖出订单很少，很多层级没有被重置
- 这些层级在9.26-10.26期间可能无法再次触发

## 建议的解决方案

### 1. **检查 filled_levels 状态**

在回测日志中添加：
- 每个时间点的 `filled_levels` 数量
- 哪些层级被标记为 filled
- 这些层级是否在后续被正确重置

### 2. **检查订单触发频率**

对比：
- 9.26-10.26单独回测：订单触发次数
- 7.10-10.26回测中9.26-10.26期间：订单触发次数

如果差异很大，说明是状态累积问题。

### 3. **修复建议**

如果确认是 `filled_levels` 状态累积问题，可以考虑：
- 在卖出订单匹配后，立即重置对应的买入层级
- 或者在每个bar开始时，检查并清理过期的 `filled_levels`
- 或者定期重置 `filled_levels`，允许层级重复触发

## 总结

最可能的原因是 **`filled_levels` 状态累积问题**：
- 7.10-9.26期间，某些层级被标记为 filled
- 这些层级在9.26-10.26期间无法再次触发
- 导致订单触发频率降低，交易数量减少

建议检查回测日志，确认 `filled_levels` 的状态变化。

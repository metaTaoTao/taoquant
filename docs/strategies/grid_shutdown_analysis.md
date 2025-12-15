# 网格过早关闭问题诊断

## 问题识别

根据你的专业判断，当前结果明显异常：
- **之前表现**：ROE 50%，最大回撤 20%，夏普 5+，交易笔数多
- **当前表现**：ROE 2.95%，最大回撤 -3.61%，夏普 0.26，只有 17 笔交易

## 根本原因

### 问题 1: 网格过早关闭且未自动重新启用

**发现**：
- 网格在 `2025-07-10 16:20:00` 触发关闭
- 之后**整个月（30天）都没有交易**
- 在 44,640 根 1 分钟 K 线中，只有前 980 根（2.2%）有交易活动

**原因**：
1. 网格关闭后，`grid_enabled = False`
2. 代码中 `check_risk_level()` 只在关闭时设置状态，**没有自动重新启用逻辑**
3. 即使风险条件改善，网格也不会自动恢复交易

**修复**：
已在 `check_risk_level()` 中添加自动重新启用逻辑：
```python
elif not should_shutdown and not self.grid_enabled:
    # Auto re-enable grid when risk conditions improve
    self.grid_enabled = True
    self.grid_shutdown_reason = None
    self.risk_zone_entry_time = None
```

### 问题 2: 卖出订单无法匹配（matched_trades=0）

**发现**：
- `2025-07-10 16:15:00` 的卖出订单 `matched_trades=0`
- 这意味着卖出订单无法找到对应的买入持仓进行配对

**可能原因**：
1. `grid_manager.buy_positions` 中的持仓结构可能不匹配
2. `match_sell_order()` 的匹配逻辑可能有问题
3. 或者之前的卖出已经消耗了所有持仓

### 问题 3: 风控触发条件可能过于严格

**分析**：
- 在 16:20 触发关闭时，未实现盈亏为 **+$256**（盈利状态）
- 但风控仍然触发，说明可能是价格条件触发（`price < shutdown_price_threshold`）

**计算公式**：
```
shutdown_price_threshold = support - (max_risk_atr_mult × ATR)
                        = 107,000 - (3.0 × 27.19)
                        ≈ 106,918
```

如果当前价格 < 106,918，就会触发关闭。

## 修复方案

### 1. 添加网格自动重新启用逻辑 ✅

已添加：当 `should_shutdown = False` 且 `grid_enabled = False` 时，自动重新启用网格。

### 2. 检查匹配逻辑

需要检查 `match_sell_order()` 为什么返回 None。可能的问题：
- `buy_positions` 结构不正确
- `target_sell_level` 匹配失败
- 持仓已被消耗但未正确清理

### 3. 调整风控阈值（可选）

如果价格阈值过于严格，可以调整：
```python
max_risk_atr_mult=4.0,  # 从 3.0 提高到 4.0
# 或者
enable_mm_risk_zone=False,  # 暂时禁用，测试基本功能
```

## 下一步行动

1. ✅ **已修复**：网格自动重新启用逻辑
2. **需要测试**：重新运行回测，验证网格是否会恢复交易
3. **需要检查**：为什么会有 matched_trades=0 的情况
4. **需要优化**：如果风控仍然过早触发，调整阈值参数

## 预期改善

修复后应该看到：
- ✅ 交易笔数大幅增加（从 17 笔增加到数百/数千笔）
- ✅ 夏普比率提升（从 0.26 提升到 5+）
- ✅ ROE 提升（从 2.95% 提升到 50%+）
- ✅ 最大回撤可能略增，但在可接受范围内（20%左右）

---

**状态**: 🔄 已修复自动重新启用逻辑，待验证  
**优先级**: 🔴 高 - 这是导致策略失效的根本原因
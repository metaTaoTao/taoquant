# 风控逻辑变更说明

## 变更总结

### ✅ 风控判断逻辑 - **未改变**

风控判断的核心逻辑（`check_risk_level()` 方法）**完全没有改变**：

1. **价格条件触发**：
   ```python
   if current_price < shutdown_price_threshold:
       should_shutdown = True
   ```
   - 未改变

2. **未实现亏损触发**：
   ```python
   elif unrealized_pnl < -adjusted_loss_threshold * equity:
       should_shutdown = True
   ```
   - 未改变（但由于 cost basis bug 修复，计算现在更准确）

3. **库存风险触发**：
   ```python
   elif inv_risk_pct > max_risk_inventory_pct:
       should_shutdown = True
   ```
   - 未改变

4. **风险级别判断**：
   - Level 1-4 的判断逻辑完全未改变

### ✅ 添加的功能 - **自动重新启用**

**新增功能**（第970-974行）：
```python
elif not should_shutdown and not self.grid_enabled:
    # Auto re-enable grid when risk conditions improve
    self.grid_enabled = True
    self.grid_shutdown_reason = None
    self.risk_zone_entry_time = None
```

**说明**：
- 这不是改变风控逻辑，而是修复了一个**设计缺陷**
- 原来网格关闭后需要手动重新启用，现在会自动恢复
- 当 `should_shutdown = False` 且网格已关闭时，自动重新启用

**为什么这是修复而不是改变**：
- 原来的行为：网格关闭后永久关闭（需要手动恢复）
- 修复后的行为：网格关闭后，当风险条件改善时自动恢复
- 这符合风控的预期行为：**临时保护，条件改善后恢复**

### ⚠️ 配置变更 - **暂时禁用 MM Risk Zone**

**位置**：`algorithms/taogrid/simple_lean_runner.py:753`

```python
enable_mm_risk_zone=False,  # 暂时禁用用于测试
```

**说明**：
- 这只是**测试配置**，不是逻辑改变
- 可以随时改回 `True` 重新启用
- 目的是验证基本交易逻辑是否正常

**影响**：
- 当 `enable_mm_risk_zone=False` 时，`check_risk_level()` 直接返回 `(0, False, None)`
- 所有 MM Risk Zone 相关的风控检查都被跳过
- 但其他风控（如 inventory threshold）仍然有效（通过 `check_throttle()`）

## 详细对比

### 修复前的行为

```
风险条件触发 → should_shutdown = True → grid_enabled = False
↓
之后即使风险条件改善 → should_shutdown = False
↓
但 grid_enabled 仍然是 False（不会自动恢复）
↓
网格永久关闭（需要手动调用 enable_grid()）
```

### 修复后的行为

```
风险条件触发 → should_shutdown = True → grid_enabled = False
↓
风险条件改善 → should_shutdown = False
↓
检测到 should_shutdown = False 且 grid_enabled = False
↓
自动设置 grid_enabled = True（网格恢复）
```

## 其他相关修改

### 1. Cost Basis 修复（影响风控准确性）

**位置**：`algorithms/taogrid/simple_lean_runner.py:496-499`

**变更**：
- 修复了卖出时 `total_cost_basis` 未更新的 bug
- 这**不影响风控逻辑**，但**提高了风控判断的准确性**

**影响**：
- 未实现亏损计算现在更准确
- 风控触发更合理（不会被错误的 cost basis 误导）

### 2. 安全检查（防止边界情况）

**位置**：`algorithms/taogrid/simple_lean_runner.py:500-502`

```python
# Safety check: if holdings is zero, cost basis should also be zero
if abs(self.holdings) < 1e-8:
    self.total_cost_basis = 0.0
```

**说明**：
- 这是**防御性编程**，不是改变逻辑
- 确保持仓为0时成本基础也为0（防止计算错误）

## 结论

### 风控判断逻辑：**未改变** ✅

所有风控判断条件、阈值、逻辑都完全保持原样。

### 唯一的功能性变更：**自动重新启用** ✅

这是修复设计缺陷，不是改变逻辑。现在的行为更符合预期：
- 风险条件触发 → 临时关闭保护
- 风险条件改善 → 自动恢复交易

### 配置变更：**暂时禁用 MM Risk Zone** ⚠️

这只是测试配置，可以随时改回。如果需要重新启用：

```python
enable_mm_risk_zone=True,  # 重新启用
```

---

**总结**：风控逻辑本身**没有改变**，只是添加了自动恢复功能，并暂时禁用了 MM Risk Zone 用于测试基本功能。

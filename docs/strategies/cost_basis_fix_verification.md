# Cost Basis 修复验证文档

## 问题描述

在原始代码中，卖出订单执行时，`total_cost_basis` 没有被正确更新，导致：
1. 未实现亏损计算错误（包含已卖出持仓的成本基础）
2. 风控系统过早触发（因为未实现亏损被高估）

## 修复方案

### 修复位置
`algorithms/taogrid/simple_lean_runner.py` - `execute_order()` 方法的卖出逻辑

### 修复逻辑

#### 买入时（保持不变）
```python
# 买入时：增加成本基础
self.total_cost_basis += size * execution_price
```
- `execution_price` 是网格层级价格（不包括手续费）
- 成本基础只跟踪价格基础，不包括手续费

#### 卖出时（修复后）
```python
# 1. 初始化成本基础减少量
total_cost_basis_reduction = 0.0

# 2. 在匹配循环中累计减少量
for each matched_position:
    matched_cost_basis = matched_size * buy_price
    total_cost_basis_reduction += matched_cost_basis

# 3. 卖出完成后，减少总成本基础
self.total_cost_basis -= total_cost_basis_reduction
self.total_cost_basis = max(0.0, self.total_cost_basis)  # 防止负数

# 4. 安全检查：如果持仓为0，成本基础也应该是0
if abs(self.holdings) < 1e-8:
    self.total_cost_basis = 0.0
```

## 逻辑验证

### 场景 1: 简单买入-卖出

**初始状态**:
- `holdings = 0.0`
- `total_cost_basis = 0.0`

**买入 1 BTC @ 100,000**:
- `holdings = 1.0`
- `total_cost_basis = 100,000` ✅

**卖出 1 BTC @ 101,000** (匹配到买入 @ 100,000):
- `matched_cost_basis = 1.0 * 100,000 = 100,000`
- `total_cost_basis_reduction = 100,000`
- `holdings = 0.0`
- `total_cost_basis = 100,000 - 100,000 = 0.0` ✅

**未实现亏损**:
- `unrealized_pnl = holdings * current_price - total_cost_basis = 0 * 101,000 - 0 = 0` ✅

### 场景 2: 部分卖出

**初始状态**:
- `holdings = 2.0 BTC`
- `total_cost_basis = 200,000` (买入 2 BTC @ 100,000)

**卖出 0.5 BTC @ 101,000** (匹配到买入 @ 100,000):
- `matched_cost_basis = 0.5 * 100,000 = 50,000`
- `total_cost_basis_reduction = 50,000`
- `holdings = 1.5 BTC`
- `total_cost_basis = 200,000 - 50,000 = 150,000` ✅

**未实现亏损** (假设当前价格 101,000):
- `current_value = 1.5 * 101,000 = 151,500`
- `unrealized_pnl = 151,500 - 150,000 = 1,500` ✅ (正确反映剩余持仓的盈亏)

### 场景 3: 多次买入后卖出

**买入 1 BTC @ 100,000**:
- `holdings = 1.0`
- `total_cost_basis = 100,000`

**买入 1 BTC @ 105,000**:
- `holdings = 2.0`
- `total_cost_basis = 100,000 + 105,000 = 205,000`

**卖出 1 BTC @ 103,000** (匹配到第一个买入 @ 100,000, FIFO):
- `matched_cost_basis = 1.0 * 100,000 = 100,000`
- `total_cost_basis_reduction = 100,000`
- `holdings = 1.0 BTC`
- `total_cost_basis = 205,000 - 100,000 = 105,000` ✅

**未实现亏损** (假设当前价格 103,000):
- `current_value = 1.0 * 103,000 = 103,000`
- `unrealized_pnl = 103,000 - 105,000 = -2,000` ✅ (正确反映剩余持仓的亏损)

## 修复前后对比

### 修复前（Bug）

**买入 1 BTC @ 100,000**:
- `total_cost_basis = 100,000` ✅

**卖出 1 BTC @ 101,000**:
- `total_cost_basis = 100,000` ❌ (没有减少！)

**未实现亏损** (假设当前价格 101,000):
- `holdings = 0.0`
- `unrealized_pnl = 0 * 101,000 - 100,000 = -100,000` ❌ (错误！应该是 0)

**结果**: 即使没有持仓，未实现亏损仍然是 -100,000，导致风控错误触发。

### 修复后

**买入 1 BTC @ 100,000**:
- `total_cost_basis = 100,000` ✅

**卖出 1 BTC @ 101,000**:
- `total_cost_basis = 0.0` ✅

**未实现亏损**:
- `unrealized_pnl = 0` ✅

## 边界情况处理

### 1. 持仓为 0 时成本基础也应为 0
```python
if abs(self.holdings) < 1e-8:
    self.total_cost_basis = 0.0
```
- 确保没有持仓时，成本基础为 0
- 防止浮点数精度问题导致的小误差

### 2. 成本基础不能为负数
```python
self.total_cost_basis = max(0.0, self.total_cost_basis)
```
- 防止因计算误差导致的负数

### 3. 匹配不到持仓的情况
- 如果 `match_result is None`，`total_cost_basis_reduction` 保持为 0.0
- 这种情况下 `total_cost_basis` 不会减少
- 但理论上不应该发生（因为卖出前应该检查 `holdings >= size`）

## 测试建议

### 单元测试场景

1. **简单买入卖出**: 验证成本基础正确归零
2. **部分卖出**: 验证成本基础按比例减少
3. **多次买入后卖出**: 验证 FIFO 匹配逻辑
4. **完全平仓**: 验证持仓为 0 时成本基础为 0
5. **多次部分卖出**: 验证累计减少逻辑

### 回测验证

1. 检查未实现亏损是否合理（不应该在没有持仓时为负数）
2. 检查风控触发是否更合理（不应该过早触发）
3. 对比修复前后的回测结果

## 预期效果

修复后，应该看到：
1. ✅ 未实现亏损计算正确
2. ✅ 风控触发更合理（不会因为 bug 而过早触发）
3. ✅ 最大回撤和未实现亏损的关系更一致

## 相关代码位置

- **买入逻辑**: `algorithms/taogrid/simple_lean_runner.py:378`
- **卖出逻辑**: `algorithms/taogrid/simple_lean_runner.py:496-499`
- **未实现亏损计算**: `algorithms/taogrid/simple_lean_runner.py:254`
- **风控检查**: `algorithms/taogrid/helpers/grid_manager.py:937`

---

**修复日期**: 2025-12-XX  
**修复人**: AI Assistant  
**状态**: ✅ 已修复，待验证
# Neutral Grid Implementation - Issues & Lessons Learned

## 问题记录

### Issue #1: Position Size累加（已修复）
- **错误**：每次成交后累加同一grid的order size
- **修复**：不累加，每个order保持独立size
- **状态**：✓ 已修复

### Issue #2: 每个Bar只处理一个订单（已修复但引入新问题）
- **错误**：同一bar多个订单被触发，但只处理第一个
- **修复**：While loop处理所有触发订单
- **新问题**：导致同一bar内无限re-entry，订单爆炸
- **状态**：❌ 需要重新设计

### Issue #3: 同一Grid Level允许多个订单（核心问题）
- **错误**：Re-entry逻辑没有限制每个grid只能有1个订单
- **表现**：
  - 同一grid被反复触发
  - Position无限堆积
  - 超出资金限制
- **根本原因**：没有复刻交易所"每个grid level最多1个订单"的核心逻辑
- **状态**：❌ 需要重新设计

## 标准网格的正确逻辑

### 交易所网格的特点
1. **Grid Level唯一性**：每个price level最多1个活跃订单
2. **Pairing机制**：Buy@grid[i] → Sell@grid[i+1]
3. **Re-entry条件**：只有当grid的订单被成交后，才能重新挂单
4. **资金管理**：总投资额固定，分配到所有grids

### 我当前实现的问题
1. ❌ 允许同一grid多个订单（通过re-entry）
2. ❌ 没有检查grid是否已有订单
3. ❌ 在同一bar内可以重复re-entry

## 修复方案

### 方案A：Grid Level Order Map
维护一个map：`grid_index -> active_order`，确保每个grid最多1个订单。

```python
class NeutralGridManager:
    def __init__(self):
        self.active_buy_orders: Dict[int, GridOrder] = {}  # grid_index -> order
        self.active_sell_orders: Dict[int, GridOrder] = {}

    def place_order(self, grid_index, direction, price, size):
        # Check if already exists
        if direction == "buy":
            if grid_index in self.active_buy_orders:
                return  # Already has order
            order = GridOrder(...)
            self.active_buy_orders[grid_index] = order
        # Similar for sell
```

### 方案B：简化Re-entry逻辑
不在fill时立即re-entry，而是在下一个bar开始时检查哪些grids缺少订单。

### 方案C：完全重写（推荐）
基于交易所的标准逻辑从头实现：
1. 初始化：所有grids挂单
2. Fill处理：移除成交订单 + 挂对冲单
3. 维护期：每个bar开始时检查并补充缺失的订单
4. 资金检查：确保不超过total_investment

## 下一步

建议：**暂停当前实现，重新用方案C从头写**。

原因：
1. 当前代码已经有太多patch，逻辑混乱
2. 核心设计缺陷（允许多订单）需要大改
3. 从头写更清晰，参考交易所API文档

关键参考：
- Binance Grid Trading API
- OKX Grid Trading Docs
- 确保完全复刻"每个grid level最多1个订单"的核心逻辑

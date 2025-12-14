# TaoGrid 网格配对逻辑修复

> **问题**: 在 111K 附近买入，要到 118K 附近才卖出，不符合网格策略逻辑  
> **修复**: 实现正确的网格层级配对机制

---

## 🐛 问题分析

### 原始问题

从订单数据可以看到：
- **买入**: 在 111K 附近（buy_level[0]）
- **卖出**: 在 118K 附近（sell_level[4] 或更高）

这不符合网格策略的逻辑：
- 网格策略应该是：在 `buy_level[i]` 买入后，应该在**对应的 `sell_level[i]`** 卖出
- 而不是等到价格涨到任意更高的 sell_level 才卖出

### 根本原因

原始的 `check_grid_trigger()` 逻辑：
```python
# 问题：只要价格 >= 任何 sell_level 就卖出
for i, level in enumerate(self.sell_levels):
    if current_price >= level:
        return ("sell", i, level)  # ❌ 没有检查是否有对应的买入持仓
```

这导致：
- 在 buy_level[0] (111K) 买入
- 价格涨到 sell_level[4] (118K) 时，直接触发卖出
- 没有检查这个卖出是否对应 buy_level[0] 的买入

---

## ✅ 修复方案

### 1. 网格配对规则

**配对逻辑**：
- 在 `buy_level[i]` 买入 → 在 `sell_level[i]` 卖出
- 这意味着：买入后，价格回到 mid 附近（一个网格间距）就卖出

**示例**：
```
Mid = 112K, Spacing = 1%
buy_levels[0] = 110.9K  →  sell_levels[0] = 113.1K
buy_levels[1] = 109.8K  →  sell_levels[1] = 114.2K
```

### 2. 实现细节

#### 2.1 买入持仓跟踪

```python
# 在 GridManager 中添加
self.buy_positions: Dict[int, List[dict]] = {}

# 每个买入持仓包含：
{
    'size': float,              # 持仓数量
    'buy_price': float,         # 买入价格
    'target_sell_level': int,   # 目标卖出层级
}
```

#### 2.2 卖出触发逻辑

```python
def check_grid_trigger(self, current_price: float):
    # 买入：价格 <= buy_level 时触发
    for i, level in enumerate(self.buy_levels):
        if current_price <= level and not filled:
            return ("buy", i, level)
    
    # 卖出：价格 >= sell_level 时触发
    # BUT: 只触发有对应买入持仓的 sell_level
    for i, level in enumerate(self.sell_levels):
        # 检查是否有买入持仓目标这个 sell_level
        has_target_position = False
        for buy_level_idx, positions in self.buy_positions.items():
            for pos in positions:
                if pos['target_sell_level'] == i:
                    has_target_position = True
                    break
        
        if has_target_position and current_price >= level:
            return ("sell", i, level)  # ✅ 只触发有持仓的层级
```

#### 2.3 持仓管理

```python
def add_buy_position(self, buy_level_index: int, size: float, buy_price: float):
    """买入后，创建持仓并设置目标卖出层级"""
    target_sell_level = buy_level_index  # 配对：buy[i] -> sell[i]
    
    self.buy_positions[buy_level_index].append({
        'size': size,
        'buy_price': buy_price,
        'target_sell_level': target_sell_level,
    })
    
    # 标记买入层级为已填充（防止重复触发）
    self.filled_levels[f"buy_L{buy_level_index + 1}"] = True

def match_sell_order(self, sell_level_index: int, sell_size: float):
    """卖出时，匹配对应的买入持仓"""
    for buy_level_idx, positions in self.buy_positions.items():
        for pos in positions:
            if pos['target_sell_level'] == sell_level_index:
                # 匹配成功，移除持仓
                matched_size = min(sell_size, pos['size'])
                pos['size'] -= matched_size
                
                if pos['size'] < 0.0001:
                    # 持仓全部卖出，重置买入层级（允许再次触发）
                    del self.filled_levels[f"buy_L{buy_level_idx + 1}"]
                
                return (buy_level_idx, pos['buy_price'], matched_size)
```

---

## 📊 修复效果

### 之前
```
买入: 111K (buy_level[0])
价格涨到 118K (sell_level[4])
→ 直接卖出 ❌ (没有检查配对)
```

### 之后
```
买入: 111K (buy_level[0])
→ 创建持仓，目标: sell_level[0] (113K)
价格涨到 113K (sell_level[0])
→ 触发卖出 ✅ (检查到有对应持仓)
```

---

## 🔧 代码变更

### 主要文件

1. **`algorithms/taogrid/helpers/grid_manager.py`**
   - 添加 `buy_positions` 跟踪买入持仓
   - 修改 `check_grid_trigger()` 只触发有持仓的卖出层级
   - 添加 `add_buy_position()` 管理买入持仓
   - 添加 `match_sell_order()` 匹配卖出订单

2. **`algorithms/taogrid/algorithm.py`**
   - 修改 `on_order_filled()` 调用 `add_buy_position()`

---

## ✅ 验证

修复后，网格策略应该：
- ✅ 在 buy_level[i] 买入后，只在 sell_level[i] 卖出
- ✅ 不会在更高的 sell_level 提前卖出
- ✅ 买入层级卖出后可以再次触发
- ✅ 支持多个买入持仓（不同层级）

---

## 🎯 下一步

可能的进一步优化：
1. **动态目标层级**: 根据市场情况调整目标卖出层级
2. **部分卖出**: 支持部分平仓，保留部分持仓
3. **止损机制**: 在价格下跌时触发止损卖出

---

**修复完成！** 🎉


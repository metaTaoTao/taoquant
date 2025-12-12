# 智能动态网格策略逻辑说明

## 核心改进（相比基础网格策略）

### 1. ✅ 支持做空

**问题**：基础网格策略中，卖单需要先有持仓才能卖出

**解决方案**：
- `allow_shorting=True` 时，卖单可以直接做空
- 做空时：`current_cash += order_size * price`（做空获得资金）
- 做空持仓：`short_position += order_size`

**代码位置**：
```python
# strategies/grid/smart_grid_strategy.py:351-383
if self.config.allow_shorting:
    # 允许做空：直接做空，不需要先有持仓
    order_size = (available_cash * decayed_weight) / grid_price
    orders.append({
        'size': -order_size,  # 负数表示做空
        ...
    })
    current_cash += order_size * grid_price  # 做空获得资金
    short_position += order_size
```

### 2. ✅ 多笔交易

**问题**：基础网格策略中，每个网格只触发一次

**解决方案**：
- `allow_multiple_positions=True` 时，允许多个网格同时持仓
- **也允许同一网格多次触发**（只要不超过最大暴露限制）
- 每个网格的持仓独立跟踪：`self.current_positions[grid_key]`

**代码位置**：
```python
# strategies/grid/smart_grid_strategy.py:347-349, 381-383
# 记录持仓（多笔交易：允许同一网格多次加仓）
if self.config.allow_multiple_positions:
    self.current_positions[grid_key] = self.current_positions.get(grid_key, 0) + order_size
```

### 3. ✅ 几何网格

**问题**：基础网格策略使用线性间距

**解决方案**：
- 几何序列：`price_n = price_0 * (1 ± gap * alpha^n)`
- 价格越远，间距越大
- 符合真实市场的波动结构

**代码位置**：
```python
# strategies/grid/smart_grid_strategy.py:124-126
# 几何序列：间距 = gap * alpha^n
spacing = gap * (self.config.alpha ** n)
price = current_price * (1 - spacing)  # 向下
price = current_price * (1 + spacing)  # 向上
```

**示例**（gap=0.0018, alpha=2.0）：
- Level 0: $117,485（中心）
- Level -1: $117,485 × (1 - 0.0018 × 2^1) = $117,062
- Level -2: $117,485 × (1 - 0.0018 × 2^2) = $116,639
- Level -3: $117,485 × (1 - 0.0018 × 2^3) = $115,793

可以看到：**间距越来越大**（$423 → $1,076 → $846）

### 4. ✅ 边缘加权仓位

**问题**：基础网格策略使用简单的衰减式仓位

**解决方案**：
- 靠近支撑/阻力权重更大
- 中轴附近权重最小
- 权重 = `base_weight × (1 + edge_multiplier × (1 - distance_from_edge))`

**代码位置**：
```python
# strategies/grid/smart_grid_strategy.py:160-175
if direction == 'buy':
    # 买入：靠近支撑（distance ≈ 0）权重最大
    edge_factor = 1.0 + self.config.edge_weight_multiplier * (1.0 - distance)
else:  # sell
    # 卖出：靠近阻力（distance ≈ 0）权重最大
    edge_factor = 1.0 + self.config.edge_weight_multiplier * (1.0 - distance)

weights[i] = self.config.position_fraction * edge_factor
```

**示例**（edge_multiplier=2.0）：
- 靠近支撑（distance=0.1）：权重 = 5% × (1 + 2.0 × 0.9) = 14%
- 中轴附近（distance=0.5）：权重 = 5% × (1 + 2.0 × 0.5) = 10%
- 靠近阻力（distance=0.1）：权重 = 5% × (1 + 2.0 × 0.9) = 14%

### 5. ✅ 命中衰减机制

**问题**：频繁触发的网格可能累积过多风险

**解决方案**：
- 衰减公式：`w_decayed = w_raw × exp(-hits / decay_k)`
- 频繁触发的网格权重自动衰减
- 防止单价格层反复建仓

**代码位置**：
```python
# strategies/grid/smart_grid_strategy.py:195-207
def _apply_hit_decay(self, grid_key, base_weight):
    hits = self.grid_hit_counts.get(grid_key, 0)
    decay_factor = np.exp(-hits / self.config.decay_k)
    return base_weight * decay_factor
```

**示例**（decay_k=2.0）：
- 首次触发（hits=0）：权重 = 100% × exp(0) = 100%
- 第1次触发（hits=1）：权重 = 100% × exp(-0.5) = 60.7%
- 第2次触发（hits=2）：权重 = 100% × exp(-1.0) = 36.8%
- 第3次触发（hits=3）：权重 = 100% × exp(-1.5) = 22.3%

## 完整工作流程

### 场景：中性市场，价格在区间内震荡

1. **初始化**：
   - 生成几何网格（基于区间中点）
   - 计算边缘加权仓位
   - 重置命中计数

2. **价格触及网格线**：
   - 买单（价格下跌）：触发买入/做多
   - 卖单（价格上涨）：触发卖出/做空（不需要先有持仓）

3. **订单生成**：
   - 应用命中衰减（如果启用）
   - 计算订单大小（基于衰减后的权重）
   - 检查最大暴露限制
   - 生成订单

4. **状态更新**：
   - 更新资金和持仓
   - 记录网格持仓（多笔交易）
   - 更新命中计数（用于下次衰减）

5. **重复触发**：
   - 同一网格可以多次触发（多笔交易）
   - 每次触发都会应用衰减
   - 总持仓受最大暴露限制

## 关键参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `grid_gap_pct` | 0.0018 | 基础网格间距（文档建议） |
| `alpha` | 2.0 | 几何序列系数（越大，远端间距越大） |
| `edge_weight_multiplier` | 2.0 | 边缘权重倍数（越大，边缘仓位越重） |
| `decay_k` | 2.0 | 衰减系数（越大，衰减越慢） |
| `allow_shorting` | True | 允许做空 |
| `allow_multiple_positions` | True | 允许多笔交易 |
| `max_exposure_pct` | 0.50 | 最大资金暴露（50%） |

## 与基础网格策略的对比

| 特性 | 基础网格 | 智能网格 |
|------|---------|---------|
| 做空支持 | ❌ | ✅ |
| 多笔交易 | ❌（每个网格只触发一次） | ✅（允许重复触发） |
| 网格类型 | 线性 | 几何 |
| 仓位分配 | 简单衰减 | 边缘加权 + 衰减 |
| 衰减机制 | ❌ | ✅ |
| 动态仓位 | ❌ | ✅ |

## 使用示例

```python
from strategies.grid import SmartGridStrategy, SmartGridConfig, SmartGridBacktester

# 创建配置
config = SmartGridConfig(
    name="Smart Grid",
    description="智能动态网格",
    upper_bound=120000.0,
    lower_bound=115000.0,
    grid_gap_pct=0.0018,  # 文档建议值
    alpha=2.0,
    edge_weight_multiplier=2.0,
    enable_hit_decay=True,
    decay_k=2.0,
    allow_shorting=True,  # 允许做空
    allow_multiple_positions=True,  # 多笔交易
)

# 创建策略和回测器
strategy = SmartGridStrategy(config)
backtester = SmartGridBacktester(strategy)

# 运行回测
result = backtester.run(
    execution_data=data_1m,
    initial_cash=100000.0,
)
```

## 注意事项

1. **做空风险**：做空时需要注意最大暴露限制，避免过度杠杆
2. **多笔交易**：虽然允许同一网格多次触发，但需要控制总持仓
3. **衰减机制**：频繁触发的网格权重会衰减，这是正常行为
4. **几何网格**：远端网格间距较大，可能错过一些交易机会，但更符合市场结构


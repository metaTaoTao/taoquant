# 网格模式说明

## 三种网格模式

### 1. Neutral（中性模式）

**适用场景**：
- 市场在支撑和阻力之间震荡
- 没有明确方向偏好
- 希望双向捕捉波动

**特点**：
- ✅ 双向网格（long + short）
- ✅ 仓位中性，不压方向
- ✅ 买入和卖出权重相等（基于边缘加权）
- ✅ 允许做空（卖单可以直接做空）

**仓位分配**：
- 买入网格：靠近支撑权重更大
- 卖出网格：靠近阻力权重更大
- 中轴附近：权重较小

**示例**：
```python
config = SmartGridConfig(
    grid_mode='Neutral',
    upper_bound=123000.0,
    lower_bound=111500.0,
    ...
)
```

### 2. Long（震荡做多模式）

**适用场景**：
- 价格靠近支撑
- 判断市场可能反弹
- 希望偏向做多，但保留平仓能力

**特点**：
- ✅ 偏向做多（买入权重 × 2.0）
- ⚠️ 减少做空（卖出权重 × 0.3，主要用于平多）
- ✅ 如果有持仓，优先平多
- ✅ 不是 All-in，而是 grid size + zone-based sizing

**仓位分配**：
- 买入网格：权重加倍（2.0倍）
- 卖出网格：权重减少（0.3倍），主要用于平多
- 如果无持仓，卖出网格基本不触发

**示例**：
```python
config = SmartGridConfig(
    grid_mode='Long',  # 震荡做多
    upper_bound=123000.0,
    lower_bound=111500.0,
    ...
)
```

### 3. Short（震荡做空模式）

**适用场景**：
- 价格靠近阻力
- 判断市场可能回调
- 希望偏向做空，但保留平仓能力

**特点**：
- ✅ 偏向做空（卖出权重 × 2.0）
- ⚠️ 减少做多（买入权重 × 0.3，主要用于平空）
- ✅ 如果有空头持仓，优先平空
- ✅ 不是 All-in，而是 grid size + zone-based sizing

**仓位分配**：
- 卖出网格：权重加倍（2.0倍）
- 买入网格：权重减少（0.3倍），主要用于平空
- 如果无空头持仓，买入网格基本不触发

**示例**：
```python
config = SmartGridConfig(
    grid_mode='Short',  # 震荡做空
    upper_bound=123000.0,
    lower_bound=111500.0,
    ...
)
```

## 模式切换逻辑

### 动态切换建议

根据市场状态动态切换模式：

```python
# 判断当前价格位置
current_price = data['close'].iloc[-1]
mid_price = (upper_bound + lower_bound) / 2.0
distance_from_support = (current_price - lower_bound) / (upper_bound - lower_bound)
distance_from_resistance = (upper_bound - current_price) / (upper_bound - lower_bound)

# 切换逻辑
if distance_from_support < 0.2:  # 靠近支撑
    grid_mode = 'Long'  # 震荡做多
elif distance_from_resistance < 0.2:  # 靠近阻力
    grid_mode = 'Short'  # 震荡做空
else:
    grid_mode = 'Neutral'  # 中性
```

### 突破后切换

根据文档，突破后可以切换模式：

```python
# 突破阻力 → 切换到 Long（跟随趋势）
if price > upper_bound:
    grid_mode = 'Long'  # 突破后做多

# 跌破支撑 → 切换到 Short（跟随趋势）
if price < lower_bound:
    grid_mode = 'Short'  # 跌破后做空
```

## 权重调整公式

### Neutral 模式
```
buy_weight = base_weight × edge_factor × 1.0
sell_weight = base_weight × edge_factor × 1.0
```

### Long 模式
```
buy_weight = base_weight × edge_factor × 2.0  # 做多方向加倍
sell_weight = base_weight × edge_factor × 0.3  # 做空方向减少（主要用于平多）
```

### Short 模式
```
buy_weight = base_weight × edge_factor × 0.3  # 做多方向减少（主要用于平空）
sell_weight = base_weight × edge_factor × 2.0  # 做空方向加倍
```

## 使用示例

### 示例1：中性市场（7.21开始）

```python
config = SmartGridConfig(
    grid_mode='Neutral',
    upper_bound=123000.0,
    lower_bound=111500.0,
    ...
)
```

### 示例2：突破阻力后切换为 Long

```python
# 初始：Neutral
config = SmartGridConfig(
    grid_mode='Neutral',
    ...
)

# 突破后：切换为 Long
if price > upper_bound:
    config.grid_mode = 'Long'
```

### 示例3：价格靠近支撑，使用 Long 模式

```python
# 判断价格位置
if current_price < lower_bound * 1.02:  # 靠近支撑
    config = SmartGridConfig(
        grid_mode='Long',  # 震荡做多
        ...
    )
```

## 注意事项

1. **不是 All-in**：Long/Short 模式不是完全单向，而是权重调整
2. **保留平仓能力**：即使 Long 模式，卖出网格仍保留（权重较小），用于平多
3. **动态切换**：可以根据市场状态动态切换模式
4. **风险控制**：最大暴露限制仍然有效，不会因为模式切换而过度暴露


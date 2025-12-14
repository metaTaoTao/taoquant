# TaoGrid 限价单模式实现

## 概述

将 TaoGrid 策略从"市价单触发模式"重构为"限价单模式"，实现真正的网格交易逻辑：
- **挂限价单**：在网格层级挂限价单，等待价格触发
- **限价单成交**：价格穿过限价单价格时成交
- **立即挂新单**：成交后立即在配对层级挂新的限价单

## 实现细节

### 1. GridManager 限价单管理

#### 1.1 待挂限价单列表

```python
# algorithms/taogrid/helpers/grid_manager.py

self.pending_limit_orders: List[dict] = []
```

每个限价单包含：
- `direction`: 'buy' 或 'sell'
- `level_index`: 网格层级索引
- `price`: 网格层级价格（限价单价格）
- `size`: 订单大小（触发时计算）
- `placed`: 是否已挂单

#### 1.2 初始化限价单

```python
def _initialize_pending_orders(self) -> None:
    """初始化时在所有买入层级挂限价单"""
    # 在所有 buy_levels 挂买入限价单
    for i, level_price in enumerate(self.buy_levels):
        if not self.filled_levels.get(f"buy_L{i+1}", False):
            self.pending_limit_orders.append({
                'direction': 'buy',
                'level_index': i,
                'price': level_price,
                'size': None,
                'placed': True,
            })
```

**初始化逻辑**：
- 策略启动时，在所有买入层级挂限价单
- 卖出限价单在买入成交后自动挂出

#### 1.3 限价单触发检测

```python
def check_limit_order_triggers(
    self, 
    current_price: float,
    prev_price: Optional[float] = None,
    bar_high: Optional[float] = None,
    bar_low: Optional[float] = None
) -> Optional[dict]:
    """检查限价单是否被触发"""
```

**触发逻辑**：
- **买入限价单**：当 `bar_low <= limit_price` 且 `prev_price > limit_price` 时触发（价格向下穿过限价单）
- **卖出限价单**：当 `bar_high >= limit_price` 且 `prev_price < limit_price` 时触发（价格向上穿过限价单）

**为什么需要 `prev_price`**：
- 避免在同一根 K 线内重复触发
- 确保价格真正"穿过"限价单价格，而不是仅仅"触及"

### 2. Algorithm 限价单处理

#### 2.1 on_data() 方法

```python
def on_data(self, current_time: datetime, bar_data: dict, portfolio_state: dict):
    """每个 bar 检查限价单是否被触发"""
    # 检查限价单触发
    triggered_order = self.grid_manager.check_limit_order_triggers(
        current_price=current_price,
        prev_price=prev_price,
        bar_high=bar_high,
        bar_low=bar_low
    )
    
    if triggered_order is None:
        return None  # 没有限价单被触发
    
    # 计算订单大小
    size, throttle_status = self.grid_manager.calculate_order_size(...)
    
    # 返回订单
    return order
```

#### 2.2 on_order_filled() 方法

```python
def on_order_filled(self, order: dict):
    """限价单成交后，立即挂新的配对限价单"""
    if direction == "buy":
        # 移除已成交的买入限价单
        self.grid_manager.remove_pending_order('buy', level)
        # 挂卖出限价单（配对层级）
        target_sell_level = level  # buy[i] -> sell[i]
        self.grid_manager.place_pending_order('sell', target_sell_level, target_sell_price)
        
    elif direction == "sell":
        # 移除已成交的卖出限价单
        self.grid_manager.remove_pending_order('sell', level)
        # 挂新的买入限价单（同一层级，重新入场）
        self.grid_manager.place_pending_order('buy', level, buy_level_price)
```

**配对逻辑**：
- **买入成交** → 挂卖出限价单（配对层级，`buy[i] -> sell[i]`）
- **卖出成交** → 挂买入限价单（同一层级，重新入场）

### 3. SimpleLeanRunner 执行逻辑

`SimpleLeanRunner` 已经正确处理限价单价格：

```python
def execute_order(self, order: dict, market_price: float, timestamp: datetime):
    """使用网格层级价格执行订单（不是市场价格）"""
    grid_level_price = order.get('price')  # 限价单价格
    execution_price = grid_level_price  # 使用限价单价格
    # ... 执行订单
```

**关键点**：
- 使用 `order['price']`（网格层级价格）执行，而不是 `market_price`
- 确保网格间距被正确遵守

## 工作流程

### 初始化阶段

```
1. setup_grid() → 生成网格层级
2. _initialize_pending_orders() → 在所有买入层级挂限价单
   - buy_L1 @ $110,000
   - buy_L2 @ $109,800
   - buy_L3 @ $109,600
   - ...
```

### 运行阶段（每个 bar）

```
1. check_limit_order_triggers() → 检查限价单是否被触发
   - 如果 bar_low <= buy_limit_price → 买入限价单触发
   - 如果 bar_high >= sell_limit_price → 卖出限价单触发

2. 如果触发：
   - calculate_order_size() → 计算订单大小
   - execute_order() → 执行订单（使用限价单价格）
   - on_order_filled() → 挂新的配对限价单
```

### 示例流程

```
初始状态：
  - 挂买入限价单 @ $110,000 (buy_L1)

价格下跌到 $110,000：
  - 买入限价单触发 → 成交 @ $110,000
  - 移除买入限价单
  - 挂卖出限价单 @ $110,193 (sell_L1, 1x spacing)

价格上涨到 $110,193：
  - 卖出限价单触发 → 成交 @ $110,193
  - 移除卖出限价单
  - 挂新的买入限价单 @ $110,000 (buy_L1, 重新入场)

循环往复...
```

## 优势

### 1. 真实的网格交易逻辑

- **之前**：价格触发网格层级 → 立即市价下单
- **现在**：在网格层级挂限价单 → 等待价格触发 → 成交

### 2. 更准确的回测

- 限价单价格 = 网格层级价格
- 确保网格间距被正确遵守
- 避免市场价格波动导致的滑点

### 3. 更接近实盘

- 实盘网格策略就是挂限价单
- 回测逻辑与实盘逻辑一致

## 注意事项

### 1. 限价单触发检测

- 使用 `prev_price` 和 `bar_high/bar_low` 检测价格"穿过"限价单
- 避免在同一根 K 线内重复触发

### 2. 配对逻辑

- 买入成交 → 挂卖出限价单（配对层级）
- 卖出成交 → 挂买入限价单（同一层级，重新入场）

### 3. 价格执行

- 使用网格层级价格执行，不是市场价格
- 确保网格间距被正确遵守

## 测试建议

1. **验证限价单触发**：
   - 检查限价单是否在正确价格触发
   - 检查是否避免重复触发

2. **验证配对逻辑**：
   - 买入成交后是否立即挂卖出限价单
   - 卖出成交后是否立即挂买入限价单

3. **验证价格执行**：
   - 订单价格是否等于网格层级价格
   - 买卖价格差是否等于网格间距（1x spacing）

## 相关文件

- `algorithms/taogrid/helpers/grid_manager.py` - 限价单管理
- `algorithms/taogrid/algorithm.py` - 限价单触发处理
- `algorithms/taogrid/simple_lean_runner.py` - 订单执行


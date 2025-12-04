# 使用 VectorBT 实现网格策略

## VectorBT 对网格策略的支持

**答案：是的，VectorBT 可以用来实现网格策略，但需要正确使用其 API。**

## VectorBT 的能力

### ✅ 支持的功能

1. **动态订单生成** - 使用 `Portfolio.from_order_func()`
   - 可以在每个 bar 动态决定是否下单
   - 支持复杂的状态机逻辑
   - 可以维护网格状态（当前网格价格、已挂单等）

2. **部分成交** - 支持部分成交
   - `from_orders()` 和 `from_order_func()` 都支持部分成交
   - 可以精确控制每次交易的量

3. **多订单管理** - 可以在同一个 bar 生成多个订单
   - 使用 `flexible=True` 参数
   - 可以同时下多个买单和卖单

### ⚠️ 限制

1. **撤单的模拟** - VectorBT 不直接支持"撤单"操作
   - 但可以通过不在下一个 bar 生成订单来模拟撤单
   - 或者通过 `from_order_func()` 动态决定是否生成订单

2. **限价单的精确模拟** - VectorBT 主要基于 OHLC 数据
   - 无法精确模拟限价单在 bar 内的成交价格
   - 通常假设订单在 bar 的 close 价格成交

3. **订单簿模拟** - 不支持真实的订单簿
   - 无法模拟订单簿的深度和流动性
   - 无法模拟滑点对订单簿的影响

## 实现方案

### 方案 1: 使用 `from_order_func()` 实现网格策略

```python
import vectorbt as vbt
import pandas as pd
import numpy as np

def grid_order_func(close, size, size_type, direction, fees, slippage, 
                    min_size, max_size, reject_prob, lock_cash, 
                    allow_partial, raise_reject, log, group_by, 
                    cash_sharing, call_seq, auto_call_seq, 
                    ffill_val_price, update_value, settle_cash, 
                    accumulate, use_stops, stop_entry_price, 
                    stop_exit_price, stop_conf, stop_conf_isl, 
                    stop_conf_tsl, stop_trail, stop_args, 
                    stop_kwargs, sl_stop, tp_stop, 
                    **kwargs):
    """
    网格策略的订单生成函数
    
    在每个 bar，根据当前价格和网格状态决定是否下单
    """
    n_bars = len(close)
    orders = np.zeros(n_bars)
    
    # 网格参数
    grid_spacing = 0.01  # 1% 网格间距
    grid_levels = 10     # 上下各10层网格
    base_price = close.iloc[0]  # 基准价格
    
    # 维护网格状态
    grid_state = {
        'buy_orders': {},   # {price: remaining_size}
        'sell_orders': {},  # {price: remaining_size}
        'position': 0.0,    # 当前持仓
    }
    
    for i in range(n_bars):
        current_price = close.iloc[i]
        
        # 1. 检查已挂订单是否成交
        # 买单成交：价格 >= 订单价格
        for price in list(grid_state['buy_orders'].keys()):
            if current_price <= price:  # 价格跌到或低于买单价格
                # 订单成交
                order_size = grid_state['buy_orders'].pop(price)
                grid_state['position'] += order_size
                orders[i] += order_size  # 正数表示买入
        
        # 卖单成交：价格 >= 订单价格
        for price in list(grid_state['sell_orders'].keys()):
            if current_price >= price:  # 价格涨到或高于卖单价格
                # 订单成交
                order_size = grid_state['sell_orders'].pop(price)
                grid_state['position'] -= order_size
                orders[i] -= order_size  # 负数表示卖出
        
        # 2. 根据当前价格和持仓，决定是否下新订单
        # 计算网格价格
        price_diff = current_price - base_price
        grid_index = int(price_diff / (base_price * grid_spacing))
        
        # 如果价格偏离基准价格，在下方挂买单，上方挂卖单
        if grid_index < 0:  # 价格低于基准
            # 在下方挂买单
            buy_price = base_price * (1 - abs(grid_index) * grid_spacing)
            if buy_price not in grid_state['buy_orders']:
                grid_state['buy_orders'][buy_price] = 0.1  # 挂买单
                # 注意：这里不能直接修改 orders[i]，因为订单还没成交
                # 需要在下一个 bar 检查是否成交
        
        if grid_index > 0:  # 价格高于基准
            # 在上方挂卖单
            sell_price = base_price * (1 + abs(grid_index) * grid_spacing)
            if sell_price not in grid_state['sell_orders']:
                grid_state['sell_orders'][sell_price] = 0.1  # 挂卖单
    
    return orders

# 使用 from_order_func 创建组合
portfolio = vbt.Portfolio.from_order_func(
    close=close_prices,
    order_func=grid_order_func,
    size_type='amount',  # 使用绝对数量
    init_cash=10000,
    fees=0.001,  # 0.1% 手续费
)
```

### 方案 2: 使用 `from_orders()` 预先生成订单序列

```python
def generate_grid_orders(data: pd.DataFrame, 
                        grid_spacing: float = 0.01,
                        grid_levels: int = 10) -> pd.Series:
    """
    预先生成网格订单序列
    
    这种方法更简单，但无法动态撤单
    """
    close = data['close']
    orders = pd.Series(0.0, index=close.index)
    
    base_price = close.iloc[0]
    
    for i in range(len(close)):
        current_price = close.iloc[i]
        price_diff = current_price - base_price
        grid_index = int(price_diff / (base_price * grid_spacing))
        
        # 根据网格位置决定订单
        if grid_index < -grid_levels:
            # 价格太低，买入
            orders.iloc[i] = 0.1
        elif grid_index > grid_levels:
            # 价格太高，卖出
            orders.iloc[i] = -0.1
    
    return orders

# 使用预生成的订单
orders = generate_grid_orders(data)
portfolio = vbt.Portfolio.from_orders(
    close=data['close'],
    size=orders,
    size_type='amount',
    init_cash=10000,
    fees=0.001,
)
```

## 推荐实现方式

对于网格策略，推荐使用 **方案 1 (`from_order_func()`)**，因为：

1. **灵活性更高** - 可以动态管理订单状态
2. **更接近真实交易** - 可以模拟挂单、成交、撤单
3. **状态管理** - 可以在函数内部维护网格状态

## 注意事项

1. **性能考虑** - `from_order_func()` 是逐 bar 执行的，比向量化操作慢
   - 但对于网格策略，这是必要的权衡

2. **撤单模拟** - VectorBT 不直接支持撤单
   - 可以通过不在下一个 bar 生成订单来模拟
   - 或者通过状态管理，跳过已撤订单

3. **限价单价格** - VectorBT 假设订单在 bar 的 close 价格成交
   - 如果需要更精确的模拟，可能需要使用 tick 数据或自定义引擎

## 总结

**VectorBT 可以用于网格策略回测**，但需要：
- 使用 `from_order_func()` 实现动态订单管理
- 在函数内部维护网格状态和订单簿
- 通过状态管理模拟撤单操作

如果需要更精确的订单簿模拟或 tick 级别的回测，可能需要考虑其他框架（如 Backtrader）或自定义引擎。


# 网格策略执行说明

## 1分钟K线执行 vs 15分钟K线执行

### 核心区别

**1分钟K线执行（推荐）：**
- ✅ 更精确地捕捉网格触发
- ✅ 更真实的成交模拟
- ✅ 更准确的回测收益统计
- ✅ 能捕捉到15分钟K线可能错过的触发机会

**15分钟K线执行：**
- ⚠️ 可能错过网格触发（如果价格在15分钟内触及网格线但收盘价不在）
- ⚠️ 成交时间不够精确
- ⚠️ 回测收益可能不准确

### 示例对比

假设网格价格是 $90,000：

**场景1：价格在15分钟内触及网格线**
- 15分钟K线：high=$90,100, low=$89,800, close=$89,900
- 1分钟K线：第3分钟时 low=$89,950（触及网格），第8分钟时 high=$90,050

**结果：**
- 15分钟K线：可能检测到触发（如果网格价格在high/low范围内）
- 1分钟K线：**精确检测到第3分钟触发**，成交时间更准确

**场景2：价格快速波动**
- 15分钟K线：high=$90,200, low=$89,700, close=$89,950
- 1分钟K线：第2分钟触及下网格，第5分钟触及上网格

**结果：**
- 15分钟K线：可能只检测到一次触发
- 1分钟K线：**检测到两次触发**，收益更准确

## 使用方法

### 方式1：直接使用1分钟数据（推荐）

```python
from data.data_manager import DataManager
from strategies.grid import GridStrategy, GridStrategyConfig, GridBacktester

# 获取1分钟数据
data_manager = DataManager()
execution_data = data_manager.get_klines(
    symbol="BTCUSDT",
    timeframe="1m",  # 1分钟数据
    source="okx"
)

# 创建策略（网格设置独立于数据时间框架）
config = GridStrategyConfig(
    upper_bound=123000.0,
    lower_bound=111500.0,
    grid_spacing_pct=1.5,
    # ... 其他参数
)

strategy = GridStrategy(config)
backtester = GridBacktester(strategy)

# 在1分钟数据上执行
result = backtester.run(
    execution_data=execution_data,  # 1分钟数据
    initial_cash=100000.0,
)
```

### 方式2：网格设置基于15分钟，执行使用1分钟

```python
# 获取15分钟数据用于分析（可选）
data_15m = data_manager.get_klines("BTCUSDT", "15m", source="okx")

# 基于15分钟数据确定网格区间（交易员手动判断）
upper_bound = 123000.0  # 基于15分钟阻力
lower_bound = 111500.0  # 基于15分钟支撑

# 但执行使用1分钟数据
execution_data = data_manager.get_klines("BTCUSDT", "1m", source="okx")

# 创建策略和执行
config = GridStrategyConfig(
    upper_bound=upper_bound,  # 基于15分钟分析
    lower_bound=lower_bound,  # 基于15分钟分析
    grid_spacing_pct=1.5,
)

strategy = GridStrategy(config)
backtester = GridBacktester(strategy)

# 在1分钟数据上执行（更精确）
result = backtester.run(execution_data=execution_data)
```

## 性能考虑

### 数据量

- **1分钟数据量**：1天 = 1440条，1个月 ≈ 43,200条
- **15分钟数据量**：1天 = 96条，1个月 ≈ 2,880条

### 优化建议

1. **数据缓存**：使用 `use_cache=True` 缓存1分钟数据
2. **日期范围**：只获取需要的日期范围，不要获取过多历史数据
3. **分批回测**：如果数据量很大，可以分批回测然后合并结果

### 内存使用

1分钟数据的内存使用大约是15分钟数据的15倍，但现代计算机通常可以轻松处理。

## 测试验证

运行测试脚本验证1分钟执行：

```bash
python strategies/grid/test_1m_execution.py
```

这个脚本会：
1. 获取1分钟数据
2. 生成网格订单
3. 运行回测
4. 对比1分钟 vs 15分钟的执行结果

## 总结

**推荐使用1分钟K线执行网格策略**，因为：
1. ✅ 更精确的成交判断
2. ✅ 更真实的回测收益
3. ✅ 能捕捉更多网格触发机会
4. ✅ 成交时间更准确

网格设置（区间、间距等）可以基于任何时间框架的分析，但**执行应该使用1分钟数据**。


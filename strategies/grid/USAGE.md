# 网格策略优化工具 - 使用指南

## 快速开始

### 1. 基本使用

```python
from strategies.grid import GridOptimizer, OptimizationBounds
from data.data_manager import DataManager
import pandas as pd

# 获取数据
data_manager = DataManager()
data = data_manager.get_klines("BTCUSDT", "15m", source="okx")

# 设置网格区间（交易员手动判断）
start_date = pd.Timestamp("2024-08-01", tz='UTC')  # 注意：使用实际数据日期
upper_bound = 85000.0  # 上界
lower_bound = 65000.0  # 下界

# 创建优化器
optimizer = GridOptimizer(
    data=data,
    upper_bound=upper_bound,
    lower_bound=lower_bound,
    start_date=start_date,
    initial_cash=100000.0,
)

# 运行优化
result = optimizer.optimize(max_iterations=50)

# 查看结果
print(f"最优 Sharpe Ratio: {result.best_sharpe:.3f}")
print(f"最优参数: {result.best_params}")
```

### 2. 运行示例脚本

```bash
# Windows PowerShell
$env:PYTHONPATH="C:\Users\tzhang\PycharmProjects\taoquant"
python strategies/grid/example_optimization.py

# 或者快速测试
python strategies/grid/test_grid_quick.py
```

## 重要注意事项

### 1. 数据日期范围

**问题：** 如果设置的开始日期早于数据开始日期，优化器会自动使用数据开始日期。

**解决方案：**
- 检查数据日期范围：`data.index[0]` 到 `data.index[-1]`
- 确保 `start_date` 在数据范围内
- 或者获取更早的数据

```python
# 检查数据范围
print(f"数据范围: {data.index[0]} 到 {data.index[-1]}")

# 使用数据开始日期
start_date = data.index[0]
```

### 2. 价格区间设置

**问题：** 如果设置的网格区间超出数据价格范围，可能无法生成订单。

**解决方案：**
- 检查数据价格范围：`data['close'].min()` 到 `data['close'].max()`
- 确保网格区间在价格范围内
- 建议：区间宽度 = 数据价格范围的 20-40%

```python
# 基于数据自动设置区间
price_min = data['close'].quantile(0.1)
price_max = data['close'].quantile(0.9)
mid_price = (price_min + price_max) / 2

lower_bound = mid_price - (price_max - price_min) * 0.3
upper_bound = mid_price + (price_max - price_min) * 0.3
```

### 3. 优化时间

**优化可能需要较长时间**（几分钟到几十分钟），取决于：
- 数据量
- 优化迭代次数（`max_iterations`）
- 种群大小（`population_size`）

**建议：**
- 先用小数据集测试（如 `test_grid_quick.py`）
- 减少迭代次数进行快速测试（`max_iterations=10`）
- 确认功能正常后再进行完整优化

### 4. 参数范围设置

**合理的参数范围：**

```python
bounds = OptimizationBounds(
    grid_spacing_pct=(0.5, 2.5),      # 网格间距：0.5% - 2.5%
    position_fraction=(0.03, 0.08),    # 单格仓位：3% - 8%
    max_exposure_pct=(0.30, 0.50),     # 最大暴露：30% - 50%
    weight_decay_param=(0.10, 0.30),   # 衰减参数：0.1 - 0.3
)
```

**根据市场调整：**
- 高波动市场：增大 `grid_spacing_pct`（1.5% - 3%）
- 低波动市场：减小 `grid_spacing_pct`（0.5% - 1.5%）
- 保守策略：减小 `max_exposure_pct`（20% - 40%）
- 激进策略：增大 `max_exposure_pct`（40% - 60%）

## 常见问题

### Q1: 没有生成订单？

**可能原因：**
1. 价格没有触及网格线
2. 网格区间超出数据价格范围
3. 网格间距太大

**解决方法：**
- 检查数据价格范围
- 减小网格间距
- 扩大网格区间

### Q2: Sharpe Ratio 为 0 或负数？

**可能原因：**
1. 交易次数太少
2. 没有盈利交易
3. 数据量不足

**解决方法：**
- 增加数据量
- 调整网格间距（更小的间距 = 更多交易）
- 检查网格区间是否合理

### Q3: 优化时间太长？

**解决方法：**
- 减少 `max_iterations`（如 20-30）
- 减少 `population_size`（如 10）
- 使用更小的数据集测试

### Q4: 如何验证优化结果？

**建议：**
1. 使用样本外数据验证
2. 检查参数是否在边界上（可能过拟合）
3. 多次运行优化，检查结果稳定性

## 输出结果

优化完成后，结果保存在 `run/results/grid_optimization_*.json`：

```json
{
  "symbol": "BTCUSDT",
  "timeframe": "15m",
  "start_date": "2024-08-01",
  "upper_bound": 85000.0,
  "lower_bound": 65000.0,
  "best_params": {
    "grid_spacing_pct": 1.25,
    "position_fraction": 0.045,
    "max_exposure_pct": 0.38,
    "weight_decay_param": 0.18
  },
  "best_sharpe": 2.345,
  "metrics": {
    "total_return": 12.5,
    "max_drawdown": -3.2,
    "win_rate": 65.0
  }
}
```

## 下一步

1. **验证结果**：使用样本外数据回测
2. **实盘测试**：小资金实盘验证
3. **参数调整**：根据实盘表现微调
4. **风险监控**：设置止损和风险限制

## 参考

- `strategies/grid/README.md` - 完整文档
- `strategies/grid/example_optimization.py` - 完整示例
- `strategies/grid/test_grid_quick.py` - 快速测试
- `docs/网格策略的研究.pdf` - 策略研究文档


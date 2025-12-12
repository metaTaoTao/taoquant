# 网格策略回测与优化工具

## 概述

这是一个网格策略回测和参数优化工具，基于文档《网格策略的研究.pdf》的 Part 4（网格区间内的仓位管理）。

**核心功能：**
- 在指定价格区间内设置网格
- 衰减式仓位分配（底部重，顶部轻）
- **使用1分钟K线精确执行订单**（更真实的成交模拟）
- 自动回测网格策略
- **参数优化以最大化 Sharpe Ratio**

**重要特性：**
- ✅ **1分钟K线执行**：使用1分钟数据判断订单成交，比15分钟数据更精确
- ✅ **网格设置独立**：网格区间由交易员手动设置，不依赖数据时间框架
- ✅ **真实回测**：基于1分钟K线的high/low判断网格触发，更接近实盘

## 使用场景

**典型工作流程：**
1. 交易员手动判断市场环境（Part 1: Regime Detection）
2. 交易员手动确定网格区间（Part 3: 支撑/阻力）
3. **使用本工具优化仓位管理参数（Part 4），目标：最大化 Sharpe Ratio**

## 快速开始

### 示例：优化 BTCUSDT 网格策略（1分钟K线执行）

```python
from datetime import datetime
import pandas as pd
from data.data_manager import DataManager
from strategies.grid import GridOptimizer, OptimizationBounds

# 1. 获取1分钟执行数据（更精确）
data_manager = DataManager()
execution_data = data_manager.get_klines(
    symbol="BTCUSDT",
    timeframe="1m",  # 使用1分钟数据执行
    source="okx"
)

# 2. 设置网格区间（交易员手动判断）
start_date = pd.Timestamp("2024-07-21", tz='UTC')
upper_bound = 123000.0  # 上界
lower_bound = 111500.0  # 下界

# 3. 创建优化器
optimizer = GridOptimizer(
    data=data,
    upper_bound=upper_bound,
    lower_bound=lower_bound,
    start_date=start_date,
    initial_cash=100000.0,
    commission=0.001,  # 0.1%
    slippage=0.0005,   # 0.05%
    weight_decay_type='exponential',
    bounds=OptimizationBounds(
        grid_spacing_pct=(0.5, 2.5),      # 网格间距 0.5% - 2.5%
        position_fraction=(0.03, 0.08),    # 单格仓位 3% - 8%
        max_exposure_pct=(0.30, 0.50),     # 最大暴露 30% - 50%
        weight_decay_param=(0.10, 0.30),   # 衰减参数
    )
)

# 4. 运行优化
result = optimizer.optimize(
    method='differential_evolution',
    max_iterations=50,
    population_size=15
)

# 5. 查看结果
print(f"最优 Sharpe Ratio: {result.best_sharpe:.3f}")
print(f"最优参数:")
print(f"  网格间距: {result.best_params['grid_spacing_pct']:.2f}%")
print(f"  单格仓位: {result.best_params['position_fraction']*100:.2f}%")
print(f"  最大暴露: {result.best_params['max_exposure_pct']*100:.2f}%")
print(f"  衰减参数: {result.best_params['weight_decay_param']:.3f}")
```

### 运行示例脚本

```bash
python strategies/grid/example_optimization.py
```

## 核心组件

### 1. GridStrategy（网格策略）

实现网格策略的核心逻辑：
- 生成网格价格水平
- 衰减式仓位分配（linear/exponential/power）
- 网格订单生成

```python
from strategies.grid import GridStrategy, GridStrategyConfig

config = GridStrategyConfig(
    name="Grid Strategy",
    description="My grid strategy",
    upper_bound=123000.0,
    lower_bound=111500.0,
    grid_spacing_pct=1.5,      # 网格间距 1.5%
    position_fraction=0.05,     # 单格仓位 5%
    max_exposure_pct=0.40,     # 最大暴露 40%
    weight_decay_type='exponential',
    weight_decay_param=0.15,
)

strategy = GridStrategy(config)
grid_levels = strategy.generate_grid_levels()  # 查看网格水平
```

### 2. GridBacktester（回测引擎）

使用 VectorBT 进行高性能回测，**支持1分钟K线精确执行**：

```python
from strategies.grid import GridBacktester

backtester = GridBacktester(strategy)

# 使用1分钟数据执行（推荐）
result = backtester.run(
    execution_data=execution_data_1m,  # 1分钟数据
    start_date=start_date,
    initial_cash=100000.0,
    commission=0.001,
    slippage=0.0005,
)
```

**为什么使用1分钟数据？**
- 更精确地捕捉网格触发：1分钟K线的high/low能更准确地判断价格是否触及网格线
- 更真实的成交模拟：15分钟K线可能错过很多网格触发机会
- 更准确的回测收益：订单成交时间更精确，收益统计更真实

# 查看结果
print(f"Sharpe Ratio: {result.metrics['sharpe_ratio']:.3f}")
print(f"总收益率: {result.metrics['total_return']:.2f}%")
print(f"最大回撤: {result.metrics['max_drawdown']:.2f}%")
```

### 3. GridOptimizer（参数优化器）

优化仓位管理参数，目标：最大化 Sharpe Ratio

**优化参数：**
- `grid_spacing_pct`: 网格间距（价格百分比）
- `position_fraction`: 单格仓位比例（资金的百分比）
- `max_exposure_pct`: 最大资金暴露
- `weight_decay_param`: 仓位衰减参数

**优化方法：**
- `differential_evolution`: 差分进化算法（全局优化，推荐）
- `minimize`: 局部优化（L-BFGS-B）

## 参数说明

### GridStrategyConfig

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `upper_bound` | float | - | 网格上界（阻力） |
| `lower_bound` | float | - | 网格下界（支撑） |
| `grid_spacing_pct` | float | 1.5 | 网格间距（%） |
| `position_fraction` | float | 0.05 | 单格仓位比例（0-1） |
| `max_exposure_pct` | float | 0.40 | 最大资金暴露（0-1） |
| `weight_decay_type` | str | 'exponential' | 衰减类型：'linear', 'exponential', 'power' |
| `weight_decay_param` | float | 0.15 | 衰减强度参数 |
| `commission` | float | 0.001 | 手续费率 |
| `slippage` | float | 0.0005 | 滑点率 |

### OptimizationBounds

参数优化边界：

```python
bounds = OptimizationBounds(
    grid_spacing_pct=(0.5, 3.0),      # 网格间距范围
    position_fraction=(0.03, 0.10),   # 单格仓位范围
    max_exposure_pct=(0.20, 0.60),    # 最大暴露范围
    weight_decay_param=(0.05, 0.50),  # 衰减参数范围
)
```

## 仓位衰减类型

### 1. Linear（线性衰减）
```
w = 1 - α * normalized_level
```
- 底部权重 = 1
- 顶部权重 = 1 - α

### 2. Exponential（指数衰减，推荐）
```
w = exp(-α * normalized_level)
```
- 底部权重 = 1
- 顶部权重 = exp(-α)

### 3. Power（幂衰减）
```
w = (1 - normalized_level)^α
```
- 底部权重 = 1
- 顶部权重 = 0（当 α 足够大时）

## 输出结果

优化完成后，结果保存在 `run/results/grid_optimization_*.json`：

```json
{
  "symbol": "BTCUSDT",
  "timeframe": "15m",
  "start_date": "2024-07-21",
  "upper_bound": 123000.0,
  "lower_bound": 111500.0,
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
    "win_rate": 65.0,
    ...
  }
}
```

## 注意事项

1. **数据质量**：确保数据完整，没有缺失值
2. **区间设置**：上下界应该基于技术分析（支撑/阻力）
3. **优化时间**：参数优化可能需要几分钟到几十分钟，取决于：
   - 数据量
   - 优化迭代次数
   - 种群大小
4. **过拟合风险**：优化结果可能过拟合历史数据，建议：
   - 使用样本外数据验证
   - 不要过度优化参数
   - 关注 Sharpe Ratio 的稳定性

## 依赖

- `pandas >= 1.5`
- `numpy >= 1.21`
- `scipy >= 1.9.0`（用于优化）
- `vectorbt >= 0.25.0`（用于回测）

## 参考文档

- `docs/网格策略的研究.pdf` - 网格策略研究文档
- `docs/网格策略-辅助工具视角评估.md` - 辅助工具评估


# TaoQuant 开发日志 - VectorBT 迁移后的改进记录

> **版本**: 2.0+  
> **日期**: 2025-12-03  
> **状态**: 持续开发中

---

## 📋 概述

本文档记录了从 Claude Code 完成 Phase 1 和 Phase 2（VectorBT 迁移）后，AI Assistant 进行的主要改进、修复和功能增强。这些改进确保了系统的稳定性和功能的完整性。

---

## 🎯 初始状态

### 已完成的工作（Claude Code）

根据 `docs/phase1_completion_summary.md` 和 `docs/phase2_completion_summary.md`：

1. **Phase 1: Core Engine Refactoring**
   - ✅ `BacktestEngine` 抽象接口
   - ✅ `VectorBTEngine` 实现
   - ✅ `PositionManager` 系统
   - ✅ `SignalGenerator` 框架

2. **Phase 2: Strategy Refactoring**
   - ✅ `BaseStrategy` 抽象类
   - ✅ `sr_zones.py` SR 检测
   - ✅ `volatility.py` ATR 计算
   - ✅ `position_sizer.py` 仓位计算
   - ✅ `sr_short.py` 策略重构
   - ✅ `backtest_runner.py` 编排层
   - ✅ `run_backtest_new.py` 入口点

---

## 🔧 主要改进和修复

### 1. VectorBT 方向处理修复（Critical Bug Fix）

**问题**：
- `KeyError: ''` - VectorBT 的 `Direction` enum 不接受空字符串
- 当 `order_directions` 包含空字符串时，`from_orders()` 会抛出异常

**修复**：
- 文件：`execution/engines/vectorbt_engine.py`
- 将 `order_directions` 初始化为 `None` 而不是空字符串
- 只对有订单的 bar 设置 direction（'shortonly' 或 'longonly'）
- 对于没有订单的 bar，保持 `None`，让 VectorBT 从 `size` 的正负号推断

**代码变更**：
```python
# 修复前
order_directions = pd.Series('', index=close.index, dtype='object')
order_directions = order_directions.fillna('')

# 修复后
order_directions = pd.Series(None, index=close.index, dtype='object')
# 不填充 None，让 VectorBT 从 size 推断
```

**影响**：解决了回测无法运行的问题，确保所有订单都能正确执行。

---

### 2. 部分平仓功能实现（Major Feature）

**问题**：
- 初始实现使用 `from_signals()`，不支持部分平仓
- 策略需要 TP1（30% 平仓）和 TP2（70% 追踪止损）功能
- VectorBT 的 `from_signals()` 只能整仓平仓

**解决方案**：
- 从 `from_signals()` 迁移到 `from_orders()`
- 策略生成 `orders` Series（精确订单大小）而不是 `signals` DataFrame（布尔标志）
- 使用 `size_type='amount'` 支持小数仓位

**代码变更**：

**策略层** (`strategies/signal_based/sr_short.py`):
```python
# 生成 orders Series 而不是 signals DataFrame
orders = pd.Series(0.0, index=data.index, dtype=float)
order_types = pd.Series('', index=data.index, dtype='object')

# TP1: 30% 平仓
if profit_rr >= tp1_rr_ratio:
    partial_size = position_size * tp1_exit_pct
    orders.iloc[i] = partial_size
    order_types.iloc[i] = 'TP1'

# TP2: 追踪止损（剩余 70%）
# ...

return pd.DataFrame({
    'orders': orders,
    'direction': direction,
    'order_types': order_types,
}, index=data.index)
```

**引擎层** (`execution/engines/vectorbt_engine.py`):
```python
# 使用 from_orders 而不是 from_signals
portfolio = vbt.Portfolio.from_orders(
    close=close,
    size=order_amounts,
    size_type='amount',  # 支持小数仓位
    direction=order_directions,
    init_cash=config.initial_cash,
    fees=config.commission,
    slippage=config.slippage,
    freq='min',
)
```

**影响**：实现了完整的零成本持仓管理（TP1 + 追踪止损），策略逻辑更加完善。

---

### 3. 订单类型标记和详细记录（Feature Enhancement）

**问题**：
- `trades.csv` 只包含合并后的交易记录，无法看到每个订单的详细信息
- 无法区分 ENTRY、TP1、TP2、SL 等订单类型
- 部分平仓导致同一 entry 对应多个 exit，难以分析

**解决方案**：
- 在策略中标记每个订单的类型（ENTRY, TP1, TP2, SL）
- 在引擎中提取所有订单的详细信息
- 生成 `orders.csv` 文件，包含每个订单的时间、价格、大小、方向、类型

**代码变更**：

**策略层** (`strategies/signal_based/sr_short.py`):
```python
order_types = pd.Series('', index=data.index, dtype='object')

# 标记订单类型
orders.iloc[i] = entry_size
order_types.iloc[i] = 'ENTRY'

orders.iloc[i] = partial_size
order_types.iloc[i] = 'TP1'

orders.iloc[i] = remaining_size
order_types.iloc[i] = 'TP2'

orders.iloc[i] = position_size
order_types.iloc[i] = 'SL'
```

**引擎层** (`execution/engines/vectorbt_engine.py`):
```python
def _extract_orders(self, portfolio: vbt.Portfolio) -> pd.DataFrame:
    """提取所有订单的详细信息"""
    orders_records = portfolio.orders.records_readable
    orders_list = []
    
    for _, order in orders_records.iterrows():
        # 从 VectorBT 获取订单信息
        timestamp = order.get('Timestamp')
        price = order.get('Price', order.get('Avg. Price'))
        size = order.get('Size', 0)
        
        # 从 metadata 获取订单类型
        order_type = order_types_map.get(timestamp, 'UNKNOWN')
        
        # 从 VectorBT 内部数据推断方向
        direction = self._infer_direction(order, size)
        
        orders_list.append({
            'timestamp': timestamp,
            'price': price,
            'size': abs(size),
            'direction': direction,
            'order_type': order_type,
        })
    
    return pd.DataFrame(orders_list)
```

**编排层** (`orchestration/backtest_runner.py`):
```python
# 保存订单详情
if hasattr(result, 'metadata') and result.metadata:
    orders_df = result.metadata.get('orders_df')
    if orders_df is not None and not orders_df.empty:
        orders_path = config.output_dir / f"{prefix}_orders.csv"
        orders_df.to_csv(orders_path, index=False)
```

**影响**：提供了完整的订单级别分析能力，便于策略优化和调试。

---

### 4. 方向判断逻辑优化（Bug Fix）

**问题**：
- `orders.csv` 中 TP 订单显示为 `LONG`，但策略是 short-only
- 硬编码了方向判断逻辑，不够灵活

**修复**：
- 从 VectorBT 的内部数据（`Direction` 或 `Side` 列）读取方向
- 如果 VectorBT 没有提供方向信息，从 `size` 的正负号推断
- 不再硬编码基于策略类型或订单类型的方向

**代码变更** (`execution/engines/vectorbt_engine.py`):
```python
def _extract_orders(self, portfolio: vbt.Portfolio) -> pd.DataFrame:
    # 优先从 VectorBT 内部数据读取方向
    direction_from_vbt = None
    if 'Direction' in order.index:
        direction_from_vbt = order.get('Direction')
    elif 'Side' in order.index:
        direction_from_vbt = order.get('Side')
    
    # 如果 VectorBT 提供了方向，使用它
    if direction_from_vbt is not None:
        if 'short' in str(direction_from_vbt).lower():
            direction = 'SHORT'
        elif 'long' in str(direction_from_vbt).lower():
            direction = 'LONG'
        else:
            direction = 'SHORT' if size < 0 else 'LONG'
    else:
        # 否则从 size 推断
        direction = 'SHORT' if size < 0 else 'LONG'
```

**影响**：方向判断更加准确和灵活，支持任意策略类型。

---

### 5. 可视化改进（Major Enhancement）

#### 5.1 交易标记显示修复

**问题**：
- 部分 entry 标记不显示（特别是部分平仓的情况）
- `trades.csv` 中的交易被合并，导致某些 entry 丢失

**修复**：
- 新增 `_plot_orders_bokeh()` 函数，从 `orders.csv` 读取所有订单
- 优先使用 `orders_data`，回退到 `trades` 数据
- 使用 `seen_entries` 集合避免重复标记

**代码变更** (`execution/visualization.py`):
```python
def _plot_orders_bokeh(p: figure, orders: pd.DataFrame, data: pd.DataFrame):
    """从 orders.csv 绘制所有订单标记"""
    seen_entries = set()
    
    for _, order in orders.iterrows():
        if order_type == "ENTRY":
            entry_key = pd.Timestamp(timestamp)
            if entry_key not in seen_entries:
                entry_times.append(timestamp)
                entry_prices.append(price)
                seen_entries.add(entry_key)
```

#### 5.2 工具提示修复

**问题**：
- 工具提示显示 index 而不是时间
- 重复的 hover 信息

**修复**：
- 移除 `crosshair` 工具（会显示 index）
- 设置自定义 `HoverTool`，格式化时间为 `"%Y-%m-%d %H:%M"`
- 使用 `mode='vline'` 避免重复信息

**代码变更**:
```python
# 移除 crosshair
p1 = figure(..., tools="pan,wheel_zoom,box_zoom,reset,save")

# 自定义 hover tool
hover1 = HoverTool(
    tooltips=[
        ("Time", "@date{%Y-%m-%d %H:%M}"),
        ("Open", "@open{0,0.00}"),
        ("High", "@high{0,0.00}"),
        ("Low", "@low{0,0.00}"),
        ("Close", "@close{0,0.00}"),
        ("Volume", "@volume{0,0.00}"),
    ],
    formatters={'@date': 'datetime'},
    mode='vline',  # 垂直线模式，避免重复
)
```

#### 5.3 Bokeh 警告修复

**问题**：
- Bokeh 3.8+ 警告：`Expected hatch_color and fill_color to reference fields in the supplied data source`

**修复**：
- 显式设置 `hatch_pattern=None` 和 `hatch_alpha=0` 禁用 hatching

**代码变更**:
```python
p.vbar(..., hatch_pattern=None, hatch_alpha=0)
p.patch(..., hatch_pattern=None, hatch_alpha=0)
```

**影响**：图表更加清晰、准确，所有交易都能正确显示。

---

### 6. 输出路径统一（Code Organization）

**问题**：
- 不同脚本使用不同的输出路径
- 运行位置不同导致结果分散

**解决方案**：
- 创建 `utils/paths.py` 工具模块
- 提供 `get_project_root()` 和 `get_results_dir()` 函数
- 所有脚本统一使用 `get_results_dir()` 获取输出路径

**代码变更**:

**新文件** (`utils/paths.py`):
```python
import sys
from pathlib import Path

def get_project_root() -> Path:
    """Returns the project root path."""
    return Path(__file__).parent.parent.absolute()

def get_results_dir() -> Path:
    """Returns the unified results directory path."""
    return get_project_root() / "run" / "results"
```

**更新的文件**：
- `run/run_backtest.py`
- `run/visualize_zones.py`
- `run/analyze_strategy.py`
- `run/analyze_partial_exits.py`
- `orchestration/backtest_runner.py`

**影响**：所有结果统一保存到 `run/results/`，无论从哪里运行脚本。

---

### 7. 缓存读取优化（Performance Fix）

**问题**：
- 缓存检查逻辑过于严格，导致缓存命中率低
- 即使时间范围相同，也重新获取数据

**修复**：
- 放宽缓存结束时间检查（允许一个 bar 的容差）
- 处理时区和舍入问题

**代码变更** (`data/data_manager.py`):
```python
# 修复前
cache_covers = (
    (request_start is None or cache_start <= request_start) and
    (request_end is None or cache_end >= request_end)
)

# 修复后
time_delta = pd.Timedelta(minutes=timeframe_to_minutes(timeframe))
cache_covers = (
    (request_start is None or cache_start <= request_start) and
    (request_end is None or cache_end >= (request_end - time_delta))
)
```

**影响**：提高了缓存命中率，减少了不必要的数据获取。

---

### 8. 代码清理（Code Maintenance）

**删除的测试文件**：
- `run/debug_orders.py`
- `run/debug_vectorbt_orders.py`
- `run/debug_tp1_orders.py`
- `run/debug_zones_timing.py`
- `run/test_zone_timing.py`
- `run/test_sr_parameters.py`
- `run/check_zone_appearance.py`
- `run/check_vectorbt_orders.py`

**保留的分析脚本**：
- `run/analyze_strategy.py` - 策略行为分析
- `run/analyze_partial_exits.py` - 部分平仓分析
- `run/visualize_zones.py` - SR 区间可视化

**影响**：代码库更加整洁，只保留有用的分析工具。

---

### 9. 打印输出改进（User Experience）

**问题**：
- 使用 emoji 导致 `UnicodeEncodeError`（某些终端不支持）
- 输出格式不统一

**修复**：
- 移除所有 emoji，使用文本标签
- 统一输出格式

**代码变更**:
```python
# 修复前
print("📊 Loading data...")
print("✅ Backtest completed successfully!")

# 修复后
print("[Data] Loading data...")
print("[Success] Backtest completed successfully!")
```

**影响**：提高了兼容性，避免了编码错误。

---

### 10. Git 错误修复（Infrastructure Fix）

**问题**：
- Git commit 失败：`short read while indexing nul nul: failed to insert into database unable to index file 'nul'`
- Windows 保留文件名（`nul`, `con`, `prn`）导致问题

**修复**：
- 删除 `nul` 文件
- 在 `.gitignore` 中添加 Windows 保留文件名

**代码变更** (`.gitignore`):
```
# Windows reserved filenames
nul
con
prn
```

**影响**：解决了 Git 操作问题，确保版本控制正常工作。

---

## 📊 改进统计

| 类别 | 数量 | 说明 |
|------|------|------|
| **Critical Bug Fixes** | 3 | 方向处理、缓存读取、Git 错误 |
| **Major Features** | 2 | 部分平仓、订单详细记录 |
| **Enhancements** | 3 | 可视化改进、路径统一、输出改进 |
| **Code Cleanup** | 1 | 删除测试代码 |
| **总计** | **9** | 主要改进项 |

---

## 🔄 当前系统状态

### ✅ 已完成的功能

1. **核心回测引擎**
   - VectorBT 集成完成
   - 支持部分平仓
   - 支持小数仓位
   - 方向处理正确

2. **策略层**
   - SR Short 策略完整实现
   - TP1 + TP2 追踪止损
   - 单仓位管理
   - 单区间单次进入

3. **数据层**
   - 统一数据接口（OKX/Binance/CSV）
   - Parquet 缓存
   - 缓存优化

4. **可视化**
   - Bokeh K 线图
   - 交易标记（entry/exit）
   - SR 区间显示
   - 权益曲线和成交量

5. **结果导出**
   - `trades.csv` - 交易记录
   - `orders.csv` - 订单详情
   - `equity.csv` - 权益曲线
   - `metrics.json` - 性能指标
   - `plot.html` - 交互式图表

### ⚠️ 已知问题

1. **VectorBT 交互式图表**
   - 需要 `anywidget` 依赖（可选）
   - 如果未安装，会显示警告但不影响功能

2. **遗留代码**
   - `backtests/run_backtest.py` 仍存在（使用旧的 `backtesting.py`）
   - 建议归档或删除

### 🚀 下一步建议

1. **代码清理**
   - 归档或删除 `backtests/run_backtest.py`
   - 检查是否有其他遗留代码

2. **功能增强**
   - 参数优化框架（Optuna）
   - Walk-forward 分析
   - 多策略回测

3. **文档完善**
   - API 文档
   - 使用指南
   - 策略开发指南

---

## 📝 关键文件清单

### 核心文件（已修改）

1. **引擎层**
   - `execution/engines/vectorbt_engine.py` - VectorBT 引擎实现
   - `execution/engines/base.py` - 抽象接口

2. **策略层**
   - `strategies/signal_based/sr_short.py` - SR Short 策略

3. **编排层**
   - `orchestration/backtest_runner.py` - 回测编排

4. **可视化**
   - `execution/visualization.py` - Bokeh 图表

5. **工具**
   - `utils/paths.py` - 路径工具（新建）
   - `data/data_manager.py` - 数据管理（缓存优化）

### 配置文件

- `run/run_backtest.py` - 主入口点
- `.gitignore` - Git 忽略规则

---

## 🎓 技术要点

### VectorBT 使用要点

1. **方向处理**
   - 使用 `direction` 参数明确指定方向
   - 对于混合方向，传递 Series（None 表示从 size 推断）
   - 不要使用空字符串

2. **部分平仓**
   - 使用 `from_orders()` 而不是 `from_signals()`
   - `size_type='amount'` 支持小数仓位
   - 订单大小可以是任意小数

3. **价格记录**
   - `portfolio.orders.records_readable['Price']` 已包含滑点和手续费
   - 这是实际成交价格，不是 K 线 close 价格

### 策略开发要点

1. **订单生成**
   - 生成 `orders` Series（订单大小）而不是 `signals` DataFrame（布尔标志）
   - 标记每个订单的类型（ENTRY, TP1, TP2, SL）
   - 确保方向正确（负数 = short entry，正数 = long entry）

2. **仓位管理**
   - 使用 `used_zones` 集合避免重复进入同一区间
   - 确保只有一个活跃仓位
   - 正确处理部分平仓后的剩余仓位

---

## 📚 相关文档

- `docs/system_design.md` - 系统架构设计
- `docs/phase1_completion_summary.md` - Phase 1 完成总结
- `docs/phase2_completion_summary.md` - Phase 2 完成总结
- `docs/vector_bt_migration_todo.md` - VectorBT 迁移计划
- `docs/refactoring_plan.md` - 重构计划

---

## 🔗 重要链接

- VectorBT 文档: https://vectorbt.dev/
- Bokeh 文档: https://docs.bokeh.org/
- 项目 GitHub: https://github.com/metaTaoTao/taoquant.git

---

**文档状态**: ACTIVE  
**最后更新**: 2025-12-03  
**维护者**: AI Assistant (接力 Claude Code)

---

*本文档将持续更新，记录所有重要的改进和修复。*


# TaoGrid 网格策略实现 TODO

> **策略文档**：`docs/TaoGrid 网格策略.pdf`  
> **执行版文档**：`docs/TaoGrid 网格策略执行版.pdf`  
> **架构指导**：`CLAUDE.md`  
> **创建日期**：2025-12-07

---

## 📋 总体目标

实现 TaoGrid 主动网格策略，包括：
- 基于 S/R 区间的动态网格生成
- Regime 判定（手动/自动）
- 不对称仓位分配（边缘重、中枢轻）
- 动态节流规则
- 全局风险预算控制

---

## 🏗️ 架构设计

### 文件组织（遵循 CLAUDE.md）

```
analytics/indicators/
  ├── regime_detector.py          # Regime判定指标（GREEN/RED/YELLOW）
  ├── grid_generator.py            # 网格生成（基于S/R区间）
  └── grid_position_sizer.py      # 网格仓位分配（不对称权重）

strategies/grid/
  ├── taogrid_strategy.py          # 主策略类（继承BaseStrategy）
  ├── taogrid_config.py            # 配置类
  ├── grid_manager.py              # 网格状态管理（订单、配对、库存）
  ├── throttle_manager.py          # 动态节流规则
  └── risk_budget_manager.py       # 风险预算控制

execution/grid_engine/
  ├── grid_order_manager.py       # 网格订单管理（生成、执行、配对）
  └── grid_backtest_engine.py     # 网格回测引擎（支持部分成交、配对）

orchestration/
  └── grid_backtest_runner.py      # 网格回测运行器

run/
  └── run_taogrid_backtest.py      # 回测入口脚本
```

---

## 📝 详细 TODO 列表

### Phase 1: 核心指标开发（Layer 1: Analytics）

#### ✅ TODO-1.1: Regime 判定指标
**文件**：`analytics/indicators/regime_detector.py`

**任务**：
- [ ] 实现 `detect_regime()` 函数
  - [ ] GREEN 候选判定（日线 + 4H 条件）
    - [ ] 日线：`close_D > ema200_D` 且 `ema50_D > ema200_D` 且斜率 > 0
    - [ ] 4H：连续 N 根 4H 收盘 > 4H 200EMA
    - [ ] 日线统计：连续天数确认
  - [ ] RED 候选判定
    - [ ] 熊市型 RED：`close_D < ema200_D` 且 `ema50_D < ema200_D` 且斜率 < 0
    - [ ] 疯牛末端型 RED：`close_D > ema200_D * (1 + dev)` 且 ATR/close > 阈值
  - [ ] 锁定机制：防止频繁切换（lock_days）
- [ ] 实现 `get_regime()` 函数：返回 "GREEN"/"RED"/"YELLOW"
- [ ] 实现 `detect_trend_regime()` 函数：返回 "UP_RANGE"/"NEUTRAL_RANGE"/"DOWN_RANGE"
  - [ ] 支持手动指定（交易员介入模式）
  - [ ] 支持自动判定（基于趋势强度、动能、波动率）
- [ ] 添加趋势过滤器
  - [ ] ADX > 25 → 禁止网格（趋势过强）
  - [ ] 动能指标（ROC、Z-score）→ 禁止网格
  - [ ] 波动率状态（ATR、BB宽度）→ 降低密度或暂停

**依赖**：
- `analytics/indicators/volatility.py` (ATR)
- `utils/resample.py` (多时间框架)

**测试**：
- [ ] 单元测试：GREEN/RED/YELLOW 判定逻辑
- [ ] 单元测试：锁定机制
- [ ] 单元测试：趋势过滤器

---

#### ✅ TODO-1.2: 网格生成器
**文件**：`analytics/indicators/grid_generator.py`

**任务**：
- [ ] 实现 `generate_grid_from_sr_zones()` 函数
  - [ ] 输入：S/R 区间（使用现有 `compute_sr_zones`）
  - [ ] 输入：Regime（UP_RANGE/NEUTRAL_RANGE/DOWN_RANGE）
  - [ ] 输入：波动率（ATR）用于动态 spacing
  - [ ] 输出：网格层级列表（每层包含：价格、方向、权重）
- [ ] 实现动态 spacing 计算
  - [ ] 基于 ATR 的 spacing：`spacing = atr * spacing_multiplier`
  - [ ] 根据 Regime 调整 spacing（上行/下行时轻微偏移）
- [ ] 实现网格层级生成
  - [ ] 从 S/R 区间边界开始
  - [ ] 向 mid 方向生成层级
  - [ ] 支持 mid-shift（动态结构调整）
- [ ] 实现网格边界定义
  - [ ] 支撑（S）：网格下限
  - [ ] 阻力（R）：网格上限
  - [ ] 中轴（mid）：(S + R) / 2 或动态调整

**依赖**：
- `analytics/indicators/sr_zones.py` (S/R 区间)
- `analytics/indicators/volatility.py` (ATR)

**测试**：
- [ ] 单元测试：网格层级生成
- [ ] 单元测试：spacing 计算
- [ ] 单元测试：mid-shift 逻辑

---

#### ✅ TODO-1.3: 网格仓位分配器
**文件**：`analytics/indicators/grid_position_sizer.py`

**任务**：
- [ ] 实现 `calculate_grid_weights()` 函数
  - [ ] 输入：网格层级列表、Regime
  - [ ] 输出：每层的权重（归一化）
- [ ] 实现不对称权重分配
  - [ ] 中性区间：边缘重、中枢轻（线性权重）
    - [ ] `raw_w(i) = 1 + k × (i - 1)`，i=1 最靠近 mid
    - [ ] 归一化：`w(i) = raw_w(i) / Σ raw_w`
  - [ ] 震荡上行（UP_RANGE）：下重上轻，偏多
    - [ ] 买侧总权重：70%
    - [ ] 卖侧总权重：30%
    - [ ] 买方层级：边缘重、中间轻
    - [ ] 卖方层级：中间略重、最远稍轻
  - [ ] 震荡下行（DOWN_RANGE）：上重下轻，偏空
    - [ ] 买侧总权重：30%
    - [ ] 卖侧总权重：70%
- [ ] 实现 `calculate_layer_size()` 函数
  - [ ] 输入：总风险预算、层级权重、价格
  - [ ] 输出：每层的名义金额和数量（币数）

**测试**：
- [ ] 单元测试：中性区间权重分配
- [ ] 单元测试：上行区间权重分配（70/30）
- [ ] 单元测试：下行区间权重分配（30/70）
- [ ] 单元测试：归一化验证

---

### Phase 2: 策略核心开发（Layer 3: Strategy）

#### ✅ TODO-2.1: TaoGrid 配置类
**文件**：`strategies/grid/taogrid_config.py`

**任务**：
- [ ] 创建 `TaoGridConfig` 类（继承 `StrategyConfig`）
  - [ ] Regime 参数
    - [ ] `regime_mode`: "manual" 或 "auto"
    - [ ] `manual_regime`: "UP_RANGE"/"NEUTRAL_RANGE"/"DOWN_RANGE"（手动模式）
    - [ ] `green_confirm_days`: int（GREEN 确认天数）
    - [ ] `red_confirm_days`: int（RED 确认天数）
    - [ ] `lock_days`: int（Regime 锁定天数）
  - [ ] 网格参数
    - [ ] `spacing_multiplier`: float（ATR 倍数，默认 1.0）
    - [ ] `grid_layers_buy`: int（买侧层数）
    - [ ] `grid_layers_sell`: int（卖侧层数）
    - [ ] `weight_k`: float（权重系数，默认 0.5）
  - [ ] 风险参数
    - [ ] `risk_budget_pct`: float（风险预算百分比，默认 0.3）
    - [ ] `side_budget_pct`: float（单侧预算百分比，默认 0.6）
    - [ ] `daily_loss_limit`: float（日最大亏损，默认 2000）
    - [ ] `max_long_units`: float（最大多仓单位）
    - [ ] `max_short_units`: float（最大空仓单位）
  - [ ] 节流参数
    - [ ] `profit_target_pct`: float（盈利目标百分比，默认 0.01-0.02）
    - [ ] `profit_lock_reduction`: float（盈利锁定后规模缩减，默认 0.5）
    - [ ] `volatility_threshold`: float（波动率异常阈值）
  - [ ] S/R 参数（复用现有）
    - [ ] `sr_left_len`: int
    - [ ] `sr_right_len`: int
    - [ ] `sr_merge_atr_mult`: float
    - [ ] `sr_atr_period`: int

**测试**：
- [ ] 单元测试：配置验证
- [ ] 单元测试：默认值检查

---

#### ✅ TODO-2.2: 网格管理器
**文件**：`strategies/grid/grid_manager.py`

**任务**：
- [ ] 创建 `GridManager` 类
  - [ ] 状态管理
    - [ ] `current_grid`: 当前网格层级列表
    - [ ] `active_orders`: 活跃订单字典（价格 → 订单信息）
    - [ ] `filled_orders`: 已成交订单列表
    - [ ] `paired_orders`: 已配对订单对
  - [ ] 方法
    - [ ] `update_grid()`: 更新网格（基于新的 S/R 区间）
    - [ ] `generate_orders()`: 生成网格订单
    - [ ] `match_orders()`: 订单配对（买单 ↔ 卖单）
    - [ ] `get_inventory()`: 获取当前库存（E_long, E_short）
    - [ ] `get_unpaired_orders()`: 获取未配对订单

**数据结构**：
```python
@dataclass
class GridOrder:
    price: float
    side: str  # 'buy' or 'sell'
    size: float
    layer: int
    weight: float
    order_id: str
    filled: bool = False
    filled_time: Optional[pd.Timestamp] = None
    paired: bool = False
    paired_with: Optional[str] = None
```

**测试**：
- [ ] 单元测试：网格更新
- [ ] 单元测试：订单生成
- [ ] 单元测试：订单配对逻辑

---

#### ✅ TODO-2.3: 节流管理器
**文件**：`strategies/grid/throttle_manager.py`

**任务**：
- [ ] 创建 `ThrottleManager` 类
  - [ ] Inventory Limit（仓位上限）
    - [ ] `check_inventory_limit()`: 检查是否超过单侧上限
    - [ ] `should_pause_buy()`: 是否暂停新买单
    - [ ] `should_pause_sell()`: 是否暂停新卖单
  - [ ] Profit Lock-in（盈利锁定）
    - [ ] `check_profit_target()`: 检查是否达到盈利目标
    - [ ] `get_size_reduction()`: 获取规模缩减系数（0.5 或 1.0）
    - [ ] `should_stop_new_orders()`: 是否停止新订单
  - [ ] 波动异常降频
    - [ ] `check_volatility_spike()`: 检查波动率异常
    - [ ] `get_volatility_reduction()`: 获取波动率缩减系数
  - [ ] 综合节流决策
    - [ ] `get_throttle_factor()`: 返回综合节流系数（0.0-1.0）

**测试**：
- [ ] 单元测试：Inventory Limit
- [ ] 单元测试：Profit Lock-in
- [ ] 单元测试：波动率降频
- [ ] 单元测试：综合节流决策

---

#### ✅ TODO-2.4: 风险预算管理器
**文件**：`strategies/grid/risk_budget_manager.py`

**任务**：
- [ ] 创建 `RiskBudgetManager` 类
  - [ ] 全局风险预算
    - [ ] `total_capital`: 总资金
    - [ ] `risk_budget`: 策略风险预算（30% × Capital）
    - [ ] `side_budget`: 单侧预算（60% × Risk_budget）
  - [ ] 方法
    - [ ] `check_budget()`: 检查是否超过预算
    - [ ] `get_available_budget()`: 获取可用预算
    - [ ] `update_daily_pnl()`: 更新日 PnL
    - [ ] `check_daily_loss_limit()`: 检查日亏损限制
    - [ ] `allocate_budget()`: 分配预算到买卖侧（根据 Regime）

**测试**：
- [ ] 单元测试：预算计算
- [ ] 单元测试：预算分配（70/30, 50/50, 30/70）
- [ ] 单元测试：日亏损限制

---

#### ✅ TODO-2.5: TaoGrid 主策略类
**文件**：`strategies/grid/taogrid_strategy.py`

**任务**：
- [ ] 创建 `TaoGridStrategy` 类（继承 `BaseStrategy`）
  - [ ] `__init__()`: 初始化
    - [ ] 创建 GridManager
    - [ ] 创建 ThrottleManager
    - [ ] 创建 RiskBudgetManager
  - [ ] `compute_indicators()`: 计算指标
    - [ ] 计算 Regime（手动或自动）
    - [ ] 计算 S/R 区间（使用现有 `compute_sr_zones`）
    - [ ] 计算 ATR（用于 spacing）
    - [ ] 生成网格（使用 `generate_grid_from_sr_zones`）
    - [ ] 计算仓位权重（使用 `calculate_grid_weights`）
  - [ ] `generate_signals()`: 生成信号
    - [ ] 检查节流规则
    - [ ] 检查风险预算
    - [ ] 生成网格订单信号
    - [ ] 返回订单 DataFrame（特殊格式，不同于传统信号）
  - [ ] `calculate_position_size()`: 计算仓位
    - [ ] 根据网格层级权重和风险预算
    - [ ] 返回每层的仓位大小

**信号格式**（特殊）：
```python
# 网格策略的信号格式不同于传统策略
signals = pd.DataFrame({
    'order_type': ['GRID_BUY', 'GRID_SELL', ...],  # 订单类型
    'price': [100.0, 101.0, ...],                  # 挂单价格
    'size': [0.1, 0.1, ...],                       # 订单数量
    'layer': [1, 1, ...],                          # 网格层级
    'side': ['buy', 'sell', ...],                  # 方向
}, index=data.index)
```

**测试**：
- [ ] 单元测试：指标计算
- [ ] 单元测试：信号生成
- [ ] 单元测试：仓位计算

---

### Phase 3: 执行引擎开发（Layer 2: Execution）

#### ✅ TODO-3.1: 网格订单管理器
**文件**：`execution/grid_engine/grid_order_manager.py`

**任务**：
- [ ] 创建 `GridOrderManager` 类
  - [ ] 订单状态跟踪
    - [ ] `pending_orders`: 待执行订单
    - [ ] `active_orders`: 活跃订单（已挂单）
    - [ ] `filled_orders`: 已成交订单
    - [ ] `cancelled_orders`: 已取消订单
  - [ ] 方法
    - [ ] `place_order()`: 挂单
    - [ ] `cancel_order()`: 撤单
    - [ ] `check_fill()`: 检查订单是否成交（价格触发）
    - [ ] `match_pairs()`: 配对订单（买单 ↔ 卖单）
    - [ ] `calculate_pnl()`: 计算已实现盈亏
    - [ ] `get_inventory()`: 获取当前库存

**订单执行逻辑**：
- [ ] 价格触发：当 `close >= buy_order.price` 时，买单成交
- [ ] 价格触发：当 `close <= sell_order.price` 时，卖单成交
- [ ] 配对规则：买单成交后，寻找对应的卖单配对
- [ ] 配对规则：卖单成交后，寻找对应的买单配对

**测试**：
- [ ] 单元测试：订单挂单
- [ ] 单元测试：订单成交
- [ ] 单元测试：订单配对
- [ ] 单元测试：盈亏计算

---

#### ✅ TODO-3.2: 网格回测引擎
**文件**：`execution/grid_engine/grid_backtest_engine.py`

**任务**：
- [ ] 创建 `GridBacktestEngine` 类（继承或独立于 VectorBTEngine）
  - [ ] 特殊需求：
    - [ ] 支持部分成交（价格在订单价格范围内）
    - [ ] 支持订单配对（买单 ↔ 卖单）
    - [ ] 支持动态撤单和重新挂单（网格更新时）
    - [ ] 支持库存跟踪（E_long, E_short）
  - [ ] 方法
    - [ ] `run()`: 运行回测
      - [ ] 遍历每个 bar
      - [ ] 检查订单成交
      - [ ] 执行订单配对
      - [ ] 更新库存
      - [ ] 计算 PnL
    - [ ] `process_bar()`: 处理单个 bar
    - [ ] `update_orders()`: 更新订单（网格更新时）

**回测流程**：
```
For each bar:
  1. 检查策略信号（网格订单）
  2. 更新订单管理器（新订单、撤单）
  3. 检查订单成交（价格触发）
  4. 执行订单配对
  5. 计算已实现 PnL
  6. 更新库存（E_long, E_short）
  7. 检查节流规则
  8. 检查风险预算
```

**测试**：
- [ ] 单元测试：基本回测流程
- [ ] 单元测试：订单成交逻辑
- [ ] 单元测试：订单配对逻辑
- [ ] 单元测试：库存跟踪

---

### Phase 4: 回测运行器（Layer 4: Orchestration）

#### ✅ TODO-4.1: 网格回测运行器
**文件**：`orchestration/grid_backtest_runner.py`

**任务**：
- [ ] 创建 `GridBacktestRunner` 类
  - [ ] 继承或参考 `BacktestRunner`
  - [ ] 特殊处理：
    - [ ] 网格订单格式转换
    - [ ] 调用 `GridBacktestEngine`
    - [ ] 结果统计（配对次数、平均盈亏、库存曲线）
  - [ ] 方法
    - [ ] `run()`: 运行回测
    - [ ] `_export_results()`: 导出结果（特殊格式）
      - [ ] 订单记录（所有挂单、成交、配对）
      - [ ] 库存曲线（E_long, E_short 随时间变化）
      - [ ] 配对统计（配对次数、平均盈亏）
      - [ ] 节流事件记录

**结果格式**：
```python
@dataclass
class GridBacktestResult:
    equity_curve: pd.DataFrame
    inventory_curve: pd.DataFrame  # E_long, E_short
    orders_df: pd.DataFrame  # 所有订单记录
    pairs_df: pd.DataFrame  # 配对记录
    throttle_events: pd.DataFrame  # 节流事件
    metrics: Dict[str, float]  # 统计指标
```

**测试**：
- [ ] 集成测试：完整回测流程
- [ ] 集成测试：结果导出

---

### Phase 5: 回测脚本和测试（Layer 5: Application）

#### ✅ TODO-5.1: 回测入口脚本
**文件**：`run/run_taogrid_backtest.py`

**任务**：
- [ ] 创建回测脚本
  - [ ] 配置 TaoGridConfig
  - [ ] 初始化策略
  - [ ] 初始化引擎
  - [ ] 运行回测
  - [ ] 保存结果
- [ ] 支持参数化
  - [ ] Regime 模式（手动/自动）
  - [ ] 风险预算
  - [ ] 网格参数
  - [ ] S/R 参数

**示例**：
```python
config = TaoGridConfig(
    name="TaoGrid Strategy",
    description="Active grid strategy with S/R zones",
    regime_mode="manual",
    manual_regime="NEUTRAL_RANGE",
    risk_budget_pct=0.3,
    spacing_multiplier=1.0,
    # ... 其他参数
)
```

**测试**：
- [ ] 手动测试：运行回测脚本
- [ ] 验证：结果文件生成

---

#### ✅ TODO-5.2: 回测验证和优化
**任务**：
- [ ] 回测验证
  - [ ] 测试不同 Regime（UP_RANGE/NEUTRAL_RANGE/DOWN_RANGE）
  - [ ] 测试不同风险预算（10%, 20%, 30%）
  - [ ] 测试不同 spacing_multiplier（0.5, 1.0, 1.5）
  - [ ] 测试节流规则（Inventory Limit、Profit Lock-in）
- [ ] 性能分析
  - [ ] 配对次数统计
  - [ ] 平均盈亏分析
  - [ ] 库存曲线分析
  - [ ] 节流事件分析
- [ ] 参数优化
  - [ ] 网格参数优化（spacing、层数）
  - [ ] 权重系数优化（weight_k）
  - [ ] 风险预算优化

---

## 🔄 实现顺序建议

### 第一阶段：核心功能（Week 1-2）
1. ✅ TODO-1.1: Regime 判定指标
2. ✅ TODO-1.2: 网格生成器
3. ✅ TODO-1.3: 网格仓位分配器
4. ✅ TODO-2.1: TaoGrid 配置类

### 第二阶段：策略逻辑（Week 2-3）
5. ✅ TODO-2.2: 网格管理器
6. ✅ TODO-2.3: 节流管理器
7. ✅ TODO-2.4: 风险预算管理器
8. ✅ TODO-2.5: TaoGrid 主策略类

### 第三阶段：执行引擎（Week 3-4）
9. ✅ TODO-3.1: 网格订单管理器
10. ✅ TODO-3.2: 网格回测引擎

### 第四阶段：回测和优化（Week 4-5）
11. ✅ TODO-4.1: 网格回测运行器
12. ✅ TODO-5.1: 回测入口脚本
13. ✅ TODO-5.2: 回测验证和优化

---

## 📊 关键设计决策

### 1. 网格订单格式
**决策**：使用特殊的信号格式，而非传统的 entry/exit 信号

**理由**：
- 网格策略需要同时管理多个订单（买/卖）
- 订单有价格、数量、层级等属性
- 需要支持动态更新（撤单、重新挂单）

### 2. 回测引擎选择
**决策**：创建独立的 `GridBacktestEngine`，而非直接使用 VectorBT

**理由**：
- VectorBT 主要针对传统信号（entry/exit）
- 网格策略需要订单管理、配对逻辑
- 需要支持部分成交、动态撤单

### 3. Regime 判定
**决策**：支持手动和自动两种模式

**理由**：
- 文档强调"交易员介入模式"（手动指定 Regime）
- 同时提供自动判定作为备选
- 灵活性更高

### 4. 风险预算控制
**决策**：在策略层和引擎层双重控制

**理由**：
- 策略层：计算仓位时考虑预算
- 引擎层：执行时再次检查，防止超限

---

## ⚠️ 注意事项

1. **遵循架构原则**：
   - 指标必须是纯函数（Layer 1）
   - 策略只生成信号，不执行（Layer 3）
   - 引擎负责执行和状态管理（Layer 2）

2. **复用现有代码**：
   - 使用 `compute_sr_zones` 获取 S/R 区间
   - 使用 `calculate_atr` 计算波动率
   - 参考 `BacktestRunner` 设计网格回测运行器

3. **测试优先**：
   - 每个模块都要有单元测试
   - 关键逻辑要有集成测试
   - 回测结果要有验证

4. **文档完善**：
   - 每个函数都要有 docstring
   - 关键设计决策要有注释
   - 使用示例要有说明

---

## 📈 成功标准

1. **功能完整性**：
   - ✅ 所有 TODO 项完成
   - ✅ 所有测试通过
   - ✅ 回测可以运行

2. **性能指标**：
   - ✅ 回测速度：1000+ bars/秒
   - ✅ 内存使用：合理（< 2GB for 1 year data）

3. **代码质量**：
   - ✅ 通过 lint 检查
   - ✅ 类型提示完整
   - ✅ 文档完整

4. **回测结果**：
   - ✅ 配对逻辑正确
   - ✅ 盈亏计算准确
   - ✅ 风险预算控制有效

---

**最后更新**：2025-12-07  
**状态**：🟡 待开始


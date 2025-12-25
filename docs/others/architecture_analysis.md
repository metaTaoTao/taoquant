# TaoQuant 架构全局分析

## 当前架构概览

### Layer 0: Data Layer
```
data/
├── data_manager.py          # 数据获取、缓存
└── sources/                 # OKX, Binance APIs
```
**职责**: 数据获取

---

### Layer 1: Analytics Layer
```
analytics/
├── indicators/              # 技术指标（纯函数）
│   ├── volatility.py       # ATR, Bollinger等
│   └── sr_zones.py         # S/R Zone检测
└── transforms/             # 数据转换
```
**职责**: 技术分析（纯函数，无状态）

---

### Layer 2: Risk Management Layer
```
risk_management/
└── position_sizer.py       # ⭐ 关键组件
    ├── calculate_fixed_size()
    ├── calculate_risk_based_size()      # 核心：根据风险计算仓位
    └── calculate_multi_position_size()
```
**职责**: **ENTRY时**的仓位计算
- 输入: equity + stop_distance + risk% → 输出: position_size
- 纯函数，无状态
- **关注点**: "应该开多大的仓？"

---

### Layer 3: Strategy Layer
```
strategies/
├── base_strategy.py        # 定义接口
│   ├── compute_indicators()        # 纯函数
│   ├── generate_signals()          # 纯函数
│   └── calculate_position_size()   # 调用risk_management
└── signal_based/
    └── sr_short.py         # ⚠️ 当前问题所在
        └── generate_signals()      # 700行，混杂了：
            ├── Entry信号逻辑      ✓ 应该在这
            ├── Position tracking   ✗ 不应该在这
            ├── Exit执行逻辑       ✗ 不应该在这
            └── Trailing stop计算  ✗ 不应该在这
```
**应有职责**:
- 定义**WHAT**: 入场条件、退出规则（声明式）
- 纯函数，无状态

**当前问题**:
- ❌ 策略内部维护`positions[]`列表（状态管理）
- ❌ 策略内部计算trailing stop（执行逻辑）
- ❌ 策略内部决定何时TP1/TP2（执行逻辑）
- ❌ 违反Single Responsibility Principle

---

### Layer 4: Execution Layer
```
execution/
├── engines/
│   ├── base.py
│   └── vectorbt_engine.py   # Portfolio simulation
└── position_manager/        # ⭐ 新创建的组件（但位置可能不对！）
    ├── models.py
    ├── exit_rules.py
    └── position_manager.py
```

**当前设计的问题**:
1. `position_manager/`放在`execution/`下 → 混淆了概念
2. VectorBT Engine本身就有position tracking → 重复
3. 缺少明确的**Execution Layer vs Engine Layer**区分

---

### Layer 5: Orchestration Layer
```
orchestration/
└── backtest_runner.py      # 协调所有组件
```

---

## 核心问题诊断

### 问题1: Position Manager vs Position Sizer 职责混淆

| 组件 | 当前职责 | 应有职责 |
|------|----------|----------|
| **position_sizer** | ✅ ENTRY sizing | ✅ ENTRY sizing |
| **position_manager** | EXIT tracking + execution | ❓ 是否需要？ |

**问题**:
- `position_sizer`: 关注**"开多大仓"**（纯函数）
- `position_manager`: 关注**"何时平仓"**（状态管理）
- 命名相似，容易混淆！

### 问题2: Strategy层职责过重

**当前**: Strategy同时做了：
1. ✅ 信号逻辑（应该）
2. ❌ Position tracking（不应该）
3. ❌ Exit execution（不应该）

**结果**: `sr_short.py::generate_signals()` 700行代码

### 问题3: 架构层次不清晰

**当前流程**:
```
Strategy.generate_signals()
  → 内部维护positions列表
  → 内部计算trailing stops
  → 返回orders (entry + exit混在一起)
  → VectorBT Engine执行
```

**问题**: Strategy承担了太多执行职责

---

## 设计方案对比

### 方案A: 保留Position Manager（当前实现）

```
Strategy (pure logic)
  ↓ signals + exit_rules
Position Manager (stateful tracking)
  ↓ orders (entry + exit)
VectorBT Engine (simulation)
  ↓ results
```

**优点**:
- 清晰分离concerns
- 可测试性强
- 可复用性强

**缺点**:
- 增加了一层抽象
- 与VectorBT的position tracking可能重复

---

### 方案B: 简化为Signal-based（VectorBT原生）

```
Strategy (pure signals)
  ↓ entry/exit signals (boolean)
VectorBT Engine (handles everything)
  ↓ results
```

**优点**:
- 简单
- 充分利用VectorBT能力

**缺点**:
- ❌ VectorBT**不支持**复杂exit逻辑！
- ❌ VectorBT不支持partial exits (TP1 30%, TP2 70%)
- ❌ VectorBT不支持动态trailing stops
- ❌ 无法实现零成本持仓策略

**结论**: 方案B不可行！VectorBT太简单，不支持我们的需求。

---

### 方案C: Order-based Signal Generation（当前变通）

```
Strategy.generate_signals()
  ↓ orders (not signals!) - 内部管理positions
VectorBT Engine (from_orders)
  ↓ results
```

**当前实现**: 就是这个方案
- Strategy返回`orders`列ï（不是boolean signals）
- Strategy内部维护`positions[]`列表
- VectorBT用`from_orders()`执行

**问题**:
- ❌ Strategy职责过重（信号 + 执行混在一起）
- ❌ 难以测试（状态管理复杂）
- ❌ 难以复用（每个策略都要重写position tracking）

---

### 方案D: Hybrid - Signal Processor Layer（推荐！）

```
┌─────────────────────────────────────────────┐
│ Strategy Layer (strategies/)                 │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ 职责: 定义WHAT（纯逻辑，无状态）              │
│                                              │
│ class SRShortStrategy(BaseStrategy):        │
│     def compute_indicators()   → DataFrame  │
│     def generate_entry_signals() → Signals  │
│     def get_exit_rules()       → ExitRules  │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Signal Processor Layer (execution/)          │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ 职责: 执行HOW（状态管理，order生成）          │
│                                              │
│ class SignalProcessor:                      │
│   def process(                              │
│       entry_signals: Signals,               │
│       exit_rules: ExitRules,                │
│       data: DataFrame                       │
│   ) -> Orders                               │
│                                              │
│   内部使用:                                  │
│   - PositionTracker (tracks open positions) │
│   - ExitCalculator (calculates exits)       │
│   - OrderGenerator (generates order flow)   │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Engine Layer (execution/engines/)            │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ 职责: Portfolio simulation                   │
│                                              │
│ class VectorBTEngine:                       │
│     def run(orders) → BacktestResult        │
└─────────────────────────────────────────────┘
```

**关键设计原则**:

1. **Strategy Layer**: 纯粹的信号逻辑
   ```python
   class SRShortStrategy(BaseStrategy):
       def generate_entry_signals(self, data):
           """返回: 哪里入场（WHERE）"""
           return EntrySignals(
               condition=(data['close'] >= zones['bottom']),
               zone_info=zones
           )

       def get_exit_rules(self, is_2b=False):
           """返回: 如何退出（RULES）"""
           return ExitRules(
               stop_loss=StopLossRule(atr_mult=3.0),
               take_profit=[
                   ZeroCostRule(trigger_rr=3.33, exit_pct=0.30)
               ],
               trailing_stop=TrailingStopRule(
                   distance_atr_mult=5.0,
                   offset_atr_mult=2.0
               )
           )
   ```

2. **Signal Processor Layer**: 执行引擎
   ```python
   class SignalProcessor:
       def __init__(self):
           self.position_tracker = PositionTracker()
           self.exit_calculator = ExitCalculator()

       def process(self, entry_signals, exit_rules, data):
           """
           输入:
             - entry_signals (WHERE to enter)
             - exit_rules (HOW to exit)
             - data (price + ATR)

           输出:
             - orders (WHEN to enter/exit)
           """
           orders = []

           for i, bar in enumerate(data):
               # Check exits first
               exit_orders = self.exit_calculator.check_exits(
                   positions=self.position_tracker.positions,
                   price=bar['close'],
                   atr=bar['atr'],
                   exit_rules=exit_rules
               )
               orders.extend(exit_orders)

               # Check entries
               if entry_signals.iloc[i]:
                   entry_order = self.create_entry(...)
                   orders.append(entry_order)
                   self.position_tracker.add_position(...)

           return orders
   ```

3. **Position Tracker**: 纯状态管理（无业务逻辑）
   ```python
   class PositionTracker:
       """只负责追踪positions，不决定何时exit"""
       def __init__(self):
           self.positions: List[Position] = []

       def add_position(self, ...):
           self.positions.append(Position(...))

       def remove_position(self, position_id):
           self.positions.remove(...)

       def update_best_price(self, position, price):
           """Update tracking info (no business logic)"""
           if position.is_short and price < position.best_price:
               position.best_price = price
   ```

4. **Exit Calculator**: 纯业务逻辑（无状态）
   ```python
   class ExitCalculator:
       """根据ExitRules计算exit信号，但不管理状态"""
       def check_stop_loss(self, position, price, rules):
           sl_price = rules.stop_loss.calculate(...)
           if price >= sl_price:
               return ExitSignal(type='SL', ...)

       def check_trailing_stop(self, position, price, atr, rules):
           new_stop = rules.trailing_stop.calculate(
               best_price=position.best_price,
               atr=atr
           )
           # Update position's trailing stop
           position.update_trailing_stop(new_stop)

           if price >= position.trailing_stop:
               return ExitSignal(type='TP2', ...)
   ```

---

## 重命名建议

**避免混淆**，建议重命名：

| 当前名称 | 新名称 | 职责 |
|---------|--------|------|
| `risk_management/position_sizer.py` | ✅ 保持不变 | ENTRY sizing |
| `execution/position_manager/` | → `execution/signal_processor/` | 信号处理 |
| `PositionManager` | → `SignalProcessor` | 处理signals→orders |
| 内部: `PositionTracker` | ✅ 保持 | 状态追踪 |
| 内部: `ExitCalculator` | ✅ 保持 | Exit逻辑 |

---

## 推荐实现路径

### Phase 1: 重构为Signal Processor架构
1. 创建 `execution/signal_processor/`
   - `signal_processor.py` - 主协调器
   - `position_tracker.py` - 状态管理
   - `exit_calculator.py` - Exit逻辑
   - `models.py` - 数据模型
   - `exit_rules.py` - 规则定义（已完成）

2. 简化 `BaseStrategy` 接口
   ```python
   class BaseStrategy(ABC):
       @abstractmethod
       def compute_indicators(data) -> DataFrame

       @abstractmethod
       def generate_entry_signals(data) -> EntrySignals  # 新增

       @abstractmethod
       def get_exit_rules(is_2b=False) -> ExitRules      # 新增

       @abstractmethod
       def calculate_position_size(data, equity) -> Series
   ```

3. 重构 `SRShortStrategy`
   - 从700行减到~200行
   - 只保留信号逻辑
   - 移除position tracking代码

### Phase 2: 集成到Orchestration
```python
# orchestration/backtest_runner.py
class BacktestRunner:
    def run(self, config):
        # 1. Load data
        data = self.data_manager.get_klines(...)

        # 2. Strategy generates indicators + entry signals + rules
        data = config.strategy.compute_indicators(data)
        entry_signals = config.strategy.generate_entry_signals(data)
        exit_rules = config.strategy.get_exit_rules()
        sizes = config.strategy.calculate_position_size(data, equity)

        # 3. Signal Processor converts to orders
        processor = SignalProcessor()
        orders = processor.process(
            entry_signals=entry_signals,
            exit_rules=exit_rules,
            data=data,
            sizes=sizes
        )

        # 4. Engine simulates
        result = config.engine.run(data, orders, config.backtest_config)

        return result
```

---

## 架构对比：Before vs After

### Before (当前)
```
Strategy
├── compute_indicators()     ✓
├── generate_signals()       ✗ 700行，包含：
│   ├── 入场逻辑            ✓
│   ├── Position tracking   ✗
│   ├── Exit计算            ✗
│   ├── Trailing stop更新   ✗
│   └── Order生成           ✗
└── calculate_position_size() ✓
```

### After (推荐)
```
Strategy                          Signal Processor
├── compute_indicators()     →
├── generate_entry_signals() →   ├── PositionTracker
├── get_exit_rules()         →   ├── ExitCalculator
└── calculate_position_size()→   └── OrderGenerator
    (~200 lines, pure logic)         (~400 lines, execution)
```

---

## 总结

### 核心设计原则
1. **Separation of Concerns**:
   - Strategy = WHAT (logic)
   - Processor = HOW (execution)
   - Engine = SIMULATE (portfolio)

2. **Single Responsibility**:
   - `position_sizer`: ENTRY sizing (纯函数)
   - `SignalProcessor`: Signal→Order conversion (状态管理)
   - `VectorBTEngine`: Portfolio simulation

3. **Clarity in Naming**:
   - 避免`PositionManager`（太泛）
   - 使用`SignalProcessor`（明确职责）

### 下一步
是否按照这个架构重构？还是你有其他想法？


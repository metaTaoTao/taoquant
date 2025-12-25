# 架构重构方案：Position Manager Pattern

## 当前问题

**违反关注点分离（SoC）**：
```python
# strategies/signal_based/sr_short.py (当前)
class SRShortStrategy:
    def generate_signals(self):
        # ❌ 策略层做了太多事情：
        - 追踪positions列表
        - 计算trailing stops
        - 管理position lifecycle (TP1/TP2/SL)
        - 生成orders
        - 处理force close
```

**后果**：
1. 策略代码臃肿（700+ lines）
2. 难以测试（状态管理复杂）
3. 难以复用（trailing stop逻辑耦合在策略中）
4. 难以扩展（加新的exit策略需要修改策略代码）

---

## 重构目标

### 清晰的分层架构

```
┌───────────────────────────────────────────────────────────┐
│ Strategy Layer (strategies/)                               │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ 职责：定义WHAT（信号逻辑 + 风险规则）                        │
│                                                            │
│ class SRShortStrategy(BaseStrategy):                      │
│     def generate_entry_signals() → EntrySignals           │
│     def get_exit_rules() → ExitRules                      │
│     def get_risk_config() → RiskConfig                    │
└───────────────────────────────────────────────────────────┘
                         ↓ signals + rules
┌───────────────────────────────────────────────────────────┐
│ Position Manager Layer (execution/position_manager/)       │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ 职责：执行HOW（Position tracking + Exit execution）        │
│                                                            │
│ class PositionManager:                                    │
│     def track_positions()                                 │
│     def calculate_trailing_stops()                        │
│     def execute_exits(exit_rules)                         │
│     def generate_orders() → Orders                        │
└───────────────────────────────────────────────────────────┘
                         ↓ orders
┌───────────────────────────────────────────────────────────┐
│ Engine Layer (execution/engines/vectorbt_engine.py)        │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ 职责：Portfolio simulation                                 │
│                                                            │
│ class VectorBTEngine:                                     │
│     def run(orders) → BacktestResult                      │
└───────────────────────────────────────────────────────────┘
```

---

## 详细设计

### 1. Strategy Layer (纯粹的信号逻辑)

```python
# strategies/signal_based/sr_short.py

from dataclasses import dataclass
from execution.position_manager.exit_rules import (
    ExitRules, TrailingStopRule, ZeroCostRule
)

@dataclass
class SRShortConfig(StrategyConfig):
    """只包含策略参数，不包含执行细节"""
    # Zone detection
    left_len: int = 90
    right_len: int = 10

    # Risk management (定义规则，不执行)
    risk_per_trade_pct: float = 0.5
    stop_loss_atr_mult: float = 3.0

    # Exit rules configuration (而不是直接计算)
    use_zero_cost: bool = True
    zero_cost_trigger_rr: float = 3.33
    zero_cost_exit_pct: float = 0.30
    trailing_stop_atr_mult: float = 5.0
    trailing_offset_atr_mult: float = 2.0

class SRShortStrategy(BaseStrategy):
    """只负责信号生成和规则定义"""

    def generate_entry_signals(self, data: pd.DataFrame) -> EntrySignals:
        """纯函数：生成入场信号"""
        # 1. 检测阻力区
        zones = self._detect_resistance_zones(data)

        # 2. 生成入场条件
        entry_condition = (
            (data['close'] >= zones['zone_bottom']) &
            (data['close'] <= zones['zone_top'])
        )

        return EntrySignals(
            entries=entry_condition,
            direction='short',
            zone_info=zones,  # 附加信息供Position Manager使用
        )

    def get_exit_rules(self, is_2b_trade: bool = False) -> ExitRules:
        """定义退出规则（配置，不执行）"""
        if is_2b_trade:
            return ExitRules(
                stop_loss=StopLossRule(
                    type='atr',
                    atr_mult=self.config.b2_stop_loss_atr_mult
                ),
                take_profit=[
                    ZeroCostRule(
                        trigger_rr=self.config.b2_zero_cost_trigger_rr,
                        exit_pct=0.30,
                        lock_risk=True
                    )
                ],
                trailing_stop=TrailingStopRule(
                    distance_atr_mult=self.config.b2_trailing_stop_atr_mult,
                    offset_atr_mult=self.config.b2_trailing_offset_atr_mult
                )
            )
        else:
            return ExitRules(
                stop_loss=StopLossRule(
                    type='atr',
                    atr_mult=self.config.stop_loss_atr_mult
                ),
                take_profit=[
                    ZeroCostRule(
                        trigger_rr=self.config.zero_cost_trigger_rr,
                        exit_pct=self.config.zero_cost_exit_pct,
                        lock_risk=True
                    )
                ],
                trailing_stop=TrailingStopRule(
                    distance_atr_mult=self.config.trailing_stop_atr_mult,
                    offset_atr_mult=self.config.trailing_offset_atr_mult
                )
            )

    def get_risk_config(self) -> RiskConfig:
        """定义风险配置"""
        return RiskConfig(
            risk_per_trade=self.config.risk_per_trade_pct / 100,
            leverage=self.config.leverage,
            max_positions=5
        )
```

### 2. Position Manager Layer (执行逻辑)

```python
# execution/position_manager/position_manager.py

from dataclasses import dataclass
from typing import List, Dict
import pandas as pd

@dataclass
class Position:
    """Position状态（纯数据）"""
    id: str
    entry_idx: int
    entry_price: float
    entry_atr: float
    direction: str  # 'long' or 'short'
    size: float
    is_2b_trade: bool = False

    # Exit tracking
    tp1_hit: bool = False
    best_price: float = None  # Tracks best profit price
    trailing_stop_price: float = None

    # Metadata
    zone_key: tuple = None
    exit_rules: ExitRules = None

class PositionManager:
    """管理position lifecycle和exits"""

    def __init__(self):
        self.positions: List[Position] = []
        self.orders: pd.Series = None

    def process_bar(
        self,
        idx: int,
        price: float,
        atr: float,
        entry_signal: bool,
        exit_rules: ExitRules
    ) -> OrderAction:
        """处理每个bar的逻辑"""

        # 1. Check exits for existing positions
        for pos in self.positions:
            exit_action = self._check_exits(pos, idx, price, atr)
            if exit_action:
                return exit_action

        # 2. Check new entries
        if entry_signal and len(self.positions) < self.max_positions:
            return self._create_entry(idx, price, atr, exit_rules)

        return None

    def _check_exits(
        self,
        pos: Position,
        idx: int,
        price: float,
        atr: float
    ) -> OrderAction:
        """检查所有退出条件"""

        # 1. Update best price (for trailing stop)
        if pos.direction == 'short':
            if price < pos.best_price:
                pos.best_price = price
        else:
            if price > pos.best_price:
                pos.best_price = price

        # 2. Check Stop Loss
        sl_hit, sl_price = self._check_stop_loss(pos, price)
        if sl_hit:
            return OrderAction(
                type='SL',
                position_id=pos.id,
                size=1.0,  # Close 100%
                price=price
            )

        # 3. Check TP1 (Zero-Cost)
        if not pos.tp1_hit:
            tp1_hit, tp1_pct = self._check_zero_cost_tp(pos, price)
            if tp1_hit:
                pos.tp1_hit = True
                return OrderAction(
                    type='TP1',
                    position_id=pos.id,
                    size=tp1_pct,  # Partial exit
                    price=price
                )

        # 4. Check Trailing Stop (only after TP1)
        if pos.tp1_hit:
            ts_hit, ts_price = self._check_trailing_stop(pos, price, atr)
            if ts_hit:
                return OrderAction(
                    type='TP2',
                    position_id=pos.id,
                    size=1.0,  # Close remaining
                    price=price
                )

        return None

    def _check_trailing_stop(
        self,
        pos: Position,
        price: float,
        atr: float
    ) -> tuple[bool, float]:
        """计算和检查trailing stop"""
        rule = pos.exit_rules.trailing_stop

        # Calculate new trailing stop
        distance = atr * rule.distance_atr_mult
        offset = atr * rule.offset_atr_mult

        if pos.direction == 'short':
            new_stop = pos.best_price + distance - offset

            # Update trailing stop (move DOWN for short)
            if pos.trailing_stop_price is None:
                pos.trailing_stop_price = new_stop
            else:
                pos.trailing_stop_price = min(pos.trailing_stop_price, new_stop)

            # Check if hit
            return price >= pos.trailing_stop_price, pos.trailing_stop_price
        else:
            new_stop = pos.best_price - distance + offset

            # Update trailing stop (move UP for long)
            if pos.trailing_stop_price is None:
                pos.trailing_stop_price = new_stop
            else:
                pos.trailing_stop_price = max(pos.trailing_stop_price, new_stop)

            # Check if hit
            return price <= pos.trailing_stop_price, pos.trailing_stop_price
```

### 3. Orchestration (整合)

```python
# orchestration/backtest_runner.py

class BacktestRunner:
    def run(self, config: BacktestRunConfig) -> BacktestResult:
        # 1. Load data
        data = self.data_manager.get_klines(...)

        # 2. Strategy generates signals and rules
        data = config.strategy.compute_indicators(data)
        entry_signals = config.strategy.generate_entry_signals(data)
        exit_rules = config.strategy.get_exit_rules()

        # 3. Position Manager executes
        pm = PositionManager()
        orders = pm.process_signals(
            data=data,
            entry_signals=entry_signals,
            exit_rules=exit_rules
        )

        # 4. Engine simulates
        result = config.engine.run(
            data=data,
            orders=orders,
            config=config.backtest_config
        )

        return result
```

---

## 优势

### ✅ 关注点分离
- Strategy: 只定义WHAT（信号逻辑）
- Position Manager: 只执行HOW（position管理）
- Engine: 只模拟结果

### ✅ 可测试性
```python
# 测试trailing stop逻辑（独立）
def test_trailing_stop_short():
    pm = PositionManager()
    pos = Position(entry_price=100, direction='short')

    # Price drops to 90
    pm._update_trailing_stop(pos, price=90, atr=2)
    assert pos.trailing_stop_price == 90 + 6  # 3 ATR

    # Price drops to 85
    pm._update_trailing_stop(pos, price=85, atr=2)
    assert pos.trailing_stop_price == 85 + 6  # Follows down

    # Price rises to 88
    pm._update_trailing_stop(pos, price=88, atr=2)
    assert pos.trailing_stop_price == 85 + 6  # Doesn't move up!
```

### ✅ 可复用性
```python
# 任何策略都可以用Position Manager
class MACDStrategy(BaseStrategy):
    def get_exit_rules(self):
        return ExitRules(
            trailing_stop=TrailingStopRule(...)  # 复用相同的trailing stop逻辑
        )
```

### ✅ 可扩展性
```python
# 添加新的exit rule类型（不修改策略代码）
class TimeBasedExitRule(ExitRule):
    max_holding_hours: int = 48

# Position Manager自动支持
pm.register_exit_rule(TimeBasedExitRule)
```

---

## 迁移路径

### Phase 1: 创建Position Manager（不破坏现有代码）
1. 创建 `execution/position_manager/` 模块
2. 实现 `PositionManager` 类
3. 添加单元测试

### Phase 2: 重构一个策略（作为示例）
1. 重构 `SRShortStrategy` 使用 `PositionManager`
2. 对比回测结果（应该完全一致）
3. 性能测试

### Phase 3: 迁移其他策略
1. 将 `BaseStrategy` 改为使用 `PositionManager`
2. 迁移现有策略
3. 删除旧代码

---

## 总结

当前问题：**策略做了太多事情**
- generate_signals() 700+ lines
- 混杂了信号逻辑、position tracking、exit execution

重构后：**清晰分层**
- Strategy (100 lines): 信号 + 规则定义
- Position Manager (300 lines): Position lifecycle
- Engine: Portfolio simulation

**符合Clean Architecture原则**：
- Single Responsibility
- Open/Closed (添加新exit rule不修改现有代码)
- Dependency Inversion (Strategy依赖抽象的ExitRules，不依赖具体实现)


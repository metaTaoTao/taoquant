# TaoGrid迁移到Lean框架 - 实施计划

> **创建日期**: 2025-12-13
> **目标**: 将TaoGrid策略从VectorBT迁移到Lean框架，实现完整的throttling和DGT验证
> **预期时间**: 2-3小时核心开发 + 1-2小时测试验证

---

## 🎯 迁移目标

### 主要目标

1. ✅ **完整验证Sprint 2功能**
   - Throttling (Inventory/Profit/Volatility)
   - DGT (Mid-shift)
   - Real-time risk management

2. ✅ **实现Event-Driven执行**
   - 逐bar处理
   - 实时状态访问
   - 动态decision making

3. ✅ **代码复用最大化**
   - 复用grid_generator
   - 复用grid_weights
   - 复用risk_manager
   - 复用inventory_tracker

4. ✅ **准备实盘部署**
   - Lean原生支持交易所连接
   - 无缝backtest→live切换

---

## 📋 Phase 1: 环境准备

### Task 1.1: 安装Lean框架

**优先级**: 🔴 Critical
**预估时间**: 30分钟

**步骤**:

```bash
# Option A: 使用QuantConnect Cloud（推荐入门）
# 1. 注册账号: https://www.quantconnect.com/
# 2. 创建新项目
# 3. 直接在云端开发

# Option B: 本地安装Lean Engine
# 1. Clone Lean仓库
git clone https://github.com/QuantConnect/Lean.git

# 2. 安装依赖
cd Lean
pip install -r requirements.txt

# 3. 安装Python.NET（Lean的Python支持）
pip install pythonnet

# Option C: 使用Docker（最简单）
docker pull quantconnect/lean:latest
```

**验收标准**:
- [ ] Lean环境可运行
- [ ] 能够运行示例算法
- [ ] Python环境配置正确

**参考资源**:
- Lean官方文档: https://www.quantconnect.com/docs
- GitHub: https://github.com/QuantConnect/Lean

---

### Task 1.2: 理解Lean架构

**优先级**: 🟡 Medium
**预估时间**: 20分钟

**学习要点**:

1. **QCAlgorithm基类**:
   ```python
   class MyAlgorithm(QCAlgorithm):
       def Initialize(self):
           """策略初始化（类似__init__）"""
           pass

       def OnData(self, data: Slice):
           """每个数据点触发（event-driven核心）"""
           pass
   ```

2. **关键API**:
   - `self.Portfolio`: 访问持仓、equity
   - `self.Securities[symbol]`: 访问价格、指标
   - `self.MarketOrder()`: 下单
   - `self.AddCrypto()`: 添加加密货币

3. **Indicator系统**:
   ```python
   self.atr = self.ATR(symbol, period)
   self.sma = self.SMA(symbol, period)
   ```

**验收标准**:
- [ ] 理解Initialize()和OnData()的作用
- [ ] 理解Portfolio和Securities
- [ ] 能运行一个简单的买卖策略

**参考代码**:
```python
# 最简单的Lean算法示例
from AlgorithmImports import *

class SimpleAlgorithm(QCAlgorithm):
    def Initialize(self):
        self.SetStartDate(2025, 1, 1)
        self.SetCash(100000)
        self.symbol = self.AddCrypto("BTCUSDT", Resolution.Minute).Symbol

    def OnData(self, data):
        if not self.Portfolio.Invested:
            self.MarketOrder(self.symbol, 0.01)
```

---

## 📋 Phase 2: 项目结构设计

### Task 2.1: 创建Lean项目目录

**优先级**: 🔴 Critical
**预估时间**: 10分钟

**目录结构**:

```
taoquant/
├── algorithms/                    # 新增：Lean算法目录
│   ├── __init__.py
│   ├── taogrid_lean.py           # 主算法文件
│   └── taogrid_lean_config.py    # 配置文件
│
├── analytics/                     # 保持不变（直接复用）
│   ├── indicators/
│   │   ├── grid_generator.py     ✅ 直接import
│   │   ├── grid_weights.py       ✅ 直接import
│   │   └── volatility.py         ✅ 直接import
│
├── risk_management/               # 保持不变（直接复用）
│   ├── grid_inventory.py         ✅ 直接import
│   └── grid_risk_manager.py      ✅ 直接import
│
├── strategies/                    # VectorBT版本（保留）
│   └── signal_based/
│       └── taogrid_strategy.py
│
├── run/                           # 回测脚本
│   ├── run_taogrid_lean.py       # 新增：Lean回测脚本
│   ├── run_taogrid_sprint2.py    # 保留：VectorBT版本
│
└── docs/
    └── strategies/
        ├── taogrid_lean_migration_plan.md  # 本文档
        └── taogrid_lean_usage.md           # 新增：使用文档
```

**操作**:
```bash
# 创建目录
mkdir -p algorithms
touch algorithms/__init__.py
touch algorithms/taogrid_lean.py
touch algorithms/taogrid_lean_config.py

# 创建文档
touch docs/strategies/taogrid_lean_usage.md
```

**验收标准**:
- [ ] 目录结构创建完成
- [ ] 文件占位符创建
- [ ] __init__.py正确配置

---

### Task 2.2: 设计Lean算法架构

**优先级**: 🔴 Critical
**预估时间**: 20分钟

**架构设计**:

```python
"""
TaoGrid Lean算法架构设计

核心类:
1. TaoGridLeanAlgorithm (QCAlgorithm)
   - 主算法类，继承QCAlgorithm
   - 管理整体执行流程

2. GridManager
   - 管理网格levels
   - 检测价格穿越
   - 触发买卖信号

3. 复用现有模块:
   - GridInventoryTracker (risk_management/)
   - GridRiskManager (risk_management/)
   - grid_generator (analytics/indicators/)
   - grid_weights (analytics/indicators/)

执行流程:
Initialize() → 配置策略、生成初始网格
   ↓
OnData() → 检查价格穿越
   ↓
OnGridSignal() → 应用throttling → 执行订单
   ↓
UpdateInventory() → 更新持仓追踪
"""
```

**类图**:
```
QCAlgorithm (Lean基类)
    ↑
    |
TaoGridLeanAlgorithm
    |-- GridManager (网格管理)
    |-- GridInventoryTracker (持仓追踪)
    |-- GridRiskManager (风险管理)
    |-- ATR Indicators (技术指标)
    |
    ↓
grid_generator (复用)
grid_weights (复用)
```

**验收标准**:
- [ ] 架构设计清晰
- [ ] 类职责明确
- [ ] 复用策略确定

---

## 📋 Phase 3: 核心模块实现

### Task 3.1: 实现GridManager辅助类

**优先级**: 🔴 Critical
**预估时间**: 30分钟

**文件**: `algorithms/grid_manager.py`

**功能需求**:
1. 存储当前网格levels
2. 检测价格穿越
3. 管理网格更新（DGT）

**代码框架**:

```python
"""Grid Manager for Lean Algorithm"""

import numpy as np
from typing import List, Tuple, Optional

class GridManager:
    """
    管理TaoGrid的网格层级和穿越检测.

    职责:
    1. 存储buy/sell levels
    2. 检测价格穿越事件
    3. 支持DGT（动态网格更新）
    """

    def __init__(
        self,
        buy_levels: np.ndarray,
        sell_levels: np.ndarray,
        enable_dgt: bool = False
    ):
        self.buy_levels = buy_levels
        self.sell_levels = sell_levels
        self.enable_dgt = enable_dgt

        # 记录上一个价格（用于穿越检测）
        self.previous_price: Optional[float] = None

        # 记录已触发的levels（避免重复触发）
        self.triggered_buy_levels = set()
        self.triggered_sell_levels = set()

    def update_price(self, current_price: float) -> List[Tuple[str, int, float]]:
        """
        更新价格，检测穿越事件.

        Returns:
            List of (signal_type, level_index, level_price)
            - signal_type: 'buy' or 'sell'
            - level_index: 0-based index
            - level_price: 穿越的价格level
        """
        if self.previous_price is None:
            self.previous_price = current_price
            return []

        signals = []

        # 检查buy levels（向下穿越）
        for i, level in enumerate(self.buy_levels):
            if self._crossed_below(self.previous_price, current_price, level):
                if i not in self.triggered_buy_levels:
                    signals.append(('buy', i, level))
                    self.triggered_buy_levels.add(i)

        # 检查sell levels（向上穿越）
        for i, level in enumerate(self.sell_levels):
            if self._crossed_above(self.previous_price, current_price, level):
                if i not in self.triggered_sell_levels:
                    signals.append(('sell', i, level))
                    self.triggered_sell_levels.add(i)

        self.previous_price = current_price
        return signals

    def _crossed_below(self, prev: float, curr: float, level: float) -> bool:
        """检测向下穿越"""
        return prev > level and curr <= level

    def _crossed_above(self, prev: float, curr: float, level: float) -> bool:
        """检测向上穿越"""
        return prev < level and curr >= level

    def reset_triggers(self):
        """重置触发状态（价格重新进入range时）"""
        self.triggered_buy_levels.clear()
        self.triggered_sell_levels.clear()

    def update_grid(self, new_buy_levels: np.ndarray, new_sell_levels: np.ndarray):
        """更新网格levels（DGT mid-shift）"""
        self.buy_levels = new_buy_levels
        self.sell_levels = new_sell_levels
        self.reset_triggers()
```

**任务清单**:
- [ ] 创建`algorithms/grid_manager.py`
- [ ] 实现GridManager类
- [ ] 实现穿越检测逻辑
- [ ] 添加触发状态管理
- [ ] 添加网格更新功能（DGT支持）
- [ ] 编写单元测试

**测试用例**:
```python
# test_grid_manager.py
def test_crossed_below():
    manager = GridManager(
        buy_levels=np.array([99000, 98000]),
        sell_levels=np.array([101000, 102000])
    )

    # 向下穿越99000
    signals = manager.update_price(99500)
    assert len(signals) == 0

    signals = manager.update_price(98500)
    assert len(signals) == 1
    assert signals[0] == ('buy', 0, 99000)
```

---

### Task 3.2: 实现TaoGridConfig配置类

**优先级**: 🔴 Critical
**预估时间**: 15分钟

**文件**: `algorithms/taogrid_lean_config.py`

**代码框架**:

```python
"""TaoGrid Configuration for Lean Algorithm"""

from dataclasses import dataclass
from typing import Literal

RegimeType = Literal["UP_RANGE", "NEUTRAL_RANGE", "DOWN_RANGE"]

@dataclass
class TaoGridLeanConfig:
    """
    TaoGrid策略配置（Lean版本）.

    与VectorBT版本的TaoGridConfig保持一致的参数.
    """

    # === Backtest Settings ===
    start_date: tuple = (2025, 10, 1)
    end_date: tuple = (2025, 12, 1)
    initial_cash: float = 100000.0

    # === Symbol Settings ===
    symbol: str = "BTCUSDT"
    resolution: str = "Minute"  # Minute, Hour, Daily
    market: str = "Binance"

    # === Manual Inputs (Trader Specifies) ===
    support: float = 104000.0
    resistance: float = 126000.0
    regime: RegimeType = "NEUTRAL_RANGE"

    # === Grid Parameters ===
    grid_layers_buy: int = 5
    grid_layers_sell: int = 5
    weight_k: float = 0.5
    spacing_multiplier: float = 0.1
    cushion_multiplier: float = 0.8
    min_return: float = 0.005
    maker_fee: float = 0.001
    volatility_k: float = 0.6

    # === Risk Parameters ===
    risk_budget_pct: float = 0.3
    max_long_units: float = 10.0
    max_short_units: float = 10.0

    # === Sprint 2: Throttling ===
    enable_throttling: bool = True
    inventory_threshold: float = 0.9
    profit_target_pct: float = 0.5
    profit_reduction: float = 0.5
    volatility_threshold: float = 2.0
    volatility_reduction: float = 0.5

    # === Sprint 2: DGT ===
    enable_mid_shift: bool = False
    mid_shift_threshold: int = 20

    # === ATR Parameters ===
    atr_period: int = 14

    def get_mid_price(self) -> float:
        return (self.support + self.resistance) / 2

    def get_side_allocation(self) -> dict:
        if self.regime == "UP_RANGE":
            return {"buy_pct": 0.7, "sell_pct": 0.3}
        elif self.regime == "NEUTRAL_RANGE":
            return {"buy_pct": 0.5, "sell_pct": 0.5}
        else:  # DOWN_RANGE
            return {"buy_pct": 0.3, "sell_pct": 0.7}
```

**任务清单**:
- [ ] 创建配置类
- [ ] 添加所有必要参数
- [ ] 添加辅助方法
- [ ] 添加参数验证

---

### Task 3.3: 实现主算法类

**优先级**: 🔴 Critical
**预估时间**: 60分钟

**文件**: `algorithms/taogrid_lean.py`

**代码框架**:

```python
"""
TaoGrid Strategy for Lean Framework.

This is the Lean implementation of TaoGrid strategy, designed to:
1. Fully support throttling (Inventory/Profit/Volatility)
2. Fully support DGT (Dynamic Grid Trading)
3. Enable seamless backtest-to-live transition

Key differences from VectorBT version:
- Event-driven execution (vs vectorized)
- Real-time state access (Portfolio, Equity, PnL)
- Dynamic throttling application
- Direct exchange connectivity ready

References:
    - VectorBT version: strategies/signal_based/taogrid_strategy.py
    - Implementation Plan: docs/strategies/taogrid_lean_migration_plan.md
"""

from AlgorithmImports import *
import sys
from pathlib import Path

# Add project root to path (for local development)
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import TaoGrid modules (reuse existing code!)
from risk_management.grid_inventory import GridInventoryTracker
from risk_management.grid_risk_manager import GridRiskManager
from analytics.indicators.grid_generator import (
    generate_grid_levels,
    calculate_mid_shift
)
from analytics.indicators.grid_weights import (
    calculate_level_weights,
    allocate_side_budgets,
    calculate_layer_sizes
)
from algorithms.grid_manager import GridManager
from algorithms.taogrid_lean_config import TaoGridLeanConfig


class TaoGridLeanAlgorithm(QCAlgorithm):
    """
    TaoGrid Strategy implemented in Lean Framework.

    Features:
    - Manual S/R and Regime input
    - ATR-based dynamic spacing
    - Level-wise weighting (edge-heavy)
    - Regime-based allocation (70/30, 50/50, 30/70)
    - Real-time throttling (Inventory/Profit/Volatility)
    - DGT (Dynamic Grid Trading) support
    """

    def Initialize(self):
        """Initialize strategy (called once at start)"""

        # === Load Configuration ===
        self.config = TaoGridLeanConfig()

        # === Backtest Settings ===
        self.SetStartDate(*self.config.start_date)
        self.SetEndDate(*self.config.end_date)
        self.SetCash(self.config.initial_cash)

        # === Add Symbol ===
        resolution = Resolution.Minute  # or Resolution.Hour
        self.symbol = self.AddCrypto(
            self.config.symbol,
            resolution,
            Market.Binance
        ).Symbol

        # === Initialize Indicators ===
        self.atr = self.ATR(
            self.symbol,
            self.config.atr_period,
            MovingAverageType.Simple,
            resolution
        )
        self.atr_sma = IndicatorExtensions.SMA(self.atr, 20)

        # Warm up indicators
        self.SetWarmup(self.config.atr_period + 20)

        # === Initialize Risk Management ===
        if self.config.enable_throttling:
            self.inventory_tracker = GridInventoryTracker(
                max_long_units=self.config.max_long_units,
                max_short_units=self.config.max_short_units
            )

            self.risk_manager = GridRiskManager(
                max_long_units=self.config.max_long_units,
                max_short_units=self.config.max_short_units,
                inventory_threshold=self.config.inventory_threshold,
                profit_target_pct=self.config.profit_target_pct,
                profit_reduction=self.config.profit_reduction,
                volatility_threshold=self.config.volatility_threshold,
                volatility_reduction=self.config.volatility_reduction
            )
        else:
            self.inventory_tracker = None
            self.risk_manager = None

        # === Generate Initial Grid ===
        self.UpdateGrid()

        # === Initialize Grid Manager ===
        self.grid_manager = GridManager(
            buy_levels=self.buy_levels,
            sell_levels=self.sell_levels,
            enable_dgt=self.config.enable_mid_shift
        )

        # === DGT State ===
        self.current_mid = self.config.get_mid_price()
        self.bars_since_last_shift = 0

        # === Logging ===
        self.Debug("=" * 60)
        self.Debug("TaoGrid Lean Algorithm Initialized")
        self.Debug("=" * 60)
        self.Debug(f"Symbol: {self.config.symbol}")
        self.Debug(f"S/R: ${self.config.support:,.0f} - ${self.config.resistance:,.0f}")
        self.Debug(f"Regime: {self.config.regime}")
        self.Debug(f"Layers: {self.config.grid_layers_buy} buy, {self.config.grid_layers_sell} sell")
        self.Debug(f"Throttling: {self.config.enable_throttling}")
        self.Debug(f"DGT: {self.config.enable_mid_shift}")
        self.Debug("=" * 60)

    def UpdateGrid(self):
        """Generate/update grid levels"""

        # Get current ATR
        if not self.atr.IsReady:
            current_atr = 0
        else:
            current_atr = self.atr.Current.Value

        # Calculate spacing
        cushion = current_atr * self.config.cushion_multiplier
        # Simplified spacing (use ATR-based in production)
        spacing_pct = 0.011 * self.config.spacing_multiplier

        # Generate grid
        grid = generate_grid_levels(
            mid_price=self.current_mid,
            support=self.config.support,
            resistance=self.config.resistance,
            cushion=cushion,
            spacing_pct=spacing_pct,
            layers_buy=self.config.grid_layers_buy,
            layers_sell=self.config.grid_layers_sell
        )

        self.buy_levels = grid['buy_levels']
        self.sell_levels = grid['sell_levels']

        self.Debug(f"Grid updated: {len(self.buy_levels)} buy, {len(self.sell_levels)} sell levels")

    def OnData(self, data: Slice):
        """Event handler called on each data point"""

        # Skip during warmup
        if self.IsWarmingUp:
            return

        # Check if we have data
        if not data.ContainsKey(self.symbol):
            return

        price = data[self.symbol].Close

        # === DGT: Check mid-shift ===
        if self.config.enable_mid_shift:
            self.bars_since_last_shift += 1
            if self.bars_since_last_shift >= self.config.mid_shift_threshold:
                self.CheckMidShift()

        # === Detect Grid Crosses ===
        signals = self.grid_manager.update_price(price)

        # === Process Signals ===
        for signal_type, level_index, level_price in signals:
            if signal_type == 'buy':
                self.OnGridBuySignal(price, level_index, level_price)
            elif signal_type == 'sell':
                self.OnGridSellSignal(price, level_index, level_price)

    def OnGridBuySignal(self, price: float, level_index: int, level_price: float):
        """Handle grid buy signal"""

        self.Debug(f"Buy signal: Layer {level_index+1} at ${price:,.0f}")

        # === Get Current State ===
        current_equity = self.Portfolio.TotalPortfolioValue
        long_exposure = abs(self.Portfolio[self.symbol].Quantity)

        # Simplified daily PnL (use proper calculation in production)
        daily_pnl = self.Portfolio.TotalProfit

        # === Apply Throttling ===
        if self.config.enable_throttling:
            status = self.risk_manager.check_throttle(
                long_exposure=long_exposure,
                short_exposure=0,
                daily_pnl=daily_pnl,
                risk_budget=current_equity * self.config.risk_budget_pct,
                current_atr=self.atr.Current.Value if self.atr.IsReady else 0,
                avg_atr=self.atr_sma.Current.Value if self.atr_sma.IsReady else 0
            )

            if status.size_multiplier == 0:
                self.Debug(f"  ❌ Order blocked: {status.reason}")
                return

            size_multiplier = status.size_multiplier
            if size_multiplier < 1.0:
                self.Debug(f"  ⚠️  Throttled to {size_multiplier:.0%}: {status.reason}")
        else:
            size_multiplier = 1.0

        # === Calculate Position Size ===
        size = self.CalculatePositionSize(
            level_index=level_index,
            is_buy=True,
            current_equity=current_equity,
            current_price=price
        )

        # Apply throttle
        adjusted_size = size * size_multiplier

        # === Execute Order ===
        if adjusted_size > 0:
            self.MarketOrder(self.symbol, adjusted_size)
            self.Debug(f"  ✅ Buy {adjusted_size:.6f} BTC at ${price:,.0f}")

            # Update inventory tracker
            if self.inventory_tracker:
                self.inventory_tracker.update(
                    long_size=adjusted_size,
                    grid_level=f'buy_L{level_index+1}'
                )

    def OnGridSellSignal(self, price: float, level_index: int, level_price: float):
        """Handle grid sell signal (exit long)"""

        # Check if we have position to exit
        if self.Portfolio[self.symbol].Quantity <= 0:
            return

        self.Debug(f"Sell signal: Layer {level_index+1} at ${price:,.0f}")

        # Exit position (simplified: full exit)
        # In production: calculate partial exit based on layer
        quantity = self.Portfolio[self.symbol].Quantity

        self.MarketOrder(self.symbol, -quantity)
        self.Debug(f"  ✅ Sell {quantity:.6f} BTC at ${price:,.0f}")

        # Update inventory
        if self.inventory_tracker:
            self.inventory_tracker.update(
                long_size=-quantity,
                grid_level=f'sell_L{level_index+1}'
            )

    def CalculatePositionSize(
        self,
        level_index: int,
        is_buy: bool,
        current_equity: float,
        current_price: float
    ) -> float:
        """Calculate position size for grid level"""

        # Calculate budget
        total_budget = current_equity * self.config.risk_budget_pct
        side_budgets = allocate_side_budgets(total_budget, self.config.regime)

        budget = side_budgets['buy_budget'] if is_buy else side_budgets['sell_budget']

        # Calculate weights
        num_levels = self.config.grid_layers_buy if is_buy else self.config.grid_layers_sell
        weights = calculate_level_weights(num_levels, self.config.weight_k)

        # Layer size
        layer_weight = weights[level_index]
        nominal = budget * layer_weight
        size = nominal / current_price

        return size

    def CheckMidShift(self):
        """Check and apply DGT mid-shift if needed"""

        # Get recent bars (simplified: use price history)
        history = self.History(self.symbol, self.config.mid_shift_threshold, Resolution.Minute)

        if history.empty:
            return

        # Calculate new mid
        # (Need to convert history to DataFrame format expected by calculate_mid_shift)
        # Simplified implementation here

        # Reset counter
        self.bars_since_last_shift = 0
```

**任务清单**:
- [ ] 创建主算法文件
- [ ] 实现Initialize()方法
- [ ] 实现OnData()事件处理
- [ ] 实现网格信号处理
- [ ] 实现throttling集成
- [ ] 实现position sizing
- [ ] 实现DGT mid-shift
- [ ] 添加日志和调试输出

---

## 📋 Phase 4: 测试验证

### Task 4.1: 单元测试

**优先级**: 🟡 Medium
**预估时间**: 30分钟

**测试文件**: `tests/test_taogrid_lean.py`

**测试用例**:

```python
import unittest
from algorithms.grid_manager import GridManager
import numpy as np

class TestGridManager(unittest.TestCase):

    def test_grid_initialization(self):
        """测试网格初始化"""
        manager = GridManager(
            buy_levels=np.array([99000, 98000, 97000]),
            sell_levels=np.array([101000, 102000, 103000])
        )
        self.assertEqual(len(manager.buy_levels), 3)
        self.assertEqual(len(manager.sell_levels), 3)

    def test_cross_detection_buy(self):
        """测试买入穿越检测"""
        manager = GridManager(
            buy_levels=np.array([99000]),
            sell_levels=np.array([101000])
        )

        # 价格从100000降到98000，应该触发99000 buy
        manager.update_price(100000)
        signals = manager.update_price(98000)

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0][0], 'buy')
        self.assertEqual(signals[0][1], 0)

    def test_no_duplicate_triggers(self):
        """测试避免重复触发"""
        manager = GridManager(
            buy_levels=np.array([99000]),
            sell_levels=np.array([101000])
        )

        manager.update_price(100000)
        signals1 = manager.update_price(98000)
        signals2 = manager.update_price(97000)  # 继续下跌

        self.assertEqual(len(signals1), 1)
        self.assertEqual(len(signals2), 0)  # 不应重复触发

if __name__ == '__main__':
    unittest.main()
```

**任务清单**:
- [ ] 创建测试文件
- [ ] 测试GridManager
- [ ] 测试穿越检测
- [ ] 测试throttling逻辑
- [ ] 运行所有测试

---

### Task 4.2: Lean回测运行

**优先级**: 🔴 Critical
**预估时间**: 30分钟

**回测脚本**: `run/run_taogrid_lean.py`

```python
"""
Run TaoGrid Lean backtest locally.

Usage:
    python run/run_taogrid_lean.py
"""

from pathlib import Path
import sys

# Add Lean path
lean_path = Path("path/to/Lean/Launcher/bin/Debug")
sys.path.insert(0, str(lean_path))

# Import Lean
from QuantConnect import *
from QuantConnect.Algorithm import *

# Import TaoGrid algorithm
from algorithms.taogrid_lean import TaoGridLeanAlgorithm

# Run backtest
if __name__ == "__main__":
    # Option 1: Use QuantConnect Cloud
    # Upload taogrid_lean.py to cloud and run

    # Option 2: Local Lean Engine
    # Configure and run through Lean CLI

    print("Please run this algorithm through:")
    print("1. QuantConnect Cloud: Upload to project")
    print("2. Lean CLI: lean backtest <project-name>")
```

**验收标准**:
- [ ] 算法成功运行
- [ ] 无报错
- [ ] 生成交易记录
- [ ] 可以查看结果

---

### Task 4.3: 功能验证

**优先级**: 🔴 Critical
**预估时间**: 45分钟

**验证清单**:

1. **Grid Level生成验证**
   - [ ] 检查buy/sell levels是否正确
   - [ ] 验证层数正确
   - [ ] 验证spacing合理

2. **穿越检测验证**
   - [ ] 验证buy signal在价格下穿时触发
   - [ ] 验证sell signal在价格上穿时触发
   - [ ] 验证无重复触发

3. **Throttling验证** ⭐ 关键
   - [ ] Inventory limit: 检查是否在90%时停止
   - [ ] Profit lock: 检查是否在达标时减仓
   - [ ] Volatility throttle: 检查是否在ATR spike时减仓
   - [ ] 检查日志输出throttling原因

4. **Position Sizing验证**
   - [ ] 验证edge-heavy weighting
   - [ ] 验证regime-based allocation
   - [ ] 验证总budget不超限

5. **DGT验证** (如果启用)
   - [ ] 验证mid shift触发条件
   - [ ] 验证网格更新
   - [ ] 验证mid在S/R范围内

**验证方法**:

```python
# 检查Lean日志输出
# 应该看到类似：
"""
Buy signal: Layer 1 at $113,742
  ⚠️  Throttled to 50%: Inventory limit exceeded (92.5% of max)
  ✅ Buy 0.013256 BTC at $113,742

Buy signal: Layer 2 at $112,498
  ❌ Order blocked: Inventory limit exceeded (95.0% of max)
"""

# 对比VectorBT结果
# Lean应该有更少的orders（因为throttling生效）
```

---

## 📋 Phase 5: 结果对比与分析

### Task 5.1: VectorBT vs Lean对比

**优先级**: 🟡 Medium
**预估时间**: 30分钟

**对比维度**:

| 维度 | VectorBT (Sprint 2) | Lean | 预期差异 |
|------|---------------------|------|---------|
| Entry Signals | 131 | ? | 应该更少（throttling） |
| Orders Executed | 131 | ? | 显著更少 |
| Total Return | -18.18% | ? | 应该改善 |
| Max Drawdown | -28.82% | ? | 应该更小 |
| Win Rate | 0% | ? | 应该提升 |

**分析报告**: `docs/strategies/taogrid_lean_vs_vectorbt.md`

```markdown
# TaoGrid: Lean vs VectorBT对比分析

## 回测设置
- Period: 2025-10-01 to 2025-12-01
- Symbol: BTCUSDT 15m
- S/R: 104k-126k
- Regime: NEUTRAL_RANGE

## 结果对比

### Signals & Execution
- VectorBT: 131 signals → 131 orders (throttling无效)
- Lean: 131 signals → XX orders (throttling生效)
- Reduction: XX%

### Performance
- VectorBT Return: -18.18%
- Lean Return: XX%
- Improvement: XX%

### Throttling Effect
- Inventory throttle triggered: XX times
- Profit lock triggered: XX times
- Volatility throttle triggered: XX times

### Key Insights
1. Throttling有效防止过度累积仓位
2. ...
```

**任务清单**:
- [ ] 运行两个版本的回测
- [ ] 收集关键指标
- [ ] 生成对比图表
- [ ] 撰写分析报告

---

### Task 5.2: 性能分析

**优先级**: 🟢 Low
**预估时间**: 20分钟

**性能指标**:

```python
# 回测速度对比
VectorBT: ~X bars/second (vectorized)
Lean: ~Y bars/second (event-driven)

# 内存使用
VectorBT: ~Z MB
Lean: ~W MB

# 结论：
# VectorBT更快（100x+），但无法支持动态风控
# Lean更慢但功能完整，适合grid trading
```

---

## 📋 Phase 6: 文档与交付

### Task 6.1: 使用文档

**优先级**: 🟡 Medium
**预估时间**: 30分钟

**文件**: `docs/strategies/taogrid_lean_usage.md`

**内容大纲**:

```markdown
# TaoGrid Lean版本使用指南

## 快速开始

### 1. 环境准备
...

### 2. 配置策略
...

### 3. 运行回测
...

### 4. 查看结果
...

## 配置参数说明

### 手动输入参数
- support: 支撑位
- resistance: 阻力位
- regime: 市场regime

### 网格参数
...

### Throttling参数
...

## 实盘部署

### 1. 连接交易所
...

### 2. 监控运行
...

## FAQ

### Q: Throttling如何生效？
A: ...

### Q: 如何调整grid spacing？
A: ...
```

**任务清单**:
- [ ] 撰写使用文档
- [ ] 添加配置示例
- [ ] 添加FAQ
- [ ] 添加troubleshooting

---

### Task 6.2: 代码审查清单

**优先级**: 🟡 Medium
**预估时间**: 20分钟

**审查项目**:

```markdown
## Code Review Checklist

### Architecture
- [ ] 代码遵循Lean框架规范
- [ ] 正确使用QCAlgorithm基类
- [ ] 模块职责清晰

### Code Quality
- [ ] 所有函数有type hints
- [ ] 所有函数有docstrings
- [ ] 变量命名清晰
- [ ] 代码可读性好

### Functionality
- [ ] Grid生成正确
- [ ] 穿越检测准确
- [ ] Throttling逻辑正确
- [ ] Position sizing正确

### Testing
- [ ] 单元测试覆盖核心逻辑
- [ ] 回测验证通过
- [ ] 对比分析完成

### Documentation
- [ ] 代码注释完整
- [ ] 使用文档完善
- [ ] 对比报告清晰
```

---

## 📋 Phase 7: 实盘准备（可选）

### Task 7.1: 实盘配置

**优先级**: 🟢 Low (如需实盘)
**预估时间**: 60分钟

**实盘checklist**:

```python
# 1. 连接交易所
self.SetBrokerageModel(BrokerageName.Binance)

# 2. API配置
# 在Lean配置文件中设置API key

# 3. Risk limits
# 设置实盘risk limits（更保守）

# 4. 监控
# 设置报警和监控

# 5. 小资金测试
# 先用小金额测试

# 6. 逐步增加
# 验证后再增加资金
```

---

## 🎯 验收标准

### Sprint 2功能验证

| 功能 | VectorBT | Lean | 状态 |
|------|----------|------|------|
| Inventory Tracking | ⚠️ 无法验证 | ✅ 验证 | 待测试 |
| Inventory Throttle | ⚠️ 无法验证 | ✅ 验证 | 待测试 |
| Profit Lock | ⚠️ 无法验证 | ✅ 验证 | 待测试 |
| Volatility Throttle | ⚠️ 无法验证 | ✅ 验证 | 待测试 |
| DGT Mid-shift | ❌ Bug | ✅ 验证 | 待测试 |
| Static Grid | ✅ 已验证 | ✅ 验证 | 待测试 |

### 代码质量标准

- [ ] 所有模块实现完成
- [ ] 单元测试通过
- [ ] 回测成功运行
- [ ] 文档完整
- [ ] Code review通过

---

## 📈 预期成果

### 技术成果

1. **完整的Lean实现**
   - TaoGrid算法适配Lean
   - 所有现有模块复用
   - Event-driven执行

2. **完整的功能验证**
   - Throttling效果验证
   - DGT功能验证
   - 性能对比分析

3. **实盘就绪**
   - 可直接连接交易所
   - Production-ready代码
   - 监控和日志完善

### 学习成果

1. **Lean框架掌握**
   - QCAlgorithm使用
   - Event-driven编程
   - Portfolio管理

2. **架构理解**
   - Vectorized vs Event-driven
   - Trade-offs分析
   - 最佳实践

---

## 📚 参考资源

### Lean官方资源

- **官方文档**: https://www.quantconnect.com/docs
- **API Reference**: https://www.quantconnect.com/docs/v2/our-platform/api-reference
- **示例代码**: https://github.com/QuantConnect/Lean/tree/master/Algorithm.Python
- **社区论坛**: https://www.quantconnect.com/forum

### TaoGrid相关

- **VectorBT版本**: `strategies/signal_based/taogrid_strategy.py`
- **实施计划**: `docs/strategies/taogrid_implementation_plan_v2.md`
- **Sprint 2总结**: `docs/strategies/taogrid_sprint2_summary.md`

---

## ✅ 总结

### 关键里程碑

1. ✅ **环境准备** (30分钟)
2. ✅ **架构设计** (20分钟)
3. ✅ **GridManager实现** (30分钟)
4. ✅ **主算法实现** (60分钟)
5. ✅ **测试验证** (60分钟)
6. ✅ **对比分析** (30分钟)
7. ✅ **文档完善** (30分钟)

**总计**: ~4小时

### 成功标准

- [ ] Lean版本成功运行
- [ ] Throttling验证生效
- [ ] 性能优于VectorBT版本
- [ ] 文档完整清晰
- [ ] 实盘ready

---

**Last Updated**: 2025-12-13
**Status**: 📋 Ready for Implementation
**Next Step**: Phase 1.1 - 安装Lean框架

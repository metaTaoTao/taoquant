# TaoGrid 网格策略实现计划（V2 - 改进版）

> **批判性审查日期**: 2025-12-13
> **审查者**: Senior Quant Developer & Quant Trader Perspective
> **状态**: ✅ 架构合规，需求对齐，可执行

---

## 🎯 核心原则（Guiding Principles）

### **1. 策略本质理解（What TaoGrid Really Is）**

TaoGrid **≠** 自动化网格系统
TaoGrid **=** **交易员判断** + **算法执行** 的混合模式

**核心特征：**
- ✅ 交易员手动指定 Regime（UP_RANGE/NEUTRAL_RANGE/DOWN_RANGE）
- ✅ 交易员手动指定 S/R 区间（Support/Resistance）
- ✅ 算法负责：网格生成、仓位分配、订单管理、风险控制
- ✅ DGT（动态网格）是**可选的高级特性**，非核心依赖

**这不是一个"黑盒交易系统"，而是一个"交易员的执行工具"**

---

### **2. 架构合规性（Architecture Compliance）**

**必须遵循的架构原则：**
1. 策略继承 `BaseStrategy`，实现三个方法
2. 信号格式符合 `{'entry', 'exit', 'direction', 'reason'}`
3. 复用现有引擎（`VectorBTEngine`），不创建独立引擎
4. 纯函数式指标，无副作用
5. 分层清晰：数据层 → 分析层 → 策略层 → 执行层

---

### **3. MVP 迭代法（Iterative Development）**

**不要一次性实现所有功能！**

**Sprint 1**: 静态网格 + 手动 Regime（可验证）
**Sprint 2**: 动态特性（DGT + 节流）
**Sprint 3**: 自动判定（可选辅助）

---

## 📐 架构设计（Architecture）

### **文件组织（遵循 CLAUDE.md 规范）**

```
analytics/indicators/
  ├── grid_generator.py           # 网格层级生成（纯函数）
  ├── grid_weights.py              # 层级权重计算（纯函数）
  └── regime_detector.py           # 【可选】自动 Regime 判定（Sprint 3）

strategies/signal_based/
  └── taogrid_strategy.py          # TaoGrid 主策略（继承 BaseStrategy）

risk_management/
  ├── grid_position_sizer.py       # 网格仓位计算
  └── grid_risk_manager.py         # 网格风险管理（节流、预算）

execution/engines/
  └── vectorbt_engine.py           # 复用现有引擎（无需修改）

orchestration/
  └── backtest_runner.py           # 复用现有运行器

run/
  └── run_taogrid_backtest.py      # 回测入口脚本
```

**关键变化：**
- ❌ 不创建 `strategies/grid/` 独立目录
- ❌ 不创建 `execution/grid_engine/`
- ✅ 复用现有架构，最小化改动

---

## 📝 详细实现计划（Implementation Plan）

---

## Sprint 1: 静态网格 + 手动 Regime（MVP - 可验证）

**目标**: 实现最简化的可验证版本，验证核心逻辑

### **Phase 1.1: 配置类**
**文件**: `strategies/signal_based/taogrid_strategy.py`

```python
from dataclasses import dataclass
from strategies.base_strategy import StrategyConfig

@dataclass
class TaoGridConfig(StrategyConfig):
    """TaoGrid 策略配置（MVP 版本）."""

    name: str
    description: str

    # === S/R 手动输入（核心） ===
    support: float  # 支撑位（交易员手动指定）
    resistance: float  # 阻力位（交易员手动指定）

    # === Regime 手动输入（核心） ===
    regime: str  # "UP_RANGE" | "NEUTRAL_RANGE" | "DOWN_RANGE"

    # === 网格参数 ===
    spacing_multiplier: float = 1.0  # ATR 倍数
    cushion_multiplier: float = 0.8  # Volatility Cushion 倍数
    min_return: float = 0.005  # 最小收益率（0.5%）
    maker_fee: float = 0.001  # Maker 费率
    volatility_k: float = 0.6  # 波动率安全因子

    grid_layers_buy: int = 5  # 买侧层数
    grid_layers_sell: int = 5  # 卖侧层数
    weight_k: float = 0.5  # 权重线性系数

    # === 风险参数 ===
    risk_budget_pct: float = 0.3  # 总风险预算（30%）
    max_long_units: float = 10.0  # 最大多仓层数
    max_short_units: float = 10.0  # 最大空仓层数
    daily_loss_limit: float = 2000.0  # 日最大亏损

    # === DGT 参数（MVP 阶段禁用） ===
    enable_mid_shift: bool = False  # 是否启用 mid shift
    mid_shift_threshold: int = 20  # 触发 mid shift 的 K线数

    # === ATR 参数 ===
    atr_period: int = 14

    def __post_init__(self):
        """配置验证."""
        if self.support >= self.resistance:
            raise ValueError("Support must be less than Resistance")

        if self.regime not in ["UP_RANGE", "NEUTRAL_RANGE", "DOWN_RANGE"]:
            raise ValueError("Invalid regime")

        if not (0 < self.risk_budget_pct < 1):
            raise ValueError("risk_budget_pct must be in (0, 1)")
```

**任务清单：**
- [ ] 创建 `TaoGridConfig` 类
- [ ] 实现配置验证逻辑
- [ ] 单元测试：验证配置合法性

---

### **Phase 1.2: 网格生成器（纯函数）**
**文件**: `analytics/indicators/grid_generator.py`

```python
"""
Grid level generator (pure functions).

Core logic:
1. Calculate mid = (support + resistance) / 2
2. Apply volatility cushion (avoid false breakouts)
3. Generate buy/sell levels based on ATR-based spacing
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple

def calculate_grid_spacing(
    atr: pd.Series,
    min_return: float = 0.005,
    maker_fee: float = 0.001,
    volatility_k: float = 0.6
) -> pd.Series:
    """
    Calculate grid spacing based on ATR.

    Formula (from strategy doc):
        gap_% = min_return + maker_fee + k × volatility

    Args:
        atr: ATR series
        min_return: Minimum return per grid (default 0.5%)
        maker_fee: Maker fee (default 0.1%)
        volatility_k: Volatility safety factor (0.4-1.0)

    Returns:
        Spacing percentage series
    """
    atr_pct = atr / atr.rolling(window=20).mean()  # ATR normalized
    gap_pct = min_return + maker_fee + volatility_k * atr_pct
    return gap_pct


def generate_grid_levels(
    mid_price: float,
    support: float,
    resistance: float,
    cushion: float,
    spacing_pct: float,
    layers_buy: int,
    layers_sell: int
) -> Dict[str, np.ndarray]:
    """
    Generate grid levels from mid price.

    Logic (from strategy doc):
    - Effective support: support - cushion
    - Effective resistance: resistance + cushion
    - Buy levels: from mid down to effective support
    - Sell levels: from mid up to effective resistance

    Args:
        mid_price: Mid price (can be adjusted in DGT)
        support: Support level (manual input)
        resistance: Resistance level (manual input)
        cushion: Volatility cushion (ATR × multiplier)
        spacing_pct: Spacing percentage
        layers_buy: Number of buy layers
        layers_sell: Number of sell layers

    Returns:
        Dict with 'buy_levels' and 'sell_levels' arrays
    """
    # Apply volatility cushion
    eff_support = support - cushion
    eff_resistance = resistance + cushion

    # Generate buy levels (from mid down to support)
    buy_levels = []
    price = mid_price
    for i in range(layers_buy):
        price = price / (1 + spacing_pct)
        if price >= eff_support:
            buy_levels.append(price)
        else:
            break

    # Generate sell levels (from mid up to resistance)
    sell_levels = []
    price = mid_price
    for i in range(layers_sell):
        price = price * (1 + spacing_pct)
        if price <= eff_resistance:
            sell_levels.append(price)
        else:
            break

    return {
        'buy_levels': np.array(buy_levels),
        'sell_levels': np.array(sell_levels),
        'mid': mid_price,
        'eff_support': eff_support,
        'eff_resistance': eff_resistance
    }
```

**任务清单：**
- [ ] 实现 `calculate_grid_spacing()` 函数
- [ ] 实现 `generate_grid_levels()` 函数
- [ ] 单元测试：验证网格层级生成
- [ ] 单元测试：验证 spacing 计算

---

### **Phase 1.3: 层级权重计算（纯函数）**
**文件**: `analytics/indicators/grid_weights.py`

```python
"""
Grid level weighting (pure functions).

Core logic (from strategy doc):
1. Neutral regime: edge-heavy, mid-light (linear weighting)
2. UP_RANGE: buy 70%, sell 30%
3. DOWN_RANGE: buy 30%, sell 70%
"""

import numpy as np
from typing import Dict

def calculate_level_weights(
    num_levels: int,
    weight_k: float = 0.5
) -> np.ndarray:
    """
    Calculate linear weights for grid levels.

    Formula (from strategy doc):
        raw_w(i) = 1 + k × (i - 1), where i=1 is closest to mid
        w(i) = raw_w(i) / Σ raw_w (normalized)

    Example (num_levels=4, k=0.5):
        i=1: raw=1.0 -> w ≈ 14%
        i=2: raw=1.5 -> w ≈ 21%
        i=3: raw=2.0 -> w ≈ 29%
        i=4: raw=2.5 -> w ≈ 36%

    Args:
        num_levels: Number of grid levels
        weight_k: Linear coefficient (default 0.5)

    Returns:
        Normalized weights array (sums to 1.0)
    """
    raw_weights = 1 + weight_k * np.arange(num_levels)
    normalized_weights = raw_weights / raw_weights.sum()
    return normalized_weights


def allocate_side_budgets(
    total_budget: float,
    regime: str
) -> Dict[str, float]:
    """
    Allocate budget to buy/sell sides based on regime.

    Logic (from strategy doc):
    - UP_RANGE: buy 70%, sell 30%
    - NEUTRAL_RANGE: buy 50%, sell 50%
    - DOWN_RANGE: buy 30%, sell 70%

    Args:
        total_budget: Total risk budget
        regime: "UP_RANGE" | "NEUTRAL_RANGE" | "DOWN_RANGE"

    Returns:
        Dict with 'buy_budget' and 'sell_budget'
    """
    if regime == "UP_RANGE":
        buy_pct, sell_pct = 0.7, 0.3
    elif regime == "NEUTRAL_RANGE":
        buy_pct, sell_pct = 0.5, 0.5
    elif regime == "DOWN_RANGE":
        buy_pct, sell_pct = 0.3, 0.7
    else:
        raise ValueError(f"Invalid regime: {regime}")

    return {
        'buy_budget': total_budget * buy_pct,
        'sell_budget': total_budget * sell_pct
    }


def calculate_layer_sizes(
    budget: float,
    weights: np.ndarray,
    prices: np.ndarray
) -> np.ndarray:
    """
    Calculate position size for each layer.

    Formula:
        size_i = (budget × weight_i) / price_i

    Args:
        budget: Total budget for this side
        weights: Weight array (normalized)
        prices: Price array for each level

    Returns:
        Size array (in base currency)
    """
    nominal_per_layer = budget * weights
    sizes = nominal_per_layer / prices
    return sizes
```

**任务清单：**
- [ ] 实现 `calculate_level_weights()` 函数
- [ ] 实现 `allocate_side_budgets()` 函数
- [ ] 实现 `calculate_layer_sizes()` 函数
- [ ] 单元测试：中性区间权重分配
- [ ] 单元测试：上行区间权重分配（70/30）
- [ ] 单元测试：下行区间权重分配（30/70）
- [ ] 单元测试：归一化验证

---

### **Phase 1.4: TaoGrid 主策略类**
**文件**: `strategies/signal_based/taogrid_strategy.py`

```python
"""
TaoGrid Strategy (adapts grid logic to BaseStrategy interface).

Key design decisions:
1. Adapts grid levels to entry/exit signals
2. Uses VectorBT limit orders for grid execution
3. Maintains compatibility with existing backtest infrastructure
"""

from strategies.base_strategy import BaseStrategy
from analytics.indicators.grid_generator import (
    calculate_grid_spacing,
    generate_grid_levels
)
from analytics.indicators.grid_weights import (
    calculate_level_weights,
    allocate_side_budgets,
    calculate_layer_sizes
)
from analytics.indicators.volatility import calculate_atr
import pandas as pd
import numpy as np

class TaoGridStrategy(BaseStrategy):
    """
    TaoGrid Strategy (MVP version).

    Features:
    - Manual S/R input
    - Manual Regime input
    - Static grid (no mid-shift in MVP)
    - Level-wise weighting
    - Regime-based side allocation

    Future enhancements (Sprint 2+):
    - Dynamic mid-shift (DGT)
    - Throttling rules
    - Auto regime detection (optional)
    """

    def __init__(self, config: TaoGridConfig):
        super().__init__(config)
        self.config = config

    def compute_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Compute grid levels and weights.

        Returns data with additional columns:
        - atr: ATR indicator
        - grid_spacing_pct: Grid spacing percentage
        - grid_mid: Mid price
        - cushion: Volatility cushion
        """
        # Calculate ATR
        atr = calculate_atr(
            data['high'],
            data['low'],
            data['close'],
            period=self.config.atr_period
        )

        # Calculate grid spacing (ATR-based)
        spacing_pct = calculate_grid_spacing(
            atr=atr,
            min_return=self.config.min_return,
            maker_fee=self.config.maker_fee,
            volatility_k=self.config.volatility_k
        )

        # Calculate mid price (static in MVP)
        mid = (self.config.support + self.config.resistance) / 2

        # Calculate volatility cushion
        cushion = atr * self.config.cushion_multiplier

        return data.assign(
            atr=atr,
            grid_spacing_pct=spacing_pct,
            grid_mid=mid,
            cushion=cushion
        )

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate grid entry/exit signals.

        Logic:
        1. Generate grid levels at each bar
        2. Check if price crosses any grid level
        3. Convert to entry/exit signals

        Note: This is a simplified adaptation for VectorBT.
        Full grid logic (order pairing, inventory) will be in Sprint 2.
        """
        # Get latest grid parameters
        last_idx = data.index[-1]
        spacing_pct = data.loc[last_idx, 'grid_spacing_pct']
        mid = data.loc[last_idx, 'grid_mid']
        cushion = data.loc[last_idx, 'cushion']

        # Generate grid levels
        grid = generate_grid_levels(
            mid_price=mid,
            support=self.config.support,
            resistance=self.config.resistance,
            cushion=cushion,
            spacing_pct=spacing_pct,
            layers_buy=self.config.grid_layers_buy,
            layers_sell=self.config.grid_layers_sell
        )

        # Simplified signal generation (MVP)
        # Entry when price crosses any buy level (from above)
        # Exit when price crosses any sell level (from below)

        entry = pd.Series(False, index=data.index)
        exit_signal = pd.Series(False, index=data.index)
        direction = pd.Series('long', index=data.index)

        for i in range(1, len(data)):
            close_prev = data['close'].iloc[i-1]
            close_curr = data['close'].iloc[i]

            # Check if crossed any buy level (downward cross)
            for buy_level in grid['buy_levels']:
                if close_prev > buy_level and close_curr <= buy_level:
                    entry.iloc[i] = True
                    direction.iloc[i] = 'long'
                    break

            # Check if crossed any sell level (upward cross)
            for sell_level in grid['sell_levels']:
                if close_prev < sell_level and close_curr >= sell_level:
                    exit_signal.iloc[i] = True
                    break

        return pd.DataFrame({
            'entry': entry,
            'exit': exit_signal,
            'direction': direction,
            'reason': 'grid_trade'
        }, index=data.index)

    def calculate_position_size(
        self,
        data: pd.DataFrame,
        equity: pd.Series,
        base_size: float = 1.0
    ) -> pd.Series:
        """
        Calculate grid-based position sizes.

        Logic:
        1. Total budget = equity × risk_budget_pct
        2. Allocate to buy/sell sides based on regime
        3. Calculate size per layer based on weights

        Returns:
            Position size series (in base currency units)
        """
        # Calculate total risk budget
        total_budget = equity * self.config.risk_budget_pct

        # Allocate to buy/sell sides
        budgets = allocate_side_budgets(
            total_budget=total_budget.iloc[-1],
            regime=self.config.regime
        )

        # Calculate weights
        buy_weights = calculate_level_weights(
            num_levels=self.config.grid_layers_buy,
            weight_k=self.config.weight_k
        )

        # Get grid levels (use latest bar)
        last_idx = data.index[-1]
        spacing_pct = data.loc[last_idx, 'grid_spacing_pct']
        mid = data.loc[last_idx, 'grid_mid']
        cushion = data.loc[last_idx, 'cushion']

        grid = generate_grid_levels(
            mid_price=mid,
            support=self.config.support,
            resistance=self.config.resistance,
            cushion=cushion,
            spacing_pct=spacing_pct,
            layers_buy=self.config.grid_layers_buy,
            layers_sell=self.config.grid_layers_sell
        )

        # Calculate layer sizes
        buy_sizes = calculate_layer_sizes(
            budget=budgets['buy_budget'],
            weights=buy_weights,
            prices=grid['buy_levels']
        )

        # Use average buy size as position size (simplified)
        avg_size = buy_sizes.mean()

        return pd.Series(avg_size, index=data.index)
```

**任务清单：**
- [ ] 实现 `TaoGridStrategy` 类
- [ ] 实现 `compute_indicators()` 方法
- [ ] 实现 `generate_signals()` 方法（简化版）
- [ ] 实现 `calculate_position_size()` 方法
- [ ] 单元测试：指标计算
- [ ] 单元测试：信号生成
- [ ] 单元测试：仓位计算

---

### **Phase 1.5: 回测脚本（MVP 验证）**
**文件**: `run/run_taogrid_backtest.py`

```python
"""
TaoGrid Strategy Backtest Script (MVP).

Usage:
    python run/run_taogrid_backtest.py
"""

from pathlib import Path
import pandas as pd

from data import DataManager
from strategies.signal_based.taogrid_strategy import TaoGridStrategy, TaoGridConfig
from execution.engines.vectorbt_engine import VectorBTEngine
from execution.engines.base import BacktestConfig
from orchestration.backtest_runner import BacktestRunner, BacktestRunConfig

def main():
    # === Configuration ===

    # Manual S/R input (trader specifies)
    SUPPORT = 95000.0  # Example: BTC support at 95k
    RESISTANCE = 105000.0  # Example: BTC resistance at 105k

    # Manual Regime input (trader specifies)
    REGIME = "NEUTRAL_RANGE"  # Options: UP_RANGE, NEUTRAL_RANGE, DOWN_RANGE

    # Strategy configuration
    config = TaoGridConfig(
        name="TaoGrid MVP",
        description="Static grid with manual S/R and Regime",

        # Manual inputs
        support=SUPPORT,
        resistance=RESISTANCE,
        regime=REGIME,

        # Grid parameters
        spacing_multiplier=1.0,
        cushion_multiplier=0.8,
        min_return=0.005,  # 0.5%
        maker_fee=0.001,  # 0.1%
        volatility_k=0.6,

        grid_layers_buy=5,
        grid_layers_sell=5,
        weight_k=0.5,

        # Risk parameters
        risk_budget_pct=0.3,  # 30%
        max_long_units=10.0,
        max_short_units=10.0,
        daily_loss_limit=2000.0,

        # DGT (disabled in MVP)
        enable_mid_shift=False,

        # ATR
        atr_period=14
    )

    # === Initialize ===
    data_manager = DataManager()
    strategy = TaoGridStrategy(config)
    engine = VectorBTEngine()
    runner = BacktestRunner(data_manager)

    # === Run Backtest ===
    result = runner.run(BacktestRunConfig(
        symbol="BTCUSDT",
        timeframe="15m",  # MVP: use K-line data
        start=pd.Timestamp("2025-10-01", tz="UTC"),
        end=pd.Timestamp("2025-12-01", tz="UTC"),
        source="okx",
        strategy=strategy,
        engine=engine,
        backtest_config=BacktestConfig(
            initial_cash=100000.0,
            commission=0.001,
            slippage=0.0005,
            leverage=1.0,  # No leverage in MVP
        ),
        output_dir=Path("run/results_taogrid_mvp"),
        save_results=True,
    ))

    # === Print Results ===
    print("\n" + "="*60)
    print("TaoGrid MVP Backtest Results")
    print("="*60)
    print(f"Total Return: {result.metrics.get('total_return', 0):.2%}")
    print(f"Sharpe Ratio: {result.metrics.get('sharpe_ratio', 0):.2f}")
    print(f"Max Drawdown: {result.metrics.get('max_drawdown', 0):.2%}")
    print(f"Win Rate: {result.metrics.get('win_rate', 0):.2%}")
    print(f"Total Trades: {result.metrics.get('total_trades', 0)}")
    print("="*60)

    print(f"\nResults saved to: {result.output_dir}")

if __name__ == "__main__":
    main()
```

**任务清单：**
- [ ] 创建回测脚本
- [ ] 配置 TaoGridConfig
- [ ] 运行回测
- [ ] 验证结果合理性
- [ ] 分析网格交易行为

---

## Sprint 1 验收标准（Acceptance Criteria）

✅ **功能完整性：**
- [ ] 能够手动指定 S/R 和 Regime
- [ ] 能够生成网格层级
- [ ] 能够根据 Regime 分配买卖侧仓位
- [ ] 能够运行完整回测

✅ **代码质量：**
- [ ] 所有函数有 type hints
- [ ] 所有函数有 docstrings
- [ ] 通过单元测试
- [ ] 遵循 TaoQuant 架构规范

✅ **回测结果：**
- [ ] 能够生成完整的权益曲线
- [ ] 能够输出交易记录
- [ ] 结果符合预期（合理的交易频率、盈亏分布）

---

## Sprint 2: 动态特性（DGT + 节流）

**目标**: 实现动态网格和风险控制

### **Phase 2.1: DGT（Mid Shift）实现**

**文件**: `analytics/indicators/grid_generator.py`（扩展）

```python
def calculate_mid_shift(
    data: pd.DataFrame,
    current_mid: float,
    support: float,
    resistance: float,
    threshold_bars: int = 20
) -> float:
    """
    Calculate new mid price based on price distribution.

    Logic (from strategy doc):
    - If price stays in upper half for N bars -> shift mid up
    - If price stays in lower half for N bars -> shift mid down

    Args:
        data: OHLCV DataFrame (recent bars)
        current_mid: Current mid price
        support: Support level
        resistance: Resistance level
        threshold_bars: Number of bars to check

    Returns:
        New mid price (or current_mid if no shift needed)
    """
    if len(data) < threshold_bars:
        return current_mid

    recent_data = data.tail(threshold_bars)
    upper_half = (recent_data['close'] > current_mid).sum()
    lower_half = (recent_data['close'] < current_mid).sum()

    upper_pct = upper_half / threshold_bars
    lower_pct = lower_half / threshold_bars

    if upper_pct > 0.8:
        # Price consistently in upper half -> shift up
        shift_amount = (resistance - current_mid) * 0.2
        new_mid = min(current_mid + shift_amount, resistance)
        return new_mid

    elif lower_pct > 0.8:
        # Price consistently in lower half -> shift down
        shift_amount = (current_mid - support) * 0.2
        new_mid = max(current_mid - shift_amount, support)
        return new_mid

    return current_mid
```

**任务清单：**
- [ ] 实现 `calculate_mid_shift()` 函数
- [ ] 在策略中集成 mid shift 逻辑
- [ ] 单元测试：mid shift 触发条件
- [ ] 回测验证：mid shift 效果

---

### **Phase 2.2: 动态节流规则**

**文件**: `risk_management/grid_risk_manager.py`

```python
"""
Grid Risk Manager (Throttling Rules).

Implements three throttling rules (from strategy doc):
1. Inventory Limit: pause orders when inventory exceeds limit
2. Profit Lock-in: reduce size when daily PnL reaches target
3. Volatility Spike: reduce size when ATR spikes
"""

from dataclasses import dataclass
import pandas as pd

@dataclass
class ThrottleStatus:
    """Throttling status."""
    inventory_throttled: bool = False
    profit_locked: bool = False
    volatility_throttled: bool = False
    size_multiplier: float = 1.0  # Final size multiplier (0.0 - 1.0)

class GridRiskManager:
    """Grid-specific risk management."""

    def __init__(
        self,
        max_long_units: float,
        max_short_units: float,
        profit_target_pct: float = 0.02,
        profit_reduction: float = 0.5,
        volatility_threshold: float = 2.0
    ):
        self.max_long_units = max_long_units
        self.max_short_units = max_short_units
        self.profit_target_pct = profit_target_pct
        self.profit_reduction = profit_reduction
        self.volatility_threshold = volatility_threshold

    def check_inventory_limit(
        self,
        long_exposure: float,
        short_exposure: float
    ) -> bool:
        """
        Check if inventory exceeds limits.

        Returns:
            True if throttling needed
        """
        if long_exposure >= self.max_long_units:
            return True
        if short_exposure >= self.max_short_units:
            return True
        return False

    def check_profit_target(
        self,
        daily_pnl: float,
        risk_budget: float
    ) -> bool:
        """
        Check if daily PnL reaches target.

        Returns:
            True if profit locked
        """
        profit_target = risk_budget * self.profit_target_pct
        return daily_pnl >= profit_target

    def check_volatility_spike(
        self,
        current_atr: float,
        avg_atr: float
    ) -> bool:
        """
        Check if volatility spikes.

        Returns:
            True if volatility throttling needed
        """
        return current_atr > avg_atr * self.volatility_threshold

    def get_throttle_status(
        self,
        long_exposure: float,
        short_exposure: float,
        daily_pnl: float,
        risk_budget: float,
        current_atr: float,
        avg_atr: float
    ) -> ThrottleStatus:
        """
        Get comprehensive throttling status.

        Returns:
            ThrottleStatus with size_multiplier
        """
        status = ThrottleStatus()

        # Check inventory limit
        status.inventory_throttled = self.check_inventory_limit(
            long_exposure, short_exposure
        )

        # Check profit lock
        status.profit_locked = self.check_profit_target(
            daily_pnl, risk_budget
        )

        # Check volatility spike
        status.volatility_throttled = self.check_volatility_spike(
            current_atr, avg_atr
        )

        # Calculate size multiplier
        if status.inventory_throttled:
            status.size_multiplier = 0.0  # Stop new orders
        elif status.profit_locked:
            status.size_multiplier = self.profit_reduction  # 50% reduction
        elif status.volatility_throttled:
            status.size_multiplier = 0.5  # 50% reduction
        else:
            status.size_multiplier = 1.0  # Full size

        return status
```

**任务清单：**
- [ ] 实现 `GridRiskManager` 类
- [ ] 实现三个节流规则
- [ ] 在策略中集成节流逻辑
- [ ] 单元测试：各个节流规则
- [ ] 回测验证：节流效果

---

## Sprint 2 验收标准

✅ **功能完整性：**
- [ ] DGT（mid shift）正常工作
- [ ] 三个节流规则正常工作
- [ ] 节流事件可追踪

✅ **回测验证：**
- [ ] Mid shift 在合适时机触发
- [ ] 节流规则有效控制风险
- [ ] 策略表现优于 Sprint 1

---

## Sprint 3: 自动 Regime 判定（可选）

**目标**: 实现自动 Regime 判定作为辅助工具

### **Phase 3.1: 自动 Regime 判定**

**文件**: `analytics/indicators/regime_detector.py`

```python
"""
Regime Detector (Optional - Assistant Tool).

IMPORTANT:
This is an OPTIONAL feature to assist traders.
The default mode is MANUAL regime input by traders.
"""

import pandas as pd
from typing import Literal

RegimeType = Literal["GREEN", "RED", "YELLOW"]
TrendRegimeType = Literal["UP_RANGE", "NEUTRAL_RANGE", "DOWN_RANGE"]

def detect_market_regime(
    data_daily: pd.DataFrame,
    data_4h: pd.DataFrame,
    green_confirm_days: int = 3,
    red_confirm_days: int = 3,
    lock_days: int = 5
) -> pd.Series:
    """
    Detect market regime (GREEN/RED/YELLOW).

    This is from strategy doc Section 1.2, but is OPTIONAL.
    Traders can override this with manual regime input.

    Logic:
    - GREEN: bull market (close_D > ema200_D, ema50_D > ema200_D)
    - RED: bear market or bubble top
    - YELLOW: uncertain

    Returns:
        Series with regime labels
    """
    # Implementation from strategy doc...
    # (Keep this as optional feature)
    pass

def suggest_trend_regime(
    data: pd.DataFrame,
    adx_threshold: float = 25
) -> TrendRegimeType:
    """
    Suggest trend regime based on indicators.

    This is a SUGGESTION tool for traders.
    Final decision is made by traders.

    Logic:
    - ADX > 25: trend too strong, suggest NO GRID
    - Momentum positive: suggest UP_RANGE
    - Momentum negative: suggest DOWN_RANGE
    - Else: suggest NEUTRAL_RANGE

    Returns:
        Suggested regime
    """
    # Implementation...
    pass
```

**任务清单：**
- [ ] 实现自动 Regime 判定（参考策略文档）
- [ ] 作为建议工具，不强制使用
- [ ] 在回测中对比手动 vs 自动

---

## 关键设计决策（Design Decisions）

### **1. 为什么不创建独立的网格引擎？**

**原因：**
- VectorBT 已经支持 limit order
- 创建独立引擎会导致代码重复
- 违反 DRY 原则
- 维护成本高

**方案：**
- 用 VectorBT 的 limit order 功能
- 在策略层做网格逻辑适配

---

### **2. 为什么信号格式不是网格订单格式？**

**原因：**
- 必须遵循 BaseStrategy 的接口规范
- 保持与现有回测基础设施的兼容性
- 网格订单逻辑在策略内部处理，对外暴露标准信号

**方案：**
- 网格层级 → 转换为 entry/exit 信号
- 层级权重 → 体现在 position size

---

### **3. 为什么 S/R 是手动输入，不是自动检测？**

**原因：**
- 策略文档明确强调："区间基于你的人工判断"
- 这是交易员的核心优势（市场理解）
- 自动检测的 S/R 往往不准确

**方案：**
- 默认：手动输入 S/R
- 可选：提供 `compute_sr_zones` 作为参考工具

---

### **4. 为什么 Regime 是手动输入，不是自动判定？**

**原因：**
- 策略文档核心思想："量化执行 + 人类判断"
- 自动 Regime 判定容易误判（噪音）
- 文档明确说："交易员介入模式"

**方案：**
- 默认：手动输入 Regime
- 可选：提供自动判定作为辅助工具（Sprint 3）

---

## 关键指标（Key Metrics）

### **回测指标（必须）**

```python
@dataclass
class GridBacktestMetrics:
    """Grid-specific backtest metrics."""

    # Standard metrics
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int

    # Grid-specific metrics
    avg_grid_return: float  # 单格平均收益
    grid_turnover: int  # 网格周转次数
    avg_holding_time: float  # 平均持仓时间（小时）

    # Inventory metrics
    max_long_exposure: float  # 最大多仓敞口
    max_short_exposure: float  # 最大空仓敞口
    avg_net_exposure: float  # 平均净敞口

    # Throttling metrics
    inventory_throttle_count: int  # Inventory 节流次数
    profit_lock_count: int  # Profit lock 次数
    volatility_throttle_count: int  # 波动率节流次数

    # Mid shift metrics (Sprint 2)
    mid_shift_count: int  # Mid shift 次数
    avg_mid_shift_magnitude: float  # 平均 shift 幅度
```

---

## 测试策略（Testing Strategy）

### **单元测试（Unit Tests）**

```python
# tests/test_grid_generator.py
def test_calculate_grid_spacing():
    """Test grid spacing calculation."""
    pass

def test_generate_grid_levels():
    """Test grid level generation."""
    pass

# tests/test_grid_weights.py
def test_calculate_level_weights():
    """Test level weight calculation."""
    pass

def test_allocate_side_budgets():
    """Test side budget allocation for different regimes."""
    pass

# tests/test_taogrid_strategy.py
def test_compute_indicators():
    """Test indicator computation."""
    pass

def test_generate_signals():
    """Test signal generation."""
    pass
```

### **集成测试（Integration Tests）**

```python
# tests/test_taogrid_integration.py
def test_full_backtest():
    """Test complete backtest flow."""
    pass

def test_different_regimes():
    """Test strategy under different regimes."""
    pass

def test_extreme_volatility():
    """Test strategy under extreme volatility."""
    pass
```

---

## 成功标准（Success Criteria）

### **Sprint 1（MVP）**

✅ **技术指标：**
- [ ] 所有单元测试通过
- [ ] 代码覆盖率 > 80%
- [ ] 通过 lint 检查
- [ ] 类型提示完整

✅ **功能指标：**
- [ ] 能够手动指定 S/R 和 Regime
- [ ] 能够生成正确的网格层级
- [ ] 能够运行完整回测
- [ ] 结果符合预期

✅ **性能指标：**
- [ ] 回测速度 > 1000 bars/秒
- [ ] 内存使用 < 2GB（1年数据）

### **Sprint 2（动态特性）**

✅ **功能指标：**
- [ ] Mid shift 正常工作
- [ ] 节流规则有效
- [ ] 策略表现优于 Sprint 1

### **Sprint 3（可选功能）**

✅ **功能指标：**
- [ ] 自动 Regime 判定可用
- [ ] 作为辅助工具，不强制使用

---

## 附录：与原 TODO 的对比

### **原 TODO 的主要问题：**

1. ❌ **需求理解偏差**：优先实现自动 Regime 判定，忽略手动模式
2. ❌ **架构违反**：创建独立的网格引擎，违反 DRY
3. ❌ **信号格式不兼容**：使用特殊格式，不符合 BaseStrategy
4. ❌ **核心逻辑缺失**：DGT（mid shift）细节不清晰
5. ❌ **实现顺序不合理**：Phase 1 就实现复杂功能
6. ❌ **回测不现实**：没有考虑数据粒度和撮合逻辑

### **改进版 TODO 的优势：**

1. ✅ **需求对齐**：优先手动模式，符合策略文档意图
2. ✅ **架构合规**：复用现有引擎，遵循 BaseStrategy
3. ✅ **MVP 迭代**：分阶段实现，先简后繁
4. ✅ **核心清晰**：DGT、节流、风控逻辑明确
5. ✅ **可执行**：每个 Phase 都有清晰的任务和验收标准
6. ✅ **专业级**：符合顶级机构的开发标准

---

## 总结（Summary）

### **核心要点：**

1. **TaoGrid = 交易员工具，不是黑盒系统**
2. **手动 S/R + 手动 Regime = 核心模式**
3. **自动判定 = 可选辅助工具（Sprint 3）**
4. **遵循 TaoQuant 架构 = 非协商项**
5. **MVP 迭代法 = 快速验证，逐步完善**

### **实施建议：**

1. **从 Sprint 1 开始**：静态网格 + 手动模式
2. **验证核心逻辑**：确保网格生成、权重分配正确
3. **逐步增强**：Sprint 2 加入 DGT 和节流
4. **可选功能最后**：Sprint 3 实现自动判定

---

**最后更新**: 2025-12-13
**状态**: ✅ 已审查，可执行
**审查者**: Senior Quant Developer & Quant Trader

# TaoQuant System Design Document

> **Version**: 2.0
> **Date**: 2025-12-03
> **Authors**: System Architecture Team
> **Status**: ACTIVE DESIGN DOCUMENT

---

## 📐 Executive Summary

TaoQuant is a **professional-grade quantitative research and trading framework** designed for cryptocurrency markets. This document outlines the architecture for a clean, maintainable, and extensible system that supports:

1. **Signal-based strategy research** (current focus)
2. **Multi-factor alpha discovery** (future roadmap)
3. **Portfolio optimization** (future roadmap)
4. **Production trading** (future roadmap)

### Design Philosophy

> "Simplicity is the ultimate sophistication." - Leonardo da Vinci

Our architecture follows three core principles:

1. **Separation of Concerns**: Data → Indicators → Signals → Execution
2. **Functional Core, Imperative Shell**: Pure functions for logic, side effects at boundaries
3. **Layered Architecture**: Each layer depends only on layers below

---

## 🏛️ Architecture Overview

### System Layers (Bottom-Up)

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 5: Application Layer (Scripts, Notebooks, CLI)      │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Orchestration Layer (Runners, Workflows)         │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Strategy Layer (Signals, Alpha, Portfolio)       │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Execution Layer (Backtest, Simulation, Live)     │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Analytics Layer (Indicators, Features, Stats)    │
├─────────────────────────────────────────────────────────────┤
│  Layer 0: Data Layer (Ingestion, Storage, Access)          │
└─────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| **Backtesting Engine** | VectorBT | Native fractional positions, 100x speedup, vectorized operations |
| **Data Storage** | Parquet (cache) + Future: TimescaleDB (prod) | Fast columnar access, time-series optimized |
| **Configuration** | Python dataclasses | Type-safe, IDE-friendly, no JSON hell |
| **Testing** | pytest + hypothesis | Industry standard + property-based testing |
| **Code Style** | Black + Ruff + mypy | Consistent, enforced, type-safe |

---

## 🎯 Design Principles

### 1. Pure Functions for Core Logic

**Anti-pattern** (stateful, hard to test):
```python
class Strategy:
    def __init__(self):
        self.zones = []  # Mutable state

    def next(self):
        # Mixed concerns: detection + state mutation + execution
        if self._detect_signal():
            self.zones.append(...)
            self.buy()
```

**Clean pattern** (pure, easy to test):
```python
# Pure function: data → zones
def detect_sr_zones(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    lookback: int = 20
) -> pd.DataFrame:
    """
    Detect support/resistance zones.

    Pure function: same inputs → same outputs.
    No side effects, no state mutations.
    """
    pivots = find_pivot_highs(high, lookback)
    zones = merge_nearby_zones(pivots)
    return zones

# Strategy orchestrates pure functions
class SRStrategy:
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        zones = detect_sr_zones(data['high'], data['low'], data['close'])
        signals = detect_zone_touches(data['close'], zones)
        return signals
```

### 2. Explicit is Better Than Implicit

**Anti-pattern** (magic, hard to debug):
```python
# What does this do? Where does data come from?
strategy.run()
```

**Clean pattern** (explicit, clear):
```python
# Clear data flow: data → signals → positions → results
signals = strategy.generate_signals(data)
positions = sizer.calculate_sizes(signals, equity)
results = engine.backtest(data, positions, config)
```

### 3. Dependency Injection Over Globals

**Anti-pattern**:
```python
# Global config, hard to test, hidden dependencies
from config import COMMISSION_RATE

class Strategy:
    def calculate_cost(self, price):
        return price * COMMISSION_RATE  # Where did this come from?
```

**Clean pattern**:
```python
# Explicit dependencies, easy to test, mockable
@dataclass
class TradingConfig:
    commission: float
    slippage: float

class Strategy:
    def __init__(self, config: TradingConfig):
        self.config = config

    def calculate_cost(self, price: float) -> float:
        return price * self.config.commission
```

### 4. Type Safety Everywhere

```python
# Use type hints + mypy for compile-time safety
from typing import Protocol

class DataSource(Protocol):
    """Interface for data sources (structural typing)."""

    def get_klines(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime
    ) -> pd.DataFrame:
        ...

# Type-safe strategy interface
class Strategy(Protocol):
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        ...
```

---

## 🗂️ Module Architecture

### Layer 0: Data Layer

**Purpose**: Unified interface for market data access

```
data/
├── __init__.py                 # Public API
├── data_manager.py             # Main interface
├── sources/                    # Exchange adapters
│   ├── base.py                 # Abstract base class
│   ├── okx_sdk.py              # OKX implementation
│   ├── binance_sdk.py          # Binance implementation
│   └── csv_loader.py           # Local CSV files
├── cache/                      # Parquet cache manager
│   └── cache_manager.py
└── schemas.py                  # Data schemas & validation
```

**Design Pattern**: **Repository Pattern**

```python
# data/data_manager.py

class DataManager:
    """
    Unified data access layer (Repository pattern).

    Responsibilities:
    - Abstract away data sources (exchange, CSV, database)
    - Manage caching transparently
    - Ensure data quality (validation, cleaning)
    """

    def get_klines(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        source: str = "okx"
    ) -> pd.DataFrame:
        """
        Get OHLCV data from any source.

        Returns:
            DataFrame with columns: [open, high, low, close, volume]
            Index: timezone-aware DatetimeIndex (UTC)
        """
        # 1. Check cache
        if self._cache.has(symbol, timeframe, start, end):
            return self._cache.get(symbol, timeframe, start, end)

        # 2. Fetch from source
        data = self._sources[source].fetch(symbol, timeframe, start, end)

        # 3. Validate & clean
        data = self._validate(data)

        # 4. Cache for future use
        self._cache.store(symbol, timeframe, data)

        return data
```

**Key Principles**:
- **Single Responsibility**: DataManager only manages data access
- **Open/Closed**: Easy to add new sources without modifying existing code
- **Dependency Inversion**: Depend on abstract `DataSource` interface

---

### Layer 1: Analytics Layer

**Purpose**: Transform raw data into features/indicators

```
analytics/
├── __init__.py
├── indicators/                 # Technical indicators
│   ├── base.py                 # Abstract indicator class
│   ├── trend.py                # SMA, EMA, MACD
│   ├── volatility.py           # ATR, Bollinger Bands
│   ├── volume.py               # Volume indicators
│   └── sr_zones.py             # Support/Resistance detection
├── features/                   # Feature engineering (future)
│   ├── technical.py            # Technical features
│   ├── microstructure.py       # Order book features
│   └── sentiment.py            # Social sentiment features
└── transforms/                 # Data transformations
    ├── resample.py             # Timeframe resampling
    ├── normalize.py            # Normalization/scaling
    └── outliers.py             # Outlier detection
```

**Design Pattern**: **Strategy Pattern + Functional Programming**

```python
# analytics/indicators/base.py

from typing import Protocol
import pandas as pd

class Indicator(Protocol):
    """
    Indicator interface (structural typing).

    All indicators are pure functions: DataFrame → DataFrame
    """

    def compute(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Compute indicator values.

        Args:
            data: OHLCV DataFrame

        Returns:
            Original data with new indicator columns added
        """
        ...

# analytics/indicators/sr_zones.py

def compute_sr_zones(
    data: pd.DataFrame,
    left_len: int = 90,
    right_len: int = 10,
    merge_atr_mult: float = 3.5
) -> pd.DataFrame:
    """
    Detect support/resistance zones using pivot analysis.

    Pure function: deterministic, no side effects.

    Args:
        data: OHLCV DataFrame with 'high', 'low', 'close' columns
        left_len: Left bars for pivot detection
        right_len: Right bars for pivot confirmation
        merge_atr_mult: ATR multiplier for zone merging

    Returns:
        DataFrame with added columns:
        - zone_top: Top of resistance zone (NaN if no zone)
        - zone_bottom: Bottom of resistance zone
        - zone_touches: Number of times zone was touched

    Example:
        >>> data = pd.DataFrame(...)
        >>> zones = compute_sr_zones(data, left_len=20, right_len=5)
        >>> assert 'zone_top' in zones.columns
    """
    # 1. Detect pivot highs
    pivots = _detect_pivot_highs(data['high'], left_len, right_len)

    # 2. Calculate ATR for merging tolerance
    atr = compute_atr(data['high'], data['low'], data['close'], period=14)

    # 3. Merge nearby pivots into zones
    zones = _merge_zones(pivots, atr, merge_atr_mult)

    # 4. Add zone columns to data
    return data.assign(
        zone_top=zones['top'],
        zone_bottom=zones['bottom'],
        zone_touches=zones['touches']
    )
```

**Key Principles**:
- **Pure Functions**: No state, no side effects
- **Composability**: Chain indicators easily
- **Testability**: Easy to test with sample data

---

### Layer 2: Execution Layer

**Purpose**: Execute strategies (backtest, simulation, live trading)

```
execution/
├── __init__.py
├── engines/                    # Backtest engines
│   ├── base.py                 # Abstract engine interface
│   ├── vectorbt_engine.py      # VectorBT implementation
│   └── custom_engine.py        # Custom engine (future)
├── simulation/                 # Paper trading (future)
│   └── simulator.py
├── live/                       # Live trading (future)
│   ├── executor.py
│   └── order_manager.py
└── position_manager.py         # Multi-position tracking
```

**Design Pattern**: **Strategy Pattern + Template Method**

```python
# execution/engines/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
import pandas as pd

@dataclass
class BacktestConfig:
    """Engine-agnostic backtest configuration."""
    initial_cash: float
    commission: float
    slippage: float
    leverage: float = 1.0

@dataclass
class BacktestResult:
    """Standardized backtest results (engine-agnostic)."""
    trades: pd.DataFrame           # All executed trades
    equity_curve: pd.DataFrame     # Equity over time
    positions: pd.DataFrame        # Position snapshots
    metrics: dict                  # Performance metrics

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            'trades': self.trades.to_dict('records'),
            'metrics': self.metrics,
            # ...
        }

class BacktestEngine(ABC):
    """
    Abstract base class for all backtest engines.

    Template Method pattern: defines workflow, subclasses implement details.
    """

    @abstractmethod
    def run(
        self,
        data: pd.DataFrame,
        signals: pd.DataFrame,
        sizes: pd.Series,
        config: BacktestConfig
    ) -> BacktestResult:
        """
        Run backtest with given signals and position sizes.

        Args:
            data: OHLCV data
            signals: Entry/exit signals
            sizes: Position sizes (fractional)
            config: Backtest configuration

        Returns:
            Standardized backtest results
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Return engine name (for logging)."""
        pass

# execution/engines/vectorbt_engine.py

import vectorbt as vbt

class VectorBTEngine(BacktestEngine):
    """VectorBT implementation of backtest engine."""

    def run(
        self,
        data: pd.DataFrame,
        signals: pd.DataFrame,
        sizes: pd.Series,
        config: BacktestConfig
    ) -> BacktestResult:
        """
        Run vectorized backtest using VectorBT.

        VectorBT is 100x faster than event-driven backtesting
        because it uses vectorized NumPy operations.
        """
        # 1. Convert signals to VectorBT format
        entries = signals['entry'].fillna(False)
        exits = signals['exit'].fillna(False)

        # 2. Create portfolio
        portfolio = vbt.Portfolio.from_signals(
            close=data['close'],
            entries=entries,
            exits=exits,
            size=sizes,
            init_cash=config.initial_cash,
            fees=config.commission,
            slippage=config.slippage,
        )

        # 3. Extract results
        trades = portfolio.trades.records_readable
        equity = portfolio.value()

        # 4. Calculate metrics
        metrics = {
            'total_return': portfolio.total_return(),
            'sharpe_ratio': portfolio.sharpe_ratio(),
            'max_drawdown': portfolio.max_drawdown(),
            'win_rate': portfolio.trades.win_rate(),
            # ... more metrics
        }

        # 5. Return standardized results
        return BacktestResult(
            trades=trades,
            equity_curve=equity.to_frame('equity'),
            positions=pd.DataFrame(),  # TODO: extract positions
            metrics=metrics
        )

    def get_name(self) -> str:
        return "VectorBT"
```

**Key Principles**:
- **Abstraction**: Engine interface hides implementation details
- **Swappable Engines**: Easy to switch or compare engines
- **Standardized Output**: All engines return same result format

---

### Layer 3: Strategy Layer

**Purpose**: Generate trading signals and alpha

```
strategies/
├── __init__.py
├── base_strategy.py            # Abstract strategy class
├── signal_based/               # Signal-based strategies
│   ├── sr_short.py             # SR short strategy
│   ├── sma_cross.py            # SMA crossover
│   └── mean_reversion.py       # Mean reversion
├── alpha/                      # Alpha strategies (future)
│   ├── momentum.py             # Momentum factor
│   ├── value.py                # Value factor
│   └── multi_factor.py         # Multi-factor alpha
└── portfolio/                  # Portfolio strategies (future)
    ├── equal_weight.py
    ├── risk_parity.py
    └── mean_variance.py
```

**Design Pattern**: **Template Method + Strategy Pattern**

```python
# strategies/base_strategy.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import pandas as pd

@dataclass
class StrategyConfig:
    """Base configuration for all strategies."""
    name: str
    description: str

class BaseStrategy(ABC):
    """
    Abstract base class for all strategies.

    Template Method pattern: defines workflow, subclasses implement steps.

    Workflow:
    1. compute_indicators(data) → data with indicators
    2. generate_signals(data) → entry/exit signals
    3. calculate_position_size(data, equity) → position sizes
    """

    def __init__(self, config: StrategyConfig):
        self.config = config

    @abstractmethod
    def compute_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all required indicators.

        Pure function: data → data with indicator columns.

        Args:
            data: OHLCV DataFrame

        Returns:
            Original data with new indicator columns added
        """
        pass

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate entry/exit signals.

        Pure function: data with indicators → signals.

        Args:
            data: DataFrame with OHLCV + indicators

        Returns:
            DataFrame with columns:
            - entry: bool (True = enter position)
            - exit: bool (True = exit position)
            - direction: str ('long' or 'short')
            - reason: str (entry/exit reason for logging)
        """
        pass

    @abstractmethod
    def calculate_position_size(
        self,
        data: pd.DataFrame,
        equity: pd.Series,
        base_size: float = 1.0
    ) -> pd.Series:
        """
        Calculate position sizes based on risk management.

        Args:
            data: DataFrame with OHLCV + indicators + signals
            equity: Current equity at each bar
            base_size: Base position size (fraction of equity)

        Returns:
            Series with position sizes (fractional, can be > 1 with leverage)
        """
        pass

    # Template method: defines workflow
    def run(
        self,
        data: pd.DataFrame,
        initial_equity: float = 100000.0
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
        """
        Run complete strategy workflow (template method).

        Returns:
            (data_with_indicators, signals, sizes)
        """
        # Step 1: Compute indicators
        data = self.compute_indicators(data)

        # Step 2: Generate signals
        signals = self.generate_signals(data)

        # Step 3: Calculate position sizes
        # Note: In backtest, equity is dynamic. For now, use initial.
        # TODO: Integrate with BacktestEngine for dynamic equity
        equity = pd.Series(initial_equity, index=data.index)
        sizes = self.calculate_position_size(data, equity)

        return data, signals, sizes

# strategies/signal_based/sr_short.py

from dataclasses import dataclass
import pandas as pd
from strategies.base_strategy import BaseStrategy, StrategyConfig
from analytics.indicators.sr_zones import compute_sr_zones
from analytics.indicators.volatility import compute_atr

@dataclass
class SRShortConfig(StrategyConfig):
    """Configuration for SR Short strategy."""
    # Zone detection
    left_len: int = 90
    right_len: int = 10
    merge_atr_mult: float = 3.5

    # Risk management
    risk_per_trade: float = 0.005  # 0.5%
    leverage: float = 5.0

    # Entry filters
    min_touches: int = 1
    max_retries: int = 3

class SRShortStrategy(BaseStrategy):
    """
    Short-only strategy based on 4H resistance zones.

    Logic:
    1. Detect resistance zones on 4H timeframe
    2. Enter short when price touches zone
    3. Exit at SL (ATR-based) or trailing stop
    """

    def __init__(self, config: SRShortConfig):
        super().__init__(config)
        self.config = config  # Type hint for IDE

    def compute_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Compute SR zones and ATR."""
        # Resample to 4H for zone detection
        data_4h = resample_ohlcv(data, '4h')

        # Detect zones on 4H
        zones_4h = compute_sr_zones(
            data_4h,
            left_len=self.config.left_len,
            right_len=self.config.right_len,
            merge_atr_mult=self.config.merge_atr_mult
        )

        # Align zones back to original timeframe
        data = align_htf_to_ltf(data, zones_4h, '4h')

        # Compute ATR on original timeframe (for position sizing)
        data = data.assign(
            atr=compute_atr(data['high'], data['low'], data['close'], period=200)
        )

        return data

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate entry/exit signals based on zone touches."""
        entries = []
        exits = []
        reasons = []

        for i in range(len(data)):
            # Entry: close inside resistance zone
            if pd.notna(data['zone_top'].iloc[i]):
                zone_top = data['zone_top'].iloc[i]
                zone_bottom = data['zone_bottom'].iloc[i]
                close = data['close'].iloc[i]

                if zone_bottom <= close <= zone_top:
                    entries.append(True)
                    reasons.append('zone_touch')
                else:
                    entries.append(False)
                    reasons.append('')
            else:
                entries.append(False)
                reasons.append('')

            # Exit: handled by position manager (SL/TP)
            exits.append(False)

        return pd.DataFrame({
            'entry': entries,
            'exit': exits,
            'direction': 'short',
            'reason': reasons
        }, index=data.index)

    def calculate_position_size(
        self,
        data: pd.DataFrame,
        equity: pd.Series,
        base_size: float = 1.0
    ) -> pd.Series:
        """Calculate risk-based position sizes."""
        # Risk per trade = 0.5% of equity
        risk_amount = equity * self.config.risk_per_trade

        # Stop distance = 3 * ATR(200)
        stop_distance = data['atr'] * 3

        # Position size = risk / stop_distance
        # This gives us quantity in base asset (e.g., BTC)
        sizes = risk_amount / stop_distance

        # Apply leverage
        sizes = sizes * self.config.leverage

        # Convert to fraction of equity
        sizes = (sizes * data['close']) / equity

        return sizes.fillna(0)
```

**Key Principles**:
- **Clear Separation**: Indicators → Signals → Sizes
- **Pure Functions**: Each step is deterministic
- **Testable**: Easy to test each step independently
- **Composable**: Mix and match indicators/signals

---

### Layer 4: Orchestration Layer

**Purpose**: Coordinate components for end-to-end workflows

```
orchestration/
├── __init__.py
├── backtest_runner.py          # Backtest orchestration
├── optimization_runner.py      # Parameter optimization (future)
├── walk_forward.py             # Walk-forward analysis (future)
└── multi_strategy_runner.py    # Multi-strategy backtest (future)
```

**Design Pattern**: **Facade Pattern**

```python
# orchestration/backtest_runner.py

from dataclasses import dataclass
from pathlib import Path
import pandas as pd

from data import DataManager
from strategies.base_strategy import BaseStrategy
from execution.engines.base import BacktestEngine, BacktestConfig, BacktestResult
from analytics.metrics import calculate_metrics

@dataclass
class BacktestRunConfig:
    """Configuration for a complete backtest run."""
    # Data
    symbol: str
    timeframe: str
    start: datetime
    end: datetime
    source: str = 'okx'

    # Strategy
    strategy: BaseStrategy

    # Execution
    engine: BacktestEngine
    backtest_config: BacktestConfig

    # Output
    output_dir: Path
    save_results: bool = True

class BacktestRunner:
    """
    Orchestrates complete backtest workflow (Facade pattern).

    Hides complexity of coordinating multiple components:
    - DataManager
    - Strategy
    - BacktestEngine
    - Results export
    """

    def __init__(self, data_manager: DataManager):
        self.data_manager = data_manager

    def run(self, config: BacktestRunConfig) -> BacktestResult:
        """
        Run complete backtest workflow.

        Steps:
        1. Load data
        2. Run strategy (indicators → signals → sizes)
        3. Run backtest engine
        4. Calculate additional metrics
        5. Export results
        """
        print(f"Starting backtest: {config.strategy.config.name}")
        print(f"  Symbol: {config.symbol}")
        print(f"  Period: {config.start} to {config.end}")

        # Step 1: Load data
        print("Loading data...")
        data = self.data_manager.get_klines(
            symbol=config.symbol,
            timeframe=config.timeframe,
            start=config.start,
            end=config.end,
            source=config.source
        )
        print(f"  Loaded {len(data)} bars")

        # Step 2: Run strategy
        print("Running strategy...")
        data_with_indicators, signals, sizes = config.strategy.run(
            data,
            initial_equity=config.backtest_config.initial_cash
        )
        num_signals = signals['entry'].sum()
        print(f"  Generated {num_signals} entry signals")

        # Step 3: Run backtest
        print(f"Running backtest with {config.engine.get_name()}...")
        result = config.engine.run(
            data=data_with_indicators,
            signals=signals,
            sizes=sizes,
            config=config.backtest_config
        )
        print(f"  Executed {len(result.trades)} trades")

        # Step 4: Calculate additional metrics
        print("Calculating metrics...")
        additional_metrics = calculate_metrics(result)
        result.metrics.update(additional_metrics)

        # Step 5: Export results
        if config.save_results:
            print(f"Saving results to {config.output_dir}...")
            self._export_results(result, config)

        # Step 6: Print summary
        self._print_summary(result)

        return result

    def _export_results(self, result: BacktestResult, config: BacktestRunConfig):
        """Export results to files."""
        config.output_dir.mkdir(parents=True, exist_ok=True)

        # Export trades
        trades_path = config.output_dir / 'trades.csv'
        result.trades.to_csv(trades_path, index=False)

        # Export equity curve
        equity_path = config.output_dir / 'equity_curve.csv'
        result.equity_curve.to_csv(equity_path)

        # Export metrics
        metrics_path = config.output_dir / 'metrics.json'
        with open(metrics_path, 'w') as f:
            json.dump(result.metrics, f, indent=2)

        print(f"  Saved: {trades_path}")
        print(f"  Saved: {equity_path}")
        print(f"  Saved: {metrics_path}")

    def _print_summary(self, result: BacktestResult):
        """Print backtest summary."""
        print("\n" + "="*60)
        print("BACKTEST RESULTS")
        print("="*60)
        print(f"Total Return: {result.metrics['total_return']:.2%}")
        print(f"Sharpe Ratio: {result.metrics['sharpe_ratio']:.2f}")
        print(f"Max Drawdown: {result.metrics['max_drawdown']:.2%}")
        print(f"Win Rate: {result.metrics['win_rate']:.2%}")
        print(f"Total Trades: {len(result.trades)}")
        print("="*60)
```

**Key Principles**:
- **Single Responsibility**: Runner only orchestrates, doesn't implement logic
- **Dependency Injection**: All dependencies passed in (easy to test)
- **Clean API**: Simple `run()` method hides complexity

---

### Layer 5: Application Layer

**Purpose**: User-facing interfaces (scripts, CLI, notebooks)

```
run/
├── run_backtest.py             # Simple backtest script
├── run_optimization.py         # Parameter optimization (future)
└── run_walk_forward.py         # Walk-forward analysis (future)

notebooks/
├── 01_strategy_development.ipynb
├── 02_backtest_analysis.ipynb
└── 03_multi_factor_research.ipynb  # Future

cli/                            # CLI interface (future)
└── taoquant.py
```

**Design Pattern**: **Minimal Boilerplate**

```python
# run/run_backtest.py

"""
Minimal backtest script.

This is the ONLY file users need to modify for basic backtests.
All complexity is hidden in orchestration layer.
"""

from datetime import datetime
from pathlib import Path

from data import DataManager
from strategies.signal_based.sr_short import SRShortStrategy, SRShortConfig
from execution.engines.vectorbt_engine import VectorBTEngine
from execution.engines.base import BacktestConfig
from orchestration.backtest_runner import BacktestRunner, BacktestRunConfig

# ============================================================================
# CONFIGURATION - Modify this section only
# ============================================================================

# Data parameters
SYMBOL = "BTCUSDT"
TIMEFRAME = "15m"
START = datetime(2025, 10, 1)
END = datetime(2025, 12, 1)
SOURCE = "okx"

# Strategy parameters
STRATEGY_CONFIG = SRShortConfig(
    name="SR Short 4H",
    description="Short-only strategy based on 4H resistance zones",
    left_len=90,
    right_len=10,
    merge_atr_mult=3.5,
    risk_per_trade=0.005,
    leverage=5.0,
)

# Backtest parameters
BACKTEST_CONFIG = BacktestConfig(
    initial_cash=100000.0,
    commission=0.001,  # 0.1%
    slippage=0.0005,   # 0.05%
    leverage=5.0,
)

# Output
OUTPUT_DIR = Path("run/results")

# ============================================================================
# EXECUTION - No need to modify below
# ============================================================================

if __name__ == "__main__":
    # Initialize components
    data_manager = DataManager()
    strategy = SRShortStrategy(STRATEGY_CONFIG)
    engine = VectorBTEngine()
    runner = BacktestRunner(data_manager)

    # Run backtest
    result = runner.run(BacktestRunConfig(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start=START,
        end=END,
        source=SOURCE,
        strategy=strategy,
        engine=engine,
        backtest_config=BACKTEST_CONFIG,
        output_dir=OUTPUT_DIR,
        save_results=True,
    ))

    print("\n✅ Backtest completed successfully!")
    print(f"📊 Results saved to: {OUTPUT_DIR}")
```

**Key Principles**:
- **Minimal Configuration**: Users only set parameters
- **Zero Boilerplate**: All complexity hidden
- **Clear Separation**: Config vs Execution

---

## 🧬 Multi-Factor Alpha Framework (Future Design)

### Architecture for Factor-Based Strategies

```python
# strategies/alpha/base_factor.py

from abc import ABC, abstractmethod
import pandas as pd

class AlphaFactor(ABC):
    """
    Base class for alpha factors.

    A factor is a transformation: DataFrame → Series of expected returns.
    """

    @abstractmethod
    def compute(self, data: pd.DataFrame) -> pd.Series:
        """
        Compute factor values (expected returns).

        Args:
            data: Multi-asset DataFrame (columns = assets, rows = timestamps)

        Returns:
            Series of expected returns for each asset
        """
        pass

# strategies/alpha/momentum.py

class MomentumFactor(AlphaFactor):
    """Momentum factor: assets with high past returns."""

    def __init__(self, lookback: int = 20):
        self.lookback = lookback

    def compute(self, data: pd.DataFrame) -> pd.Series:
        """Compute momentum scores."""
        # Simple: return over lookback period
        returns = data.pct_change(self.lookback)
        return returns.iloc[-1]  # Latest momentum scores

# strategies/alpha/multi_factor.py

class MultiFactorStrategy:
    """
    Combine multiple alpha factors for portfolio construction.

    Workflow:
    1. Compute each factor
    2. Combine factors (weighted average, ML, etc.)
    3. Rank assets by combined alpha
    4. Construct portfolio (long top N, short bottom N)
    """

    def __init__(self, factors: list[AlphaFactor], weights: list[float]):
        self.factors = factors
        self.weights = weights

    def generate_alpha(self, data: pd.DataFrame) -> pd.Series:
        """Combine factors into single alpha signal."""
        alphas = []
        for factor in self.factors:
            alphas.append(factor.compute(data))

        # Weighted average
        combined = sum(a * w for a, w in zip(alphas, self.weights))
        return combined

    def construct_portfolio(
        self,
        alpha: pd.Series,
        long_pct: float = 0.2,  # Long top 20%
        short_pct: float = 0.2  # Short bottom 20%
    ) -> dict:
        """Construct long-short portfolio from alpha scores."""
        # Rank assets
        ranked = alpha.sort_values(ascending=False)

        # Select top/bottom
        n_assets = len(alpha)
        n_long = int(n_assets * long_pct)
        n_short = int(n_assets * short_pct)

        long_assets = ranked.head(n_long).index.tolist()
        short_assets = ranked.tail(n_short).index.tolist()

        return {
            'long': long_assets,
            'short': short_assets,
            'alpha': alpha
        }
```

### Factor Research Workflow

```python
# notebooks/multi_factor_research.ipynb

# 1. Load universe of assets
universe = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', ...]
data = load_multi_asset_data(universe, start, end)

# 2. Define factors
factors = [
    MomentumFactor(lookback=20),
    ValueFactor(),  # Market cap weighted
    VolatilityFactor(),  # Low vol anomaly
]

# 3. Backtest each factor individually
for factor in factors:
    alpha = factor.compute(data)
    result = backtest_factor(alpha, data)
    print(f"{factor.name}: Sharpe={result.sharpe:.2f}")

# 4. Find optimal factor combination
from sklearn.linear_model import Ridge
from factor_research import FactorCombiner

combiner = FactorCombiner(method='ml')  # or 'equal', 'risk_parity'
optimal_weights = combiner.fit(factors, data)

# 5. Backtest combined strategy
strategy = MultiFactorStrategy(factors, optimal_weights)
result = backtest_strategy(strategy, data)
```

---

## 🔄 Data Flow Diagrams

### Backtest Workflow

```
┌──────────────┐
│   User       │
│ (run script) │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────┐
│     BacktestRunner                   │
│  (Orchestration Layer)               │
└──────┬───────────────────────────────┘
       │
       ├─────► DataManager ──► [OKX/Binance] ──► Raw OHLCV
       │         │
       │         └──────────────────────► Cached Parquet
       │
       ├─────► Strategy
       │         ├─► compute_indicators()  ──► data + indicators
       │         ├─► generate_signals()    ──► signals
       │         └─► calculate_sizes()     ──► position sizes
       │
       ├─────► BacktestEngine (VectorBT)
       │         ├─► Portfolio simulation
       │         └─► Trade execution
       │
       └─────► Results
                 ├─► Metrics calculation
                 ├─► Export to CSV/JSON
                 └─► Generate plots
```

### Strategy Execution Flow

```
Raw Data
   │
   ▼
┌──────────────────┐
│ Compute          │  Pure function: data → data + indicators
│ Indicators       │  (SMA, EMA, ATR, SR zones, etc.)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Generate         │  Pure function: data → signals
│ Signals          │  (entry/exit decisions)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Calculate        │  Function: data + equity → sizes
│ Position Sizes   │  (risk management)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Execute          │  Engine: signals + sizes → trades
│ Backtest         │  (VectorBT, custom, etc.)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Analyze          │  Metrics + visualizations
│ Results          │
└──────────────────┘
```

---

## 🛡️ Best Practices

### 1. Testing Strategy

```python
# tests/test_sr_strategy.py

import pytest
import pandas as pd
from strategies.signal_based.sr_short import SRShortStrategy, SRShortConfig

def test_sr_strategy_indicators():
    """Test indicator computation."""
    # Arrange: Create sample data
    data = pd.DataFrame({
        'open': [100, 101, 102],
        'high': [105, 106, 107],
        'low': [99, 100, 101],
        'close': [104, 105, 106],
        'volume': [1000, 1100, 1200]
    })

    strategy = SRShortStrategy(SRShortConfig(
        name="test",
        description="test"
    ))

    # Act: Compute indicators
    result = strategy.compute_indicators(data)

    # Assert: Check expected columns exist
    assert 'zone_top' in result.columns
    assert 'zone_bottom' in result.columns
    assert 'atr' in result.columns

def test_sr_strategy_signals():
    """Test signal generation."""
    # Use property-based testing with hypothesis
    from hypothesis import given, strategies as st

    @given(
        closes=st.lists(st.floats(min_value=1, max_value=1000), min_size=100, max_size=100),
        zone_top=st.floats(min_value=100, max_value=500),
        zone_bottom=st.floats(min_value=50, max_value=99)
    )
    def test_signal_logic(closes, zone_top, zone_bottom):
        # Property: signal should trigger when close is in zone
        for close in closes:
            if zone_bottom <= close <= zone_top:
                assert should_enter(close, zone_top, zone_bottom) == True
```

### 2. Error Handling

```python
# data/data_manager.py

class DataFetchError(Exception):
    """Raised when data fetching fails."""
    pass

class DataManager:
    def get_klines(self, symbol: str, ...) -> pd.DataFrame:
        """Get OHLCV data with robust error handling."""
        try:
            data = self._fetch(symbol, ...)
        except requests.RequestException as e:
            raise DataFetchError(f"Failed to fetch {symbol}: {e}") from e

        # Validate data
        if data.empty:
            raise DataFetchError(f"No data returned for {symbol}")

        if not self._validate_data(data):
            raise DataFetchError(f"Invalid data for {symbol}")

        return data
```

### 3. Logging

```python
# Use structured logging
import structlog

logger = structlog.get_logger()

class BacktestRunner:
    def run(self, config: BacktestRunConfig) -> BacktestResult:
        logger.info(
            "backtest_started",
            symbol=config.symbol,
            strategy=config.strategy.config.name,
            start=config.start.isoformat(),
            end=config.end.isoformat()
        )

        # ... run backtest ...

        logger.info(
            "backtest_completed",
            num_trades=len(result.trades),
            total_return=result.metrics['total_return'],
            sharpe=result.metrics['sharpe_ratio']
        )

        return result
```

### 4. Configuration Management

```python
# Use dataclasses with validation
from dataclasses import dataclass, field
from typing import ClassVar

@dataclass
class SRShortConfig(StrategyConfig):
    left_len: int = 90
    right_len: int = 10
    risk_per_trade: float = 0.005

    # Class-level validation
    MIN_LEFT_LEN: ClassVar[int] = 1
    MAX_LEFT_LEN: ClassVar[int] = 200

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not (self.MIN_LEFT_LEN <= self.left_len <= self.MAX_LEFT_LEN):
            raise ValueError(
                f"left_len must be in [{self.MIN_LEFT_LEN}, {self.MAX_LEFT_LEN}]"
            )

        if not (0 < self.risk_per_trade < 0.1):
            raise ValueError("risk_per_trade must be in (0, 0.1)")
```

---

## 📊 Performance Considerations

### 1. Vectorization

**Slow** (loop):
```python
signals = []
for i in range(len(data)):
    if data['close'].iloc[i] > data['sma'].iloc[i]:
        signals.append(True)
    else:
        signals.append(False)
```

**Fast** (vectorized):
```python
signals = data['close'] > data['sma']
```

### 2. Memory Efficiency

```python
# Use categorical for repeated string columns
data['signal_reason'] = data['signal_reason'].astype('category')

# Use appropriate dtypes
data = data.astype({
    'open': 'float32',   # float32 sufficient for prices
    'volume': 'int32',   # int32 sufficient for volumes
})

# Process data in chunks for large datasets
def process_large_dataset(file_path: Path, chunk_size: int = 10000):
    for chunk in pd.read_csv(file_path, chunksize=chunk_size):
        yield process_chunk(chunk)
```

### 3. Caching

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def compute_expensive_indicator(
    data_hash: str,  # Hash of data for cache key
    period: int
) -> pd.Series:
    """Cache expensive indicator calculations."""
    # ... compute ...
    pass
```

---

## 🔮 Future Roadmap

### Phase 1: Foundation (Current)
- [x] Clean architecture design
- [ ] VectorBT migration
- [ ] Core strategy refactoring

### Phase 2: Research Tools (3-6 months)
- [ ] Parameter optimization framework (Optuna)
- [ ] Walk-forward analysis
- [ ] Factor research framework
- [ ] Multi-factor backtesting

### Phase 3: Production Ready (6-12 months)
- [ ] Live trading engine
- [ ] Order management system
- [ ] Risk monitoring
- [ ] Database persistence (TimescaleDB)
- [ ] Dashboard (Streamlit/Grafana)

### Phase 4: Advanced Features (12+ months)
- [ ] Machine learning integration (sklearn, PyTorch)
- [ ] High-frequency trading support
- [ ] Options/futures support
- [ ] Multi-exchange arbitrage

---

## 📚 Appendix

### A. Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Backtesting** | VectorBT | Native fractional positions, 100x speedup |
| **Data Storage** | Parquet | Fast columnar storage |
| **Data Access** | pandas | Industry standard |
| **Optimization** | Optuna | State-of-the-art Bayesian optimization |
| **Visualization** | Plotly/Bokeh | Interactive charts |
| **Testing** | pytest + hypothesis | Unit + property-based testing |
| **Type Checking** | mypy | Compile-time safety |
| **Code Quality** | Black + Ruff | Consistent style |
| **Logging** | structlog | Structured, machine-readable logs |

### B. Code Style Guide

```python
# Use type hints everywhere
def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """Calculate ATR with explicit types."""
    ...

# Use descriptive names (no abbreviations unless standard)
# Good
def calculate_moving_average(data, period):
    ...

# Bad
def calc_ma(d, p):
    ...

# Use docstrings (Google style)
def detect_zones(data: pd.DataFrame) -> pd.DataFrame:
    """
    Detect support/resistance zones.

    Args:
        data: OHLCV DataFrame with columns [open, high, low, close, volume]

    Returns:
        DataFrame with added columns:
        - zone_top: Top of zone
        - zone_bottom: Bottom of zone

    Raises:
        ValueError: If required columns are missing

    Example:
        >>> data = pd.DataFrame(...)
        >>> zones = detect_zones(data)
        >>> assert 'zone_top' in zones.columns
    """
    ...
```

### C. Git Workflow

```bash
# Feature branch workflow
git checkout -b feature/vectorbt-migration
git commit -m "feat: implement VectorBT engine interface"
git commit -m "test: add VectorBT engine tests"
git commit -m "docs: update architecture documentation"

# Commit message format: type(scope): description
# Types: feat, fix, test, docs, refactor, perf, chore
```

---

**Document Status**: ACTIVE
**Last Updated**: 2025-12-03
**Next Review**: After VectorBT migration completion

---

This design document is a living document and should be updated as the system evolves.

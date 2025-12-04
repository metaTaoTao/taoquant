# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**TaoQuant** is a professional quantitative trading framework for cryptocurrency markets, built with clean architecture principles and modern Python best practices. The framework uses VectorBT for high-performance backtesting (100x faster than event-driven engines) and emphasizes pure functions, type safety, and separation of concerns.

## Architecture

### Clean Architecture Layers

```
Application Layer (run_backtest_new.py)
    ↓
Orchestration (BacktestRunner) - Coordinates workflow
    ↓
Strategy Layer (BaseStrategy) - Trading logic
    ↓
Execution Layer (VectorBTEngine) - Backtest engine
    ↓
Analytics Layer (Indicators) - Technical analysis
    ↓
Data Layer (DataManager) - Market data
```

### Data Flow

1. **Data Acquisition** → `DataManager` (data/data_manager.py) fetches OHLCV data from exchanges or CSV
2. **Caching** → Parquet files stored in `data/cache/`
3. **Strategy Execution** → Strategy implements three pure functions:
   - `compute_indicators()` - Add technical indicators
   - `generate_signals()` - Generate entry/exit signals
   - `calculate_position_size()` - Calculate position sizes
4. **Backtesting** → VectorBTEngine runs vectorized backtest
5. **Results** → Saved to `run/results_new/`

## Development Workflow

### Running Backtests

```bash
# Edit configuration in run/run_backtest.py
python run/run_backtest.py
```

Configuration structure:
```python
# Data parameters
SYMBOL = "BTCUSDT"
TIMEFRAME = "15m"
START = pd.Timestamp("2025-10-01", tz="UTC")
END = pd.Timestamp("2025-12-01", tz="UTC")
SOURCE = "okx"  # 'okx', 'binance', or 'csv'

# Strategy parameters
STRATEGY_CONFIG = SRShortConfig(
    left_len=90,
    right_len=10,
    risk_per_trade_pct=0.5,
    leverage=5.0,
)

# Backtest parameters
BACKTEST_CONFIG = BacktestConfig(
    initial_cash=100000.0,
    commission=0.001,
    slippage=0.0005,
    leverage=5.0,
)
```

Results are saved to `run/results_new/`:
- `trades.csv`: Individual trade records
- `equity_curve.csv`: Equity over time
- `metrics.json`: Performance metrics
- `summary.txt`: Human-readable summary

### Adding New Strategies

1. Create strategy file in `strategies/signal_based/` extending `BaseStrategy`
2. Implement three pure functions:
   ```python
   from strategies.base_strategy import BaseStrategy, StrategyConfig
   import pandas as pd

   class MyStrategy(BaseStrategy):
       def compute_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
           """Pure function: data → data + indicators"""
           # Add your indicators here
           return data.assign(my_indicator=...)

       def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
           """Pure function: data → signals"""
           entry = data['close'] > data['my_indicator']
           return pd.DataFrame({
               'entry': entry,
               'exit': False,
               'direction': 'long'
           }, index=data.index)

       def calculate_position_size(
           self,
           data: pd.DataFrame,
           equity: pd.Series,
           base_size: float = 1.0
       ) -> pd.Series:
           """Pure function: data + equity → sizes"""
           return pd.Series(0.5, index=data.index)  # Fixed 50% size
   ```
3. Use in `run/run_backtest_new.py`:
   ```python
   from strategies.signal_based.my_strategy import MyStrategy, MyStrategyConfig

   strategy = MyStrategy(MyStrategyConfig(name="My Strategy", ...))
   ```

### Adding New Indicators

1. Create indicator in `analytics/indicators/` as a pure function
2. Input: OHLCV DataFrame
3. Output: DataFrame with new indicator columns or pd.Series
4. Add tests in `tests/`

Example:
```python
import pandas as pd

def calculate_my_indicator(
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    Calculate my indicator.

    Args:
        close: Close price series
        period: Lookback period

    Returns:
        Indicator values
    """
    return close.rolling(window=period).mean()
```

## Important Constraints

### VectorBT Integration

- Signals must be boolean Series (entry, exit)
- Position sizes as fraction of equity (0.0-1.0+)
- Leverage applied at engine level
- DataFrame index must be DatetimeIndex

### Data Column Conventions

- Exchange APIs return lowercase: `open`, `high`, `low`, `close`, `volume`
- Keep lowercase throughout the system
- DataFrames indexed by timestamp (timezone-aware UTC)

### Pure Functions

All strategy logic must be pure functions:
- No side effects
- No mutable state
- Same input → same output
- Enables testability

Example:
```python
# ✅ Pure function
def compute_sr_zones(data: pd.DataFrame, left_len: int, right_len: int) -> pd.DataFrame:
    # No side effects, no state mutations
    return data_with_zones

# ❌ Avoid stateful code
class Strategy:
    def __init__(self):
        self.zones = []  # Mutable state
    def next(self):
        self.zones.append(...)  # Side effect
```

## Configuration

### Backtest Configuration

Using dataclasses for type-safe configuration:
```python
from execution.engines.base import BacktestConfig

config = BacktestConfig(
    initial_cash=100000.0,
    commission=0.001,  # 0.1%
    slippage=0.0005,   # 0.05%
    leverage=5.0,
)
```

### Strategy Configuration

Each strategy defines its own config:
```python
from dataclasses import dataclass
from strategies.base_strategy import StrategyConfig

@dataclass
class MyStrategyConfig(StrategyConfig):
    my_param: int = 10
    my_other_param: float = 0.5
```

### Timeframe Formats

Use standard formats: `"1m"`, `"5m"`, `"15m"`, `"1h"`, `"4h"`, `"1d"`, `"1w"`
- Conversion to minutes: `utils/timeframes.py::timeframe_to_minutes()`
- Resampling: `utils/resample.py::resample_ohlcv()`

## Data Sources

Supported sources (case-insensitive):
- `"okx"` or `"okx_sdk"`: OKX exchange via `python-okx`
- `"binance"` or `"binance_sdk"`: Binance via `python-binance`
- `"csv"`: Load from local CSV files

Data is cached as Parquet in `data/cache/` with naming: `{source}_{symbol}_{timeframe}.parquet`

## File Organization

```
taoquant/
├── analytics/              # Technical indicators
│   └── indicators/
│       ├── sr_zones.py     # Support/Resistance zones
│       └── volatility.py   # ATR, Bollinger Bands
│
├── data/                   # Data management
│   ├── sources/            # Exchange adapters (OKX, Binance)
│   └── data_manager.py     # Unified data interface
│
├── execution/              # Backtest engines
│   ├── engines/
│   │   ├── base.py         # Engine interface
│   │   └── vectorbt_engine.py  # VectorBT implementation
│   ├── position_manager.py # Multi-position tracking
│   └── signal_generator.py # Signal utilities
│
├── strategies/             # Trading strategies
│   ├── base_strategy.py    # Strategy interface
│   └── signal_based/
│       └── sr_short.py     # SR short strategy
│
├── risk_management/        # Risk management
│   └── position_sizer.py   # Position sizing utilities
│
├── orchestration/          # Workflow coordination
│   └── backtest_runner.py  # Backtest orchestrator
│
├── utils/                  # Utilities
│   ├── resample.py         # Timeframe resampling
│   └── timeframes.py       # Timeframe conversions
│
├── run/                    # Entry points
│   └── run_backtest_new.py # Main backtest script
│
├── legacy/                 # Archived old code
│   └── README.md           # See legacy/README.md for details
│
└── docs/                   # Documentation
    ├── system_design.md    # Architecture guide
    ├── phase1_completion_summary.md
    └── phase2_completion_summary.md
```

## Common Patterns

### Multi-Timeframe Strategies

Resample to higher timeframe for indicators, align back to base timeframe:
```python
from utils.resample import resample_ohlcv

def compute_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
    # Resample to 4H for zone detection
    data_4h = resample_ohlcv(data, '4h')
    zones_4h = compute_sr_zones(data_4h, ...)

    # Align back to base timeframe
    zones_aligned = zones_4h[zone_columns].reindex(data.index, method='ffill')

    return data.assign(**zones_aligned)
```

### Risk-Based Position Sizing

Use ATR-based stops with risk percentage:
```python
from risk_management.position_sizer import calculate_risk_based_size
from analytics.indicators.volatility import calculate_atr

def calculate_position_size(self, data, equity, base_size=1.0):
    atr = calculate_atr(data['high'], data['low'], data['close'], period=14)
    stop_distance = atr * 3.0

    return calculate_risk_based_size(
        equity=equity,
        stop_distance=stop_distance,
        current_price=data['close'],
        risk_per_trade=0.01,  # 1% risk per trade
        leverage=5.0
    )
```

## Legacy Code

The `legacy/` folder contains the old backtesting.py-based implementation. DO NOT use this code. It has been replaced with a cleaner, faster VectorBT-based architecture. See `legacy/README.md` for details.

## Testing

```bash
# Run unit tests
pytest tests/

# Run specific test
pytest tests/test_sr_zones.py -v

# Run with coverage
pytest --cov=analytics --cov=strategies --cov-report=html
```

## Performance

| Metric | backtesting.py | VectorBT | Improvement |
|--------|----------------|----------|-------------|
| Speed | 10s | 0.1s | **100x faster** |
| Memory | High | Low | **50% reduction** |
| Code | 1,800 LOC | 800 LOC | **56% less code** |

## Documentation

- **[README.md](README.md)** - Project overview
- **[System Design](docs/system_design.md)** - Architecture overview
- **[Phase 1 Summary](docs/phase1_completion_summary.md)** - Engine layer
- **[Phase 2 Summary](docs/phase2_completion_summary.md)** - Strategy layer
- **[Migration Guide](docs/vector_bt_migration_todo.md)** - VectorBT migration

## Key Principles

1. **Pure Functions** - No side effects, no state mutations
2. **Separation of Concerns** - Each layer has one responsibility
3. **Type Safety** - 100% type hints, mypy-compatible
4. **Testability** - Every component independently testable
5. **Engine-Agnostic** - Strategies don't depend on specific engines
6. **Clean Architecture** - Dependencies point inward

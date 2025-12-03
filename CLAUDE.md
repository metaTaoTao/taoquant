# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**TaoQuant** is a quantitative trading framework focused on support/resistance (SR) strategies and high-frequency guard rail trading. The project integrates with cryptocurrency exchanges (OKX, Binance) and uses the `backtesting.py` library for strategy testing.

## Architecture

### Data Flow
1. **Data Acquisition** → `DataManager` (data/data_manager.py) fetches OHLCV data from exchanges or CSV
2. **Caching** → Parquet files stored in `data/cache/` (configurable via `CacheConfig`)
3. **Indicators** → Calculate technical indicators (BaseIndicator subclasses)
4. **Strategies** → Implement trading logic (backtesting.Strategy subclasses)
5. **Backtesting** → `backtest/engine.py` runs strategies and generates reports

### Strategy Registry Pattern
Strategies are registered in `strategies/__init__.py` using a `STRATEGY_REGISTRY` dict:
```python
STRATEGY_REGISTRY = {
    "sr_guard": SRGuardRailStrategy,
    "sma_cross": SMACrossStrategy,
    # ...
}
```
The registry enables dynamic strategy loading by name string.

### Indicator System
All indicators extend `BaseIndicator` (indicators/base_indicator.py):
- `calculate(df) -> pd.DataFrame`: Adds indicator columns to the dataframe
- `plot(df)`: Returns mplfinance addplot list for visualization

Key indicators:
- `SupportResistanceVolumeBoxesIndicator`: Core SR detection with volume analysis
- `VolumeHeatmapIndicator`: Volume-weighted price levels
- `EMAIndicator`: Exponential moving averages

### Guard Rail Strategy Pattern
The `SRGuardRailStrategy` (strategies/sr_guard.py) implements a mean-reversion approach:
1. Detects SR levels using pivot analysis
2. Builds "guard rails" (support/resistance boundaries)
3. Enters long near support, short near resistance
4. Uses ATR-based stops

## Development Workflow

### Running Backtests
```bash
# Edit configuration in scripts/run_backtest.py
python scripts/run_backtest.py
```

Configuration structure:
```python
run_config = {
    "symbol": "BTCUSDT",
    "timeframe": "15m",
    "strategy": "sr_guard",  # Must match STRATEGY_REGISTRY key
    "source": "okx",
    "lookback_days": 30,
    "output": "backtest/results",
    "strategy_params": {
        "lookback_period": 20,
        "box_width_mult": 1.0,
        # ...
    }
}
```

Results are saved to `backtest/results/`:
- `trades.csv`: Individual trade records
- `equity_curve.csv`: Equity over time
- `backtest_plot.html`: Interactive Bokeh chart
- `guard_rails.csv`: Support/resistance levels (if strategy exposes them)

### Data Sources
Supported sources (case-insensitive):
- `"okx"` or `"okx_sdk"`: OKX exchange via `python-okx`
- `"binance"` or `"binance_sdk"`: Binance via `python-binance`
- `"csv"`: Load from local CSV files

Data is cached as Parquet in `data/cache/` with naming: `{source}_{symbol}_{timeframe}.parquet`

### Adding New Strategies
1. Create strategy file in `strategies/` extending `backtesting.Strategy`
2. Implement `init()` and `next()` methods
3. Register in `strategies/__init__.py`:
   ```python
   from strategies.my_strategy import MyStrategy
   STRATEGY_REGISTRY["my_strategy"] = MyStrategy
   ```
4. Configure and run via `scripts/run_backtest.py`

### Adding New Indicators
1. Create indicator in `indicators/` extending `BaseIndicator`
2. Implement `calculate(df)` to add columns to dataframe
3. Optionally implement `plot(df)` for visualization
4. Import in strategy's `init()` method and call `calculate()`

## Important Constraints

### Backtesting.py Integration
- Input dataframes must have columns: `Open`, `High`, `Low`, `Close` (title case)
- Index must be timezone-naive datetime (use `.tz_convert(None)`)
- The `_prepare_dataset()` function in `backtest/engine.py` handles normalization

### Data Column Conventions
- Exchange APIs return lowercase: `open`, `high`, `low`, `close`, `volume`
- Backtesting.py requires title case: `Open`, `High`, `Low`, `Close`
- Indicators work with lowercase columns
- Conversion happens in `backtest/engine.py::_prepare_dataset()`

### PineScript Integration
The `TV/` directory contains TradingView PineScript implementations:
- `sr_indicator_v1.txt`: Original SR indicator (indicator mode)
- `sr_indicator_v2_clean.txt`: Multi-timeframe (MTF) version
- These are **text files** for copy-paste into TradingView Pine Editor
- PineScript MCP server may have validation issues - always verify in TradingView

## Configuration

### Default Configuration (core/config.py)
```python
default_config = ProjectConfig(
    cache=CacheConfig(
        enabled=True,
        cache_dir=Path("data/cache")
    ),
    backtest=BacktestConfig(
        initial_capital=200000.0,
        commission=0.004,  # 0.4%
        slippage=0.0005    # 0.05%
    )
)
```

### Timeframe Formats
Use standard formats: `"1m"`, `"5m"`, `"15m"`, `"1h"`, `"4h"`, `"1d"`, `"1w"`
- Conversion to minutes: `utils/timeframes.py::timeframe_to_minutes()`

## Jupyter Notebooks

Notebooks in `notebooks/` demonstrate indicator visualization:
- `01_visualize_indicator.ipynb`: Shows how to use `DataManager`, apply indicators, and plot with `ChartPlotter`

Usage pattern:
```python
from data import DataManager
from indicators.sr_volume_boxes import SupportResistanceVolumeBoxesIndicator

manager = DataManager()
df = manager.get_klines("BTCUSDT", "15m", source="okx")

indicator = SupportResistanceVolumeBoxesIndicator(lookback_period=20)
result = indicator.calculate(df)
```

## File Organization

```
taoquant/
├── backtest/          # Backtesting engine
├── core/              # Configuration, strategy registry, scheduler
├── data/              # Data management, sources, schemas
│   ├── sources/       # Exchange adapters (OKX, Binance)
│   └── cache/         # Parquet cache (gitignored)
├── indicators/        # Technical indicators
├── strategies/        # Trading strategies
├── risk_management/   # Risk checker utilities
├── scripts/           # Runnable scripts (backtesting, data fetch)
├── notebooks/         # Jupyter analysis notebooks
├── utils/             # Helper utilities (CSV loader, timeframes, SR detection)
└── TV/                # TradingView PineScript files (.txt format)
```

## Common Patterns

### Strategy Parameter Optimization
Parameters can be passed via `strategy_params` dict in run config. All class-level attributes become tunable:
```python
class MyStrategy(Strategy):
    my_param: int = 10  # Tunable parameter

# In run_backtest.py:
"strategy_params": {"my_param": 20}
```

### Guard Rail Logging
The `SRGuardRailStrategy` logs guard rail decisions to `_order_log` list, which is exported to `guard_orders.csv` if available.

### Data Trimming
`DataManager.get_klines()` supports `start` and `end` parameters (pd.Timestamp):
- If cache exists, data is trimmed to requested range
- If no cache, fetches from exchange API with date range

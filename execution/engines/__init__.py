"""
Backtest engines for TaoQuant.

Currently supported:
- VectorBT (vectorized backtesting)

Future:
- Custom engine (event-driven)
- Nautilus (high-frequency)
"""

from execution.engines.base import (
    BacktestConfig,
    BacktestEngine,
    BacktestResult,
)
from execution.engines.vectorbt_engine import VectorBTEngine

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestResult",
    "VectorBTEngine",
]

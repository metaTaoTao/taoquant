"""
Execution layer for TaoQuant.

This module provides abstractions for backtesting, simulation, and live trading.
All engines implement the same interface for consistency and swappability.
"""

from execution.engines.base import (
    BacktestConfig,
    BacktestEngine,
    BacktestResult,
)

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestResult",
]

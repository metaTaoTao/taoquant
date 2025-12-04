"""
Orchestration layer for TaoQuant.

This module coordinates complex workflows:
- Backtest execution
- Parameter optimization (future)
- Walk-forward analysis (future)
- Multi-strategy backtesting (future)
"""

from orchestration.backtest_runner import BacktestRunner, BacktestRunConfig

__all__ = [
    "BacktestRunner",
    "BacktestRunConfig",
]

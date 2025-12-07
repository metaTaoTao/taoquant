"""
Abstract base class for all backtest engines.

This module defines the interface that all engines must implement,
ensuring consistency and swappability across different implementations.

Design Principles:
- Engine-agnostic: strategies don't depend on specific engines
- Pure data in/out: no side effects, all state in results
- Type-safe: full type hints for compile-time safety
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

import pandas as pd


@dataclass
class BacktestConfig:
    """
    Engine-agnostic backtest configuration.

    This configuration works with any engine that implements BacktestEngine.

    Attributes
    ----------
    initial_cash : float
        Starting capital in quote currency (e.g., USDT)
    commission : float
        Commission rate as decimal (e.g., 0.001 = 0.1%)
    slippage : float
        Slippage as decimal (e.g., 0.0005 = 0.05%)
    leverage : float
        Maximum leverage multiplier (default: 1.0 = no leverage)

    Examples
    --------
    >>> config = BacktestConfig(
    ...     initial_cash=100000.0,
    ...     commission=0.001,
    ...     slippage=0.0005,
    ...     leverage=5.0
    ... )
    """

    initial_cash: float
    commission: float
    slippage: float
    leverage: float = 1.0

    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.initial_cash <= 0:
            raise ValueError(f"initial_cash must be positive, got {self.initial_cash}")

        if not (0 <= self.commission < 1):
            raise ValueError(f"commission must be in [0, 1), got {self.commission}")

        if not (0 <= self.slippage < 1):
            raise ValueError(f"slippage must be in [0, 1), got {self.slippage}")

        if self.leverage <= 0:
            raise ValueError(f"leverage must be positive, got {self.leverage}")


@dataclass
class BacktestResult:
    """
    Standardized backtest results (engine-agnostic).

    All engines return results in this format for consistency.

    Attributes
    ----------
    trades : pd.DataFrame
        All executed trades with columns:
        - entry_time: datetime
        - exit_time: datetime
        - entry_price: float
        - exit_price: float
        - size: float (negative for short)
        - pnl: float (realized P&L)
        - return_pct: float (return percentage)
        - duration: timedelta

    equity_curve : pd.DataFrame
        Equity over time with columns:
        - equity: float (total equity)
        - cash: float (available cash)
        - position_value: float (value of open positions)

    positions : pd.DataFrame
        Position snapshots with columns:
        - time: datetime
        - size: float (position size)
        - value: float (position value)
        - entry_price: float
        - current_price: float
        - unrealized_pnl: float

    metrics : dict
        Performance metrics:
        - total_return: float (total return %)
        - sharpe_ratio: float
        - sortino_ratio: float
        - max_drawdown: float (%)
        - win_rate: float (%)
        - profit_factor: float
        - total_trades: int
        - ... (more metrics)

    metadata : dict
        Backtest metadata:
        - engine: str (engine name)
        - start_time: datetime
        - end_time: datetime
        - duration: timedelta
        - symbol: str (optional)
        - timeframe: str (optional)

    Examples
    --------
    >>> result = engine.run(data, signals, sizes, config)
    >>> print(f"Total Return: {result.metrics['total_return']:.2%}")
    >>> print(f"Sharpe Ratio: {result.metrics['sharpe_ratio']:.2f}")
    >>> result.trades.to_csv('trades.csv')
    """

    trades: pd.DataFrame
    equity_curve: pd.DataFrame
    positions: pd.DataFrame
    metrics: Dict[str, float]
    metadata: Dict[str, any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """
        Serialize result to dictionary.

        Returns
        -------
        dict
            Dictionary with all results (DataFrames converted to records)
        """
        return {
            'trades': self.trades.to_dict('records'),
            'equity_curve': self.equity_curve.to_dict('records'),
            'positions': self.positions.to_dict('records'),
            'metrics': self.metrics,
            'metadata': self.metadata,
        }

    def summary(self) -> str:
        """
        Generate human-readable summary.

        Returns
        -------
        str
            Formatted summary string
        """
        lines = [
            "=" * 60,
            "BACKTEST RESULTS",
            "=" * 60,
            f"Engine: {self.metadata.get('engine', 'Unknown')}",
            f"Period: {self.metadata.get('start_time', '?')} to {self.metadata.get('end_time', '?')}",
            "-" * 60,
            "Performance Metrics:",
            f"  Total Return:    {self.metrics.get('total_return', 0):.2%}",
            f"  Total PnL:       ${self.metrics.get('total_pnl', 0):,.2f}",
            f"  Sharpe Ratio:    {self.metrics.get('sharpe_ratio', 0):.2f}",
            f"  Sortino Ratio:   {self.metrics.get('sortino_ratio', 0):.2f}",
            f"  Max Drawdown:    {self.metrics.get('max_drawdown', 0):.2%}",
            f"  Win Rate:        {self.metrics.get('win_rate', 0):.2%}",
            f"  Profit Factor:   {self.metrics.get('profit_factor', 0):.2f}",
            "-" * 60,
            "Trading Activity:",
            f"  Total Trades:    {self.metrics.get('total_trades', 0)}",
            f"  Winning Trades:  {self.metrics.get('winning_trades', 0)}",
            f"  Losing Trades:   {self.metrics.get('losing_trades', 0)}",
            "=" * 60,
        ]
        return "\n".join(lines)


class BacktestEngine(ABC):
    """
    Abstract base class for all backtest engines.

    This defines the interface that all engines must implement.
    Engines can be event-driven (backtesting.py), vectorized (VectorBT),
    or custom implementations.

    Design Pattern: Strategy Pattern
    - Defines the interface (contract)
    - Concrete engines implement the algorithm
    - Clients depend only on the abstract interface

    Examples
    --------
    >>> from execution.engines.vectorbt_engine import VectorBTEngine
    >>>
    >>> engine = VectorBTEngine()
    >>> result = engine.run(data, signals, sizes, config)
    >>> print(result.summary())
    """

    @abstractmethod
    def run(
        self,
        data: pd.DataFrame,
        signals: pd.DataFrame,
        sizes: pd.Series,
        config: BacktestConfig,
    ) -> BacktestResult:
        """
        Run backtest with given signals and position sizes.

        This is the main entry point for all engines.

        Parameters
        ----------
        data : pd.DataFrame
            OHLCV data with columns: [open, high, low, close, volume]
            Index: DatetimeIndex (timezone-aware)

        signals : pd.DataFrame
            Entry/exit signals with columns:
            - entry: bool (True = enter position)
            - exit: bool (True = exit position)
            - direction: str ('long' or 'short')
            Index: DatetimeIndex (must match data.index)

        sizes : pd.Series
            Position sizes (fractional, can be > 1 with leverage)
            Index: DatetimeIndex (must match data.index)
            Values: float (e.g., 0.5 = 50% of equity, 2.0 = 200% with leverage)

        config : BacktestConfig
            Backtest configuration (capital, fees, etc.)

        Returns
        -------
        BacktestResult
            Standardized backtest results

        Raises
        ------
        ValueError
            If inputs are invalid (missing columns, mismatched indices, etc.)

        Notes
        -----
        - All DataFrames must have matching DatetimeIndex
        - Signals and sizes are aligned to data bars
        - Position sizes are fractional (0.5 = 50% of equity)
        - Leverage is applied automatically per config

        Examples
        --------
        >>> signals = pd.DataFrame({
        ...     'entry': [False, True, False, False],
        ...     'exit': [False, False, False, True],
        ...     'direction': ['long', 'long', 'long', 'long']
        ... }, index=data.index)
        >>>
        >>> sizes = pd.Series([0, 0.5, 0.5, 0], index=data.index)
        >>>
        >>> result = engine.run(data, signals, sizes, config)
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """
        Return engine name for logging and identification.

        Returns
        -------
        str
            Engine name (e.g., "VectorBT", "Custom")
        """
        pass

    def validate_inputs(
        self,
        data: pd.DataFrame,
        signals: pd.DataFrame,
        sizes: pd.Series,
    ) -> None:
        """
        Validate inputs before running backtest.

        This is a helper method that concrete engines can call
        to validate inputs before processing.

        Parameters
        ----------
        data : pd.DataFrame
            OHLCV data
        signals : pd.DataFrame
            Entry/exit signals
        sizes : pd.Series
            Position sizes

        Raises
        ------
        ValueError
            If any validation fails
        """
        # Check data columns
        required_data_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_data_cols = [col for col in required_data_cols if col not in data.columns]
        if missing_data_cols:
            raise ValueError(f"Data missing required columns: {missing_data_cols}")

        # Check signals columns
        required_signal_cols = ['entry', 'exit', 'direction']
        missing_signal_cols = [col for col in required_signal_cols if col not in signals.columns]
        if missing_signal_cols:
            raise ValueError(f"Signals missing required columns: {missing_signal_cols}")

        # Check index alignment
        if not data.index.equals(signals.index):
            raise ValueError("Data and signals must have matching indices")

        if not data.index.equals(sizes.index):
            raise ValueError("Data and sizes must have matching indices")

        # Check for empty data
        if len(data) == 0:
            raise ValueError("Data is empty")

        # Check for valid sizes
        if sizes.isna().all():
            raise ValueError("All sizes are NaN")

"""
Base strategy class for all TaoQuant strategies.

This module defines the interface that all strategies must implement,
ensuring clean separation of concerns:
1. Indicator computation (pure transformation)
2. Signal generation (pure logic)
3. Position sizing (risk management)

Design Principles:
- Template Method Pattern: defines workflow, subclasses implement steps
- Pure Functions: each step should be deterministic
- No Side Effects: strategies don't manage state or execute trades
- Type-Safe: full type hints for compile-time safety

IMPORTANT: All strategy development must follow CLAUDE.md rules:
- Priority 1: Comply with TaoQuant Architecture (docs/system_design.md)
- Priority 2: Follow CLAUDE.md guidelines
- See CLAUDE.md for complete coding standards and workflow
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class StrategyConfig:
    """
    Base configuration for all strategies.

    All strategy-specific configs should inherit from this.

    Attributes
    ----------
    name : str
        Strategy name (for logging and identification)
    description : str
        Human-readable description
    """

    name: str
    description: str


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.

    This implements the Template Method pattern:
    1. Define the high-level workflow (run method)
    2. Subclasses implement the individual steps
    3. Each step is a pure function transformation

    Workflow:
        Data → compute_indicators() → Data + Indicators
             → generate_signals()   → Signals
             → calculate_position_size() → Sizes

    Design Goals:
    - Separation of concerns (indicators / signals / sizing)
    - Pure functions (testable, composable, debuggable)
    - Engine-agnostic (works with any BacktestEngine)
    - No state management (stateless transformations)

    Examples
    --------
    >>> from strategies.signal_based.sr_short import SRShortStrategy, SRShortConfig
    >>>
    >>> # Create strategy
    >>> config = SRShortConfig(name="SR Short", description="...")
    >>> strategy = SRShortStrategy(config)
    >>>
    >>> # Run workflow
    >>> data_with_indicators, signals, sizes = strategy.run(data, initial_equity=100000)
    >>>
    >>> # Pass to engine
    >>> result = engine.run(data_with_indicators, signals, sizes, backtest_config)
    """

    def __init__(self, config: StrategyConfig):
        """
        Initialize strategy with configuration.

        Parameters
        ----------
        config : StrategyConfig
            Strategy configuration
        """
        self.config = config

    @abstractmethod
    def compute_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all required indicators.

        This is a PURE FUNCTION: same input → same output, no side effects.

        Rules:
        - Do not modify input data (use .copy() or .assign())
        - Add new columns to DataFrame
        - Return enhanced DataFrame with indicator columns
        - No strategy state should be modified

        Parameters
        ----------
        data : pd.DataFrame
            OHLCV data with columns: [open, high, low, close, volume]
            Index: DatetimeIndex (timezone-aware)

        Returns
        -------
        pd.DataFrame
            Original data with added indicator columns

        Examples
        --------
        >>> def compute_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        ...     # Add SMA indicator
        ...     return data.assign(
        ...         sma_20=data['close'].rolling(20).mean(),
        ...         sma_50=data['close'].rolling(50).mean()
        ...     )

        Notes
        -----
        - Use pandas operations (vectorized, fast)
        - Avoid loops where possible
        - Handle NaN values appropriately
        - Document indicator parameters in strategy config
        """
        pass

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate entry/exit signals based on indicators.

        This is a PURE FUNCTION: same input → same output, no side effects.

        Rules:
        - Input data must already have indicators computed
        - Return DataFrame with specific columns (see below)
        - No strategy state should be modified
        - No execution logic (only signal generation)

        Parameters
        ----------
        data : pd.DataFrame
            Data with OHLCV + indicator columns

        Returns
        -------
        pd.DataFrame
            Signal DataFrame with required columns:
            - entry: bool (True = enter position)
            - exit: bool (True = exit position)
            - direction: str ('long' or 'short')

            Optional columns:
            - reason: str (entry/exit reason for logging)
            - confidence: float (signal confidence 0-1)

        Examples
        --------
        >>> def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        ...     # Simple SMA crossover
        ...     entry = (data['sma_20'] > data['sma_50']) & (data['sma_20'].shift(1) <= data['sma_50'].shift(1))
        ...     exit = (data['sma_20'] < data['sma_50']) & (data['sma_20'].shift(1) >= data['sma_50'].shift(1))
        ...
        ...     return pd.DataFrame({
        ...         'entry': entry,
        ...         'exit': exit,
        ...         'direction': 'long'
        ...     }, index=data.index)

        Notes
        -----
        - Use vectorized operations (pandas boolean indexing)
        - Avoid iterating over rows
        - Signal validation happens in SignalGenerator
        - Complex signal logic can be extracted to helper methods
        """
        pass

    @abstractmethod
    def calculate_position_size(
        self,
        data: pd.DataFrame,
        equity: pd.Series,
        base_size: float = 1.0,
    ) -> pd.Series:
        """
        Calculate position sizes based on risk management rules.

        This is a FUNCTION with limited state: depends on current equity.

        Rules:
        - Size should be a fraction of equity (0 < size < leverage)
        - Incorporate risk management (ATR, volatility, etc.)
        - Consider portfolio constraints (max position, concentration, etc.)

        Parameters
        ----------
        data : pd.DataFrame
            Data with OHLCV + indicators + signals
        equity : pd.Series
            Current equity at each bar (from backtest engine)
            Note: In initial run, this is constant (initial_equity)
            In iterative backtest, this is dynamic
        base_size : float
            Base position size multiplier (default: 1.0)

        Returns
        -------
        pd.Series
            Position sizes as fraction of equity
            Index: must match data.index
            Values: float (e.g., 0.5 = 50% of equity, 2.0 = 200% with leverage)

        Examples
        --------
        >>> def calculate_position_size(
        ...     self,
        ...     data: pd.DataFrame,
        ...     equity: pd.Series,
        ...     base_size: float = 1.0
        ... ) -> pd.Series:
        ...     # Fixed 50% of equity per trade
        ...     return pd.Series(0.5, index=data.index)
        >>>
        >>> def calculate_position_size(
        ...     self,
        ...     data: pd.DataFrame,
        ...     equity: pd.Series,
        ...     base_size: float = 1.0
        ... ) -> pd.Series:
        ...     # Risk-based sizing: risk 1% per trade
        ...     risk_per_trade = 0.01
        ...     stop_distance = data['atr'] * 2  # 2 ATR stop
        ...     risk_amount = equity * risk_per_trade
        ...
        ...     # Size = risk_amount / stop_distance
        ...     # Then convert to fraction of equity
        ...     sizes = risk_amount / stop_distance
        ...     sizes = (sizes * data['close']) / equity
        ...
        ...     return sizes.fillna(0)

        Notes
        -----
        - Sizes are in fraction of equity (not absolute quantities)
        - Engine will convert to actual position sizes
        - Consider slippage and commission in sizing
        - Use ATR or volatility for dynamic sizing
        """
        pass

    def run(
        self,
        data: pd.DataFrame,
        initial_equity: float = 100000.0,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
        """
        Run complete strategy workflow (Template Method).

        This method orchestrates the three-step process:
        1. Compute indicators
        2. Generate signals
        3. Calculate position sizes

        Parameters
        ----------
        data : pd.DataFrame
            Raw OHLCV data
        initial_equity : float
            Starting capital (for position sizing)

        Returns
        -------
        tuple[pd.DataFrame, pd.DataFrame, pd.Series]
            (data_with_indicators, signals, sizes)

        Examples
        --------
        >>> strategy = SRShortStrategy(config)
        >>> data_with_indicators, signals, sizes = strategy.run(data, initial_equity=100000)
        >>>
        >>> # Now pass to engine
        >>> result = engine.run(data_with_indicators, signals, sizes, backtest_config)
        """
        # Step 1: Compute indicators
        data_with_indicators = self.compute_indicators(data)

        # Step 2: Generate signals
        signals = self.generate_signals(data_with_indicators)

        # Step 3: Calculate position sizes
        # Note: For now, we use constant equity. In future, this will be dynamic.
        equity = pd.Series(initial_equity, index=data_with_indicators.index)
        sizes = self.calculate_position_size(data_with_indicators, equity)

        return data_with_indicators, signals, sizes

    def validate_data(self, data: pd.DataFrame) -> None:
        """
        Validate input data format.

        Parameters
        ----------
        data : pd.DataFrame
            Input data to validate

        Raises
        ------
        ValueError
            If data is invalid
        """
        # Check required columns
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            raise ValueError(
                f"Data missing required columns: {missing_cols}. "
                f"Expected: {required_cols}"
            )

        # Check index is DatetimeIndex
        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("Data index must be DatetimeIndex")

        # Check for empty data
        if len(data) == 0:
            raise ValueError("Data is empty")

        # Check for NaN in OHLCV
        ohlcv_cols = ['open', 'high', 'low', 'close', 'volume']
        if data[ohlcv_cols].isna().any().any():
            raise ValueError("Data contains NaN values in OHLCV columns")

    def get_name(self) -> str:
        """Get strategy name."""
        return self.config.name

    def get_description(self) -> str:
        """Get strategy description."""
        return self.config.description

    def __repr__(self) -> str:
        """String representation."""
        return f"{self.__class__.__name__}(name='{self.config.name}')"

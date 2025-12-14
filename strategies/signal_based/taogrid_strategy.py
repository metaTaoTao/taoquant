"""
TaoGrid Strategy - Active Grid Trading with Manual Regime Input.

This strategy implements a professional grid trading system that combines:
1. Manual S/R (Support/Resistance) input by traders
2. Manual Regime input (UP_RANGE/NEUTRAL_RANGE/DOWN_RANGE)
3. ATR-based dynamic spacing
4. Level-wise asymmetric position weighting
5. Regime-based side allocation (70/30, 50/50, 30/70)

Core Philosophy:
    TaoGrid = Trader Judgment + Algorithmic Execution
    NOT a black-box automated system

Design Principles (from CLAUDE.md):
1. Comply with TaoQuant Architecture
2. Inherit from BaseStrategy
3. Pure functions for indicators
4. Standard signal format: {entry, exit, direction, reason}
5. No state management in strategy

Implementation Status:
    Sprint 1 (MVP): ✅ Static grid + manual inputs
    Sprint 2 (Current): 🔄 DGT (mid shift) + throttling + inventory tracking
    Sprint 3 (Future): Auto regime detection (optional)

References:
    - Strategy Doc: docs/TaoGrid 网格策略.pdf
    - Implementation Plan: docs/strategies/taogrid_implementation_plan_v2.md
    - Architecture: CLAUDE.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from strategies.base_strategy import BaseStrategy, StrategyConfig

# Type definitions
RegimeType = Literal["UP_RANGE", "NEUTRAL_RANGE", "DOWN_RANGE"]


@dataclass
class TaoGridConfig(StrategyConfig):
    """
    TaoGrid Strategy Configuration (MVP version).

    This config implements the manual input mode emphasized in strategy docs:
    - Trader manually specifies S/R levels
    - Trader manually specifies Regime
    - Algorithm handles execution

    Attributes
    ----------
    name : str
        Strategy name
    description : str
        Strategy description

    Manual Inputs (Core - Trader specifies):
    support : float
        Support level (lower bound of grid range)
        Example: 95000.0 for BTC
    resistance : float
        Resistance level (upper bound of grid range)
        Example: 105000.0 for BTC
    regime : RegimeType
        Market regime (trader's judgment)
        Options: "UP_RANGE", "NEUTRAL_RANGE", "DOWN_RANGE"

    Grid Parameters:
    spacing_multiplier : float
        ATR multiplier for grid spacing (default: 1.0)
    cushion_multiplier : float
        Volatility cushion multiplier (default: 0.8)
        Used for: support_eff = support - cushion × ATR
    min_return : float
        Minimum return per grid (default: 0.005 = 0.5%)
    maker_fee : float
        Maker fee rate (default: 0.001 = 0.1%)
    volatility_k : float
        Volatility safety factor (default: 0.6, range: 0.4-1.0)
    grid_layers_buy : int
        Number of buy grid layers (default: 5)
    grid_layers_sell : int
        Number of sell grid layers (default: 5)
    weight_k : float
        Linear weight coefficient (default: 0.5)
        For formula: raw_w(i) = 1 + k × (i - 1)

    Risk Parameters:
    risk_budget_pct : float
        Total risk budget as fraction of capital (default: 0.3 = 30%)
    max_long_units : float
        Maximum long exposure in units (default: 10.0)
    max_short_units : float
        Maximum short exposure in units (default: 10.0)
    daily_loss_limit : float
        Daily loss limit in absolute amount (default: 2000.0)

    DGT Parameters (disabled in MVP):
    enable_mid_shift : bool
        Whether to enable mid-shift (default: False in MVP)
    mid_shift_threshold : int
        Number of bars to trigger mid-shift (default: 20)

    ATR Parameters:
    atr_period : int
        ATR calculation period (default: 14)

    Examples
    --------
    >>> # Manual input mode (default)
    >>> config = TaoGridConfig(
    ...     name="TaoGrid BTC",
    ...     description="Manual grid for BTC 95k-105k range",
    ...     support=95000.0,  # Trader specifies
    ...     resistance=105000.0,  # Trader specifies
    ...     regime="NEUTRAL_RANGE",  # Trader specifies
    ...     grid_layers_buy=5,
    ...     grid_layers_sell=5,
    ... )
    >>>
    >>> # UP_RANGE configuration
    >>> config_up = TaoGridConfig(
    ...     name="TaoGrid BTC Up",
    ...     description="Bullish range grid",
    ...     support=95000.0,
    ...     resistance=105000.0,
    ...     regime="UP_RANGE",  # Favors long side (70/30)
    ... )

    Notes
    -----
    - S/R levels should be based on trader's technical analysis
    - Regime should reflect trader's market view
    - Grid spacing is automatically calculated based on ATR
    - Position weights are automatically allocated based on regime
    """

    # === Manual Inputs (Core) ===
    support: float
    resistance: float
    regime: RegimeType

    # === Grid Parameters ===
    spacing_multiplier: float = 1.0
    cushion_multiplier: float = 0.8
    min_return: float = 0.005  # 0.5%
    maker_fee: float = 0.001  # 0.1%
    volatility_k: float = 0.6

    grid_layers_buy: int = 5
    grid_layers_sell: int = 5
    weight_k: float = 0.5

    # === Risk Parameters ===
    risk_budget_pct: float = 0.3  # 30%
    max_long_units: float = 10.0
    max_short_units: float = 10.0
    daily_loss_limit: float = 2000.0

    # === Throttling Parameters (Sprint 2) ===
    enable_throttling: bool = False  # Sprint 2: Set to True to enable
    inventory_threshold: float = 0.9  # Throttle at 90% of max inventory
    profit_target_pct: float = 0.5  # Daily profit target (50% of risk budget)
    profit_reduction: float = 0.5  # Reduce size to 50% when profit target reached
    volatility_threshold: float = 2.0  # Throttle when ATR > 2x average
    volatility_reduction: float = 0.5  # Reduce size to 50% during volatility spike

    # === DGT Parameters (Sprint 2) ===
    enable_mid_shift: bool = False  # Sprint 2: Set to True to enable DGT
    mid_shift_threshold: int = 20

    # === ATR Parameters ===
    atr_period: int = 14

    def __post_init__(self):
        """
        Validate configuration after initialization.

        Raises
        ------
        ValueError
            If configuration is invalid
        """
        # Validate S/R relationship
        if self.support >= self.resistance:
            raise ValueError(
                f"Support ({self.support}) must be less than Resistance ({self.resistance})"
            )

        # Validate regime
        valid_regimes = ["UP_RANGE", "NEUTRAL_RANGE", "DOWN_RANGE"]
        if self.regime not in valid_regimes:
            raise ValueError(
                f"Invalid regime: {self.regime}. Must be one of {valid_regimes}"
            )

        # Validate risk budget
        if not (0 < self.risk_budget_pct < 1):
            raise ValueError(
                f"risk_budget_pct ({self.risk_budget_pct}) must be in (0, 1)"
            )

        # Validate grid layers
        if self.grid_layers_buy < 1:
            raise ValueError("grid_layers_buy must be >= 1")
        if self.grid_layers_sell < 1:
            raise ValueError("grid_layers_sell must be >= 1")

        # Validate multipliers
        if self.spacing_multiplier <= 0:
            raise ValueError("spacing_multiplier must be > 0")
        if self.cushion_multiplier < 0:
            raise ValueError("cushion_multiplier must be >= 0")

        # Validate fees and returns
        if self.min_return < 0:
            raise ValueError("min_return must be >= 0")
        if self.maker_fee < 0:
            raise ValueError("maker_fee must be >= 0")

    def get_mid_price(self) -> float:
        """
        Calculate mid price from S/R levels.

        Returns
        -------
        float
            Mid price: (support + resistance) / 2

        Notes
        -----
        In MVP, mid is static (calculated from S/R).
        In Sprint 2 (DGT), mid can shift dynamically.
        """
        return (self.support + self.resistance) / 2

    def get_side_allocation(self) -> dict[str, float]:
        """
        Get buy/sell side allocation based on regime.

        Returns
        -------
        dict[str, float]
            Dictionary with 'buy_pct' and 'sell_pct' keys

        Examples
        --------
        >>> config = TaoGridConfig(..., regime="UP_RANGE")
        >>> config.get_side_allocation()
        {'buy_pct': 0.7, 'sell_pct': 0.3}
        >>>
        >>> config.regime = "NEUTRAL_RANGE"
        >>> config.get_side_allocation()
        {'buy_pct': 0.5, 'sell_pct': 0.5}

        Notes
        -----
        Allocation logic from strategy doc Section 5.1.3:
        - UP_RANGE: buy 70%, sell 30% (favor long)
        - NEUTRAL_RANGE: buy 50%, sell 50% (neutral)
        - DOWN_RANGE: buy 30%, sell 70% (favor short)
        """
        if self.regime == "UP_RANGE":
            return {"buy_pct": 0.7, "sell_pct": 0.3}
        elif self.regime == "NEUTRAL_RANGE":
            return {"buy_pct": 0.5, "sell_pct": 0.5}
        else:  # DOWN_RANGE
            return {"buy_pct": 0.3, "sell_pct": 0.7}

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"{self.__class__.__name__}("
            f"name='{self.name}', "
            f"regime='{self.regime}', "
            f"S={self.support:.2f}, "
            f"R={self.resistance:.2f}, "
            f"mid={self.get_mid_price():.2f})"
        )


class TaoGridStrategy(BaseStrategy):
    """
    TaoGrid Strategy (MVP version - Sprint 1).

    Implements active grid trading with manual S/R and Regime inputs.

    Features (Sprint 1):
    - Manual S/R input by trader
    - Manual Regime input by trader
    - Static grid (no mid-shift)
    - ATR-based spacing
    - Level-wise weighting (edge-heavy, mid-light)
    - Regime-based side allocation (70/30, 50/50, 30/70)

    Future (Sprint 2+):
    - Dynamic mid-shift (DGT)
    - Throttling rules (inventory, profit lock, volatility)
    - Auto regime detection (optional)

    Design Notes:
    - Adapts grid logic to BaseStrategy interface
    - Returns standard signals: {entry, exit, direction, reason}
    - Grid-specific logic (levels, weights) computed in indicators
    - Simplified signal generation for MVP (price crosses grid levels)

    Examples
    --------
    >>> from data import DataManager
    >>> from execution.engines.vectorbt_engine import VectorBTEngine
    >>>
    >>> # Configure strategy
    >>> config = TaoGridConfig(
    ...     name="TaoGrid BTC",
    ...     description="Manual grid 95k-105k",
    ...     support=95000.0,
    ...     resistance=105000.0,
    ...     regime="NEUTRAL_RANGE",
    ...     grid_layers_buy=5,
    ...     grid_layers_sell=5
    ... )
    >>>
    >>> # Create strategy
    >>> strategy = TaoGridStrategy(config)
    >>>
    >>> # Run backtest
    >>> data_manager = DataManager()
    >>> data = data_manager.get_klines("BTCUSDT", "15m", ...)
    >>> data_with_indicators, signals, sizes = strategy.run(data, initial_equity=100000)
    >>>
    >>> # Pass to engine
    >>> engine = VectorBTEngine()
    >>> result = engine.run(data_with_indicators, signals, sizes, backtest_config)
    """

    def __init__(self, config: TaoGridConfig):
        """
        Initialize TaoGrid strategy.

        Parameters
        ----------
        config : TaoGridConfig
            Strategy configuration
        """
        super().__init__(config)
        self.config: TaoGridConfig = config  # Type hint for IDE

        # Sprint 2: Initialize inventory tracker and risk manager
        if config.enable_throttling:
            from risk_management.grid_inventory import GridInventoryTracker
            from risk_management.grid_risk_manager import GridRiskManager

            self.inventory_tracker = GridInventoryTracker(
                max_long_units=config.max_long_units,
                max_short_units=config.max_short_units,
            )

            self.risk_manager = GridRiskManager(
                max_long_units=config.max_long_units,
                max_short_units=config.max_short_units,
                inventory_threshold=config.inventory_threshold,
                profit_target_pct=config.profit_target_pct,
                profit_reduction=config.profit_reduction,
                volatility_threshold=config.volatility_threshold,
                volatility_reduction=config.volatility_reduction,
            )
        else:
            self.inventory_tracker = None
            self.risk_manager = None

    def compute_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Compute grid-related indicators.

        Returns data with additional columns:
        - atr: ATR indicator
        - grid_spacing_pct: Grid spacing percentage
        - grid_mid: Mid price (static in MVP, dynamic in Sprint 2)
        - cushion: Volatility cushion
        - grid_buy_1, grid_buy_2, ...: Buy level prices
        - grid_sell_1, grid_sell_2, ...: Sell level prices

        Parameters
        ----------
        data : pd.DataFrame
            OHLCV data

        Returns
        -------
        pd.DataFrame
            Data with grid indicators

        Notes
        -----
        - All grid levels are calculated upfront
        - In MVP, grid is static (constant levels)
        - In Sprint 2, grid can shift dynamically (DGT)
        """
        from analytics.indicators.grid_generator import (
            calculate_effective_mid,
            calculate_grid_spacing,
            generate_grid_levels,
        )
        from analytics.indicators.volatility import calculate_atr

        # Calculate ATR
        atr = calculate_atr(
            data["high"],
            data["low"],
            data["close"],
            period=self.config.atr_period,
        )

        # Calculate grid spacing (ATR-based)
        spacing_pct_base = calculate_grid_spacing(
            atr=atr,
            min_return=self.config.min_return,
            maker_fee=self.config.maker_fee,
            volatility_k=self.config.volatility_k,
        )

        # Apply spacing multiplier (allows trader to scale spacing)
        spacing_pct = spacing_pct_base * self.config.spacing_multiplier

        # Calculate mid price (static in MVP, dynamic in Sprint 2)
        mid = calculate_effective_mid(
            data=data,
            static_mid=self.config.get_mid_price(),
            support=self.config.support,
            resistance=self.config.resistance,
            enable_mid_shift=self.config.enable_mid_shift,
            mid_shift_threshold=self.config.mid_shift_threshold,
        )

        # Calculate volatility cushion
        cushion = atr * self.config.cushion_multiplier

        # Sprint 2: Add throttling indicators
        atr_sma = atr.rolling(window=20, min_periods=1).mean() if self.config.enable_throttling else atr

        # Add indicators to data
        data_with_indicators = data.assign(
            atr=atr,
            atr_sma=atr_sma,
            grid_spacing_pct=spacing_pct,
            grid_mid=mid,
            cushion=cushion
        )

        # Generate grid levels (use last bar for simplicity in MVP)
        # In production, this could be done per bar for dynamic grids
        last_idx = data_with_indicators.index[-1]
        last_mid = mid.iloc[-1]
        last_spacing = spacing_pct.iloc[-1]
        last_cushion = cushion.iloc[-1]

        grid = generate_grid_levels(
            mid_price=last_mid,
            support=self.config.support,
            resistance=self.config.resistance,
            cushion=last_cushion,
            spacing_pct=last_spacing,
            layers_buy=self.config.grid_layers_buy,
            layers_sell=self.config.grid_layers_sell,
        )

        # Add grid levels as columns (for debugging and visualization)
        # Need to create a dict for assign() or use copy + assignment
        grid_level_cols = {}
        for i, price in enumerate(grid["buy_levels"], 1):
            grid_level_cols[f"grid_buy_{i}"] = price

        for i, price in enumerate(grid["sell_levels"], 1):
            grid_level_cols[f"grid_sell_{i}"] = price

        # Add all grid level columns at once
        data_with_indicators = data_with_indicators.assign(**grid_level_cols)

        return data_with_indicators

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate grid entry/exit signals.

        Logic (simplified for MVP):
        1. Entry when price crosses ANY buy level (from above to below)
        2. Exit when price crosses ANY sell level (from below to above)

        Note: This is a SIMPLIFIED adaptation for VectorBT compatibility.
        Full grid logic (order pairing, inventory tracking) would require
        a custom engine or more complex signal logic.

        For Sprint 1 (MVP), we focus on:
        - Validating core grid generation logic
        - Testing ATR-based spacing
        - Testing regime-based allocation

        Parameters
        ----------
        data : pd.DataFrame
            Data with grid indicators

        Returns
        -------
        pd.DataFrame
            Standard signal DataFrame: {entry, exit, direction, reason}

        Notes
        -----
        - This is a simplified signal generation for MVP
        - In production, need to track:
          * Which level was triggered
          * Order pairing (buy ↔ sell)
          * Inventory limits
          * Throttling rules
        - For now, treat each cross as independent entry/exit
        """
        from analytics.indicators.grid_generator import generate_grid_levels

        # Get latest grid parameters
        last_idx = data.index[-1]
        mid = data.loc[last_idx, "grid_mid"]
        spacing_pct = data.loc[last_idx, "grid_spacing_pct"]
        cushion = data.loc[last_idx, "cushion"]

        # Generate grid levels
        grid = generate_grid_levels(
            mid_price=mid,
            support=self.config.support,
            resistance=self.config.resistance,
            cushion=cushion,
            spacing_pct=spacing_pct,
            layers_buy=self.config.grid_layers_buy,
            layers_sell=self.config.grid_layers_sell,
        )

        # Initialize signals
        entry = pd.Series(False, index=data.index)
        exit_signal = pd.Series(False, index=data.index)
        direction = pd.Series("long", index=data.index)  # MVP: long-only
        reason = pd.Series("", index=data.index)

        # MVP Simplification: Long-only grid strategy
        # - Entry: price crosses buy levels (downward)
        # - Exit: price crosses sell levels (upward)
        # - This validates core logic without requiring mixed long/short support
        #
        # Note: Full grid (simultaneous long/short) requires:
        #   - Custom engine OR
        #   - Separate long/short portfolio tracking

        # Generate signals by checking price crosses
        for i in range(1, len(data)):
            close_prev = data["close"].iloc[i - 1]
            close_curr = data["close"].iloc[i]

            # Entry: crossed any buy level (downward cross)
            for j, buy_level in enumerate(grid["buy_levels"], 1):
                if close_prev > buy_level and close_curr <= buy_level:
                    entry.iloc[i] = True
                    direction.iloc[i] = "long"
                    reason.iloc[i] = f"grid_buy_L{j}"
                    break  # Only one entry per bar

            # Exit: crossed any sell level (upward cross)
            for j, sell_level in enumerate(grid["sell_levels"], 1):
                if close_prev < sell_level and close_curr >= sell_level:
                    # MVP: treat as exit from long position
                    # Full grid: would simultaneously hold short
                    exit_signal.iloc[i] = True
                    reason.iloc[i] = f"grid_sell_L{j}"
                    break

        return pd.DataFrame(
            {
                "entry": entry,
                "exit": exit_signal,
                "direction": direction,
                "reason": reason,
            },
            index=data.index,
        )

    def calculate_position_size(
        self, data: pd.DataFrame, equity: pd.Series, base_size: float = 1.0
    ) -> pd.Series:
        """
        Calculate grid-based position sizes.

        Logic:
        1. Total budget = equity × risk_budget_pct
        2. Allocate to buy/sell sides based on regime
        3. Calculate size per layer based on weights
        4. Return average size (simplified for MVP)

        Parameters
        ----------
        data : pd.DataFrame
            Data with grid indicators
        equity : pd.Series
            Current equity series
        base_size : float, optional
            Base size multiplier, by default 1.0

        Returns
        -------
        pd.Series
            Position size series (fraction of equity)

        Notes
        -----
        - In MVP, we use a simplified approach: average layer size
        - In production, size should vary by layer (edge-heavy)
        - In production, need to track inventory and apply throttling
        """
        from analytics.indicators.grid_generator import generate_grid_levels
        from analytics.indicators.grid_weights import calculate_grid_position_sizes

        # Calculate total risk budget
        total_budget = equity * self.config.risk_budget_pct

        # Get latest grid parameters
        last_idx = data.index[-1]
        mid = data.loc[last_idx, "grid_mid"]
        spacing_pct = data.loc[last_idx, "grid_spacing_pct"]
        cushion = data.loc[last_idx, "cushion"]

        # Generate grid levels
        grid = generate_grid_levels(
            mid_price=mid,
            support=self.config.support,
            resistance=self.config.resistance,
            cushion=cushion,
            spacing_pct=spacing_pct,
            layers_buy=self.config.grid_layers_buy,
            layers_sell=self.config.grid_layers_sell,
        )

        # Calculate position sizes for all layers
        sizes_dict = calculate_grid_position_sizes(
            total_budget=total_budget.iloc[-1],
            regime=self.config.regime,
            buy_levels=grid["buy_levels"],
            sell_levels=grid["sell_levels"],
            weight_k=self.config.weight_k,
        )

        # Use average buy size (simplified for MVP)
        # In production, size should match the specific layer triggered
        buy_sizes = sizes_dict["buy_sizes"]

        # Check if buy_sizes is empty
        if len(buy_sizes) == 0:
            # No grid levels generated - return zero sizes
            return pd.Series(0.0, index=data.index)

        avg_buy_size_coins = buy_sizes.mean()

        # Convert to fraction of equity
        # size_fraction = (coins × price) / equity
        current_price = data["close"].iloc[-1]
        size_fraction = (avg_buy_size_coins * current_price) / equity.iloc[-1]

        # Apply base_size multiplier
        size_fraction = size_fraction * base_size

        # Ensure size_fraction is valid
        if pd.isna(size_fraction) or size_fraction <= 0:
            return pd.Series(0.0, index=data.index)

        # Return constant size for all bars (simplified)
        return pd.Series(size_fraction, index=data.index)

    def get_grid_info(self) -> dict:
        """
        Get grid configuration information.

        Returns
        -------
        dict
            Grid configuration details

        Examples
        --------
        >>> strategy = TaoGridStrategy(config)
        >>> info = strategy.get_grid_info()
        >>> print(info)
        {
            'support': 95000.0,
            'resistance': 105000.0,
            'mid': 100000.0,
            'regime': 'NEUTRAL_RANGE',
            'side_allocation': {'buy_pct': 0.5, 'sell_pct': 0.5},
            'layers_buy': 5,
            'layers_sell': 5,
            'risk_budget_pct': 0.3
        }
        """
        info = {
            "support": self.config.support,
            "resistance": self.config.resistance,
            "mid": self.config.get_mid_price(),
            "regime": self.config.regime,
            "side_allocation": self.config.get_side_allocation(),
            "layers_buy": self.config.grid_layers_buy,
            "layers_sell": self.config.grid_layers_sell,
            "risk_budget_pct": self.config.risk_budget_pct,
            "enable_mid_shift": self.config.enable_mid_shift,
        }

        # Sprint 2: Add throttling info
        if self.config.enable_throttling:
            info.update({
                "enable_throttling": True,
                "inventory_threshold": self.config.inventory_threshold,
                "profit_target_pct": self.config.profit_target_pct,
                "volatility_threshold": self.config.volatility_threshold,
            })
        else:
            info["enable_throttling"] = False

        return info

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"{self.__class__.__name__}("
            f"name='{self.config.name}', "
            f"regime='{self.config.regime}', "
            f"S={self.config.support:.0f}, "
            f"R={self.config.resistance:.0f})"
        )

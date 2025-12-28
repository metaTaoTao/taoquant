"""
Neutral Grid Configuration.

Standard exchange-style neutral grid trading bot configuration.
This config is designed to 100% replicate Binance/OKX neutral grid behavior.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class NeutralGridConfig:
    """
    Configuration for neutral grid trading.

    A neutral grid places buy orders below current price and sell orders above,
    profiting from price oscillations within a defined range.

    Parameters
    ----------
    lower_price : float
        Lower bound of grid range (all grids will be >= this price)
    upper_price : float
        Upper bound of grid range (all grids will be <= this price)
    grid_count : int
        Number of grid levels (total grids = grid_count + 1 price points)
        Example: grid_count=10 creates 11 price points with 10 intervals
    mode : Literal["geometric", "arithmetic"]
        Grid spacing mode:
        - "geometric" (等比): price[i] = lower * (upper/lower)^(i/N)
          Better for volatile markets, maintains percentage spacing
        - "arithmetic" (等差): price[i] = lower + i * (upper - lower) / N
          Better for ranging markets, maintains fixed price spacing
    total_investment : float
        Total capital to invest in the grid (USD)
        This will be split across all grid levels
    investment_mode : Literal["equal", "neutral"]
        How to distribute investment:
        - "equal": Equal USD amount per grid level
        - "neutral": Adjust for geometric grid to maintain equal position sizes
    initial_position_pct : float
        Percentage of grids to fill as initial position (0.0 - 1.0)
        Example: 0.5 = fill 50% of grids at current price
        Set to 0.0 for "start from scratch" mode
    leverage : float
        Leverage multiplier (1.0 = no leverage)
    maker_fee : float
        Maker fee rate (e.g., 0.0002 for 0.02%)
    min_order_size_usd : float
        Minimum order size in USD (exchange requirement)
    enable_console_log : bool
        Enable detailed console logging

    Example (Geometric Grid, 等比网格)
    ---------------------------------
    >>> config = NeutralGridConfig(
    ...     lower_price=90000.0,
    ...     upper_price=110000.0,
    ...     grid_count=20,
    ...     mode="geometric",
    ...     total_investment=10000.0,
    ...     initial_position_pct=0.5,
    ... )
    >>> # This creates 21 price points from 90k to 110k with geometric spacing
    >>> # Invests $10k total, fills 50% of grids at current price

    Example (Arithmetic Grid, 等差网格)
    ----------------------------------
    >>> config = NeutralGridConfig(
    ...     lower_price=90000.0,
    ...     upper_price=110000.0,
    ...     grid_count=20,
    ...     mode="arithmetic",
    ...     total_investment=10000.0,
    ...     initial_position_pct=0.5,
    ... )
    >>> # This creates 21 price points with fixed $1000 spacing
    """

    # Grid range
    lower_price: float
    upper_price: float
    grid_count: int

    # Grid mode
    mode: Literal["geometric", "arithmetic"] = "geometric"

    # Investment
    total_investment: float = 10000.0
    investment_mode: Literal["equal", "neutral"] = "equal"
    initial_position_pct: float = 0.5  # 50% initial position

    # Risk parameters
    leverage: float = 1.0
    maker_fee: float = 0.0002  # 0.02%

    # Exchange constraints
    min_order_size_usd: float = 5.0  # Minimum order size

    # Logging
    enable_console_log: bool = True

    def __post_init__(self):
        """Validate configuration."""
        # Price range validation
        if self.lower_price <= 0:
            raise ValueError("lower_price must be > 0")
        if self.upper_price <= self.lower_price:
            raise ValueError("upper_price must be > lower_price")

        # Grid count validation
        if self.grid_count < 2:
            raise ValueError("grid_count must be >= 2 (creates at least 3 price points)")
        if self.grid_count > 200:
            raise ValueError("grid_count must be <= 200 (too many grids)")

        # Investment validation
        if self.total_investment <= 0:
            raise ValueError("total_investment must be > 0")
        if not (0.0 <= self.initial_position_pct <= 1.0):
            raise ValueError("initial_position_pct must be in [0.0, 1.0]")

        # Risk validation
        if self.leverage < 1.0 or self.leverage > 100.0:
            raise ValueError("leverage must be in [1.0, 100.0]")
        if self.maker_fee < 0:
            raise ValueError("maker_fee must be >= 0")

        # Order size validation
        if self.min_order_size_usd <= 0:
            raise ValueError("min_order_size_usd must be > 0")

        # Mode validation
        if self.mode not in ["geometric", "arithmetic"]:
            raise ValueError("mode must be 'geometric' or 'arithmetic'")
        if self.investment_mode not in ["equal", "neutral"]:
            raise ValueError("investment_mode must be 'equal' or 'neutral'")

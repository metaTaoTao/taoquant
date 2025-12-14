"""
TaoGrid Lean Algorithm Configuration.

This module defines configuration for the Lean implementation of TaoGrid strategy.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class TaoGridLeanConfig:
    """
    Configuration for TaoGrid Lean algorithm.

    This config mirrors TaoGridConfig from the VectorBT version but adapted for Lean.
    """

    # === Basic Info ===
    name: str = "TaoGrid Lean"
    description: str = "TaoGrid strategy on Lean framework"

    # === Manual Inputs (Required) ===
    support: float = 104000.0
    resistance: float = 126000.0
    regime: Literal["BULLISH_RANGE", "NEUTRAL_RANGE", "BEARISH_RANGE"] = "NEUTRAL_RANGE"

    # === Grid Parameters ===
    grid_layers_buy: int = 5
    grid_layers_sell: int = 5
    weight_k: float = 0.5

    # === ATR-based Spacing ===
    spacing_multiplier: float = 0.1
    cushion_multiplier: float = 0.8
    min_return: float = 0.005
    maker_fee: float = 0.001
    volatility_k: float = 0.6
    atr_period: int = 14

    # === Risk Parameters ===
    risk_budget_pct: float = 0.3
    max_long_units: float = 10.0
    max_short_units: float = 10.0
    daily_loss_limit: float = 2000.0

    # === DGT Parameters (Sprint 2) ===
    enable_mid_shift: bool = False
    mid_shift_threshold: int = 20

    # === Throttling Parameters (Sprint 2) ===
    enable_throttling: bool = True
    inventory_threshold: float = 0.9
    profit_target_pct: float = 0.5
    profit_reduction: float = 0.5
    volatility_threshold: float = 2.0
    volatility_reduction: float = 0.5

    # === Backtest Parameters ===
    initial_cash: float = 100000.0
    leverage: float = 1.0

    def __post_init__(self):
        """Validate configuration."""
        # Basic validations
        if self.support >= self.resistance:
            raise ValueError("support must be < resistance")
        if not (1 <= self.grid_layers_buy <= 20):
            raise ValueError("grid_layers_buy must be in [1, 20]")
        if not (1 <= self.grid_layers_sell <= 20):
            raise ValueError("grid_layers_sell must be in [1, 20]")
        if self.regime not in ["BULLISH_RANGE", "NEUTRAL_RANGE", "BEARISH_RANGE"]:
            raise ValueError("Invalid regime")

        # Critical: spacing_multiplier validation
        # Values < 1.0 will reduce grid spacing below cost coverage and cause losses
        if self.spacing_multiplier < 1.0:
            raise ValueError(
                f"spacing_multiplier must be >= 1.0 (got {self.spacing_multiplier}). "
                f"Values < 1.0 violate cost coverage and will cause systematic losses! "
                f"The formula calculate_grid_spacing() already ensures min_return + costs. "
                f"spacing_multiplier should only EXPAND spacing (>=1.0), never reduce it."
            )

        # Warning for extreme values
        if self.spacing_multiplier > 5.0:
            import warnings
            warnings.warn(
                f"spacing_multiplier = {self.spacing_multiplier} is very large. "
                f"This will create very sparse grids and reduce turnover significantly."
            )

        # min_return validation
        if self.min_return <= 0:
            raise ValueError(f"min_return must be > 0 (got {self.min_return})")

        # Ensure min_return can cover trading costs
        trading_costs = 2 * self.maker_fee  # For limit orders, slippage should be 0
        if self.min_return < trading_costs:
            import warnings
            warnings.warn(
                f"min_return ({self.min_return:.2%}) < trading_costs ({trading_costs:.2%}). "
                f"This may result in negative net profit per trade!"
            )

        # Other parameter validations
        if self.maker_fee < 0:
            raise ValueError("maker_fee cannot be negative")
        if self.volatility_k < 0 or self.volatility_k > 2.0:
            raise ValueError("volatility_k should be in [0, 2.0]")
        if self.risk_budget_pct <= 0 or self.risk_budget_pct > 1.0:
            raise ValueError("risk_budget_pct must be in (0, 1.0]")
        if self.leverage < 1.0 or self.leverage > 10.0:
            raise ValueError("leverage must be in [1.0, 10.0]")

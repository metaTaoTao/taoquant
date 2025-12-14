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
    spacing_multiplier: float = 1.0
    cushion_multiplier: float = 0.8
    min_return: float = 0.005
    maker_fee: float = 0.0002  # 0.02% per side (perpetual contracts)
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
    # Inventory management (market-making style)
    # inventory_capacity_threshold_pct is measured against max notional capacity (equity * leverage).
    # Example: leverage=5x and threshold_pct=0.9 -> block new BUY when notional/equity >= 4.5.
    inventory_capacity_threshold_pct: float = 0.9
    inventory_skew_k: float = 1.0  # inventory-aware sizing strength (0 = off)
    # Factor filter (Sharpe-oriented): MR strength + trend state
    enable_mr_trend_factor: bool = True
    mr_z_lookback: int = 240  # bars
    mr_z_ref: float = 2.0  # |z| at which MR multiplier reaches 1.0
    mr_min_mult: float = 1.00  # default: do not downscale buys; keep MR for diagnostics/tuning
    trend_ema_period: int = 120  # bars
    trend_slope_lookback: int = 60  # bars
    trend_slope_ref: float = 0.001  # 0.1% move over lookback -> tanh ~0.76
    trend_block_threshold: float = 0.80  # if trend_score <= -threshold -> block BUY
    trend_buy_k: float = 0.40  # buy reduction strength vs -trend_score (mild by default)
    trend_buy_floor: float = 0.50  # floor for trend multiplier

    # Breakout risk factor (range boundary risk-off)
    enable_breakout_risk_factor: bool = True
    breakout_band_atr_mult: float = 1.5
    breakout_band_pct: float = 0.003
    breakout_trend_weight: float = 0.7
    breakout_buy_k: float = 0.6  # buy reduction strength as risk increases
    breakout_buy_floor: float = 0.4  # floor multiplier in risk band (keeps churn)
    breakout_block_threshold: float = 0.95  # block BUY if risk>=threshold

    # Funding factor (perp cost control)
    # Long-only inventory grid: positive funding => longs pay => de-risk (reduce BUY / boost SELL).
    enable_funding_factor: bool = True
    # Mode control: per user preference, we can enable funding only on SELL side (preferred),
    # because applying funding to BUY often kills churn and hurts Sharpe.
    funding_apply_to_buy: bool = False
    funding_apply_to_sell: bool = True
    # Time gate: only apply funding adjustments around settlement windows (avoid reducing churn).
    enable_funding_time_gate: bool = True
    funding_gate_minutes: int = 60  # apply in +/- window around fundingTime
    funding_ref: float = 0.0001  # normalization reference (0.01% per period)
    funding_block_threshold: float = 0.0005  # block BUY if funding >= threshold
    funding_buy_k: float = 1.0  # buy reduction strength as funding rises
    funding_buy_floor: float = 0.4  # floor buy multiplier under funding risk
    funding_sell_k: float = 1.0  # sell boost strength as funding rises
    funding_sell_cap: float = 2.0  # cap sell multiplier

    # Range position asymmetry (v2): ONLY active near boundaries (avoid killing churn).
    # Focus on TOP band because this strategy is long-inventory: near top we want
    # fewer new buys and more aggressive selling (de-inventory).
    enable_range_pos_asymmetry_v2: bool = False
    range_top_band_start: float = 0.85
    range_buy_k: float = 0.8
    range_buy_floor: float = 0.4
    range_sell_k: float = 1.0
    range_sell_cap: float = 2.5

    # Volatility regime factor (ATR% quantile score)
    enable_vol_regime_factor: bool = True
    vol_lookback: int = 1440  # 1 day of 1m bars
    vol_low_q: float = 0.20
    vol_high_q: float = 0.80
    # v2: only act in extreme high-vol conditions, and prefer SELL-only adjustments
    vol_trigger_score: float = 0.98  # apply only when vol_score >= trigger (near extreme)
    vol_apply_to_buy: bool = False
    vol_apply_to_sell: bool = True
    vol_sell_mult_high: float = 1.15  # scale SELL size in extreme high-vol
    profit_target_pct: float = 0.5
    profit_reduction: float = 0.5
    volatility_threshold: float = 2.0
    volatility_reduction: float = 0.5

    # === Market Maker Risk Zone (MM Risk Mode) ===
    # When price breaks below support + volatility buffer, enter risk mode:
    # - Reduce BUY size significantly (small positions to catch falling knife)
    # - Increase SELL size aggressively (de-inventory, sell most holdings)
    # - This mimics market maker behavior: widen spread, reduce inventory risk
    enable_mm_risk_zone: bool = True
    # Risk zone threshold: support + cushion (volatility buffer)
    # When price < risk_zone_threshold, enter risk mode
    mm_risk_buy_multiplier: float = 0.2  # Reduce BUY to 20% of normal size in risk zone
    mm_risk_sell_multiplier: float = 3.0  # Increase SELL to 300% of normal size in risk zone
    # Optional: further reduce BUY if inventory is already high in risk zone
    mm_risk_inventory_penalty: float = 0.5  # Additional reduction if inv_ratio > 0.5

    # === Backtest Parameters ===
    initial_cash: float = 100000.0
    leverage: float = 1.0
    sharpe_annualization_days: int = 365  # crypto spot/perp trades 24/7

    def __post_init__(self):
        """Validate configuration."""
        # Basic validations
        if self.support >= self.resistance:
            raise ValueError("support must be < resistance")
        # Grid layer count:
        # For 1m data + low fee environments, we may want denser grids (e.g. 30-100 layers).
        # Keep an upper bound to prevent accidental explosion / unreasonable configs.
        max_layers = 100
        if not (1 <= self.grid_layers_buy <= max_layers):
            raise ValueError(f"grid_layers_buy must be in [1, {max_layers}]")
        if not (1 <= self.grid_layers_sell <= max_layers):
            raise ValueError(f"grid_layers_sell must be in [1, {max_layers}]")
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
        if not (0.0 < self.inventory_capacity_threshold_pct <= 1.0):
            raise ValueError("inventory_capacity_threshold_pct must be in (0, 1.0]")
        if self.inventory_skew_k < 0:
            raise ValueError("inventory_skew_k must be >= 0")
        # Leverage validation:
        # For perp products, higher leverage (e.g., 20-50x) is common, but it can easily
        # produce unrealistic backtest assumptions if liquidation / margin is not modeled.
        # We allow a wider range and rely on max drawdown / inventory constraints to bound risk.
        max_leverage = 100.0
        if self.leverage < 1.0 or self.leverage > max_leverage:
            raise ValueError(f"leverage must be in [1.0, {max_leverage}]")

        if self.sharpe_annualization_days not in (252, 365):
            raise ValueError("sharpe_annualization_days must be 252 or 365")

        # Factor filter validations
        if self.mr_z_lookback <= 10:
            raise ValueError("mr_z_lookback must be > 10")
        if self.mr_z_ref <= 0:
            raise ValueError("mr_z_ref must be > 0")
        if not (0.0 <= self.mr_min_mult <= 1.0):
            raise ValueError("mr_min_mult must be in [0, 1]")
        if self.trend_ema_period <= 5:
            raise ValueError("trend_ema_period must be > 5")
        if self.trend_slope_lookback <= 1:
            raise ValueError("trend_slope_lookback must be > 1")
        if self.trend_slope_ref <= 0:
            raise ValueError("trend_slope_ref must be > 0")
        if not (0.0 <= self.trend_block_threshold <= 1.0):
            raise ValueError("trend_block_threshold must be in [0, 1]")
        if self.trend_buy_k < 0:
            raise ValueError("trend_buy_k must be >= 0")
        if not (0.0 <= self.trend_buy_floor <= 1.0):
            raise ValueError("trend_buy_floor must be in [0, 1]")

        if self.breakout_band_atr_mult <= 0:
            raise ValueError("breakout_band_atr_mult must be > 0")
        if self.breakout_band_pct <= 0:
            raise ValueError("breakout_band_pct must be > 0")
        if not (0.0 <= self.breakout_trend_weight <= 1.0):
            raise ValueError("breakout_trend_weight must be in [0, 1]")
        if self.breakout_buy_k < 0:
            raise ValueError("breakout_buy_k must be >= 0")
        if not (0.0 <= self.breakout_buy_floor <= 1.0):
            raise ValueError("breakout_buy_floor must be in [0, 1]")
        if not (0.0 <= self.breakout_block_threshold <= 1.0):
            raise ValueError("breakout_block_threshold must be in [0, 1]")

        # Funding factor validations
        if self.funding_gate_minutes <= 0 or self.funding_gate_minutes > 360:
            raise ValueError("funding_gate_minutes must be in (0, 360]")
        if self.funding_ref <= 0:
            raise ValueError("funding_ref must be > 0")
        if self.funding_block_threshold < 0:
            raise ValueError("funding_block_threshold must be >= 0")
        if self.funding_buy_k < 0:
            raise ValueError("funding_buy_k must be >= 0")
        if not (0.0 <= self.funding_buy_floor <= 1.0):
            raise ValueError("funding_buy_floor must be in [0, 1]")
        if self.funding_sell_k < 0:
            raise ValueError("funding_sell_k must be >= 0")
        if self.funding_sell_cap < 1.0:
            raise ValueError("funding_sell_cap must be >= 1.0")

        if not (0.0 < self.range_top_band_start < 1.0):
            raise ValueError("range_top_band_start must be in (0, 1)")
        if self.range_buy_k < 0:
            raise ValueError("range_buy_k must be >= 0")
        if not (0.0 <= self.range_buy_floor <= 1.0):
            raise ValueError("range_buy_floor must be in [0, 1]")
        if self.range_sell_k < 0:
            raise ValueError("range_sell_k must be >= 0")
        if self.range_sell_cap < 1.0:
            raise ValueError("range_sell_cap must be >= 1.0")

        # Volatility regime validations
        if self.vol_lookback <= 10:
            raise ValueError("vol_lookback must be > 10")
        if not (0.0 < self.vol_low_q < self.vol_high_q < 1.0):
            raise ValueError("require 0 < vol_low_q < vol_high_q < 1")
        if not (0.0 <= self.vol_trigger_score <= 1.0):
            raise ValueError("vol_trigger_score must be in [0, 1]")
        if self.vol_sell_mult_high < 1.0:
            raise ValueError("vol_sell_mult_high must be >= 1.0")

        # Market Maker Risk Zone validations
        if not (0.0 <= getattr(self, "mm_risk_buy_multiplier", 0.2) <= 1.0):
            raise ValueError("mm_risk_buy_multiplier must be in [0, 1]")
        if getattr(self, "mm_risk_sell_multiplier", 3.0) < 1.0:
            raise ValueError("mm_risk_sell_multiplier must be >= 1.0")
        if not (0.0 <= getattr(self, "mm_risk_inventory_penalty", 0.5) <= 1.0):
            raise ValueError("mm_risk_inventory_penalty must be in [0, 1]")

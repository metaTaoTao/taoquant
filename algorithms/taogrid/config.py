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
    # Mid shift trigger based on range position distance from mid (0.5).
    # Example: 0.15 -> shift when range_pos >= 0.65 or <= 0.35 AND we are flat.
    mid_shift_range_pos_trigger: float = 0.15
    # Only allow mid shift when holdings are close to flat, to avoid breaking grid pairing ledger.
    mid_shift_flat_holdings_btc: float = 0.0005

    # === Throttling Parameters (Sprint 2) ===
    enable_throttling: bool = True
    inventory_threshold: float = 0.9
    # Inventory management (market-making style)
    # inventory_capacity_threshold_pct is measured against max notional capacity (equity * leverage).
    # Example: leverage=5x and threshold_pct=0.9 -> block new BUY when notional/equity >= 4.5.
    inventory_capacity_threshold_pct: float = 0.9
    inventory_skew_k: float = 1.0  # inventory-aware sizing strength (0 = off)

    # === P0 Risk Fix: Inventory denominator + regime scaling ===
    # Problem: BULLISH_RANGE (70/30) accumulates inventory much faster than NEUTRAL (50/50),
    # but the inventory gate uses a static threshold. This creates much larger drawdowns
    # under the same price move.
    #
    # Solution:
    # - Use an equity floor for inventory denominator (avoid denominator shrinking after drawdown).
    # - Scale inventory capacity threshold by buy allocation (more buy-heavy => stricter cap).
    inventory_use_equity_floor: bool = True
    inventory_equity_floor_mode: Literal["initial_cash"] = "initial_cash"
    enable_regime_inventory_scaling: bool = True
    inventory_regime_ref_buy_ratio: float = 0.5  # neutral reference
    # Strength of regime scaling (1.0 = current behavior; >1.0 makes buy-heavy regimes stricter)
    inventory_regime_gamma: float = 1.0
    inventory_capacity_threshold_min_pct: float = 0.25
    inventory_capacity_threshold_max_pct: float = 1.0

    # === P0 Risk Fix: Cost-basis risk zone ===
    # Critical blind spot: only checking "price vs support" misses "price vs avg_cost".
    # When price is below avg_cost, the same inventory produces much larger equity drawdowns.
    # If triggered, we stop (or heavily reduce) new BUYs until price recovers.
    enable_cost_basis_risk_zone: bool = True
    cost_risk_trigger_pct: float = 0.03  # trigger when price <= avg_cost * (1 - trigger)
    cost_risk_buy_mult: float = 0.0  # 0.0 = stop adding inventory in cost-risk zone

    # === P1 Risk Fix: Forced deleveraging on large unrealized losses ===
    # When inventory is already accumulated, "stop buying" is not enough to cap drawdown.
    # This optional protection will issue a market SELL to reduce holdings when unrealized loss
    # exceeds thresholds. Use with caution in live trading (it realizes losses).
    # ENHANCED: Default enabled, lower thresholds, added Level 3 for complete position closure
    enable_forced_deleverage: bool = True  # ENHANCED: Default enabled for survival
    deleverage_level1_unrealized_loss_pct: float = 0.10  # ENHANCED: Lowered from 0.15 to 0.10
    deleverage_level2_unrealized_loss_pct: float = 0.15  # ENHANCED: Lowered from 0.25 to 0.15
    deleverage_level1_sell_frac: float = 0.25
    deleverage_level2_sell_frac: float = 0.50
    deleverage_cooldown_bars: int = 60  # on 1m bars: 60 = 1 hour
    deleverage_min_notional_usd: float = 2000.0
    # ENHANCED: Level 3 - Complete position closure at 20% unrealized loss
    deleverage_level3_unrealized_loss_pct: float = 0.20  # Complete closure threshold
    deleverage_level3_sell_frac: float = 1.0  # 100% position closure

    # === Optional: Short leg ONLY in BEARISH regime (manual trader decision) ===
    # Default remains long-only. If enabled and regime == BEARISH_RANGE, the grid will:
    # - place SELL limits to OPEN short inventory
    # - place BUY limits to COVER shorts
    enable_short_in_bearish: bool = False
    # Safety: do not open shorts if upside breakout risk is high.
    short_breakout_block_threshold: float = 0.95
    # Only consider short overlay in high band of the range (range_pos in [0,1]).
    short_range_pos_trigger: float = 0.75
    # If in high band, optionally prioritize short_open over BUY fills.
    short_priority_in_high_band: bool = True
    # Risk control: if upside breakout risk is high while a short is open, force market cover.
    enable_short_stop_on_upside_breakout: bool = True
    # Risk control: maximum holding time for a short overlay (in bars).
    # Default 180 on 1m bars ~= 3 hours.
    short_max_hold_bars: int = 180
    # Safety: do not allow simultaneous long & short in this simplified model.
    short_flat_holdings_btc: float = 0.0005
    # Safety: do not stack shorts; 1 means "one short position at a time".
    short_max_concurrent_positions: int = 1
    # Manual-trader style: limit how many short cycles (open->cover) can occur per run.
    # Default 1: "only the first trade is short", then stop shorting.
    short_max_cycles: int = 1
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

    # === Market Maker Risk Zone (MM Risk Mode) - Tiered Risk Management ===
    # When price breaks below support + volatility buffer, enter risk mode:
    # - Reduce BUY size significantly (small positions to catch falling knife)
    # - Increase SELL size aggressively (de-inventory, sell most holdings)
    # - This mimics market maker behavior: widen spread, reduce inventory risk
    enable_mm_risk_zone: bool = True
    
    # Level 1 (Mild Risk): price < support + cushion
    mm_risk_level1_buy_mult: float = 0.2   # BUY 20% of normal size
    mm_risk_level1_sell_mult: float = 3.0  # SELL 300% of normal size
    mm_risk_inventory_penalty: float = 0.5  # Additional reduction if inv_ratio > 0.5
    
    # Level 2 (Moderate Risk): price stays in risk zone for extended period
    # Note: Time threshold not set - user will manually update interval if trend reverses
    mm_risk_level2_buy_mult: float = 0.1   # BUY 10% of normal size
    mm_risk_level2_sell_mult: float = 4.0  # SELL 400% of normal size
    
    # Level 3 (Severe Risk): price < support - 2 × ATR
    mm_risk_level3_atr_mult: float = 2.0   # Trigger at support - 2 × ATR
    mm_risk_level3_buy_mult: float = 0.05  # BUY 5% of normal size
    mm_risk_level3_sell_mult: float = 5.0  # SELL 500% of normal size
    
    # Level 4 (Extreme Risk - Grid Shutdown):
    # Grid will be completely disabled if any of these conditions are met
    # ENHANCED: Lower thresholds for earlier protection, especially in 90% drawdown scenarios
    max_risk_atr_mult: float = 2.0  # ENHANCED: Lowered from 3.0 to 2.0 (earlier shutdown)
    max_risk_loss_pct: float = 0.20  # ENHANCED: Lowered from 0.30 to 0.20 (earlier shutdown)
    max_risk_inventory_pct: float = 0.8  # Inventory risk: 80% capacity
    # ENHANCED: Daily drawdown threshold for flash crash protection
    max_daily_drawdown_pct: float = 0.20  # Shutdown if daily drawdown > 20%
    # ENHANCED: Position-level stop loss - force close all positions when grid shuts down
    enable_position_level_stop_loss: bool = True  # Force close positions on Level 4 shutdown
    # ENHANCED: Grid re-enable protection
    grid_re_enable_cooldown_bars: int = 1440  # 24 hours cooldown (1440 × 1m bars)
    grid_re_enable_price_recovery_atr_mult: float = 1.0  # Price must recover to support + 1×ATR
    grid_re_enable_requires_manual_approval: bool = False  # Optional: require manual approval
    # Note: Grid stays disabled until cooldown expires AND price recovers (or manual approval)
    
    # Profit Protection: use realized profits to buffer risk threshold
    enable_profit_buffer: bool = True  # Enable profit buffer
    profit_buffer_ratio: float = 0.5  # 50% of realized profits can buffer risk

    # === Backtest Parameters ===
    initial_cash: float = 100000.0
    leverage: float = 1.0
    sharpe_annualization_days: int = 365  # crypto spot/perp trades 24/7
    # Console logging (set False for large sweeps)
    enable_console_log: bool = True

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
        if not (0.0 < self.inventory_capacity_threshold_min_pct <= 1.0):
            raise ValueError("inventory_capacity_threshold_min_pct must be in (0, 1.0]")
        if not (0.0 < self.inventory_capacity_threshold_max_pct <= 1.0):
            raise ValueError("inventory_capacity_threshold_max_pct must be in (0, 1.0]")
        if self.inventory_capacity_threshold_min_pct > self.inventory_capacity_threshold_max_pct:
            raise ValueError("inventory_capacity_threshold_min_pct must be <= inventory_capacity_threshold_max_pct")
        if self.inventory_regime_ref_buy_ratio <= 0 or self.inventory_regime_ref_buy_ratio > 1.0:
            raise ValueError("inventory_regime_ref_buy_ratio must be in (0, 1]")
        if self.inventory_regime_gamma <= 0:
            raise ValueError("inventory_regime_gamma must be > 0")
        if not (0.0 <= self.cost_risk_trigger_pct <= 0.30):
            raise ValueError("cost_risk_trigger_pct must be in [0, 0.30]")
        if not (0.0 <= self.cost_risk_buy_mult <= 1.0):
            raise ValueError("cost_risk_buy_mult must be in [0, 1]")
        if self.deleverage_level1_unrealized_loss_pct <= 0 or self.deleverage_level1_unrealized_loss_pct >= 1:
            raise ValueError("deleverage_level1_unrealized_loss_pct must be in (0, 1)")
        if self.deleverage_level2_unrealized_loss_pct <= 0 or self.deleverage_level2_unrealized_loss_pct >= 1:
            raise ValueError("deleverage_level2_unrealized_loss_pct must be in (0, 1)")
        if self.deleverage_level1_unrealized_loss_pct >= self.deleverage_level2_unrealized_loss_pct:
            raise ValueError("deleverage_level1_unrealized_loss_pct must be < deleverage_level2_unrealized_loss_pct")
        if not (0.0 < self.deleverage_level1_sell_frac <= 1.0):
            raise ValueError("deleverage_level1_sell_frac must be in (0, 1]")
        if not (0.0 < self.deleverage_level2_sell_frac <= 1.0):
            raise ValueError("deleverage_level2_sell_frac must be in (0, 1]")
        if self.deleverage_cooldown_bars < 0:
            raise ValueError("deleverage_cooldown_bars must be >= 0")
        if self.deleverage_min_notional_usd < 0:
            raise ValueError("deleverage_min_notional_usd must be >= 0")
        if not (0.0 <= self.short_breakout_block_threshold <= 1.0):
            raise ValueError("short_breakout_block_threshold must be in [0, 1]")
        if not (0.0 <= self.short_range_pos_trigger <= 1.0):
            raise ValueError("short_range_pos_trigger must be in [0, 1]")
        if self.short_flat_holdings_btc < 0:
            raise ValueError("short_flat_holdings_btc must be >= 0")
        if self.short_max_concurrent_positions < 1:
            raise ValueError("short_max_concurrent_positions must be >= 1")
        if self.short_max_cycles < 1:
            raise ValueError("short_max_cycles must be >= 1")
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

        # Mid shift validations
        if self.mid_shift_threshold < 0:
            raise ValueError("mid_shift_threshold must be >= 0")
        if not (0.0 <= self.mid_shift_range_pos_trigger <= 0.5):
            raise ValueError("mid_shift_range_pos_trigger must be in [0, 0.5]")
        if self.mid_shift_flat_holdings_btc < 0:
            raise ValueError("mid_shift_flat_holdings_btc must be >= 0")

        # Market Maker Risk Zone validations
        if not (0.0 <= self.mm_risk_level1_buy_mult <= 1.0):
            raise ValueError("mm_risk_level1_buy_mult must be in [0, 1]")
        if self.mm_risk_level1_sell_mult < 1.0:
            raise ValueError("mm_risk_level1_sell_mult must be >= 1.0")
        if not (0.0 <= self.mm_risk_inventory_penalty <= 1.0):
            raise ValueError("mm_risk_inventory_penalty must be in [0, 1]")
        if not (0.0 <= self.mm_risk_level2_buy_mult <= 1.0):
            raise ValueError("mm_risk_level2_buy_mult must be in [0, 1]")
        if self.mm_risk_level2_sell_mult < 1.0:
            raise ValueError("mm_risk_level2_sell_mult must be >= 1.0")
        if self.mm_risk_level3_atr_mult <= 0:
            raise ValueError("mm_risk_level3_atr_mult must be > 0")
        if not (0.0 <= self.mm_risk_level3_buy_mult <= 1.0):
            raise ValueError("mm_risk_level3_buy_mult must be in [0, 1]")
        if self.mm_risk_level3_sell_mult < 1.0:
            raise ValueError("mm_risk_level3_sell_mult must be >= 1.0")
        if self.max_risk_atr_mult <= 0:
            raise ValueError("max_risk_atr_mult must be > 0")
        if not (0.0 < self.max_risk_loss_pct <= 1.0):
            raise ValueError("max_risk_loss_pct must be in (0, 1]")
        if not (0.0 < self.max_risk_inventory_pct <= 1.0):
            raise ValueError("max_risk_inventory_pct must be in (0, 1]")
        # ENHANCED: Validate new parameters
        if not (0.0 < self.max_daily_drawdown_pct <= 1.0):
            raise ValueError("max_daily_drawdown_pct must be in (0, 1]")
        if self.grid_re_enable_cooldown_bars < 0:
            raise ValueError("grid_re_enable_cooldown_bars must be >= 0")
        if self.grid_re_enable_price_recovery_atr_mult <= 0:
            raise ValueError("grid_re_enable_price_recovery_atr_mult must be > 0")
        if not (0.0 < self.deleverage_level3_unrealized_loss_pct <= 1.0):
            raise ValueError("deleverage_level3_unrealized_loss_pct must be in (0, 1]")
        if not (0.0 < self.deleverage_level3_sell_frac <= 1.0):
            raise ValueError("deleverage_level3_sell_frac must be in (0, 1]")
        if not (0.0 <= self.profit_buffer_ratio <= 1.0):
            raise ValueError("profit_buffer_ratio must be in [0, 1]")

        # Market Maker Risk Zone validations
        if not (0.0 <= getattr(self, "mm_risk_buy_multiplier", 0.2) <= 1.0):
            raise ValueError("mm_risk_buy_multiplier must be in [0, 1]")
        if getattr(self, "mm_risk_sell_multiplier", 3.0) < 1.0:
            raise ValueError("mm_risk_sell_multiplier must be >= 1.0")
        if not (0.0 <= getattr(self, "mm_risk_inventory_penalty", 0.5) <= 1.0):
            raise ValueError("mm_risk_inventory_penalty must be in [0, 1]")

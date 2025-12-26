"""
Grid Manager for TaoGrid Lean Algorithm.

This helper class manages grid state and integrates with taoquant modules.
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Add taoquant to path
taoquant_root = Path(__file__).parent.parent.parent.parent
if str(taoquant_root) not in sys.path:
    sys.path.insert(0, str(taoquant_root))

# Import taoquant modules (reuse existing code)
from analytics.indicators.grid_generator import (
    calculate_grid_spacing,
    generate_grid_levels,
)
from analytics.indicators.grid_weights import (
    calculate_level_weights,
    allocate_side_budgets,
)
from analytics.indicators.volatility import calculate_atr
from risk_management.grid_inventory import GridInventoryTracker
from risk_management.grid_risk_manager import GridRiskManager


class GridManager:
    """
    Manages grid state for TaoGrid Lean algorithm.

    This class:
    1. Generates grid levels using taoquant's grid_generator
    2. Calculates position weights using taoquant's grid_weights
    3. Tracks inventory using taoquant's GridInventoryTracker
    4. Applies throttling using taoquant's GridRiskManager

    Attributes
    ----------
    config : TaoGridLeanConfig
        Strategy configuration
    inventory_tracker : GridInventoryTracker
        Tracks current positions
    risk_manager : GridRiskManager
        Applies throttling rules
    buy_levels : np.ndarray
        Buy grid levels (prices)
    sell_levels : np.ndarray
        Sell grid levels (prices)
    buy_weights : np.ndarray
        Position weights for each buy level
    sell_weights : np.ndarray
        Position weights for each sell level
    """

    def __init__(self, config):
        """
        Initialize grid manager.

        Parameters
        ----------
        config : TaoGridLeanConfig
            Strategy configuration
        """
        self.config = config

        # Initialize inventory tracker
        self.inventory_tracker = GridInventoryTracker(
            max_long_units=config.max_long_units,
            max_short_units=config.max_short_units,
        )

        # Initialize risk manager
        self.risk_manager = GridRiskManager(
            max_long_units=config.max_long_units,
            max_short_units=config.max_short_units,
            inventory_threshold=config.inventory_threshold,
            profit_target_pct=config.profit_target_pct,
            profit_reduction=config.profit_reduction,
            volatility_threshold=config.volatility_threshold,
            volatility_reduction=config.volatility_reduction,
        )

        # Grid levels (will be initialized in setup_grid)
        self.buy_levels: Optional[np.ndarray] = None
        self.sell_levels: Optional[np.ndarray] = None
        self.buy_weights: Optional[np.ndarray] = None
        self.sell_weights: Optional[np.ndarray] = None

        # Regime allocation ratios (set in setup_grid)
        self.regime_buy_ratio: float = 0.5
        self.regime_sell_ratio: float = 0.5

        # ATR tracking for spacing calculation
        self.current_atr: float = 0.0
        self.avg_atr: float = 0.0
        self._last_close: float | None = None

        # Track filled grid levels to avoid re-triggering
        # Key: "buy_L1", "sell_L2", etc.
        # Value: True if filled (waiting for exit)
        self.filled_levels: Dict[str, bool] = {}
        
        # Track buy positions and their target sell levels
        # Key: buy_level_index (int)
        # Value: list of positions with size and target sell level
        # Each position: {'size': float, 'buy_price': float, 'target_sell_level': int}
        self.buy_positions: Dict[int, List[dict]] = {}

        # Track short positions (only used when short leg is enabled in BEARISH regime)
        # Key: sell_level_index (int)
        # Value: list of positions: {'size': float, 'sell_price': float, 'target_buy_level': int}
        self.short_positions: Dict[int, List[dict]] = {}
        
        # Pending limit orders (true grid strategy: place orders and wait for them to be hit)
        # Each order: {
        #   'direction': 'buy' or 'sell',
        #   'level_index': int,
        #   'price': float,  # Grid level price
        #   'size': float,   # Calculated size (will be calculated when order is placed)
        #   'placed': bool,  # Whether order has been placed
        #   'last_checked_bar': int  # Track which bar we last checked (to avoid duplicate triggers)
        # }
        self.pending_limit_orders: List[dict] = []
        
        # Risk state tracking for tiered risk management
        self.grid_enabled: bool = True  # Grid enabled/disabled flag
        self.risk_level: int = 0  # 0=normal, 1=mild, 2=moderate, 3=severe, 4=shutdown
        self.risk_zone_entry_time: Optional[datetime] = None  # When entered risk zone
        self.grid_shutdown_reason: Optional[str] = None  # Reason for grid shutdown
        self.realized_pnl: float = 0.0  # Track realized profits for profit buffer
        # ENHANCED: Track grid shutdown time for cooldown period
        self.grid_shutdown_time: Optional[datetime] = None  # When grid was shut down
        self.grid_shutdown_bar_index: Optional[int] = None  # Bar index when grid was shut down

    def setup_grid(self, historical_data: pd.DataFrame) -> None:
        """
        Initialize grid levels based on historical data.

        This calculates ATR and generates grid levels.

        Parameters
        ----------
        historical_data : pd.DataFrame
            OHLCV data with columns: open, high, low, close, volume
        """
        # Calculate ATR
        atr = calculate_atr(
            historical_data["high"],
            historical_data["low"],
            historical_data["close"],
            period=self.config.atr_period,
        )
        self.current_atr = atr.iloc[-1]
        self.avg_atr = atr.mean()
        try:
            self._last_close = float(historical_data["close"].iloc[-1])
        except Exception:
            self._last_close = None

        # Calculate mid price
        # Default: static mid = (support + resistance) / 2
        mid = (self.config.support + self.config.resistance) / 2
        # Optional: mid shift (initialize grid centered closer to current market)
        # NOTE: We only use this at grid setup time; dynamic mid shifting is handled
        # by runner logic and is only allowed when flat, to avoid breaking pairing ledger.
        if getattr(self.config, "enable_mid_shift", False) and historical_data is not None and len(historical_data) > 0:
            last_close = float(historical_data["close"].iloc[-1])
            if last_close > 0:
                # clamp mid inside (support, resistance) with cushion buffer
                lo = float(self.config.support) + float(self.current_atr) * float(self.config.cushion_multiplier)
                hi = float(self.config.resistance) - float(self.current_atr) * float(self.config.cushion_multiplier)
                if lo < hi:
                    mid = float(min(hi, max(lo, last_close)))

        # Calculate cushion (volatility buffer)
        cushion = self.current_atr * self.config.cushion_multiplier

        # Calculate grid spacing (using ATR series)
        # NOTE: For limit orders, slippage is 0 (limit orders execute at specified price)
        spacing_pct_series = calculate_grid_spacing(
            atr=atr,
            min_return=self.config.min_return,
            maker_fee=self.config.maker_fee,
            slippage=0.0,  # Limit orders have no slippage
            volatility_k=self.config.volatility_k,
            use_limit_orders=True,  # Explicitly set to True
        )
        # Use latest spacing value
        spacing_pct_base = spacing_pct_series.iloc[-1]

        # Apply spacing_multiplier
        # IMPORTANT: spacing_multiplier must be >= 1.0 (validated in config)
        # It should only EXPAND spacing, never reduce it below cost coverage
        spacing_pct = spacing_pct_base * self.config.spacing_multiplier

        # Generate grid levels
        grid_result = generate_grid_levels(
            mid_price=mid,
            support=self.config.support,
            resistance=self.config.resistance,
            cushion=cushion,
            spacing_pct=spacing_pct,
            layers_buy=self.config.grid_layers_buy,
            layers_sell=self.config.grid_layers_sell,
        )

        self.buy_levels = grid_result["buy_levels"]
        self.sell_levels = grid_result["sell_levels"]

        # Warn if fewer levels generated than requested
        if len(self.buy_levels) < self.config.grid_layers_buy:
            import warnings
            warnings.warn(
                f"Requested {self.config.grid_layers_buy} buy layers, but only {len(self.buy_levels)} were generated. "
                f"This is because the spacing ({spacing_pct:.2%}) is too large for the available range. "
                f"Consider: (1) reducing min_return, (2) reducing spacing_multiplier, or (3) using a wider support/resistance range."
            )
        if len(self.sell_levels) < self.config.grid_layers_sell:
            import warnings
            warnings.warn(
                f"Requested {self.config.grid_layers_sell} sell layers, but only {len(self.sell_levels)} were generated. "
                f"This is because the spacing ({spacing_pct:.2%}) is too large for the available range."
            )

        # Calculate weights (use actual number of levels generated, not requested)
        self.buy_weights = calculate_level_weights(
            num_levels=len(self.buy_levels), weight_k=self.config.weight_k
        )
        self.sell_weights = calculate_level_weights(
            num_levels=len(self.sell_levels), weight_k=self.config.weight_k
        )

        # Apply regime allocation (calculate allocation ratios)
        # Define regime allocation ratios
        regime_allocations = {
            "BULLISH_RANGE": (0.7, 0.3),   # 70% buy, 30% sell
            "NEUTRAL_RANGE": (0.5, 0.5),   # 50% buy, 50% sell
            "BEARISH_RANGE": (0.3, 0.7),   # 30% buy, 70% sell
        }
        buy_ratio, sell_ratio = regime_allocations.get(
            self.config.regime, (0.5, 0.5)
        )
        self.regime_buy_ratio = float(buy_ratio)
        self.regime_sell_ratio = float(sell_ratio)
        self.buy_weights = self.buy_weights * buy_ratio
        self.sell_weights = self.sell_weights * sell_ratio
        
        # Initialize pending limit orders:
        # - long-only mode: place BUY orders at buy levels
        # - short mode (BEARISH only): place SELL orders at sell levels
        self._initialize_pending_orders()

    def _short_mode_enabled(self) -> bool:
        """Return True if short leg is enabled for current config/regime."""
        return bool(getattr(self.config, "enable_short_in_bearish", False)) and getattr(self.config, "regime", "") == "BEARISH_RANGE"

    def get_grid_info(self) -> Dict[str, any]:
        """
        Get grid configuration info for logging.

        Returns
        -------
        dict
            Grid information
        """
        if self.buy_levels is None or self.sell_levels is None:
            return {"status": "Grid not initialized"}
        if len(self.buy_levels) == 0 or len(self.sell_levels) == 0:
            return {
                "status": "Empty grid levels",
                "support": f"${self.config.support:,.0f}",
                "resistance": f"${self.config.resistance:,.0f}",
                "mid": f"${(self.config.support + self.config.resistance) / 2:,.0f}",
                "regime": self.config.regime,
                "buy_levels": len(self.buy_levels),
                "sell_levels": len(self.sell_levels),
                "current_atr": f"${self.current_atr:,.2f}",
                "avg_atr": f"${self.avg_atr:,.2f}",
            }

        return {
            "support": f"${self.config.support:,.0f}",
            "resistance": f"${self.config.resistance:,.0f}",
            "mid": f"${(self.config.support + self.config.resistance) / 2:,.0f}",
            "regime": self.config.regime,
            "buy_levels": len(self.buy_levels),
            "sell_levels": len(self.sell_levels),
            "buy_range": f"${self.buy_levels.min():,.0f} - ${self.buy_levels.max():,.0f}",
            "sell_range": f"${self.sell_levels.min():,.0f} - ${self.sell_levels.max():,.0f}",
            "current_atr": f"${self.current_atr:,.2f}",
            "avg_atr": f"${self.avg_atr:,.2f}",
            "throttling_enabled": self.config.enable_throttling,
        }

    def _initialize_pending_orders(self) -> None:
        """
        Initialize pending limit orders: place buy orders at all buy levels.
        
        This implements true grid strategy: place limit orders and wait for them to be hit.
        """
        self.pending_limit_orders = []
        
        if self.buy_levels is None:
            return

        # Always keep the long-only core grid entry orders (BUYs).
        for i, level_price in enumerate(self.buy_levels):
            level_key = f"buy_L{i+1}"
            if not self.filled_levels.get(level_key, False):
                self.pending_limit_orders.append({
                    "direction": "buy",
                    "level_index": i,
                    "price": float(level_price),
                    "size": None,
                    "placed": True,
                    "last_checked_bar": None,
                    # leg is omitted => treated as core long grid
                })

        # Optional: add ONE short overlay entry order (SELL to open) in BEARISH regime.
        if self._short_mode_enabled():
            if self.sell_levels is None or len(self.sell_levels) == 0:
                return
            # For opening shorts with a SELL limit, place the overlay in the "high band" rather than near mid.
            # This aligns with trader intent: only short when price is high within the range.
            band_rp = float(getattr(self.config, "short_range_pos_trigger", 0.75))
            trigger_price = float(self.config.support) + band_rp * (float(self.config.resistance) - float(self.config.support))
            idx = None
            for i, level_price in enumerate(self.sell_levels):
                if float(level_price) >= float(trigger_price):
                    idx = i
                    break
            if idx is None:
                # If price is above all sell levels (rare), use the highest level
                idx = len(self.sell_levels) - 1
            level_price = float(self.sell_levels[idx])
            self.pending_limit_orders.append({
                "direction": "sell",
                "level_index": int(idx),
                "price": float(level_price),
                "size": None,
                "placed": True,
                "last_checked_bar": None,
                "leg": "short_open",
            })
    
    def check_limit_order_triggers(
        self, 
        current_price: float,
        prev_price: Optional[float] = None,
        bar_high: Optional[float] = None,
        bar_low: Optional[float] = None,
        bar_index: Optional[int] = None,
        range_pos: float | None = None,
    ) -> Optional[dict]:
        """
        Check if any pending limit order is triggered by price movement.
        
        Limit order trigger logic (grid strategy):
        - A limit order can only fill if the bar's traded range *actually touches* the limit price.
          For OHLC bars, that means: bar_low <= limit_price <= bar_high.
        - Buy/Sell share the same "touch" condition; direction only affects inventory constraints.
        
        We check if price touches the limit price (not requiring a "cross").
        This is correct for grid strategy: if price reaches the limit, the order should fill.
        
        Parameters
        ----------
        current_price : float
            Current market price (close)
        prev_price : Optional[float]
            Previous bar's close price (not used, kept for compatibility)
        bar_high : Optional[float]
            Current bar's high (required for sell limit trigger)
        bar_low : Optional[float]
            Current bar's low (required for buy limit trigger)
        bar_index : Optional[int]
            Current bar index (to avoid duplicate triggers in same bar)
        
        Returns
        -------
        Optional[dict]
            If triggered: order dict with calculated size
            If not triggered: None
        """
        if not self.pending_limit_orders:
            return None
        
        # Check each pending limit order.
        # Optional: when in high band, prioritize short overlay entry (short_open) so the "first trade can be short".
        orders = list(self.pending_limit_orders)
        if bool(getattr(self.config, "short_priority_in_high_band", True)):
            rp = float(range_pos) if range_pos is not None and np.isfinite(range_pos) else None
            if rp is not None and rp >= float(getattr(self.config, "short_range_pos_trigger", 0.75)):
                orders = sorted(orders, key=lambda o: 0 if o.get("leg") == "short_open" else 1)

        for order in orders:
            if not order.get('placed', False):
                continue
            
            # Skip if already triggered in this bar (will be removed after fill)
            if order.get('triggered', False):
                continue
            
            direction = order['direction']
            limit_price = order['price']
            level_index = order['level_index']
            leg = order.get("leg")
            
            # Avoid duplicate triggers in same bar
            if bar_index is not None and order.get('last_checked_bar') == bar_index:
                continue
            
            # Check if limit order is triggered
            triggered = False
            
            # OHLC-consistent LIMIT fill condition with "gap-through" support:
            # - BUY limit fills if bar traded at/below limit => bar_low <= limit_price
            # - SELL limit fills if bar traded at/above limit => bar_high >= limit_price
            # This also correctly models gap-through (open beyond the limit) fills.
            if bar_low is not None and bar_high is not None:
                if direction == "buy":
                    touched = (bar_low <= limit_price)
                else:
                    touched = (bar_high >= limit_price)
            else:
                # Fallback when high/low are missing: approximate using current price
                touched = (current_price == limit_price) or (
                    (current_price <= limit_price) if direction == 'buy' else (current_price >= limit_price)
                )

            if direction == 'buy':
                # Buy limit: only fills if bar range touches the limit price
                triggered = touched
                
                # For core long grid BUYs, block if the level is already filled.
                # For short covers, DO NOT apply filled_levels gating.
                if leg != "short_cover":
                    level_key = f"buy_L{level_index + 1}"
                    if self.filled_levels.get(level_key, False):
                        triggered = False
                        if getattr(self.config, "enable_console_log", False):
                            print(f"[FILLED_LEVELS] BUY L{level_index+1} @ ${limit_price:,.0f} blocked - level already filled (filled_levels count: {len(self.filled_levels)})")
                elif not touched and getattr(self.config, "enable_console_log", False):
                    # Log when order is not triggered due to price not touching
                    print(f"[ORDER_TRIGGER] BUY L{level_index+1} @ ${limit_price:,.0f} not triggered - price not touched (current: ${current_price:,.0f}, bar: ${bar_low:,.0f}-${bar_high:,.0f})")
                    
            elif direction == 'sell':
                # Sell limit: only fills if bar range touches the limit price
                triggered = touched

                inventory_state = self.inventory_tracker.get_state()
                if leg == "short_open":
                    # Short mode: SELL opens short inventory.
                    # Safety: do not open shorts if we still have long exposure (avoid dual exposure).
                    flat_thr = float(getattr(self.config, "short_flat_holdings_btc", 0.0005))
                    if abs(float(inventory_state.long_exposure)) > flat_thr:
                        triggered = False
                    # Do not stack shorts: only allow one short position at a time (by default).
                    max_conc = int(getattr(self.config, "short_max_concurrent_positions", 1))
                    if max_conc <= 1 and float(inventory_state.short_exposure) > flat_thr:
                        triggered = False
                else:
                    # Long-only mode: SELL closes long inventory (requires holdings)
                    if inventory_state.long_exposure > 0:
                        pass
                    else:
                        triggered = False
                        if getattr(self.config, "enable_console_log", False):
                            print(f"[ORDER_TRIGGER] SELL L{level_index+1} @ ${limit_price:,.0f} not triggered - no long positions (long_exposure: {inventory_state.long_exposure:.4f})")
                if not touched and getattr(self.config, "enable_console_log", False):
                    # Log when order is not triggered due to price not touching
                    print(f"[ORDER_TRIGGER] SELL L{level_index+1} @ ${limit_price:,.0f} not triggered - price not touched (current: ${current_price:,.0f}, bar: ${bar_low:,.0f}-${bar_high:,.0f})")
            
            if triggered:
                # Mark this bar as checked to avoid duplicate triggers
                # Also mark order as triggered so it won't trigger again until filled
                if bar_index is not None:
                    order['last_checked_bar'] = bar_index
                order['triggered'] = True  # Mark as triggered
                # Log when order is triggered
                if getattr(self.config, "enable_console_log", False):
                    print(f"[ORDER_TRIGGER] {direction.upper()} L{level_index+1} @ ${limit_price:,.0f} TRIGGERED (current: ${current_price:,.0f}, bar: ${bar_low:,.0f}-${bar_high:,.0f})")
                # Return triggered order (size will be calculated in on_data)
                return order
        
        return None
    
    def remove_pending_order(self, direction: str, level_index: int, leg: str | None = None) -> None:
        """
        Remove a pending limit order after it's been filled.

        Parameters
        ----------
        direction : str
            'buy' or 'sell'
        level_index : int
            Grid level index
        """
        before_count = len(self.pending_limit_orders)
        self.pending_limit_orders = [
            order for order in self.pending_limit_orders
            if not (
                order.get("direction") == direction
                and int(order.get("level_index", -999999)) == int(level_index)
                and order.get("leg") == leg
            )
        ]
        after_count = len(self.pending_limit_orders)
        
        # Log order removal
        if getattr(self.config, "enable_console_log", False) and before_count != after_count:
            print(f"[PENDING_ORDER] Removed {direction.upper()} L{level_index+1} (pending_orders: {before_count} -> {after_count})")
    
    def reset_triggered_orders(self) -> None:
        """
        Reset triggered flag for all orders (called after order is filled).
        """
        for order in self.pending_limit_orders:
            if order.get('triggered', False):
                order['triggered'] = False
                order['last_checked_bar'] = None
    
    def place_pending_order(
        self,
        direction: str,
        level_index: int,
        level_price: float,
        bar_index: Optional[int] = None,
        leg: str | None = None,
    ) -> None:
        """
        Place a new pending limit order after a position is filled.
        
        Grid strategy: after a buy is filled, place a sell limit order at the target sell level.
        After a sell is filled, place a new buy limit order at the same buy level (re-entry).
        
        Parameters
        ----------
        direction : str
            'buy' or 'sell'
        level_index : int
            Grid level index
        level_price : float
            Grid level price
        """
        # Check if order already exists
        for order in self.pending_limit_orders:
            if (
                order.get("direction") == direction
                and int(order.get("level_index", -999999)) == int(level_index)
                and order.get("leg") == leg
            ):
                if getattr(self.config, "enable_console_log", False):
                    print(f"[PENDING_ORDER] {direction.upper()} L{level_index+1} @ ${level_price:,.0f} already exists, skipping")
                return  # Already exists
        
        # Add new pending order
        self.pending_limit_orders.append({
            'direction': direction,
            'level_index': level_index,
            'price': level_price,
            'size': None,  # Will be calculated when triggered
            'placed': True,
            # IMPORTANT:
            # If this order is created during processing of bar `bar_index`,
            # set last_checked_bar=bar_index to prevent it from triggering
            # in the SAME bar (more realistic for event-driven execution).
            'last_checked_bar': bar_index,
            'leg': leg,
        })
        
        # Log order placement
        if getattr(self.config, "enable_console_log", False):
            print(f"[PENDING_ORDER] Placed {direction.upper()} L{level_index+1} @ ${level_price:,.0f} (pending_orders count: {len(self.pending_limit_orders)})")
    
    def check_grid_trigger(
        self, current_price: float
    ) -> Optional[Tuple[str, int, float]]:
        """
        DEPRECATED: Use check_limit_order_triggers instead.
        
        This method is kept for backward compatibility but should not be used.
        The new limit order system replaces this trigger-based approach.
        """
        # This method is deprecated - use check_limit_order_triggers instead
        return None

    def calculate_order_size(
        self,
        direction: str,
        level_index: int,
        level_price: float,
        equity: float,
        daily_pnl: float,
        risk_budget: float,
        holdings_btc: float,
        order_leg: str | None = None,
        current_price: float | None = None,
        mr_z: float | None = None,
        trend_score: float | None = None,
        breakout_risk_down: float | None = None,
        breakout_risk_up: float | None = None,
        range_pos: float | None = None,
        funding_rate: float | None = None,
        minutes_to_funding: float | None = None,
        vol_score: float | None = None,
    ) -> float:
        """
        Calculate position size for a grid order.

        This applies:
        1. Level-based weighting
        2. Risk budget allocation
        3. Convert USD to BTC (divide by price)
        4. Throttling (if enabled)

        Parameters
        ----------
        direction : str
            'buy' or 'sell'
        level_index : int
            Index in buy_levels or sell_levels
        level_price : float
            Price at the grid level (for USD to BTC conversion)
        equity : float
            Current portfolio equity (USD)
        daily_pnl : float
            Current daily P&L (USD)
        risk_budget : float
            Daily risk budget (USD)

        Returns
        -------
        tuple
            (size_btc, throttle_status)
            - size_btc: Position size in BTC
            - throttle_status: ThrottleStatus object
        """
        # Get level weight (0.0 - 1.0)
        if direction == "buy":
            weight = self.buy_weights[level_index]
        else:
            weight = self.sell_weights[level_index]

        # Calculate USD value to allocate to this order
        # Total budget = equity × risk_budget_pct
        # This level's budget = total_budget × weight
        total_budget_usd = equity * self.config.risk_budget_pct
        this_level_budget_usd = total_budget_usd * weight

        # Convert USD to BTC
        # Size in BTC = USD value / price
        base_size_btc = this_level_budget_usd / level_price

        # Apply leverage (if > 1.0)
        base_size_btc = base_size_btc * self.config.leverage
        
        # Log initial size calculation
        if getattr(self.config, "enable_console_log", False):
            print(f"[ORDER_SIZE] {direction.upper()} L{level_index+1} @ ${level_price:,.0f} - base_size={base_size_btc:.4f} BTC (equity=${equity:,.0f}, risk_budget={self.config.risk_budget_pct:.1%}, weight={weight:.4f}, leverage={self.config.leverage}x)")

        # Market Maker Risk Zone (MM Risk Mode)
        # When price breaks below support + volatility buffer, enter risk mode:
        # - Reduce BUY size significantly (small positions to catch falling knife)
        # - Increase SELL size aggressively (de-inventory, sell most holdings)
        # This mimics market maker behavior: widen spread, reduce inventory risk
        in_risk_zone = False
        if getattr(self.config, "enable_mm_risk_zone", False) and current_price is not None:
            # Risk zone threshold: support + cushion (volatility buffer)
            risk_zone_threshold = self.config.support + (self.current_atr * self.config.cushion_multiplier)
            if current_price < risk_zone_threshold:
                in_risk_zone = True

        # Inventory-aware skew (institutional-style inventory control)
        # - If inventory is too high, block new BUYs (de-risk).
        # - Otherwise, progressively reduce BUY size as inventory rises.
        inventory_state = self.inventory_tracker.get_state()
        short_mode = order_leg in ("short_open", "short_cover")
        # Notional inventory ratio (more relevant for perp/leverage than raw BTC units):
        # inv_ratio = |position_notional| / equity
        equity_for_inv = float(equity)
        if getattr(self.config, "inventory_use_equity_floor", False):
            # Use initial_cash as denominator floor to avoid "too late" inventory gating caused by
            # equity shrinking after drawdown. This stabilizes the inventory gate and makes it
            # comparable across regimes.
            equity_floor = float(getattr(self.config, "initial_cash", equity_for_inv))
            equity_for_inv = max(equity_for_inv, equity_floor)

        inv_ratio = (abs(float(holdings_btc)) * float(level_price) / float(equity_for_inv)) if equity_for_inv > 0 else 999.0

        # Regime-scaled capacity threshold: buy-heavy regimes must have stricter caps,
        # otherwise they can accumulate large inventory before any support-based risk zone triggers.
        base_capacity_pct = float(self.config.inventory_capacity_threshold_pct)
        if direction == "buy" and getattr(self.config, "enable_regime_inventory_scaling", False):
            # Use buy/sell imbalance as the scaling driver:
            # - NEUTRAL (0.5/0.5): scale=1.0 (unchanged)
            # - BULLISH (0.7/0.3): scale~0.43 => stricter cap (prevents fast inventory accumulation)
            # - BEARISH (0.3/0.7): scale>1 but clamped by max_pct (no loosening beyond base)
            buy_ratio = float(getattr(self, "regime_buy_ratio", 0.5))
            sell_ratio = float(getattr(self, "regime_sell_ratio", 0.5))
            gamma = float(getattr(self.config, "inventory_regime_gamma", 1.0))
            scale = (sell_ratio / max(buy_ratio, 1e-9)) ** gamma
            base_capacity_pct = base_capacity_pct * scale
            base_capacity_pct = min(
                float(getattr(self.config, "inventory_capacity_threshold_max_pct", 1.0)),
                max(float(getattr(self.config, "inventory_capacity_threshold_min_pct", 0.25)), base_capacity_pct),
            )

        inv_ratio_threshold = base_capacity_pct * float(self.config.leverage)

        # Cost-basis risk zone: if price is sufficiently below avg_cost, stop (or reduce) new BUYs.
        if direction == "buy" and getattr(self.config, "enable_cost_basis_risk_zone", False) and current_price is not None:
            avg_cost = self._get_avg_cost_from_positions()
            if avg_cost is not None and avg_cost > 0:
                cost_trigger = float(getattr(self.config, "cost_risk_trigger_pct", 0.03))
                if float(current_price) <= float(avg_cost) * (1.0 - cost_trigger):
                    from risk_management.grid_risk_manager import ThrottleStatus

                    buy_mult = float(getattr(self.config, "cost_risk_buy_mult", 0.0))
                    if buy_mult <= 0.0:
                        return 0.0, ThrottleStatus(
                            size_multiplier=0.0,
                            reason="Cost-basis risk zone (price below avg_cost threshold)",
                        )
                    base_size_btc = base_size_btc * buy_mult
        if direction == "buy" and order_leg == "short_cover":
            # In short mode, BUY is used to COVER shorts.
            # It must NOT be blocked by long-inventory gates, otherwise shorts can never be closed.
            target_short_size = 0.0
            for sell_level_idx, positions in self.short_positions.items():
                for pos in positions:
                    if int(pos.get("target_buy_level", -1)) == int(level_index):
                        target_short_size += float(pos.get("size", 0.0))
            if target_short_size > 0:
                # Cover is risk-reducing: prioritize fully closing the matched short inventory.
                base_size_btc = max(0.0, float(target_short_size))
            else:
                # Fallback: cover as much as current short holdings
                base_size_btc = max(0.0, abs(float(holdings_btc)))

            # Covers are risk-reducing: DO NOT throttle or block them.
            from risk_management.grid_risk_manager import ThrottleStatus
            size_btc = base_size_btc
            throttle_status = ThrottleStatus(size_multiplier=1.0, reason="Short cover")

            if getattr(self.config, "enable_console_log", False):
                print(f"[ORDER_SIZE] BUY(COVER) L{level_index+1} @ ${level_price:,.0f} - FINAL SIZE={size_btc:.4f} BTC")
            return size_btc, throttle_status

        if direction == "buy":
            if inv_ratio >= inv_ratio_threshold:
                from risk_management.grid_risk_manager import ThrottleStatus
                return 0.0, ThrottleStatus(
                    size_multiplier=0.0,
                    reason="Inventory de-risk (notional_ratio>=capacity_threshold)",
                )
            if self.config.inventory_skew_k > 0:
                # Scale buy size down as inventory ratio rises toward capacity.
                # inventory_skew_k controls how aggressive the reduction is.
                skew_mult = max(0.0, 1.0 - self.config.inventory_skew_k * (inv_ratio / max(inv_ratio_threshold, 1e-9)))
                base_size_btc = base_size_btc * skew_mult

            # Market Maker Risk Zone: tiered risk management
            if in_risk_zone:
                # Apply risk level multipliers
                if self.risk_level == 3:
                    # Level 3: Severe risk
                    mm_buy_mult = float(getattr(self.config, "mm_risk_level3_buy_mult", 0.05))
                elif self.risk_level == 2:
                    # Level 2: Moderate risk
                    mm_buy_mult = float(getattr(self.config, "mm_risk_level2_buy_mult", 0.1))
                else:
                    # Level 1: Mild risk
                    mm_buy_mult = float(getattr(self.config, "mm_risk_level1_buy_mult", 0.2))
                
                # Additional penalty if inventory is already high
                if inv_ratio > float(getattr(self.config, "mm_risk_inventory_penalty", 0.5)):
                    mm_buy_mult = mm_buy_mult * 0.5  # Further reduce by 50%
                base_size_btc = base_size_btc * mm_buy_mult

            # MR + Trend factor filter (Sharpe-oriented)
            # Idea:
            # - In strong downtrends, block new buys (avoid inventory accumulation / left tail).
            # - Otherwise, scale buy size by:
            #   - MR strength (more oversold -> larger size)
            #   - Trend state (more negative -> smaller size)
            if getattr(self.config, "enable_mr_trend_factor", False):
                from risk_management.grid_risk_manager import ThrottleStatus

                ts = float(trend_score) if trend_score is not None and np.isfinite(trend_score) else 0.0
                z_is_valid = mr_z is not None and np.isfinite(mr_z)
                z = float(mr_z) if z_is_valid else 0.0

                # Hard block for strong downtrend
                if ts <= -float(self.config.trend_block_threshold):
                    return 0.0, ThrottleStatus(
                        size_multiplier=0.0,
                        reason="Factor block (strong downtrend)",
                    )

                # Trend multiplier: only reduce when ts < 0
                neg_ts = max(0.0, -ts)
                trend_mult = max(
                    float(self.config.trend_buy_floor),
                    1.0 - float(self.config.trend_buy_k) * neg_ts,
                )

                # MR multiplier (optional):
                # Default config sets mr_min_mult=1.0, making MR a diagnostics-only feature.
                # If user later sets mr_min_mult < 1.0, this becomes a gentle "buy less when not oversold".
                if not z_is_valid:
                    mr_mult = 1.0
                elif z >= 0:
                    mr_mult = float(self.config.mr_min_mult)
                else:
                    mr_strength = min(1.0, max(0.0, (-z) / float(self.config.mr_z_ref)))
                    mr_mult = max(float(self.config.mr_min_mult), mr_strength)

                factor_mult = trend_mult * mr_mult
                base_size_btc = base_size_btc * factor_mult

            # Breakout risk factor (near boundary risk-off)
            if getattr(self.config, "enable_breakout_risk_factor", False):
                from risk_management.grid_risk_manager import ThrottleStatus

                br_down = float(breakout_risk_down) if breakout_risk_down is not None and np.isfinite(breakout_risk_down) else 0.0
                br_up = float(breakout_risk_up) if breakout_risk_up is not None and np.isfinite(breakout_risk_up) else 0.0

                # For a long-inventory grid, downside breakout is the main tail risk.
                # Still keep upside risk for diagnostics / future use.
                if br_down >= float(self.config.breakout_block_threshold):
                    return 0.0, ThrottleStatus(
                        size_multiplier=0.0,
                        reason="Breakout risk-off (downside)",
                    )

                # Reduce buys as downside risk rises; keep a floor to preserve churn.
                risk_mult = max(
                    float(self.config.breakout_buy_floor),
                    1.0 - float(self.config.breakout_buy_k) * br_down,
                )
                base_size_btc = base_size_btc * risk_mult

            # Funding factor (perp cost control)
            if getattr(self.config, "enable_funding_factor", False):
                from risk_management.grid_risk_manager import ThrottleStatus

                fr = float(funding_rate) if funding_rate is not None and np.isfinite(funding_rate) else 0.0
                # Time gate: only apply around funding settlement windows to avoid reducing churn.
                if getattr(self.config, "enable_funding_time_gate", True):
                    mtf = float(minutes_to_funding) if minutes_to_funding is not None and np.isfinite(minutes_to_funding) else 999999.0
                    if abs(mtf) > float(self.config.funding_gate_minutes):
                        fr = 0.0

                if getattr(self.config, "funding_apply_to_buy", False):
                    if fr >= float(self.config.funding_block_threshold):
                        return 0.0, ThrottleStatus(
                            size_multiplier=0.0,
                            reason="Funding risk-off (block BUY)",
                        )
                    if fr > 0:
                        # normalize to [0, 1] using funding_ref
                        x = min(1.0, max(0.0, fr / float(self.config.funding_ref)))
                        buy_mult = max(float(self.config.funding_buy_floor), 1.0 - float(self.config.funding_buy_k) * x)
                        base_size_btc = base_size_btc * buy_mult

            # Range position asymmetry v2 (TOP band only)
            if getattr(self.config, "enable_range_pos_asymmetry_v2", False):
                rp = float(range_pos) if range_pos is not None and np.isfinite(range_pos) else 0.5
                rp = min(1.0, max(0.0, rp))
                start = float(self.config.range_top_band_start)
                if rp >= start:
                    x = (rp - start) / max(1e-9, (1.0 - start))  # 0..1 within band
                    buy_mult = max(float(self.config.range_buy_floor), 1.0 - float(self.config.range_buy_k) * x)
                    base_size_btc = base_size_btc * buy_mult

            # Volatility regime factor (v2):
            # Only act in extreme high-volatility, and prefer SELL-only de-risking to
            # avoid killing churn / Sharpe.
            if getattr(self.config, "enable_vol_regime_factor", False):
                vs = float(vol_score) if vol_score is not None and np.isfinite(vol_score) else 0.0
                if vs >= float(getattr(self.config, "vol_trigger_score", 1.0)) and getattr(self.config, "vol_apply_to_buy", False):
                    # Optional: if enabled, reduce BUY risk in extreme high vol
                    base_size_btc = base_size_btc * 1.0  # no-op by default

            # NOTE:
            # We experimented with a naive range-position asymmetry and found it can
            # dramatically reduce churn and harm Sharpe. The v2 implementation (enabled
            # via enable_range_pos_asymmetry_v2) should be applied ONLY near the range top
            # to de-inventory without suppressing mid-range trading.
        else:
            # Selling is used to close long inventory in this strategy.
            # Cap sell size to available holdings to avoid failed executions.
            rp = float(range_pos) if range_pos is not None and np.isfinite(range_pos) else 0.5
            rp = min(1.0, max(0.0, rp))

            # Short overlay: SELL(leg=short_open) opens short, so protect right-tail with breakout_risk_up.
            if order_leg == "short_open" and getattr(self.config, "enable_breakout_risk_factor", True):
                from risk_management.grid_risk_manager import ThrottleStatus
                br_up = float(breakout_risk_up) if breakout_risk_up is not None and np.isfinite(breakout_risk_up) else 0.0
                if br_up >= float(getattr(self.config, "short_breakout_block_threshold", 0.95)):
                    return 0.0, ThrottleStatus(
                        size_multiplier=0.0,
                        reason="Short blocked (upside breakout risk)",
                    )
                # Only allow short overlay in the high band of the range.
                if rp < float(getattr(self.config, "short_range_pos_trigger", 0.75)):
                    return 0.0, ThrottleStatus(
                        size_multiplier=0.0,
                        reason="Short blocked (not in high band)",
                    )

            if short_mode:
                # In short mode, SELL opens shorts. Enforce inventory cap on short notional.
                if inv_ratio >= inv_ratio_threshold:
                    from risk_management.grid_risk_manager import ThrottleStatus
                    return 0.0, ThrottleStatus(
                        size_multiplier=0.0,
                        reason="Short inventory de-risk (notional_ratio>=capacity_threshold)",
                    )
                # Cap by remaining short unit capacity (base currency units)
                avail = float(self.inventory_tracker.get_available_capacity("short"))
                base_size_btc = min(base_size_btc, max(0.0, avail))

            # Funding factor: boost sell aggressiveness when funding positive (longs pay).
            if getattr(self.config, "enable_funding_factor", False) and getattr(self.config, "funding_apply_to_sell", True):
                fr = float(funding_rate) if funding_rate is not None and np.isfinite(funding_rate) else 0.0
                if getattr(self.config, "enable_funding_time_gate", True):
                    mtf = float(minutes_to_funding) if minutes_to_funding is not None and np.isfinite(minutes_to_funding) else 999999.0
                    if abs(mtf) > float(self.config.funding_gate_minutes):
                        fr = 0.0
                if fr > 0:
                    x = min(1.0, max(0.0, fr / float(self.config.funding_ref)))
                    sell_mult = min(float(self.config.funding_sell_cap), 1.0 + float(self.config.funding_sell_k) * x)
                    base_size_btc = base_size_btc * sell_mult

            if getattr(self.config, "enable_range_pos_asymmetry_v2", False):
                # v2: ONLY apply near top band, to avoid killing churn.
                start = float(self.config.range_top_band_start)
                if rp >= start:
                    # normalize to [0, 1] within band
                    x = (rp - start) / max(1e-9, (1.0 - start))
                    sell_mult = min(float(self.config.range_sell_cap), 1.0 + float(self.config.range_sell_k) * x)
                    base_size_btc = base_size_btc * sell_mult

            # Volatility regime factor: in high vol, prioritize de-risking via SELL
            if getattr(self.config, "enable_vol_regime_factor", False):
                vs = float(vol_score) if vol_score is not None and np.isfinite(vol_score) else 0.0
                if vs >= float(getattr(self.config, "vol_trigger_score", 1.0)) and getattr(self.config, "vol_apply_to_sell", True):
                    base_size_btc = base_size_btc * float(self.config.vol_sell_mult_high)
            
            # Market Maker Risk Zone: tiered risk management for SELL
            if in_risk_zone and not short_mode:
                # Apply risk level multipliers
                if self.risk_level == 3:
                    # Level 3: Severe risk
                    mm_sell_mult = float(getattr(self.config, "mm_risk_level3_sell_mult", 5.0))
                elif self.risk_level == 2:
                    # Level 2: Moderate risk
                    mm_sell_mult = float(getattr(self.config, "mm_risk_level2_sell_mult", 4.0))
                else:
                    # Level 1: Mild risk
                    mm_sell_mult = float(getattr(self.config, "mm_risk_level1_sell_mult", 3.0))
                base_size_btc = base_size_btc * mm_sell_mult
            
            if not short_mode:
                # Long-only mode: Limit sell size to corresponding buy position size (pairing correctness)
                target_buy_size = 0.0
                for buy_level_idx, positions in self.buy_positions.items():
                    for pos in positions:
                        if pos.get('target_sell_level') == level_index:
                            target_buy_size += pos['size']
                if target_buy_size > 0:
                    size_before_limit = base_size_btc
                    base_size_btc = min(base_size_btc, target_buy_size)
                    if getattr(self.config, "enable_console_log", False) and size_before_limit > target_buy_size:
                        print(f"[ORDER_SIZE] SELL L{level_index+1} size limited to buy position size: {base_size_btc:.4f} BTC (was {size_before_limit:.4f} BTC before limit, buy position size: {target_buy_size:.4f} BTC)")
                else:
                    base_size_btc = min(base_size_btc, max(0.0, float(holdings_btc)))
                    if getattr(self.config, "enable_console_log", False):
                        print(f"[ORDER_SIZE] SELL L{level_index+1} no matching buy position found, limiting to holdings: {base_size_btc:.4f} BTC")

        # Apply throttling if enabled
        if self.config.enable_throttling:
            throttle_status = self.risk_manager.check_throttle(
                long_exposure=inventory_state.long_exposure,
                short_exposure=inventory_state.short_exposure,
                daily_pnl=daily_pnl,
                risk_budget=risk_budget,
                current_atr=self.current_atr,
                avg_atr=self.avg_atr,
            )

            # Apply throttle multiplier
            size_btc = base_size_btc * throttle_status.size_multiplier
        else:
            from risk_management.grid_risk_manager import ThrottleStatus
            size_btc = base_size_btc
            throttle_status = ThrottleStatus(size_multiplier=1.0, reason="No throttle")
        
        # Log final size
        if getattr(self.config, "enable_console_log", False):
            if size_btc == 0.0:
                print(f"[ORDER_SIZE] {direction.upper()} L{level_index+1} @ ${level_price:,.0f} - FINAL SIZE=0 (blocked: {throttle_status.reason})")
            elif throttle_status.size_multiplier < 1.0:
                print(f"[ORDER_SIZE] {direction.upper()} L{level_index+1} @ ${level_price:,.0f} - FINAL SIZE={size_btc:.4f} BTC (throttled: {throttle_status.size_multiplier:.1%}, reason: {throttle_status.reason})")
            else:
                print(f"[ORDER_SIZE] {direction.upper()} L{level_index+1} @ ${level_price:,.0f} - FINAL SIZE={size_btc:.4f} BTC")
        
        return size_btc, throttle_status

    def _get_avg_cost_from_positions(self) -> Optional[float]:
        """
        Compute average cost from internal buy_positions ledger.

        Notes:
        - This uses the position ledger (buy_positions) as source of truth for cost basis.
        - It is intentionally independent from holdings_btc input to avoid mismatches caused by
          rounding or partial fills.

        Returns:
            Average cost (USD) if available, otherwise None.
        """
        total_size = 0.0
        total_cost = 0.0
        for positions in self.buy_positions.values():
            for pos in positions:
                size = float(pos.get("size", 0.0))
                price = float(pos.get("buy_price", 0.0))
                if size <= 0.0 or price <= 0.0:
                    continue
                total_size += size
                total_cost += size * price
        if total_size <= 0.0:
            return None
        return total_cost / total_size

    def add_buy_position(
        self, buy_level_index: int, size: float, buy_price: float
    ) -> None:
        """
        Add a buy position with target sell level.
        
        Grid pairing rule: buy at buy_level[i] -> sell at sell_level[i]
        BUT: Since buy_levels and sell_levels are both generated from mid,
        buy[0] and sell[0] are both 1 spacing from mid, so pairing is 2 × spacing.
        
        For 1 × spacing pairing, we should use: buy[i] -> sell[i+1]
        But for simplicity, we keep buy[i] -> sell[i] (2 × spacing = one grid cycle)
        
        Parameters
        ----------
        buy_level_index : int
            Index of buy level (0-based)
        size : float
            Position size
        buy_price : float
            Actual buy price
        """
        level_key = f"buy_L{buy_level_index + 1}"
        
        # NOTE: Don't mark as filled here - allow continuous re-entry
        # Grid strategy: keep buying at this level as long as price is in range
        # filled_levels is now managed in on_order_filled (reset immediately after buy)
        # self.filled_levels[level_key] = True  # REMOVED: allow continuous orders
        
        # Log filled_levels state when adding buy position
        if getattr(self.config, "enable_console_log", False):
            filled_count = len(self.filled_levels)
            is_filled = self.filled_levels.get(level_key, False)
            print(f"[FILLED_LEVELS] Add BUY L{buy_level_index+1} @ ${buy_price:,.0f} - filled_levels count: {filled_count}, this level filled: {is_filled}")
        
        # Target sell level: same index (buy_level[i] -> sell_level[i])
        # With fixed grid generation: sell_levels are generated from buy_levels
        # So sell_level[i] = buy_level[i] × (1 + spacing), creating 1x spacing pairing
        target_sell_level = buy_level_index
        
        # Initialize buy_positions dict if needed
        if buy_level_index not in self.buy_positions:
            self.buy_positions[buy_level_index] = []
        
        # Add position
        self.buy_positions[buy_level_index].append({
            'size': size,
            'buy_price': buy_price,
            'target_sell_level': target_sell_level,
        })
    
    def match_sell_order(
        self, sell_level_index: int, sell_size: float
    ) -> Optional[Tuple[int, float, float]]:
        """
        Match a sell order against buy positions.
        
        Returns the matched buy position info for trade recording.
        
        Parameters
        ----------
        sell_level_index : int
            Index of sell level (0-based)
        sell_size : float
            Size to sell
        
        Returns
        -------
        Optional[Tuple[int, float, float]]
            If matched: (buy_level_index, buy_price, matched_size)
            If not matched: None
        """
        # Log match attempt
        if getattr(self.config, "enable_console_log", False):
            total_buy_positions = sum(len(positions) for positions in self.buy_positions.values())
            print(f"[SELL_MATCH] Attempting to match SELL L{sell_level_index+1} size={sell_size:.4f} against {total_buy_positions} buy positions")
        
        # Find buy position targeting this sell level
        for buy_level_idx, positions in list(self.buy_positions.items()):
            for pos_idx, pos in enumerate(positions):
                if pos.get('target_sell_level') == sell_level_index:
                    # Match found
                    matched_size = min(sell_size, pos['size'])
                    buy_price = pos['buy_price']
                    
                    # Log successful match
                    if getattr(self.config, "enable_console_log", False):
                        print(f"[SELL_MATCH] SUCCESS: SELL L{sell_level_index+1} matched with BUY L{buy_level_idx+1} @ ${buy_price:,.0f}, matched_size={matched_size:.4f}")
                    
                    # Update position
                    pos['size'] -= matched_size
                    
                    # Remove if fully matched
                    if pos['size'] < 0.0001:
                        positions.pop(pos_idx)
                    
                    # Clean up empty lists
                    if not positions:
                        del self.buy_positions[buy_level_idx]
                        # Reset buy level to allow re-triggering
                        buy_level_key = f"buy_L{buy_level_idx + 1}"
                        if buy_level_key in self.filled_levels:
                            del self.filled_levels[buy_level_key]
                            # Log when filled_levels is reset
                            if getattr(self.config, "enable_console_log", False):
                                print(f"[FILLED_LEVELS] Reset BUY L{buy_level_idx+1} after sell match (filled_levels count: {len(self.filled_levels)})")
                    
                    return (buy_level_idx, buy_price, matched_size)
        
        # Log match failure
        if getattr(self.config, "enable_console_log", False):
            print(f"[SELL_MATCH] FAILED: SELL L{sell_level_index+1} size={sell_size:.4f} - no matching buy position found (target_sell_level={sell_level_index})")
            # Show available buy positions for debugging
            available_levels = []
            for buy_level_idx, positions in self.buy_positions.items():
                for pos in positions:
                    target_level = pos.get('target_sell_level', -1)
                    available_levels.append(f"BUY L{buy_level_idx+1} -> SELL L{target_level+1} (size={pos['size']:.4f})")
            if available_levels:
                print(f"[SELL_MATCH] Available buy positions: {', '.join(available_levels[:5])}")
        
        return None
    
    def update_inventory(
        self, direction: str, size: float, level_index: int, order_leg: str | None = None
    ) -> None:
        """
        Update inventory after order execution.

        Parameters
        ----------
        direction : str
            'buy' or 'sell'
        size : float
            Position size executed
        level_index : int
            Grid level index
        """
        level_key = f"{direction}_L{level_index + 1}"

        # Update inventory tracker
        # - Core long grid: BUY increases long exposure, SELL reduces long exposure
        # - Short overlay: SELL (leg=short_open) increases short exposure, BUY (leg=short_cover) reduces short exposure
        if order_leg == "short_open":
            self.inventory_tracker.update(short_size=size, grid_level=level_key)
            return
        if order_leg == "short_cover":
            self.inventory_tracker.update(short_size=-size, grid_level=level_key)
            return

        if direction == "buy":
            self.inventory_tracker.update(long_size=size, grid_level=level_key)
        else:
            self.inventory_tracker.update(long_size=-size, grid_level=level_key)

    def add_short_position(self, sell_level_index: int, size: float, sell_price: float) -> None:
        """Add a short position (opened by SELL) with target cover buy level."""
        if sell_level_index not in self.short_positions:
            self.short_positions[sell_level_index] = []
        # Cover one level below entry (top-band micro-grid) to avoid "cover all the way to mid".
        target_buy_level = max(0, int(sell_level_index) - 1)
        self.short_positions[sell_level_index].append({
            "size": float(size),
            "sell_price": float(sell_price),
            "target_buy_level": int(target_buy_level),
        })

    def match_cover_order(
        self, buy_level_index: int, buy_size: float
    ) -> Optional[Tuple[int, float, float]]:
        """
        Match a BUY cover order against short positions.

        Returns:
            (sell_level_index, sell_price, matched_size) if matched, else None.
        """
        for sell_level_idx, positions in list(self.short_positions.items()):
            for pos_idx, pos in enumerate(positions):
                if int(pos.get("target_buy_level", -1)) == int(buy_level_index):
                    matched_size = min(float(buy_size), float(pos["size"]))
                    sell_price = float(pos["sell_price"])
                    pos["size"] -= matched_size
                    if pos["size"] < 0.0001:
                        positions.pop(pos_idx)
                    if not positions:
                        del self.short_positions[sell_level_idx]
                    return (int(sell_level_idx), sell_price, matched_size)
        return None

    def reset_filled_level(self, direction: str, level_index: int) -> None:
        """
        Reset a filled level (allow re-triggering).

        Call this when the opposite side is triggered or position is closed.

        Parameters
        ----------
        direction : str
            'buy' or 'sell'
        level_index : int
            Grid level index
        """
        level_key = f"{direction}_L{level_index + 1}"
        if level_key in self.filled_levels:
            del self.filled_levels[level_key]

    def check_risk_level(
        self,
        current_price: float,
        equity: float,
        unrealized_pnl: float,
        current_time: Optional[datetime] = None,
    ) -> Tuple[int, bool, Optional[str]]:
        """
        Check current risk level and whether grid should be shut down.
        
        Returns:
        -------
        Tuple[int, bool, Optional[str]]
            (risk_level, should_shutdown, shutdown_reason)
            - risk_level: 0=normal, 1=mild, 2=moderate, 3=severe, 4=shutdown
            - should_shutdown: True if grid should be disabled
            - shutdown_reason: Reason for shutdown (if any)
        """
        if not getattr(self.config, "enable_mm_risk_zone", False):
            return 0, False, None
        
        # Calculate risk zone thresholds
        risk_zone_threshold = self.config.support + (self.current_atr * self.config.cushion_multiplier)
        level3_threshold = self.config.support - (getattr(self.config, "mm_risk_level3_atr_mult", 2.0) * self.current_atr)
        shutdown_price_threshold = self.config.support - (getattr(self.config, "max_risk_atr_mult", 3.0) * self.current_atr)
        
        # Calculate inventory risk
        # Risk should be measured against max capacity (equity * leverage), not just equity
        inventory_state = self.inventory_tracker.get_state()
        inv_notional = abs(inventory_state.net_exposure) * current_price if current_price > 0 else 0.0
        max_capacity = equity * self.config.leverage if equity > 0 else 1.0
        inv_risk_pct = inv_notional / max_capacity if max_capacity > 0 else 999.0
        
        # Calculate profit buffer (if enabled)
        profit_buffer = 0.0
        if getattr(self.config, "enable_profit_buffer", True):
            profit_buffer = self.realized_pnl * getattr(self.config, "profit_buffer_ratio", 0.5)
        
        # Adjust risk thresholds with profit buffer
        max_loss_pct = getattr(self.config, "max_risk_loss_pct", 0.30)
        adjusted_loss_threshold = max_loss_pct - (profit_buffer / equity) if equity > 0 else max_loss_pct
        
        # Determine risk level
        risk_level = 0
        should_shutdown = False
        shutdown_reason = None
        
        if current_price < shutdown_price_threshold:
            # Level 4: Extreme risk - shutdown
            risk_level = 4
            should_shutdown = True
            shutdown_reason = f"Price below shutdown threshold (support - {getattr(self.config, 'max_risk_atr_mult', 3.0)} × ATR)"
        elif unrealized_pnl < -adjusted_loss_threshold * equity:
            # Level 4: Unrealized loss exceeds threshold (with profit buffer)
            risk_level = 4
            should_shutdown = True
            shutdown_reason = f"Unrealized loss exceeds {max_loss_pct:.0%} equity (adjusted: {adjusted_loss_threshold:.0%} with profit buffer)"
        elif inv_risk_pct > getattr(self.config, "max_risk_inventory_pct", 0.8):
            # Level 4: Inventory risk too high
            risk_level = 4
            should_shutdown = True
            shutdown_reason = f"Inventory risk exceeds {getattr(self.config, 'max_risk_inventory_pct', 0.8):.0%} capacity"
        elif current_price < level3_threshold:
            # Level 3: Severe risk
            risk_level = 3
        elif current_price < risk_zone_threshold:
            # Level 1 or 2: Mild/Moderate risk
            # Note: Level 2 would require time tracking, but user prefers manual control
            # So we'll use Level 1 for now
            risk_level = 1
        else:
            # Normal
            risk_level = 0
        
        # Update risk state
        self.risk_level = risk_level
        if risk_level > 0 and self.risk_zone_entry_time is None:
            self.risk_zone_entry_time = current_time if current_time else datetime.now()
        elif risk_level == 0:
            self.risk_zone_entry_time = None
        
        # Update grid enabled state
        if should_shutdown and self.grid_enabled:
            self.grid_enabled = False
            self.grid_shutdown_reason = shutdown_reason
            # ENHANCED: Track shutdown time for cooldown period
            self.grid_shutdown_time = current_time if current_time else datetime.now()
            # Note: grid_shutdown_bar_index should be set by caller (algorithm.py)
        elif not should_shutdown and not self.grid_enabled:
            # ENHANCED: Auto re-enable with cooldown and price recovery verification
            can_re_enable = self._can_re_enable_grid(current_price, current_time)
            if can_re_enable:
                self.grid_enabled = True
                self.grid_shutdown_reason = None
                self.risk_zone_entry_time = None
                self.grid_shutdown_time = None
                self.grid_shutdown_bar_index = None
        
        return risk_level, should_shutdown, shutdown_reason
    
    def _can_re_enable_grid(
        self,
        current_price: float,
        current_time: Optional[datetime] = None,
    ) -> bool:
        """
        ENHANCED: Check if grid can be re-enabled after shutdown.
        
        Conditions:
        1. Cooldown period must have elapsed (if configured)
        2. Price must have recovered to support + recovery_threshold × ATR (if configured)
        3. Manual approval may be required (if configured)
        
        Parameters
        ----------
        current_price : float
            Current market price
        current_time : Optional[datetime]
            Current timestamp
            
        Returns
        -------
        bool
            True if grid can be re-enabled, False otherwise
        """
        # If grid is already enabled, no need to check
        if self.grid_enabled:
            return True
        
        # Check cooldown period
        cooldown_bars = getattr(self.config, "grid_re_enable_cooldown_bars", 1440)
        if cooldown_bars > 0 and self.grid_shutdown_bar_index is not None:
            # Get current bar index from caller (should be passed via check_risk_level)
            # For now, we'll use time-based check if bar_index is not available
            if self.grid_shutdown_time is not None:
                time_elapsed = (current_time if current_time else datetime.now()) - self.grid_shutdown_time
                # Approximate: 1 bar = 1 minute for 1m timeframe
                bars_elapsed = int(time_elapsed.total_seconds() / 60)
                if bars_elapsed < cooldown_bars:
                    return False  # Cooldown not expired
        
        # Check price recovery
        recovery_atr_mult = getattr(self.config, "grid_re_enable_price_recovery_atr_mult", 1.0)
        if recovery_atr_mult > 0:
            recovery_threshold = self.config.support + (recovery_atr_mult * self.current_atr)
            if current_price < recovery_threshold:
                return False  # Price has not recovered
        
        # Check manual approval requirement
        requires_approval = getattr(self.config, "grid_re_enable_requires_manual_approval", False)
        if requires_approval:
            # Manual approval would be checked externally (e.g., via file or API)
            # For now, we assume manual approval is granted if this method is called
            # In practice, the caller should check for manual approval before calling
            pass
        
        return True
    
    def set_grid_shutdown_bar_index(self, bar_index: int) -> None:
        """
        ENHANCED: Set the bar index when grid was shut down.
        
        This is used for cooldown period calculation.
        
        Parameters
        ----------
        bar_index : int
            Bar index when grid was shut down
        """
        self.grid_shutdown_bar_index = bar_index
    
    def enable_grid(self) -> None:
        """Manually re-enable grid after shutdown."""
        self.grid_enabled = True
        self.risk_level = 0
        self.risk_zone_entry_time = None
        self.grid_shutdown_reason = None
    
    def update_realized_pnl(self, pnl: float) -> None:
        """Update realized PnL for profit buffer calculation."""
        self.realized_pnl += pnl
    
    def get_inventory_state(self) -> dict:
        """
        Get current inventory state.

        Returns
        -------
        dict
            Inventory state information
        """
        state = self.inventory_tracker.get_state()
        return {
            "long_exposure": state.long_exposure,
            "short_exposure": state.short_exposure,
            "net_exposure": state.net_exposure,
            "long_pct": state.long_pct,
            "short_pct": state.short_pct,
            "filled_levels_count": len(self.filled_levels),
            "risk_level": self.risk_level,
            "grid_enabled": self.grid_enabled,
            "grid_shutdown_reason": self.grid_shutdown_reason,
        }
    
    def force_close_all_positions(
        self,
        holdings_btc: float,
        current_price: float,
        current_time: Optional[datetime] = None,
    ) -> Optional[dict]:
        """
        ENHANCED: Force close all positions (position-level stop loss).
        
        This method is called when Level 4 risk is detected and 
        enable_position_level_stop_loss is True. It returns a market order
        instruction to close all positions immediately.
        
        Parameters
        ----------
        holdings_btc : float
            Current holdings in BTC
        current_price : float
            Current market price
        current_time : Optional[datetime]
            Current timestamp
            
        Returns
        -------
        Optional[dict]
            Order instruction dict if positions need to be closed, None otherwise.
            Format: {
                "direction": "sell",
                "quantity": holdings_btc,
                "price": None,  # Market order
                "level": -1,  # Not a grid level
                "reason": "Position-level stop loss triggered",
                "timestamp": current_time,
            }
        """
        # Check if position-level stop loss is enabled
        if not getattr(self.config, "enable_position_level_stop_loss", True):
            return None
        
        # Only close if we have positions
        if holdings_btc <= 0:
            return None
        
        # Return market order instruction to close all positions
        return {
            "symbol": getattr(self.config, "symbol", "BTCUSDT"),
            "direction": "sell",
            "quantity": holdings_btc,
            "price": None,  # Market order - immediate execution
            "level": -1,  # Sentinel: not a grid level
            "reason": f"Position-level stop loss triggered (risk_level=4, reason={self.grid_shutdown_reason})",
            "timestamp": current_time if current_time else datetime.now(),
        }
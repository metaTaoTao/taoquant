"""
Grid Manager for TaoGrid Lean Algorithm.

This helper class manages grid state and integrates with taoquant modules.
"""

from __future__ import annotations

import sys
from pathlib import Path
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

        # ATR tracking for spacing calculation
        self.current_atr: float = 0.0
        self.avg_atr: float = 0.0

        # Track filled grid levels to avoid re-triggering
        # Key: "buy_L1", "sell_L2", etc.
        # Value: True if filled (waiting for exit)
        self.filled_levels: Dict[str, bool] = {}
        
        # Track buy positions and their target sell levels
        # Key: buy_level_index (int)
        # Value: list of positions with size and target sell level
        # Each position: {'size': float, 'buy_price': float, 'target_sell_level': int}
        self.buy_positions: Dict[int, List[dict]] = {}
        
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

        # Calculate mid price
        mid = (self.config.support + self.config.resistance) / 2

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

        # Calculate weights
        self.buy_weights = calculate_level_weights(
            num_levels=self.config.grid_layers_buy, weight_k=self.config.weight_k
        )
        self.sell_weights = calculate_level_weights(
            num_levels=self.config.grid_layers_sell, weight_k=self.config.weight_k
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
        self.buy_weights = self.buy_weights * buy_ratio
        self.sell_weights = self.sell_weights * sell_ratio
        
        # Initialize pending limit orders: place buy orders at all buy levels
        self._initialize_pending_orders()

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
        
        # Place buy limit orders at all buy levels
        for i, level_price in enumerate(self.buy_levels):
            level_key = f"buy_L{i+1}"
            # Only place if not already filled
            if not self.filled_levels.get(level_key, False):
                self.pending_limit_orders.append({
                    'direction': 'buy',
                    'level_index': i,
                    'price': level_price,
                    'size': None,  # Will be calculated when order is triggered
                    'placed': True,
                    'last_checked_bar': None,  # Track which bar we last checked
                })
    
    def check_limit_order_triggers(
        self, 
        current_price: float,
        prev_price: Optional[float] = None,
        bar_high: Optional[float] = None,
        bar_low: Optional[float] = None,
        bar_index: Optional[int] = None
    ) -> Optional[dict]:
        """
        Check if any pending limit order is triggered by price movement.
        
        Limit order trigger logic (grid strategy):
        - Buy limit order: triggers when bar_low <= limit_price (price touches or crosses limit)
        - Sell limit order: triggers when bar_high >= limit_price (price touches or crosses limit)
        
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
        
        # Check each pending limit order
        for order in self.pending_limit_orders:
            if not order.get('placed', False):
                continue
            
            # Skip if already triggered in this bar (will be removed after fill)
            if order.get('triggered', False):
                continue
            
            direction = order['direction']
            limit_price = order['price']
            level_index = order['level_index']
            
            # Avoid duplicate triggers in same bar
            if bar_index is not None and order.get('last_checked_bar') == bar_index:
                continue
            
            # Check if limit order is triggered
            triggered = False
            
            if direction == 'buy':
                # Buy limit: triggers when bar_low <= limit_price
                # Grid strategy: if price touches or goes below limit, order fills
                if bar_low is not None:
                    triggered = bar_low <= limit_price
                else:
                    # Fallback: use current price
                    triggered = current_price <= limit_price
                
                # Also check if level is already filled
                level_key = f"buy_L{level_index + 1}"
                if self.filled_levels.get(level_key, False):
                    triggered = False
                    
            elif direction == 'sell':
                # Sell limit: triggers when bar_high >= limit_price
                # Grid strategy: if price touches or goes above limit, order fills
                if bar_high is not None:
                    triggered = bar_high >= limit_price
                else:
                    # Fallback: use current price
                    triggered = current_price >= limit_price

                # Traditional Grid: FREE SELL (not forced pairing)
                # Sell whenever we have long positions AND price reaches sell level
                # No need to match specific buy[i] -> sell[i]
                # This maximizes turnover and captures all profitable opportunities

                # Check if we have ANY long position
                inventory_state = self.inventory_tracker.get_state()
                if inventory_state.long_exposure > 0:
                    # We have long positions, can sell
                    pass  # Keep triggered as is
                else:
                    # No long positions, cannot sell
                    triggered = False
            
            if triggered:
                # Mark this bar as checked to avoid duplicate triggers
                # Also mark order as triggered so it won't trigger again until filled
                if bar_index is not None:
                    order['last_checked_bar'] = bar_index
                order['triggered'] = True  # Mark as triggered
                # Return triggered order (size will be calculated in on_data)
                return order
        
        return None
    
    def remove_pending_order(self, direction: str, level_index: int) -> None:
        """
        Remove a pending limit order after it's been filled.
        
        Parameters
        ----------
        direction : str
            'buy' or 'sell'
        level_index : int
            Grid level index
        """
        self.pending_limit_orders = [
            order for order in self.pending_limit_orders
            if not (order['direction'] == direction and order['level_index'] == level_index)
        ]
    
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
        level_price: float
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
            if order['direction'] == direction and order['level_index'] == level_index:
                return  # Already exists
        
        # Add new pending order
        self.pending_limit_orders.append({
            'direction': direction,
            'level_index': level_index,
            'price': level_price,
            'size': None,  # Will be calculated when triggered
            'placed': True,
            'last_checked_bar': None,  # Track which bar we last checked
        })
    
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

        # Apply throttling if enabled
        if self.config.enable_throttling:
            inventory_state = self.inventory_tracker.get_state()
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

            return size_btc, throttle_status
        else:
            from risk_management.grid_risk_manager import ThrottleStatus

            return base_size_btc, ThrottleStatus(size_multiplier=1.0, reason="No throttle")

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
        # Find buy position targeting this sell level
        for buy_level_idx, positions in list(self.buy_positions.items()):
            for pos_idx, pos in enumerate(positions):
                if pos.get('target_sell_level') == sell_level_index:
                    # Match found
                    matched_size = min(sell_size, pos['size'])
                    buy_price = pos['buy_price']
                    
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
                    
                    return (buy_level_idx, buy_price, matched_size)
        
        return None
    
    def update_inventory(
        self, direction: str, size: float, level_index: int
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
        if direction == "buy":
            self.inventory_tracker.update(
                long_size=size, grid_level=level_key
            )
        else:
            self.inventory_tracker.update(
                short_size=size, grid_level=level_key
            )

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
        }

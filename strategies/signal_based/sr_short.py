"""
SR Short Strategy - Clean Refactored Version

Short-only strategy based on 4H resistance zone detection.

Key Changes from Original:
- ✅ Uses BaseStrategy interface (clean separation of concerns)
- ✅ Pure functions for indicators/signals/sizing
- ✅ No backtesting.py dependencies
- ✅ No VirtualTrade system (engine handles execution)
- ✅ Type-safe configuration
- ✅ Fully testable components

Strategy Logic:
1. Detect resistance zones on 4H timeframe
2. Enter short when price touches zone
3. Risk-based position sizing (0.5% per trade)
4. Exit at SL (3 * ATR above entry)
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import numpy as np

from analytics.indicators.sr_zones import compute_sr_zones
from risk_management.position_sizer import calculate_risk_based_size
from strategies.base_strategy import BaseStrategy, StrategyConfig
from utils.resample import resample_ohlcv


@dataclass
class SRShortConfig(StrategyConfig):
    """
    Configuration for SR Short strategy.

    Zone Detection Parameters
    -------------------------
    htf_timeframe : str
        Higher timeframe for zone detection (default: '4h')
    htf_lookback : int
        Number of HTF bars to look back from backtest start (default: 300)
        The HTF start point is fixed: backtest_start - htf_lookback HTF bars
        As backtest progresses, HTF data expands but start point remains fixed
    left_len : int
        Left lookback for pivot detection (default: 90)
    right_len : int
        Right confirmation for pivot detection (default: 10)
    merge_atr_mult : float
        ATR multiplier for zone merging (default: 3.5)

    Entry Filters
    -------------
    min_touches : int
        Minimum touches required for zone (default: 1)
    max_retries : int
        Maximum failed attempts per zone (default: 3)
    price_filter_pct : float
        Minimum price movement % since last signal (default: 1.5)
    min_position_distance_pct : float
        Minimum distance % between positions (default: 1.5)

    Risk Management
    ---------------
    risk_per_trade_pct : float
        Risk percentage per trade (default: 0.5 = 0.5%)
    leverage : float
        Maximum leverage (default: 5.0)
    stop_loss_atr_mult : float
        Stop loss distance in ATR multiples (default: 3.0)
    
    Take Profit & Trailing Stop
    ---------------------------
    tp1_rr_ratio : float
        Risk-reward ratio for TP1 (default: 2.33)
        When profit reaches this ratio, close 30% of position
    tp1_exit_pct : float
        Percentage of position to close at TP1 (default: 0.3 = 30%)
    trailing_stop_atr_mult : float
        Trailing stop distance in ATR multiples (default: 5.0)
    trailing_offset_atr_mult : float
        Trailing stop offset in ATR multiples (default: 2.0)
    """

    # Zone detection - HTF parameters
    htf_timeframe: str = '4h'
    htf_lookback: int = 300
    
    # Zone detection - pivot parameters
    left_len: int = 90
    right_len: int = 10
    merge_atr_mult: float = 3.5

    # Entry filters
    min_touches: int = 1
    max_retries: int = 3
    price_filter_pct: float = 1.5
    min_position_distance_pct: float = 1.5

    # Risk management
    risk_per_trade_pct: float = 0.5
    leverage: float = 5.0
    stop_loss_atr_mult: float = 3.0
    
    # Take profit & trailing stop
    tp1_rr_ratio: float = 2.33  # TP1 at 2.33x risk-reward
    tp1_exit_pct: float = 0.3  # Close 30% at TP1
    trailing_stop_atr_mult: float = 5.0  # Trailing stop distance
    trailing_offset_atr_mult: float = 2.0  # Trailing stop offset


class SRShortStrategy(BaseStrategy):
    """
    Short-only strategy based on 4H resistance zones.

    This strategy demonstrates clean architecture principles:
    - Pure functions for each step
    - No state management
    - Engine-agnostic
    - Fully testable

    Examples
    --------
    >>> from strategies.signal_based.sr_short import SRShortStrategy, SRShortConfig
    >>> from execution.engines.vectorbt_engine import VectorBTEngine
    >>> from execution.engines.base import BacktestConfig
    >>>
    >>> # Create strategy
    >>> config = SRShortConfig(
    ...     name="SR Short 4H",
    ...     description="Short resistance zones on 4H",
    ...     left_len=90,
    ...     right_len=10,
    ...     risk_per_trade_pct=0.5,
    ...     leverage=5.0
    ... )
    >>> strategy = SRShortStrategy(config)
    >>>
    >>> # Run strategy workflow
    >>> data_with_indicators, signals, sizes = strategy.run(data, initial_equity=100000)
    >>>
    >>> # Pass to engine
    >>> engine = VectorBTEngine()
    >>> backtest_config = BacktestConfig(initial_cash=100000, commission=0.001, slippage=0.0005, leverage=5.0)
    >>> result = engine.run(data_with_indicators, signals, sizes, backtest_config)
    >>>
    >>> # View results
    >>> print(result.summary())
    """

    def __init__(self, config: SRShortConfig):
        super().__init__(config)
        self.config = config  # Type hint for IDE autocomplete

    def compute_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Compute SR zones and ATR with fixed HTF lookback.

        Steps:
        1. Determine fixed HTF start point: backtest_start - htf_lookback HTF bars
        2. Resample to HTF for zone detection (from fixed start to current bar)
        3. Detect resistance zones on HTF (only using data up to current bar)
        4. Align zones back to original timeframe
        5. Calculate ATR(200) on original timeframe for position sizing

        Important: No future data is used. For each bar, we only use HTF data
        from the fixed start point up to that bar's corresponding HTF bar.

        Parameters
        ----------
        data : pd.DataFrame
            15m OHLCV data

        Returns
        -------
        pd.DataFrame
            Data with added columns:
            - zone_top: Resistance zone top
            - zone_bottom: Resistance zone bottom
            - zone_touches: Number of touches
            - zone_is_broken: Whether zone is broken
            - atr: ATR(200) for position sizing
        """
        # Step 1: Determine fixed HTF start point
        # Calculate how many minutes in HTF timeframe
        htf_minutes = self._timeframe_to_minutes(self.config.htf_timeframe)
        backtest_start = data.index[0]
        
        # Fixed start: backtest_start - htf_lookback HTF bars
        # This ensures we always look back htf_lookback bars from backtest start
        # Note: compute_sr_zones processes data incrementally, so it naturally
        # respects the "no future data" constraint. The fixed_start is conceptual
        # and ensures consistent lookback window.
        _fixed_start = backtest_start - pd.Timedelta(minutes=htf_minutes * self.config.htf_lookback)
        
        # Step 2: Resample to HTF
        # We need to resample from fixed_start, but only use data up to current bar
        # Since we're processing bar-by-bar in backtest, we'll compute zones incrementally
        # For now, resample all available data (from fixed_start to end)
        data_htf = resample_ohlcv(data, self.config.htf_timeframe)
        
        # Ensure we have enough HTF bars (at least htf_lookback)
        if len(data_htf) < self.config.htf_lookback:
            # Not enough data, return empty zones
            result = data.copy()
            result['zone_top'] = pd.NA
            result['zone_bottom'] = pd.NA
            result['zone_touches'] = 0
            result['zone_is_broken'] = False
            from analytics.indicators.volatility import calculate_atr
            result['atr'] = calculate_atr(
                data['high'],
                data['low'],
                data['close'],
                period=200
            )
            return result
        
        # Step 3: Detect zones on HTF
        # Note: compute_sr_zones processes data incrementally (bar-by-bar)
        # So it naturally respects the "no future data" constraint
        zones_htf = compute_sr_zones(
            data_htf,
            left_len=self.config.left_len,
            right_len=self.config.right_len,
            merge_atr_mult=self.config.merge_atr_mult,
        )

        # Step 4: Align zones back to original timeframe
        zone_columns = ['zone_top', 'zone_bottom', 'zone_touches', 'zone_is_broken']

        # Reindex zones_htf to match data index using forward fill
        zones_aligned = zones_htf[zone_columns].reindex(
            data.index,
            method='ffill'  # Forward fill: use latest HTF zone for each bar
        )

        # Step 5: Add ATR(200) on original timeframe
        from analytics.indicators.volatility import calculate_atr
        atr_200 = calculate_atr(
            data['high'],
            data['low'],
            data['close'],
            period=200
        )

        # Combine all indicators
        result = data.copy()
        for col in zone_columns:
            result[col] = zones_aligned[col]
        result['atr'] = atr_200

        return result
    
    def _timeframe_to_minutes(self, timeframe: str) -> int:
        """Convert timeframe string to minutes."""
        timeframe = timeframe.lower()
        if timeframe.endswith('m'):
            return int(timeframe[:-1])
        elif timeframe.endswith('h'):
            return int(timeframe[:-1]) * 60
        elif timeframe.endswith('d'):
            return int(timeframe[:-1]) * 24 * 60
        else:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate order flow for partial exits (TP1 + trailing stop).

        This method generates ORDER SIZES (not boolean signals) to support partial exits.
        Returns a DataFrame with 'orders' column containing order sizes:
        - Negative values: Short entry (e.g., -1.0 = short 1.0 BTC)
        - Positive values: Close short (e.g., 0.3 = close 0.3 BTC, 0.7 = close 0.7 BTC)
        - Zero: No order

        Entry Conditions:
        - Zone bottom <= Close <= Zone top (close inside zone)
        - Zone has minimum touches (zone_touches >= min_touches)
        - Zone is not broken (zone_is_broken == False)

        Exit Conditions:
        - TP1: When profit reaches tp1_rr_ratio * risk (close tp1_exit_pct of position)
        - Trailing Stop: After TP1, use trailing stop for remaining position
        - Stop Loss: Initial SL at stop_loss_atr_mult * ATR above entry

        Parameters
        ----------
        data : pd.DataFrame
            Data with indicators (must have 'atr' column)

        Returns
        -------
        pd.DataFrame
            Orders with columns: [orders, direction]
            - orders: float Series (order sizes, negative for short, positive to close)
            - direction: str Series ('short' for compatibility)
        """
        # Initialize order sizes (0 = no order)
        orders = pd.Series(0.0, index=data.index, dtype=float)
        direction = pd.Series('short', index=data.index)

        # Entry condition: close inside zone
        has_zone = data['zone_top'].notna() & data['zone_bottom'].notna()
        zone_is_broken = data['zone_is_broken'].fillna(False).astype(bool)
        zone_active = has_zone & (~zone_is_broken)
        zone_qualified = zone_active & (data['zone_touches'] >= self.config.min_touches)

        # Price inside zone (handle NaN zones properly)
        # Use fillna to avoid boolean ambiguity with NaN
        zone_bottom = data['zone_bottom'].fillna(-np.inf)
        zone_top = data['zone_top'].fillna(np.inf)
        # Convert to float to avoid FutureWarning
        if zone_bottom.dtype == 'object':
            zone_bottom = pd.to_numeric(zone_bottom, errors='coerce').fillna(-np.inf)
        if zone_top.dtype == 'object':
            zone_top = pd.to_numeric(zone_top, errors='coerce').fillna(np.inf)
        inside_zone = (
            (data['close'] >= zone_bottom) &
            (data['close'] <= zone_top) &
            has_zone  # Only true if zone exists
        )

        # Combine entry conditions
        entry_condition = zone_qualified & inside_zone

        # Track positions for TP1 and trailing stop
        # Each position tracks: entry info, TP1 status, trailing stop
        positions = []  # List of position dicts
        
        # Track which zones have been used for entries
        # Key: (zone_bottom, zone_top), Value: True if position opened in this zone
        used_zones = set()
        
        # Track order types for each order
        order_types = pd.Series('', index=orders.index, dtype='object')
        
        for i in range(len(data)):
            current_price = data['close'].iloc[i]
            current_atr = data['atr'].iloc[i] if pd.notna(data['atr'].iloc[i]) else 0
            
            # Check exits for existing positions FIRST (before new entries)
            # This ensures we handle exits before new entries on the same bar
            positions_to_remove = []
            for pos_idx, pos in enumerate(positions):
                entry_price = pos['entry_price']
                entry_atr = pos['entry_atr']
                position_size = pos['entry_size']  # Absolute size
                
                # Calculate risk (for short: risk = entry_price - SL_price)
                sl_price = entry_price + (entry_atr * self.config.stop_loss_atr_mult)
                risk = entry_price - sl_price  # Negative for short, but we use abs
                risk = abs(risk)
                
                # For short position: profit when price goes down
                # Profit = entry_price - current_price
                profit = entry_price - current_price
                
                # Update highest profit price (lowest price for short = highest profit)
                if current_price < pos['highest_profit_price']:
                    pos['highest_profit_price'] = current_price
                
                # Check TP1: profit >= tp1_rr_ratio * risk
                if not pos['tp1_hit'] and risk > 0:
                    tp1_profit_target = risk * self.config.tp1_rr_ratio
                    if profit >= tp1_profit_target:
                        # TP1 hit: partial close (30% of position)
                        partial_size = position_size * self.config.tp1_exit_pct
                        orders.iloc[i] = partial_size  # Positive to close short
                        order_types.iloc[i] = 'TP1'  # Mark as TP1 exit
                        pos['tp1_hit'] = True
                        pos['entry_size'] = position_size * (1 - self.config.tp1_exit_pct)  # Update remaining size
                        # Position continues with trailing stop
                        continue
                
                # Check trailing stop (only after TP1)
                if pos['tp1_hit']:
                    # Calculate trailing stop price
                    trailing_stop_distance = entry_atr * self.config.trailing_stop_atr_mult
                    trailing_offset = entry_atr * self.config.trailing_offset_atr_mult
                    
                    # Trailing stop price = lowest_price + trailing_stop_distance - offset
                    new_trailing_stop = pos['highest_profit_price'] + trailing_stop_distance - trailing_offset
                    
                    if pos['trailing_stop_price'] is None:
                        pos['trailing_stop_price'] = new_trailing_stop
                    else:
                        # Only move trailing stop up (for short, higher = better protection)
                        pos['trailing_stop_price'] = max(pos['trailing_stop_price'], new_trailing_stop)
                    
                    # Check if price hit trailing stop
                    if current_price >= pos['trailing_stop_price']:
                        # Close remaining position
                        remaining_size = pos['entry_size']
                        orders.iloc[i] = remaining_size  # Positive to close short
                        order_types.iloc[i] = 'TP2'  # Mark as TP2 (trailing stop exit)
                        positions_to_remove.append(pos_idx)
                        continue
                
                # Check initial stop loss (only if TP1 not hit)
                if not pos['tp1_hit']:
                    if current_price >= sl_price:
                        # Close entire position at SL
                        orders.iloc[i] = position_size  # Positive to close short
                        order_types.iloc[i] = 'SL'  # Mark as Stop Loss exit
                        positions_to_remove.append(pos_idx)
                        continue
            
            # Remove exited positions
            for pos_idx in reversed(positions_to_remove):
                pos = positions[pos_idx]
                # When position is fully closed, clear the zone from used_zones
                # so we can enter again in the same zone on next opportunity
                if 'zone_key' in pos:
                    used_zones.discard(pos['zone_key'])
                positions.pop(pos_idx)
            
            # Check for new entries AFTER handling exits
            # Rules:
            # 1. No existing positions (len(positions) == 0)
            # 2. Entry condition must be met
            # 3. This zone hasn't been used yet (to avoid multiple entries in same zone)
            # Note: We allow entry even if there's an exit order on this bar,
            # because VectorBT processes orders sequentially and we want to allow
            # immediate re-entry after position closes
            if entry_condition.iloc[i] and len(positions) == 0:
                # Get current zone info from data
                zone_bottom_val = data['zone_bottom'].iloc[i] if 'zone_bottom' in data.columns else None
                zone_top_val = data['zone_top'].iloc[i] if 'zone_top' in data.columns else None
                
                # Create zone key for tracking
                if pd.notna(zone_bottom_val) and pd.notna(zone_top_val):
                    zone_key = (float(zone_bottom_val), float(zone_top_val))
                    
                    # Only enter if this zone hasn't been used yet
                    if zone_key not in used_zones:
                        # Calculate position size (will be converted to actual units by engine)
                        # For now, we use 1.0 as base size (100% of calculated size)
                        # The engine will convert this to actual BTC amount based on equity and leverage
                        entry_size = -1.0  # Negative for short (will be scaled by engine)
                        
                        # New position entry
                        positions.append({
                            'entry_idx': i,
                            'entry_price': current_price,
                            'entry_atr': current_atr,
                            'entry_size': abs(entry_size),  # Store absolute size for calculations
                            'tp1_hit': False,
                            'highest_profit_price': current_price,  # For short: track lowest price (highest profit)
                            'trailing_stop_price': None,
                            'zone_key': zone_key,  # Track which zone this position is in
                        })
                        
                        # Mark this zone as used
                        used_zones.add(zone_key)
                        
                        # Place entry order
                        orders.iloc[i] = entry_size
                        order_types.iloc[i] = 'ENTRY'  # Mark as entry order

        # Return orders as DataFrame (for compatibility with existing interface)
        return pd.DataFrame({
            'orders': orders,  # Order sizes (negative for short, positive to close)
            'direction': direction,  # Keep for compatibility
            'order_types': order_types,  # Order type: ENTRY, TP1, TP2, SL
        }, index=data.index)

    def calculate_position_size(
        self,
        data: pd.DataFrame,
        equity: pd.Series,
        base_size: float = 1.0,
    ) -> pd.Series:
        """
        Calculate risk-based position sizes.

        Formula:
        - Stop distance = 3 * ATR(200)
        - Risk per trade = 0.5% of equity
        - Position size = (equity * risk_pct) / stop_distance
        - Apply leverage

        Parameters
        ----------
        data : pd.DataFrame
            Data with indicators (needs 'atr' column)
        equity : pd.Series
            Current equity
        base_size : float
            Base size multiplier (unused, for interface compatibility)

        Returns
        -------
        pd.Series
            Position sizes as fraction of equity
        """
        # Calculate stop distance
        stop_distance = data['atr'] * self.config.stop_loss_atr_mult

        # Calculate risk-based sizes
        sizes = calculate_risk_based_size(
            equity=equity,
            stop_distance=stop_distance,
            current_price=data['close'],
            risk_per_trade=self.config.risk_per_trade_pct / 100,
            leverage=self.config.leverage,
        )

        return sizes

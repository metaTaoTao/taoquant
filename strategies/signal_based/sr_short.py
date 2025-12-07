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
    
    Take Profit & Trailing Stop (Zero-Cost Position Strategy)
    ----------------------------------------------------------
    use_zero_cost_strategy : bool
        Use zero-cost position strategy (default: True)
        When True: Lock in initial risk at TP1, let rest run with trailing stop
        When False: Use fixed R:R ratio and exit percentage

    tp1_rr_ratio : float
        Risk-reward ratio for TP1 (default: 2.33) [if use_zero_cost_strategy=False]
    tp1_exit_pct : float
        Percentage to close at TP1 (default: 0.3 = 30%) [if use_zero_cost_strategy=False]

    zero_cost_trigger_rr : float
        Profit level to trigger zero-cost (default: 2.0 = 2R)
    zero_cost_lock_risk : bool
        True: Lock 1R profit at TP1, False: Move SL to breakeven (default: True)

    trailing_stop_atr_mult : float
        Trailing stop distance in ATR multiples (default: 5.0)
    trailing_offset_atr_mult : float
        Trailing stop offset in ATR multiples (default: 2.0)

    2B Reversal Strategy Parameters
    --------------------------------
    enable_2b_reversal : bool
        Enable 2B reversal strategy (default: False)
        2B: Resistance broken → stopped out → price falls back below resistance
        This confirms false breakout, creating strong short opportunity

    b2_time_window_hours : float
        Time window after stop loss (hours) (default: 48.0)
    b2_breakout_threshold_pct : float
        Minimum % below zone_bottom to trigger (default: 0.0)
        0.0 = trigger on close below zone_bottom
        0.3 = require 0.3% below zone_bottom

    b2_risk_per_trade_pct : float
        Risk % for 2B trades (default: 2.0 = 2%)
        Higher risk justified by higher win rate
    b2_stop_loss_atr_mult : float
        Stop loss for 2B trades in ATR (default: 3.0)
        Following 3-sigma principle

    b2_use_zero_cost_strategy : bool
        Use zero-cost strategy for 2B trades (default: True)
    b2_zero_cost_trigger_rr : float
        Zero-cost trigger for 2B trades (default: 2.0)
    b2_trailing_stop_atr_mult : float
        Trailing stop for 2B trades (default: 5.0)
    b2_trailing_offset_atr_mult : float
        Trailing offset for 2B trades (default: 2.0)
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
    
    # Take profit & trailing stop (Zero-Cost Position Strategy)
    # 零成本持仓策略：TP1锁定初始风险，剩余仓位用trailing stop保护
    use_zero_cost_strategy: bool = True  # 使用零成本持仓策略
    tp1_rr_ratio: float = 2.33  # TP1触发条件：盈利达到N倍风险（如果use_zero_cost_strategy=False）
    tp1_exit_pct: float = 0.3  # TP1平仓比例（如果use_zero_cost_strategy=False）

    # Zero-cost strategy parameters (when use_zero_cost_strategy=True)
    # 激进型配置：3.33R + 30% = 剩余70%继续持有
    zero_cost_trigger_rr: float = 3.33  # 达到3.33R时触发零成本策略
    zero_cost_exit_pct: float = 0.30  # 平掉30%锁定1R利润
    zero_cost_lock_risk: bool = True  # True: 锁定1R利润, False: 移动止损到入场价

    trailing_stop_atr_mult: float = 5.0  # Trailing stop distance
    trailing_offset_atr_mult: float = 2.0  # Trailing stop offset

    # ========================================
    # 2B Reversal Strategy Parameters
    # ========================================
    # 2B反转：阻力被突破后再次跌破，做空机会（假突破确认）

    enable_2b_reversal: bool = False  # 启用2B反转策略

    # 2B触发条件
    b2_time_window_hours: float = 48.0  # 止损后多久内有效（小时）
    b2_breakout_threshold_pct: float = 0.0  # 跌破zone_bottom的最小幅度（0=收盘价跌破即可）

    # 2B风险管理
    b2_risk_per_trade_pct: float = 2.0  # 2B单风险（%）- 更高风险因为胜率更高
    b2_stop_loss_atr_mult: float = 3.0  # 2B单止损倍数（ATR）- 3 sigma原则

    # 2B止盈策略（也使用零成本持仓）
    b2_use_zero_cost_strategy: bool = True  # 2B单使用零成本策略
    b2_zero_cost_trigger_rr: float = 2.0  # 2B单零成本触发条件
    b2_trailing_stop_atr_mult: float = 5.0  # 2B单trailing stop
    b2_trailing_offset_atr_mult: float = 2.0  # 2B单trailing offset


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

        # Map each 15m bar to its corresponding 4H bar (no forward fill!)
        # This ensures we only use zone data from the exact 4H bar, not from past bars
        htf_minutes = self._timeframe_to_minutes(self.config.htf_timeframe)
        data_with_htf_index = data.copy()
        data_with_htf_index['htf_time'] = data.index.floor(f'{htf_minutes}min')

        # Merge zones from 4H to 15m (left join on htf_time)
        zones_aligned = data_with_htf_index[['htf_time']].merge(
            zones_htf[zone_columns],
            left_on='htf_time',
            right_index=True,
            how='left'
        ).drop(columns=['htf_time'])

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
        # Each position tracks: entry info, TP1 status, trailing stop, is_2b_trade
        positions = []  # List of position dicts

        # Track which zones have been used for entries
        # Key: (zone_bottom, zone_top), Value: True if position opened in this zone
        used_zones = set()

        # Track zones that were broken (stopped out) for 2B reversal
        # Key: (zone_bottom, zone_top)
        # Value: {'stop_time': timestamp, 'stop_price': float, 'entry_price': float, 'entry_atr': float}
        broken_zones = {}

        # Track order types for each order
        order_types = pd.Series('', index=orders.index, dtype='object')
        
        for i in range(len(data)):
            current_price = data['close'].iloc[i]
            current_atr = data['atr'].iloc[i] if pd.notna(data['atr'].iloc[i]) else 0

            # Track if we had an exit on this bar to prevent same-bar re-entry
            had_exit_this_bar = False

            # Check exits for existing positions FIRST (before new entries)
            # This ensures we handle exits before new entries on the same bar
            positions_to_remove = []
            for pos_idx, pos in enumerate(positions):
                entry_price = pos['entry_price']
                entry_atr = pos['entry_atr']
                position_size = pos['entry_size']  # Absolute size
                is_2b_trade = pos.get('is_2b_trade', False)

                # Use different parameters for 2B trades
                if is_2b_trade:
                    stop_loss_mult = self.config.b2_stop_loss_atr_mult
                    trailing_stop_mult = self.config.b2_trailing_stop_atr_mult
                    trailing_offset_mult = self.config.b2_trailing_offset_atr_mult
                    use_zero_cost = self.config.b2_use_zero_cost_strategy
                    zero_cost_rr = self.config.b2_zero_cost_trigger_rr
                else:
                    stop_loss_mult = self.config.stop_loss_atr_mult
                    trailing_stop_mult = self.config.trailing_stop_atr_mult
                    trailing_offset_mult = self.config.trailing_offset_atr_mult
                    use_zero_cost = self.config.use_zero_cost_strategy
                    zero_cost_rr = self.config.zero_cost_trigger_rr

                # Calculate risk (for short: risk = entry_price - SL_price)
                sl_price = entry_price + (entry_atr * stop_loss_mult)
                risk = entry_price - sl_price  # Negative for short, but we use abs
                risk = abs(risk)
                
                # For short position: profit when price goes down
                # Profit = entry_price - current_price
                profit = entry_price - current_price
                
                # Update highest profit price (lowest price for short = highest profit)
                if current_price < pos['highest_profit_price']:
                    pos['highest_profit_price'] = current_price
                
                # Check TP1: Zero-Cost Position Strategy or Fixed R:R
                if not pos['tp1_hit'] and risk > 0:
                    # Determine which TP1 strategy to use (account for 2B trades)
                    if use_zero_cost:
                        # Zero-Cost Strategy: Trigger at zero_cost_trigger_rr
                        tp1_trigger_rr = zero_cost_rr
                        tp1_exit_pct = self.config.zero_cost_exit_pct
                    else:
                        # Traditional Fixed R:R Strategy
                        tp1_trigger_rr = self.config.tp1_rr_ratio
                        tp1_exit_pct = self.config.tp1_exit_pct

                    # Calculate profit ratio (profit / risk)
                    profit_ratio = profit / risk

                    # Check if TP1 should trigger
                    if profit_ratio >= tp1_trigger_rr:
                        # TP1 hit: partial close
                        # IMPORTANT: Use absolute BTC amount (not fraction)
                        # This is the amount to close, not remaining
                        partial_size = position_size * tp1_exit_pct
                        orders.iloc[i] = partial_size  # Positive to close short
                        order_types.iloc[i] = 'TP1'  # Mark as TP1 exit
                        pos['tp1_hit'] = True
                        pos['entry_size'] = position_size * (1 - tp1_exit_pct)  # Update remaining size

                        # Log zero-cost achievement
                        if self.config.use_zero_cost_strategy:
                            locked_profit = partial_size * profit / position_size
                            # For short: locked_profit should equal risk for zero-cost
                            print(f"[Zero-Cost TP1] Triggered at {profit_ratio:.2f}R, "
                                  f"Exit {tp1_exit_pct*100:.0f}%, "
                                  f"Locked ${locked_profit:.2f} ≈ Risk ${risk:.2f}")

                        # Position continues with trailing stop
                        continue
                
                # Check trailing stop (only after TP1)
                if pos['tp1_hit']:
                    # Calculate trailing stop price (use 2B parameters if applicable)
                    trailing_stop_distance = entry_atr * trailing_stop_mult
                    trailing_offset = entry_atr * trailing_offset_mult
                    
                    # Trailing stop price = lowest_price + trailing_stop_distance - offset
                    new_trailing_stop = pos['highest_profit_price'] + trailing_stop_distance - trailing_offset
                    
                    if pos['trailing_stop_price'] is None:
                        pos['trailing_stop_price'] = new_trailing_stop
                    else:
                        # Only move trailing stop up (for short, higher = better protection)
                        pos['trailing_stop_price'] = max(pos['trailing_stop_price'], new_trailing_stop)
                    
                    # Check if price hit trailing stop
                    if current_price >= pos['trailing_stop_price']:
                        # Close remaining position (100% of what's left)
                        # IMPORTANT: Use 1.0 (not absolute BTC amount) to close all remaining
                        # VectorBT interprets this as fraction of current_position_btc
                        orders.iloc[i] = 1.0  # Close 100% of remaining position
                        order_types.iloc[i] = 'TP2'  # Mark as TP2 (trailing stop exit)
                        positions_to_remove.append(pos_idx)
                        had_exit_this_bar = True
                        continue
                
                # Check initial stop loss (only if TP1 not hit)
                if not pos['tp1_hit']:
                    if current_price >= sl_price:
                        # Close entire position at SL (100% of current position)
                        # IMPORTANT: Use 1.0 to close all remaining (not absolute BTC amount)
                        orders.iloc[i] = 1.0  # Close 100% of position
                        order_types.iloc[i] = 'SL'  # Mark as Stop Loss exit
                        positions_to_remove.append(pos_idx)
                        had_exit_this_bar = True

                        # Record this zone as broken for potential 2B reversal
                        # Only record if this is NOT already a 2B trade and 2B is enabled
                        if self.config.enable_2b_reversal and not pos.get('is_2b_trade', False):
                            if 'zone_key' in pos:
                                zone_key = pos['zone_key']
                                current_time = data.index[i]
                                broken_zones[zone_key] = {
                                    'stop_time': current_time,
                                    'stop_price': current_price,
                                    'entry_price': pos['entry_price'],
                                    'entry_atr': pos['entry_atr'],
                                    'zone_bottom': zone_key[0],
                                    'zone_top': zone_key[1],
                                }
                                print(f"[2B Tracker] Zone {zone_key} broken at {current_time}, SL @ ${current_price:,.2f}")

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
            # Priority 1: Check 2B Reversal opportunities (higher priority)
            # Priority 2: Check normal entry conditions

            # ========================================
            # 2B Reversal Entry Check
            # ========================================
            b2_entry_triggered = False
            b2_zone_info = None

            if self.config.enable_2b_reversal and len(positions) == 0 and not had_exit_this_bar:
                current_time = data.index[i]

                # Check all broken zones for 2B reversal opportunities
                zones_to_remove = []
                for zone_key, zone_info in broken_zones.items():
                    # Time window check: within b2_time_window_hours
                    time_diff = (current_time - zone_info['stop_time']).total_seconds() / 3600
                    if time_diff > self.config.b2_time_window_hours:
                        # Expired, remove from broken_zones
                        zones_to_remove.append(zone_key)
                        continue

                    # Price check: closed below zone_bottom
                    zone_bottom = zone_info['zone_bottom']
                    breakout_threshold = zone_bottom * (1 - self.config.b2_breakout_threshold_pct / 100)

                    if current_price <= breakout_threshold:
                        # 2B Reversal triggered!
                        b2_entry_triggered = True
                        b2_zone_info = zone_info
                        zones_to_remove.append(zone_key)  # Remove after using

                        print(f"[2B Reversal] Triggered at {current_time}!")
                        print(f"  Zone: ${zone_bottom:,.2f} - ${zone_info['zone_top']:,.2f}")
                        print(f"  Stop time: {zone_info['stop_time']}, Window: {time_diff:.1f}h")
                        print(f"  Current price: ${current_price:,.2f} (below ${zone_bottom:,.2f})")
                        break  # Only take first 2B opportunity

                # Clean up expired/used zones
                for zone_key in zones_to_remove:
                    del broken_zones[zone_key]

            # ========================================
            # Execute 2B Entry or Normal Entry
            # ========================================
            if b2_entry_triggered:
                # 2B Reversal Entry
                zone_key = (b2_zone_info['zone_bottom'], b2_zone_info['zone_top'])

                # 2B trades use higher risk: 2% vs normal 0.5% = 4x multiplier
                # We encode this in the entry_size signal
                risk_multiplier = self.config.b2_risk_per_trade_pct / self.config.risk_per_trade_pct
                entry_size = -1.0 * risk_multiplier  # Negative for short, scaled by risk

                # Use 2B-specific risk parameters
                positions.append({
                    'entry_idx': i,
                    'entry_price': current_price,
                    'entry_atr': current_atr,
                    'entry_size': abs(entry_size),
                    'tp1_hit': False,
                    'highest_profit_price': current_price,
                    'trailing_stop_price': None,
                    'zone_key': zone_key,
                    'is_2b_trade': True,  # Mark as 2B trade
                    'b2_original_entry': b2_zone_info['entry_price'],  # Track original entry
                })

                # Mark zone as used (2B trades also consume the zone)
                used_zones.add(zone_key)

                # Place entry order
                orders.iloc[i] = entry_size
                order_types.iloc[i] = '2B_ENTRY'  # Mark as 2B reversal entry

            elif entry_condition.iloc[i] and len(positions) == 0 and not had_exit_this_bar:
                # Normal Entry (original logic)
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

        # Force close any remaining positions at the end of backtest
        # This ensures all PnL is realized and prevents unrealized P&L from affecting total_return
        if positions:
            last_bar_idx = len(data) - 1
            for pos in positions:
                # Close each remaining position at the last bar
                orders.iloc[last_bar_idx] = 1.0  # Close 100% of remaining position
                order_types.iloc[last_bar_idx] = 'FORCE_CLOSE'  # Mark as forced close at end
                print(f"[WARNING] Force closing position at end of backtest: Entry @ {pos['entry_price']}, Size @ {pos['entry_size']}")

        # Return orders as DataFrame (for compatibility with existing interface)
        return pd.DataFrame({
            'orders': orders,  # Order sizes (negative for short, positive to close)
            'direction': direction,  # Keep for compatibility
            'order_types': order_types,  # Order type: ENTRY, TP1, TP2, SL, FORCE_CLOSE
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

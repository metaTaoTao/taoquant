"""
SR Short Strategy - 4H Resistance Zone Detection

Multi-timeframe short-only strategy that:
- Detects resistance zones on 4H timeframe using pivot highs
- Generates signals on 4H bars (standard touch or 2B fakeout)
- Executes entries/exits on lower timeframe bars
- Manages multiple concurrent positions with independent tracking
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

import numpy as np
import pandas as pd
from backtesting import Strategy

from utils.resample import resample_ohlcv

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class Zone:
    """Resistance zone detected on higher timeframe."""
    
    top: float
    bottom: float
    touches: int = 1
    is_broken: bool = False
    fail_count: int = 0
    start_time: pd.Timestamp = field(default_factory=pd.Timestamp.now)
    end_time: pd.Timestamp = field(default_factory=pd.Timestamp.now)


@dataclass
class VirtualTrade:
    """Virtual trade tracking object."""
    
    trade_id: str
    entry_time: pd.Timestamp
    entry_price: float
    entry_high: float
    entry_atr: float  # This will now be ATR200
    zone_top: float
    sl_price: float
    tp_price: Optional[float]  # Fixed TP target (for first 30%)
    zone_idx: int
    position_qty: float
    
    # Strategy flags
    enable_trailing: bool = False
    trailing_active: bool = False
    
    is_active: bool = True
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    exit_reason: str = ""
    realized_pnl: float = 0.0
    lowest_price: float = field(default=float('inf'))  # Track lowest price since entry for trailing stop


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Average True Range using RMA (Wilder's Smoothing), matching TradingView.
    
    TV: ta.atr(length) = ta.rma(ta.tr, length)
    RMA is an exponentially weighted moving average with alpha = 1 / length.
    """
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Use ewm with alpha=1/period to match TV's RMA
    # adjust=False corresponds to the recursive definition: y[t] = (1-a)*y[t-1] + a*x[t]
    return tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()


def detect_pivot_high(high: pd.Series, left_len: int, right_len: int) -> pd.Series:
    """
    Detect pivot highs using pandas rolling.
    Equivalent to TV: pivothigh(high, left, right)
    
    A bar at index T is a pivot if high[T] is the maximum of the window [T-left, T+right].
    """
    # Calculate rolling max with window size = left + right + 1
    # rolling() by default is trailing. So value at T represents max of [T-(L+R), T].
    # We want the value at T+right to represent max of [T-left, T+right].
    # So we shift the rolling result backwards by right_len.
    
    window_size = left_len + right_len + 1
    
    # Use min_periods=window_size to mimic TV (returns NaN if not enough data)
    # Or min_periods=1 to allow edge cases? TV returns NaN at start. Let's be strict.
    rolling_max = high.rolling(window=window_size, min_periods=window_size).max()
    
    # Shift back so at index T, we compare with the window surrounding T
    shifted_max = rolling_max.shift(-right_len)
    
    # Pivot candidates: where price equals the local max
    candidates = high[high == shifted_max]
    
    # Filter duplicates: if multiple bars have the same max value in the window,
    # TV pivothigh usually returns the one that strictly satisfies the left/right condition.
    # My manual loop logic implemented: left < (or <= if first), right <= (strictly < ?)
    # Let's stick to the candidates for now to see if we get MORE.
    # If we get 100, 100, 100, all three will be in candidates.
    # This might result in overlapping zones, but they will be merged anyway.
    
    # Return a Series with same index as high, containing values only at pivots
    pivots = pd.Series(index=high.index, dtype=float)
    pivots.loc[candidates.index] = candidates
    
    return pivots


class SRShort4HResistance(Strategy):
    """
    Short-only strategy based on 4H resistance zone detection.
    
    This strategy:
    1. Resamples input data to 4H timeframe
    2. Detects resistance zones using pivot highs
    3. Generates signals when price touches zones (standard or 2B fakeout)
    4. Manages multiple concurrent positions independently
    5. Implements break-even and three-stage profit taking
    """
    
    # Zone detection parameters
    left_len: int = 90
    right_len: int = 10
    merge_atr_mult: float = 3.5
    break_tol_atr: float = 0.5
    min_touches: int = 1
    max_retries: int = 3
    
    # Signal filtering
    global_cd: int = 30  # Time cooldown (bars)
    price_filter_pct: float = 1.5  # Price distance filter %
    min_position_distance_pct: float = 1.5  # Min distance between positions %
    max_positions: int = 5  # Max concurrent positions
    
    # Position sizing
    risk_per_trade_pct: float = 0.5  # Risk % per trade
    leverage: float = 5.0  # Maximum leverage
    strategy_sl_percent: float = 2.0  # SL % above zone top
    
    # Exit parameters
    breakeven_ratio: float = 2.33  # Profit ratio to trigger break-even (for fixed TP part)
    trailing_pct: float = 70.0     # Percentage of position to use trailing stop
    trail_trigger_atr: float = 5.0 # Activation threshold (ATR multiple)
    trail_offset_atr: float = 2.0  # Trailing distance (ATR multiple)
    
    # Old params kept for compatibility or future use
    breakeven_close_pct: float = 30.0 
    tp1_atr_mult: float = 3.0
    tp1_close_pct: float = 40.0
    tp2_atr_mult: float = 5.0
    tp2_close_pct: float = 40.0
    tp3_atr_mult: float = 8.0
    tp3_close_pct: float = 20.0
    
    # Pre-computed 4H data (optional, for S/R zone detection)
    # If provided, will be used instead of resampling from current timeframe
    # Note: This must be a class variable for backtesting.py compatibility
    # The actual DataFrame will be set via strategy_params in run()
    htf_data = None
    
    def init(self):
        """Initialize strategy indicators and state."""
        # Validate TP percentages sum to 100%
        tp_total = self.tp1_close_pct + self.tp2_close_pct + self.tp3_close_pct
        if abs(tp_total - 100.0) > 0.01:
            raise ValueError(
                f"TP1% + TP2% + TP3% must equal 100%. Current total: {tp_total}%"
            )
        
        # Check if pre-computed 4H data is provided
        # backtesting.py passes run() kwargs as class attributes
        # This allows us to use separately fetched 4H data for S/R detection
        # while backtesting on 15m data, avoiding future function issues
        # Note: htf_data is defined as a class variable (can be None)
        htf_data_provided = self.htf_data
        
        if htf_data_provided is not None:
            # Use provided 4H data (pre-computed and truncated to avoid lookahead)
            if isinstance(htf_data_provided, pd.DataFrame):
                self.htf_data = htf_data_provided.copy()
                # Ensure index is datetime
                if not isinstance(self.htf_data.index, pd.DatetimeIndex):
                    if 'timestamp' in self.htf_data.columns:
                        self.htf_data.set_index('timestamp', inplace=True)
                # Ensure timezone-aware
                if self.htf_data.index.tz is None:
                    self.htf_data.index = self.htf_data.index.tz_localize('UTC')
                elif self.htf_data.index.tz != self.data.df.index.tz:
                    self.htf_data.index = self.htf_data.index.tz_convert(self.data.df.index.tz)
            else:
                raise ValueError("htf_data must be a pandas DataFrame")
        else:
            # Fallback: resample from current timeframe data (original behavior)
            # Convert column names to lowercase for resample_ohlcv
            # backtesting.py uses Capitalized columns, but resample_ohlcv expects lowercase
            df_for_resample = self.data.df.copy()
            column_mapping = {
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
            # Only rename columns that exist
            df_for_resample.rename(columns={k: v for k, v in column_mapping.items() if k in df_for_resample.columns}, inplace=True)
            
            # Resample to 4H for zone detection
            self.htf_data = resample_ohlcv(df_for_resample, "4h")
        
        if len(self.htf_data) == 0:
            raise ValueError("No data after resampling to 4H or provided 4H data is empty")
        
        # Calculate ATR on 4H timeframe
        self.htf_atr = calculate_atr(
            self.htf_data["high"],
            self.htf_data["low"],
            self.htf_data["close"],
            period=14,
        )
        
        # Calculate ATR(200) on 15m timeframe for SL/TP
        # Convert backtesting.py data arrays to pandas Series
        self.atr200 = calculate_atr(
            pd.Series(self.data.High, index=self.data.df.index),
            pd.Series(self.data.Low, index=self.data.df.index),
            pd.Series(self.data.Close, index=self.data.df.index),
            period=200
        )
        
        # State variables
        self.zones: list[Zone] = []
        self.virtual_trades: list[VirtualTrade] = []
        self.last_sig_idx: int = -1
        self.last_sig_price: float = 0.0
        self.active_zones_log: list[dict] = []  # Log of active zones per bar
        self.zone_history: list[dict] = []  # History of zones for plotting
        
        # Map current bar time to 4H bar index
        self._build_timeframe_map()
        
        # Track last 4H bar index to detect new bars
        self.last_htf_idx = -1
        
        # --- Pre-calculate Pivot Events for Incremental Simulation ---
        # detect_pivot_high returns a Series where index=pivot_bar_index, value=pivot_high_price
        raw_pivots = detect_pivot_high(self.htf_data["high"], self.left_len, self.right_len)
        
        # Map confirmation_idx -> (price, body_top, real_idx)
        self.pivot_events = {}
        # Debug: Store raw pivots for plotting
        self.debug_pivots = []
        
        high_values = self.htf_data["high"].values
        open_values = self.htf_data["open"].values
        close_values = self.htf_data["close"].values
        
        # raw_pivots has DatetimeIndex, so items() yields (Timestamp, value).
        # We need integer indices for calculations.
        # np.where returns a tuple, we take the first element (array of indices)
        pivot_indices = np.where(~np.isnan(raw_pivots.values))[0]
        
        print(f"[SR Strategy] Detected {len(pivot_indices)} raw pivots in 4H data.")
        
        for pivot_real_idx in pivot_indices:
            p_high = raw_pivots.values[pivot_real_idx]
            
            # Pivot is confirmed 'right_len' bars after it happens
            confirmation_idx = int(pivot_real_idx + self.right_len)
            
            if confirmation_idx < len(self.htf_data):
                # TV Logic: Body Top is max(open, close) at pivot bar
                p_body = max(open_values[pivot_real_idx], close_values[pivot_real_idx])
                self.pivot_events[confirmation_idx] = (p_high, p_body, pivot_real_idx)
                
                # Debug: Record pivot for plotting
                # Use pivot_real_idx timestamp (when it happened)
                self.debug_pivots.append({
                    "time": self.htf_data.index[pivot_real_idx],
                    "price": p_high,
                    "confirm_time": self.htf_data.index[confirmation_idx]
                })
        
        print(f"[SR Strategy] Generated {len(self.pivot_events)} pivot confirmation events.")
        
        # Store 4H data for plotting (expose for external access)
        self.htf_data_for_plot = self.htf_data.copy()
        
        # Store zones for plotting (will be updated during backtest)
        # We make it reference the same list as self.zones so it auto-updates
        self.zones_for_plot = self.zones
        
        # Track active zones per bar for CSV export
        self.active_zones_log: list[dict] = []
        
        # --- Catch-up Simulation ---
        # Simulate zone creation/breaks from the beginning of htf_data 
        # up to the start of the backtest. This ensures we have existing zones
        # when the backtest starts.
        
        # Find the 4H index corresponding to the first backtest bar
        start_htf_idx = 0
        if 0 in self.timeframe_map:
            start_htf_idx = self.timeframe_map[0]
        else:
            # Fallback if map is empty? Should not happen if data loaded.
            pass
            
        print(f"[SR Strategy] Catch-up simulation: Processing 4H bars 0 to {start_htf_idx-1}")
        
        for i in range(start_htf_idx):
            self._process_htf_bar(i)
            
        print(f"[SR Strategy] Catch-up complete. Active zones: {len(self.zones)}")

    def _build_timeframe_map(self):
        """
        Build mapping from current timeframe bars to 4H bars.
        
        Since resample_ohlcv uses label="right" and closed="right",
        the 4H bar timestamp represents the END of the 4H period.
        So a 15m bar at time T belongs to the 4H bar that ends at or after T.
        """
        self.timeframe_map = {}
        
        if len(self.htf_data) == 0:
            return
        
        for i, current_time in enumerate(self.data.df.index):
            # Find the 4H bar that contains this 15m bar
            # Since label="right", htf_data.index contains the END time of each 4H bar
            # So we need to find the first 4H bar whose end time >= current_time
            htf_idx = None
            for idx, htf_end_time in enumerate(self.htf_data.index):
                if current_time <= htf_end_time:
                    htf_idx = idx
                    break
            
            # If no 4H bar found (shouldn't happen), use the last one
            if htf_idx is None:
                htf_idx = len(self.htf_data) - 1
            
            self.timeframe_map[i] = htf_idx
    
    def _process_htf_bar(self, htf_idx: int):
        """
        Process a single confirmed 4H bar to update zones.
        Used for both initial catch-up and incremental updates during backtest.
        """
        if htf_idx < 0 or htf_idx >= len(self.htf_data):
            return
            
        current_close = self.htf_data["close"].iloc[htf_idx]
        
        # Use current ATR
        current_atr = self.htf_atr.iloc[htf_idx] if htf_idx < len(self.htf_atr) else 0.01
        if np.isnan(current_atr): current_atr = 0.01
            
        # 1. Check Breaks for ACTIVE zones
        for z in self.zones:
            if not z.is_broken:
                break_threshold = z.top + (current_atr * self.break_tol_atr)
                if current_close > break_threshold:
                    z.is_broken = True
                    z.end_time = self.htf_data.index[htf_idx]
        
        # 2. Check New Pivot Confirmation
        if htf_idx in self.pivot_events:
            p_high, p_body, pivot_real_idx = self.pivot_events[htf_idx]
            
            # Add thickness
            if (p_high - p_body) < (current_atr * 0.2):
                p_body = p_high - (current_atr * 0.2)
            
            merged = False
            tolerance = current_atr * self.merge_atr_mult
            
            for z in self.zones:
                if z.is_broken:
                    continue
                
                # TV Merge Logic
                if p_high <= (z.top + tolerance) and p_high >= (z.bottom - tolerance):
                    z.top = max(z.top, p_high)
                    z.bottom = min(z.bottom, p_body)
                    z.touches += 1
                    merged = True
                    break
            
            if not merged:
                new_z = Zone(
                    top=p_high,
                    bottom=p_body,
                    start_time=self.htf_data.index[pivot_real_idx],
                    end_time=self.htf_data.index[htf_idx],
                    touches=1,
                    is_broken=False
                )
                self.zones.append(new_z)

    def _update_zones(self):
        """
        Update resistance zones incrementally based on current confirmed 4H bar.
        This simulates the behavior of TradingView Pine Script bar-by-bar.
        """
        # Get current 15m index from backtesting data
        current_15m_idx = len(self.data) - 1
        curr_htf_idx = self.timeframe_map.get(current_15m_idx)
        
        if curr_htf_idx is None:
            return

        self._process_htf_bar(curr_htf_idx)
    
    def _get_htf_bar(self, current_idx: int) -> Optional[pd.Series]:
        """
        Get corresponding 4H bar data for current bar index.
        
        Returns the 4H bar that contains the current 15m bar.
        For signal detection, we use the completed 4H bar data.
        """
        if current_idx not in self.timeframe_map:
            return None
        
        htf_idx = self.timeframe_map[current_idx]
        if htf_idx >= len(self.htf_data):
            return None
        
        # Return the 4H bar that contains this 15m bar
        # Note: This returns the COMPLETED 4H bar, not a partial one
        return self.htf_data.iloc[htf_idx]
    
    def _get_current_htf_bar_partial(self, current_idx: int) -> Optional[pd.Series]:
        """
        Get partial 4H bar data up to current 15m bar.
        
        This calculates what the current 4H bar would look like
        if we resampled only up to the current 15m bar.
        Useful for debugging or real-time signal detection.
        """
        if current_idx < 0 or current_idx >= len(self.data.df):
            return None
        
        # Get the 4H bar that should contain this 15m bar
        htf_idx = self.timeframe_map.get(current_idx)
        if htf_idx is None or htf_idx >= len(self.htf_data):
            return None
        
        htf_end_time = self.htf_data.index[htf_idx]
        current_time = self.data.df.index[current_idx]
        
        # If current time is before the 4H bar end time, calculate partial bar
        if current_time < htf_end_time:
            # Find all 15m bars that belong to this 4H bar
            mask = (self.data.df.index <= current_time) & (self.data.df.index <= htf_end_time)
            if htf_idx > 0:
                prev_htf_end = self.htf_data.index[htf_idx - 1]
                mask = mask & (self.data.df.index > prev_htf_end)
            else:
                # First 4H bar: include from data start
                mask = mask & (self.data.df.index <= current_time)
            
            partial_data = self.data.df[mask]
            if len(partial_data) == 0:
                return None
            
            # Calculate partial OHLCV (backtesting.py uses Capitalized column names)
            partial_bar = pd.Series({
                "open": partial_data["Open"].iloc[0],
                "high": partial_data["High"].max(),
                "low": partial_data["Low"].min(),
                "close": partial_data["Close"].iloc[-1],
                "volume": partial_data["Volume"].sum(),
            }, name=current_time)
            return partial_bar
        
        # If current time equals or exceeds 4H bar end time, return completed bar
        return self.htf_data.iloc[htf_idx]
    
    def _get_htf_atr(self, current_idx: int) -> float:
        """Get ATR value for current bar's 4H timeframe."""
        if current_idx not in self.timeframe_map:
            return 0.01
        
        htf_idx = self.timeframe_map[current_idx]
        if htf_idx >= len(self.htf_atr):
            return self.htf_atr.iloc[-1] if len(self.htf_atr) > 0 else 0.01
        
        return self.htf_atr.iloc[htf_idx]
    
    def _check_cooldown(self, current_idx: int) -> bool:
        """Check if enough bars have passed since last signal."""
        if self.last_sig_idx < 0:
            return True
        return (current_idx - self.last_sig_idx) > self.global_cd
    
    def _check_price_filter(self, current_price: float) -> bool:
        """Check if price has moved enough since last signal."""
        if self.last_sig_price == 0.0:
            return True
        price_diff_pct = abs(current_price - self.last_sig_price) / self.last_sig_price * 100
        return price_diff_pct > self.price_filter_pct
    
    def _check_position_distance(self, entry_price: float) -> bool:
        """Check if new position would be too close to existing positions."""
        for trade in self.virtual_trades:
            if trade.is_active:
                price_diff_pct = abs(entry_price - trade.entry_price) / trade.entry_price * 100
                if price_diff_pct < self.min_position_distance_pct:
                    return False
        return True
    
    def _count_active_positions(self) -> int:
        """Count currently active virtual trades."""
        return sum(1 for t in self.virtual_trades if t.is_active)
    
    def _calculate_position_size(
        self, entry_price: float, stop_distance: float, equity: float
    ) -> float:
        """
        Calculate position size based on risk percentage.
        
        Parameters
        ----------
        entry_price : float
            Entry price
        stop_distance : float
            Distance to stop loss
        equity : float
            Current equity
        
        Returns
        -------
        float
            Position size (quantity)
        """
        # Risk amount based on risk_per_trade_pct
        risk_amount = equity * (self.risk_per_trade_pct / 100)
        
        # Base position size from risk
        position_qty = risk_amount / stop_distance
        
        # Check margin requirement with leverage
        position_value = position_qty * entry_price
        margin_required = position_value / self.leverage
        
        # Safety check: ensure we have enough capital for margin
        if margin_required > equity:
            position_qty = (equity * self.leverage) / entry_price
        
        return position_qty
    
    def _detect_signal(
        self, current_idx: int, htf_bar: pd.Series, htf_atr_val: float
    ) -> Optional[tuple[Zone, str]]:
        """
        Detect entry signal based on zone touch.
        User Request: Close inside zone = Short.
        """
        current_price = self.data.Close[current_idx]
        
        # Check cooldown and filters
        if not self._check_cooldown(current_idx):
            return None
        # Price filter removed/relaxed as per "Touch immediately" request, 
        # but kept method for structure. 
        if not self._check_price_filter(current_price):
             # Optional: Disable price filter if user wants aggressive entry
             pass 

        if not self._check_position_distance(current_price):
            return None
        if self._count_active_positions() >= self.max_positions:
            return None
        
        # Check each zone for signal
        # We use current_price (15m Close) as per user request: "15min内，close在我的阻力区间内"
        
        debug_info = []
        nearest_dist = float('inf')
        
        for zone in self.zones:
            if zone.is_broken:
                continue
            
            # Calculate distance for debugging
            # For short, we care if price is near zone bottom
            dist_to_bottom = zone.bottom - current_price
            if abs(dist_to_bottom) < abs(nearest_dist):
                nearest_dist = dist_to_bottom
                
            if zone.touches < self.min_touches:
                continue
            if zone.fail_count >= self.max_retries:
                continue
            
            # Condition: Zone Bottom <= Close <= Zone Top
            in_zone = zone.bottom <= current_price <= zone.top
            
            if in_zone:
                print(f"[Signal] TOUCH! Time: {self.data.df.index[current_idx]}, Price: {current_price:.2f}, Zone: {zone.bottom:.2f}-{zone.top:.2f}")
                return (zone, "InZone")
        
        # Debug log every 4 hours (roughly 16 bars) or if price is very close (within 1%)
        if current_idx % 16 == 0 or (nearest_dist != float('inf') and abs(nearest_dist) < current_price * 0.01):
             print(f"[Debug] Time: {self.data.df.index[current_idx]}, Price: {current_price:.2f}, Nearest Active Zone Dist: {nearest_dist:.2f}, Active Zones: {len([z for z in self.zones if not z.is_broken])}")
        
        return None
    
    def _create_virtual_trades(
        self,
        current_idx: int,
        zone: Zone,
        signal_type: str,
        entry_price: float,
        atr200_val: float,
        equity: float,
    ) -> list[VirtualTrade]:
        """
        Create 2 split virtual trades based on simplified strategy:
        1. (100 - trailing_pct)%: TP @ 2.33R, Fixed SL
        2. trailing_pct%: Trailing Stop after 3R move
        """
        entry_high = self.data.High[current_idx]
        zone_idx = self.zones.index(zone)
        
        # 1. Calculate SL Distance based on 3 * ATR(200)
        sl_distance = 3 * atr200_val
        sl_price = entry_price + sl_distance
        
        # 2. Calculate Position Size based on 0.5% Risk
        risk_amount = equity * 0.005
        total_qty = risk_amount / sl_distance
        
        # 3. Split Quantities
        # Trailing part
        q_trailing = total_qty * (self.trailing_pct / 100.0)
        # Fixed TP part (Remainder)
        q_fixed = total_qty - q_trailing
        
        trades = []
        base_id = f"SHORT_{current_idx}_{signal_type}"
        
        # Trade 1: Fixed TP @ 2.33R (The part to cover risk/zero cost)
        if q_fixed > 0:
            tp1_price = entry_price - (self.breakeven_ratio * sl_distance)
            
            trades.append(VirtualTrade(
                trade_id=f"{base_id}_Fixed",
                entry_time=self.data.df.index[current_idx],
                entry_price=entry_price,
                entry_high=entry_high,
                entry_atr=atr200_val,
                zone_top=zone.top,
                sl_price=sl_price,
                tp_price=tp1_price,
                zone_idx=zone_idx,
                position_qty=q_fixed,
                enable_trailing=False
            ))
        
        # Trade 2: Trailing Stop (The main runner)
        if q_trailing > 0:
            trades.append(VirtualTrade(
                trade_id=f"{base_id}_Trail",
                entry_time=self.data.df.index[current_idx],
                entry_price=entry_price,
                entry_high=entry_high,
                entry_atr=atr200_val,
                zone_top=zone.top,
                sl_price=sl_price,
                tp_price=None, # No fixed TP
                zone_idx=zone_idx,
                position_qty=q_trailing,
                enable_trailing=True,
                lowest_price=entry_price # Initialize lowest price
            ))
        
        return trades
    
    def _check_exits(self, current_idx: int):
        """
        Check exits for all 3 types of trades.
        """
        current_high = self.data.High[current_idx]
        current_low = self.data.Low[current_idx]
        current_close = self.data.Close[current_idx] # Used for trailing calc
        
        total_position_size = 0.0
        active_trades = [t for t in self.virtual_trades if t.is_active]
        
        for trade in active_trades:
            
            # 1. Check Trailing Activation & Update
            if trade.enable_trailing:
                # Update lowest price since entry (for Short)
                trade.lowest_price = min(trade.lowest_price, current_low)
                
                # Calculate profit distance in points
                # For Short: Entry - Lowest
                profit_dist = trade.entry_price - trade.lowest_price
                
                # Activation threshold: 5 * ATR (trail_points)
                activation_dist = self.trail_trigger_atr * trade.entry_atr
                
                if not trade.trailing_active:
                    if profit_dist >= activation_dist:
                        trade.trailing_active = True
                        
                # If active, update SL
                if trade.trailing_active:
                    # Logic: SL = Lowest Price + Offset (2 * ATR)
                    # As lowest price drops, SL drops. SL never goes up.
                    target_sl = trade.lowest_price + (self.trail_offset_atr * trade.entry_atr)
                    
                    # Update SL if target is lower (tighter) than current
                    if target_sl < trade.sl_price:
                        trade.sl_price = target_sl

            # 2. Check Stop Loss (Fixed or Trailed)
            if current_high >= trade.sl_price:
                trade.is_active = False
                trade.exit_time = self.data.df.index[current_idx]
                trade.exit_price = trade.sl_price
                trade.exit_reason = "SL/Trail"
                continue
            
            # 3. Check Fixed TP (Trade 1 only)
            if trade.tp_price is not None:
                if current_low <= trade.tp_price:
                    trade.is_active = False
                    trade.exit_time = self.data.df.index[current_idx]
                    trade.exit_price = trade.tp_price
                    trade.exit_reason = "TP"
                    continue

            # Accumulate remaining
            if trade.is_active:
                total_position_size += trade.position_qty
        
        # Update actual position
        self._sync_position(total_position_size)

    def _sync_position(self, target_size: float):
        """
        Sync actual position with target size (in BTC units).
        
        Converts BTC quantity to percentage of equity for backtesting.py compatibility.
        backtesting.py requires size to be either:
        - A fraction of equity (0 < size < 1), OR  
        - A whole number of units (size >= 1 and integer)
        
        We use percentage mode to support fractional BTC positions.
        """
        if target_size <= 0:
            # Close position if target is zero
            if self.position and self.position.size != 0:
                self.position.close()
            return
        
        # Get current price and equity for conversion
        current_idx = len(self.data) - 1
        current_price = self.data.Close[current_idx]
        equity = self.equity
        
        # Convert BTC quantity to percentage of equity
        # Formula: size_pct = (qty * price) / equity
        target_size_pct = (target_size * current_price) / equity
        
        # Ensure it's within valid range (0 < size < 1)
        if target_size_pct >= 1.0:
            target_size_pct = 0.99  # Cap at 99% of equity
        if target_size_pct <= 0:
            return
        
        # Get current position size
        if not self.position or self.position.size == 0:
            # No position, open new one
            self.sell(size=target_size_pct)
        else:
            # We have a position, need to adjust
            current_size = abs(self.position.size)
            
            # Convert current_size to percentage if needed
            # backtesting.py returns size as percentage if < 1, or units if >= 1
            if current_size >= 1.0:
                # It's in units, convert to percentage
                current_size_pct = (current_size * current_price) / equity
                if current_size_pct >= 1.0:
                    current_size_pct = 0.99
            else:
                # Already in percentage
                current_size_pct = current_size
            
            diff_pct = target_size_pct - current_size_pct
            
            # Adjust position if difference is significant
            if abs(diff_pct) > 0.0001:  # Tolerance for percentage
                if diff_pct > 0:
                    # Need to increase short position
                    self.sell(size=diff_pct)
                else:
                    # Need to reduce short position (buy back = close short)
                    # For short positions, buying reduces the position
                    self.buy(size=abs(diff_pct))
    
    def next(self):
        """Execute strategy logic on each bar."""
        current_idx = len(self.data) - 1
        
        # Get current 4H bar (may be partial if bar not yet confirmed)
        htf_bar = self._get_current_htf_bar_partial(current_idx)
        if htf_bar is None:
            # Fallback to completed bar
            htf_bar = self._get_htf_bar(current_idx)
            if htf_bar is None:
                return
        
        # Check if this is a new confirmed 4H bar (for zone updates)
        current_htf_idx = self.timeframe_map.get(current_idx, -1)
        current_time = self.data.df.index[current_idx]
        
        # Check if current 4H bar is confirmed (current time >= 4H bar end time)
        if current_htf_idx >= 0 and current_htf_idx < len(self.htf_data):
            htf_end_time = self.htf_data.index[current_htf_idx]
            is_htf_confirmed = current_time >= htf_end_time
            
            # Update zones only when a new 4H bar is confirmed
            if is_htf_confirmed and current_htf_idx != self.last_htf_idx:
                self._update_zones()
                self.last_htf_idx = current_htf_idx
        
        # Save current zones state for plotting
        # Record each zone's current state at this point in time
        current_time = self.data.df.index[current_idx]
        
        for zone in self.zones:
            # Check if this zone is already in history
            zone_found = False
            for hist_zone in self.zone_history:
                if (abs(hist_zone["top"] - zone.top) < 0.01 and 
                    abs(hist_zone["bottom"] - zone.bottom) < 0.01):
                    # Update existing zone
                    hist_zone["end_time"] = current_time
                    hist_zone["is_broken"] = zone.is_broken
                    hist_zone["touches"] = zone.touches
                    hist_zone["fail_count"] = zone.fail_count
                    zone_found = True
                    break
            
            if not zone_found:
                # New zone, add to history
                self.zone_history.append({
                    "start_time": zone.start_time if hasattr(zone, "start_time") else current_time,
                    "end_time": current_time,
                    "top": zone.top,
                    "bottom": zone.bottom,
                    "is_broken": zone.is_broken,
                    "touches": zone.touches,
                    "fail_count": zone.fail_count,
                })
        
        # Update zones_for_plot with current zones
        # Ensure end_time is updated for all zones
        for zone in self.zones:
            if hasattr(zone, 'end_time'):
                zone.end_time = current_time
        
        self.zones_for_plot = [Zone(
            top=z.top,
            bottom=z.bottom,
            touches=z.touches,
            is_broken=z.is_broken,
            fail_count=z.fail_count,
            start_time=z.start_time if hasattr(z, 'start_time') else current_time,
            end_time=z.end_time if hasattr(z, 'end_time') else current_time,
        ) for z in self.zones]
        
        # Get 4H ATR (use completed bar ATR for calculations)
        htf_atr_val = self._get_htf_atr(current_idx)
        
        # Check exits first
        self._check_exits(current_idx)
        
        # Check for new entry signal
        # Note: We allow multiple virtual trades even if we have a position
        # The position will be managed by _check_exits to match total virtual trade sizes
        
        # Detect signal
        signal_result = self._detect_signal(current_idx, htf_bar, htf_atr_val)
        if signal_result is None:
            return
        
        zone, signal_type = signal_result
        
        # Create virtual trades
        entry_price = self.data.Close[current_idx]
        equity = self.equity
        
        # Use current ATR200
        atr200_val = self.atr200.iloc[current_idx] if current_idx < len(self.atr200) else 0.01
        
        new_trades = self._create_virtual_trades(
            current_idx, zone, signal_type, entry_price, atr200_val, equity
        )
        
        # Store virtual trades
        self.virtual_trades.extend(new_trades)
        self.last_sig_idx = current_idx
        self.last_sig_price = entry_price
        
        # Update position immediately
        # Calculate total position size from all active trades
        total_size = sum(t.position_qty for t in self.virtual_trades if t.is_active)
        self._sync_position(total_size)


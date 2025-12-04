"""
SR Short Strategy - 4H Resistance Zone Detection (Fixed for Crypto)

FIXES:
- Use satoshi units instead of percentage to support precise fractional BTC positions
- 1 BTC = 100,000,000 satoshi (整数单位)
- This avoids backtesting.py's fractional trading limitation

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

# Satoshi conversion constant
SATOSHI_PER_BTC = 100_000_000


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
    """Virtual trade tracking object (positions in satoshi)."""

    trade_id: str
    entry_time: pd.Timestamp
    entry_price: float  # USDT per BTC
    entry_high: float
    entry_atr: float  # ATR200
    zone_top: float
    sl_price: float
    tp_price: Optional[float]
    zone_idx: int
    position_satoshi: int  # Position size in satoshi (integer)

    # Strategy flags
    enable_trailing: bool = False
    trailing_active: bool = False

    is_active: bool = True
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    exit_reason: str = ""
    realized_pnl: float = 0.0
    lowest_price: float = field(default=float('inf'))


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate ATR using RMA (Wilder's Smoothing), matching TradingView."""
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()


def detect_pivot_high(high: pd.Series, left_len: int, right_len: int) -> pd.Series:
    """Detect pivot highs using pandas rolling."""
    window_size = left_len + right_len + 1
    rolling_max = high.rolling(window=window_size, min_periods=window_size).max()
    shifted_max = rolling_max.shift(-right_len)
    candidates = high[high == shifted_max]

    pivots = pd.Series(index=high.index, dtype=float)
    pivots.loc[candidates.index] = candidates
    return pivots


class SRShort4HResistance(Strategy):
    """
    Short-only strategy based on 4H resistance zone detection.

    FIXED VERSION: Uses satoshi units for precise fractional BTC positions.
    """

    # Zone detection parameters
    left_len: int = 90
    right_len: int = 10
    merge_atr_mult: float = 3.5
    break_tol_atr: float = 0.5
    min_touches: int = 1
    max_retries: int = 3

    # Signal filtering
    global_cd: int = 30
    price_filter_pct: float = 1.5
    min_position_distance_pct: float = 1.5
    max_positions: int = 5

    # Position sizing
    risk_per_trade_pct: float = 0.5
    leverage: float = 5.0
    strategy_sl_percent: float = 2.0

    # Exit parameters
    breakeven_ratio: float = 2.33
    trailing_pct: float = 70.0
    trail_trigger_atr: float = 5.0
    trail_offset_atr: float = 2.0

    # Compatibility parameters
    breakeven_close_pct: float = 30.0
    tp1_atr_mult: float = 3.0
    tp1_close_pct: float = 40.0
    tp2_atr_mult: float = 5.0
    tp2_close_pct: float = 40.0
    tp3_atr_mult: float = 8.0
    tp3_close_pct: float = 20.0

    htf_data = None

    def init(self):
        """Initialize strategy indicators and state."""
        # Validate TP percentages
        tp_total = self.tp1_close_pct + self.tp2_close_pct + self.tp3_close_pct
        if abs(tp_total - 100.0) > 0.01:
            raise ValueError(f"TP percentages must sum to 100%. Current: {tp_total}%")

        # Setup 4H data
        htf_data_provided = self.htf_data

        if htf_data_provided is not None:
            if isinstance(htf_data_provided, pd.DataFrame):
                self.htf_data = htf_data_provided.copy()
                if not isinstance(self.htf_data.index, pd.DatetimeIndex):
                    if 'timestamp' in self.htf_data.columns:
                        self.htf_data.set_index('timestamp', inplace=True)
                if self.htf_data.index.tz is None:
                    self.htf_data.index = self.htf_data.index.tz_localize('UTC')
                elif self.htf_data.index.tz != self.data.df.index.tz:
                    self.htf_data.index = self.htf_data.index.tz_convert(self.data.df.index.tz)
            else:
                raise ValueError("htf_data must be a pandas DataFrame")
        else:
            df_for_resample = self.data.df.copy()
            column_mapping = {
                "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Volume": "volume",
            }
            df_for_resample.rename(
                columns={k: v for k, v in column_mapping.items() if k in df_for_resample.columns},
                inplace=True
            )
            self.htf_data = resample_ohlcv(df_for_resample, "4h")

        if len(self.htf_data) == 0:
            raise ValueError("No 4H data available")

        # Calculate ATR(14) on 4H
        self.htf_atr = calculate_atr(
            self.htf_data["high"],
            self.htf_data["low"],
            self.htf_data["close"],
            period=14,
        )

        # Calculate ATR(200) on 15m
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
        self.active_zones_log: list[dict] = []
        self.zone_history: list[dict] = []

        # Build timeframe map
        self._build_timeframe_map()
        self.last_htf_idx = -1

        # Pre-calculate pivot events
        raw_pivots = detect_pivot_high(self.htf_data["high"], self.left_len, self.right_len)
        self.pivot_events = {}
        self.debug_pivots = []

        high_values = self.htf_data["high"].values
        open_values = self.htf_data["open"].values
        close_values = self.htf_data["close"].values

        pivot_indices = np.where(~np.isnan(raw_pivots.values))[0]
        print(f"[SR Strategy] Detected {len(pivot_indices)} raw pivots in 4H data.")

        for pivot_real_idx in pivot_indices:
            p_high = raw_pivots.values[pivot_real_idx]
            confirmation_idx = int(pivot_real_idx + self.right_len)

            if confirmation_idx < len(self.htf_data):
                p_body = max(open_values[pivot_real_idx], close_values[pivot_real_idx])
                self.pivot_events[confirmation_idx] = (p_high, p_body, pivot_real_idx)
                self.debug_pivots.append({
                    "time": self.htf_data.index[pivot_real_idx],
                    "price": p_high,
                    "confirm_time": self.htf_data.index[confirmation_idx]
                })

        print(f"[SR Strategy] Generated {len(self.pivot_events)} pivot confirmation events.")

        self.htf_data_for_plot = self.htf_data.copy()
        self.zones_for_plot = self.zones

        # Catch-up simulation
        start_htf_idx = 0
        if 0 in self.timeframe_map:
            start_htf_idx = self.timeframe_map[0]

        print(f"[SR Strategy] Catch-up simulation: Processing 4H bars 0 to {start_htf_idx-1}")
        for i in range(start_htf_idx):
            self._process_htf_bar(i)

        print(f"[SR Strategy] Catch-up complete. Active zones: {len(self.zones)}")

    def _build_timeframe_map(self):
        """Build mapping from current timeframe bars to 4H bars."""
        self.timeframe_map = {}
        if len(self.htf_data) == 0:
            return

        for i, current_time in enumerate(self.data.df.index):
            htf_idx = None
            for idx, htf_end_time in enumerate(self.htf_data.index):
                if current_time <= htf_end_time:
                    htf_idx = idx
                    break
            if htf_idx is None:
                htf_idx = len(self.htf_data) - 1
            self.timeframe_map[i] = htf_idx

    def _process_htf_bar(self, htf_idx: int):
        """Process a single confirmed 4H bar to update zones."""
        if htf_idx < 0 or htf_idx >= len(self.htf_data):
            return

        current_close = self.htf_data["close"].iloc[htf_idx]
        current_atr = self.htf_atr.iloc[htf_idx] if htf_idx < len(self.htf_atr) else 0.01
        if np.isnan(current_atr):
            current_atr = 0.01

        # Check breaks
        for z in self.zones:
            if not z.is_broken:
                break_threshold = z.top + (current_atr * self.break_tol_atr)
                if current_close > break_threshold:
                    z.is_broken = True
                    z.end_time = self.htf_data.index[htf_idx]

        # Check new pivot
        if htf_idx in self.pivot_events:
            p_high, p_body, pivot_real_idx = self.pivot_events[htf_idx]

            if (p_high - p_body) < (current_atr * 0.2):
                p_body = p_high - (current_atr * 0.2)

            merged = False
            tolerance = current_atr * self.merge_atr_mult

            for z in self.zones:
                if z.is_broken:
                    continue
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
        """Update resistance zones incrementally."""
        current_15m_idx = len(self.data) - 1
        curr_htf_idx = self.timeframe_map.get(current_15m_idx)
        if curr_htf_idx is None:
            return
        self._process_htf_bar(curr_htf_idx)

    def _get_htf_bar(self, current_idx: int) -> Optional[pd.Series]:
        """Get corresponding 4H bar data."""
        if current_idx not in self.timeframe_map:
            return None
        htf_idx = self.timeframe_map[current_idx]
        if htf_idx >= len(self.htf_data):
            return None
        return self.htf_data.iloc[htf_idx]

    def _get_current_htf_bar_partial(self, current_idx: int) -> Optional[pd.Series]:
        """Get partial 4H bar data up to current 15m bar."""
        if current_idx < 0 or current_idx >= len(self.data.df):
            return None

        htf_idx = self.timeframe_map.get(current_idx)
        if htf_idx is None or htf_idx >= len(self.htf_data):
            return None

        htf_end_time = self.htf_data.index[htf_idx]
        current_time = self.data.df.index[current_idx]

        if current_time < htf_end_time:
            mask = (self.data.df.index <= current_time) & (self.data.df.index <= htf_end_time)
            if htf_idx > 0:
                prev_htf_end = self.htf_data.index[htf_idx - 1]
                mask = mask & (self.data.df.index > prev_htf_end)
            else:
                mask = mask & (self.data.df.index <= current_time)

            partial_data = self.data.df[mask]
            if len(partial_data) == 0:
                return None

            partial_bar = pd.Series({
                "open": partial_data["Open"].iloc[0],
                "high": partial_data["High"].max(),
                "low": partial_data["Low"].min(),
                "close": partial_data["Close"].iloc[-1],
                "volume": partial_data["Volume"].sum(),
            }, name=current_time)
            return partial_bar

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

    def _calculate_position_size_satoshi(
        self, entry_price: float, stop_distance: float, equity: float
    ) -> int:
        """
        Calculate position size in satoshi based on risk percentage.

        Returns
        -------
        int
            Position size in satoshi (integer units)
        """
        # Risk amount in USDT
        risk_amount = equity * (self.risk_per_trade_pct / 100)

        # Position quantity in BTC
        position_btc = risk_amount / stop_distance

        # Check margin requirement
        position_value = position_btc * entry_price
        margin_required = position_value / self.leverage

        if margin_required > equity:
            position_btc = (equity * self.leverage) / entry_price

        # Convert to satoshi (整数)
        position_satoshi = int(position_btc * SATOSHI_PER_BTC)

        return position_satoshi

    def _detect_signal(
        self, current_idx: int, htf_bar: pd.Series, htf_atr_val: float
    ) -> Optional[tuple[Zone, str]]:
        """Detect entry signal based on zone touch."""
        current_price = self.data.Close[current_idx]

        if not self._check_cooldown(current_idx):
            return None
        if not self._check_price_filter(current_price):
            pass
        if not self._check_position_distance(current_price):
            return None
        if self._count_active_positions() >= self.max_positions:
            return None

        nearest_dist = float('inf')

        for zone in self.zones:
            if zone.is_broken:
                continue

            dist_to_bottom = zone.bottom - current_price
            if abs(dist_to_bottom) < abs(nearest_dist):
                nearest_dist = dist_to_bottom

            if zone.touches < self.min_touches:
                continue
            if zone.fail_count >= self.max_retries:
                continue

            in_zone = zone.bottom <= current_price <= zone.top

            if in_zone:
                print(f"[Signal] TOUCH! Time: {self.data.df.index[current_idx]}, "
                      f"Price: {current_price:.2f}, Zone: {zone.bottom:.2f}-{zone.top:.2f}")
                return (zone, "InZone")

        if current_idx % 16 == 0 or (nearest_dist != float('inf') and abs(nearest_dist) < current_price * 0.01):
            active_zones = len([z for z in self.zones if not z.is_broken])
            print(f"[Debug] Time: {self.data.df.index[current_idx]}, Price: {current_price:.2f}, "
                  f"Nearest Zone Dist: {nearest_dist:.2f}, Active Zones: {active_zones}")

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
        """Create 2 split virtual trades (positions in satoshi)."""
        entry_high = self.data.High[current_idx]
        zone_idx = self.zones.index(zone)

        # Calculate SL
        sl_distance = 3 * atr200_val
        sl_price = entry_price + sl_distance

        # Calculate total position in satoshi
        total_satoshi = self._calculate_position_size_satoshi(entry_price, sl_distance, equity)

        # Split: 30% fixed TP, 70% trailing
        satoshi_trailing = int(total_satoshi * (self.trailing_pct / 100.0))
        satoshi_fixed = total_satoshi - satoshi_trailing

        trades = []
        base_id = f"SHORT_{current_idx}_{signal_type}"

        # Trade 1: Fixed TP @ 2.33R
        if satoshi_fixed > 0:
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
                position_satoshi=satoshi_fixed,
                enable_trailing=False
            ))

        # Trade 2: Trailing stop
        if satoshi_trailing > 0:
            trades.append(VirtualTrade(
                trade_id=f"{base_id}_Trail",
                entry_time=self.data.df.index[current_idx],
                entry_price=entry_price,
                entry_high=entry_high,
                entry_atr=atr200_val,
                zone_top=zone.top,
                sl_price=sl_price,
                tp_price=None,
                zone_idx=zone_idx,
                position_satoshi=satoshi_trailing,
                enable_trailing=True,
                lowest_price=entry_price
            ))

        return trades

    def _check_exits(self, current_idx: int):
        """Check exits for all virtual trades."""
        current_high = self.data.High[current_idx]
        current_low = self.data.Low[current_idx]

        total_satoshi = 0
        active_trades = [t for t in self.virtual_trades if t.is_active]

        for trade in active_trades:
            # Update trailing
            if trade.enable_trailing:
                trade.lowest_price = min(trade.lowest_price, current_low)
                profit_dist = trade.entry_price - trade.lowest_price
                activation_dist = self.trail_trigger_atr * trade.entry_atr

                if not trade.trailing_active:
                    if profit_dist >= activation_dist:
                        trade.trailing_active = True

                if trade.trailing_active:
                    target_sl = trade.lowest_price + (self.trail_offset_atr * trade.entry_atr)
                    if target_sl < trade.sl_price:
                        trade.sl_price = target_sl

            # Check SL
            if current_high >= trade.sl_price:
                trade.is_active = False
                trade.exit_time = self.data.df.index[current_idx]
                trade.exit_price = trade.sl_price
                trade.exit_reason = "SL/Trail"
                continue

            # Check TP
            if trade.tp_price is not None:
                if current_low <= trade.tp_price:
                    trade.is_active = False
                    trade.exit_time = self.data.df.index[current_idx]
                    trade.exit_price = trade.tp_price
                    trade.exit_reason = "TP"
                    continue

            if trade.is_active:
                total_satoshi += trade.position_satoshi

        self._sync_position_satoshi(total_satoshi)

    def _sync_position_satoshi(self, target_satoshi: int):
        """
        Sync actual position with target size in satoshi.

        Converts satoshi to integer units for backtesting.py.
        Since backtesting.py requires size >= 1 to be integer,
        we use satoshi as the base unit (already integer).
        """
        if target_satoshi <= 0:
            if self.position and self.position.size != 0:
                self.position.close()
            return

        # Convert satoshi to BTC for display (not used in orders)
        # target_btc = target_satoshi / SATOSHI_PER_BTC

        # Use satoshi directly as integer units
        target_units = target_satoshi

        if not self.position or self.position.size == 0:
            # Open new position with integer satoshi units
            self.sell(size=target_units)
        else:
            current_units = abs(self.position.size)
            diff_units = target_units - current_units

            if abs(diff_units) > 0:  # Any difference
                if diff_units > 0:
                    self.sell(size=diff_units)
                else:
                    self.buy(size=abs(diff_units))

    def next(self):
        """Execute strategy logic on each bar."""
        current_idx = len(self.data) - 1

        htf_bar = self._get_current_htf_bar_partial(current_idx)
        if htf_bar is None:
            htf_bar = self._get_htf_bar(current_idx)
            if htf_bar is None:
                return

        current_htf_idx = self.timeframe_map.get(current_idx, -1)
        current_time = self.data.df.index[current_idx]

        if current_htf_idx >= 0 and current_htf_idx < len(self.htf_data):
            htf_end_time = self.htf_data.index[current_htf_idx]
            is_htf_confirmed = current_time >= htf_end_time

            if is_htf_confirmed and current_htf_idx != self.last_htf_idx:
                self._update_zones()
                self.last_htf_idx = current_htf_idx

        # Update zone history for plotting
        for zone in self.zones:
            zone_found = False
            for hist_zone in self.zone_history:
                if (abs(hist_zone["top"] - zone.top) < 0.01 and
                    abs(hist_zone["bottom"] - zone.bottom) < 0.01):
                    hist_zone["end_time"] = current_time
                    hist_zone["is_broken"] = zone.is_broken
                    hist_zone["touches"] = zone.touches
                    hist_zone["fail_count"] = zone.fail_count
                    zone_found = True
                    break

            if not zone_found:
                self.zone_history.append({
                    "start_time": zone.start_time if hasattr(zone, "start_time") else current_time,
                    "end_time": current_time,
                    "top": zone.top,
                    "bottom": zone.bottom,
                    "is_broken": zone.is_broken,
                    "touches": zone.touches,
                    "fail_count": zone.fail_count,
                })

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

        htf_atr_val = self._get_htf_atr(current_idx)

        # Check exits
        self._check_exits(current_idx)

        # Detect signal
        signal_result = self._detect_signal(current_idx, htf_bar, htf_atr_val)
        if signal_result is None:
            return

        zone, signal_type = signal_result

        entry_price = self.data.Close[current_idx]
        equity = self.equity
        atr200_val = self.atr200.iloc[current_idx] if current_idx < len(self.atr200) else 0.01

        new_trades = self._create_virtual_trades(
            current_idx, zone, signal_type, entry_price, atr200_val, equity
        )

        self.virtual_trades.extend(new_trades)
        self.last_sig_idx = current_idx
        self.last_sig_price = entry_price

        # Update position
        total_satoshi = sum(t.position_satoshi for t in self.virtual_trades if t.is_active)
        self._sync_position_satoshi(total_satoshi)

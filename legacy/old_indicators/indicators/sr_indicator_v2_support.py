from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import pandas as pd
import mplfinance as mpf

from utils.support_resistance import _average_true_range

@dataclass
class SupportZone:
    id: int
    top: float      # Upper bound of support zone (pivot low body)
    bottom: float   # Lower bound of support zone (pivot low - ATR*0.2)
    plot_top: float    # Initial top for plotting
    plot_bottom: float # Initial bottom for plotting
    start_idx: int
    end_idx: int
    touches: int = 0
    is_broken: bool = False
    fail_count: int = 0
    last_touch_idx: int = -999
    created_idx: int = 0

@dataclass
class LongTrade:
    entry_idx: int
    entry_price: float
    sl_price: float
    tp_price: float
    active: bool = True
    hit_sl: bool = False
    hit_tp: bool = False
    zone_id: int = -1

class SupportResistanceVolumeBoxesIndicatorV2_Support:
    """
    Python implementation of 'SR Long Strategy V1' (Pine Script mirror).
    Focuses on Support (Long) zones based on Pivot Lows.
    This is the mirror version of the Resistance (Short) indicator.
    """

    def __init__(
        self,
        lookback: int = 90,      # leftLen
        confirmation: int = 10,  # rightLen
        merge_atr_factor: float = 3.5,
        break_tol_factor: float = 0.5,
        box_width_factor: float = 1.0,
        sl_atr_mult: float = 1.0,
        max_retries: int = 3,
        cooldown: int = 30,
        min_touches: int = 1,
        price_filter: float = 1.5, # percent
        use_close_sl: bool = True,
        volume_length: int = 2 # kept for compatibility signature
    ) -> None:
        self.left_len = lookback
        self.right_len = confirmation
        self.merge_atr = merge_atr_factor
        self.break_tol = break_tol_factor
        self.sl_atr_mult = sl_atr_mult
        self.max_retries = max_retries
        self.cooldown = cooldown
        self.min_touches = min_touches
        self.price_filter = price_filter
        self.use_close_sl = use_close_sl
        
        self.zones_: List[SupportZone] = []
        self.trades_: List[LongTrade] = []
        self.df_result_: pd.DataFrame | None = None

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        data = self._prepare_dataframe(df)
        if data.empty:
            return df.copy()

        high = data["high"].values
        low = data["low"].values
        close = data["close"].values
        open_ = data["open"].values
        length = len(data)

        # 1. Calculate ATR
        atr_series = _average_true_range(data["high"], data["low"], data["close"], period=14)
        atr_series = atr_series.bfill().ffill()
        atr = atr_series.values

        # 2. Identify Pivot Lows (mirror of pivot_high)
        pivot_lows = self._pivot_low(low, self.left_len, self.right_len)

        self.zones_ = []
        self.trades_ = []
        
        # Output Arrays
        signal_l = np.full(length, np.nan)  # Long signal (mirror of S)
        signal_2b = np.full(length, np.nan)  # 2B Long signal
        trade_sl = np.full(length, np.nan)
        trade_tp = np.full(length, np.nan)
        
        last_sig_idx = -999
        last_sig_price = 0.0
        last_trade_hit_sl = False

        # Iterate bars
        for i in range(length):
            # Update Zone end_idx for plotting
            for z in self.zones_:
                if not z.is_broken:
                    z.end_idx = i

            # A. Check for New Pivot Low (Creation / Merge)
            p_val = pivot_lows[i]
            if np.isfinite(p_val):
                pivot_idx = i - self.right_len
                p_low = low[pivot_idx]
                p_body = min(open_[pivot_idx], close[pivot_idx])  # Bottom of body
                
                curr_atr = atr[i]
                # Ensure min width: if body is too close to low, add thickness
                if (p_body - p_low) < (curr_atr * 0.2):
                    p_body = p_low + (curr_atr * 0.2)
                
                merged = False
                tolerance = curr_atr * self.merge_atr
                
                for z in self.zones_:
                    if not z.is_broken:
                        # Overlap check (mirror logic)
                        if (p_low >= z.bottom - tolerance) and (p_low <= z.top + tolerance):
                            # Update LOGIC bounds (for signals)
                            z.top = max(z.top, p_body)  # Top is the higher bound
                            z.bottom = min(z.bottom, p_low)  # Bottom is the lower bound
                            
                            # DO NOT update z.plot_top / z.plot_bottom (keep visual size static)
                            
                            z.touches += 1
                            merged = True
                            break
                
                if not merged:
                    new_zone = SupportZone(
                        id=len(self.zones_),
                        top=p_body,  # Top of support zone
                        bottom=p_low,  # Bottom of support zone
                        plot_top=p_body,
                        plot_bottom=p_low,
                        start_idx=pivot_idx,
                        end_idx=i,
                        touches=1,
                        created_idx=i
                    )
                    self.zones_.append(new_zone)

            # B. Process Zones (Breakout / Signals)
            curr_atr = atr[i]
            curr_high = high[i]
            curr_low = low[i]
            curr_close = close[i]
            curr_open = open_[i]
            
            new_signal = False
            
            for z in reversed(self.zones_):
                # Touch Update (mirror: low <= z.top)
                if curr_low <= z.top:
                    z.last_touch_idx = i
                    pass

                if not z.is_broken:
                    # Breakout Check (mirror: close < z.bottom - atr * break_tol)
                    if curr_close < (z.bottom - curr_atr * self.break_tol):
                        z.is_broken = True
                        z.end_idx = i 
                        continue
                    
                    # Signal Detection (mirror logic)
                    if z.touches >= self.min_touches and not new_signal and z.fail_count < self.max_retries:
                        touch = curr_low <= z.top
                        is_bull = curr_close > curr_open  # Mirror: bullish candle
                        time_ok = (i - last_sig_idx) > self.cooldown
                        
                        price_diff = 0.0
                        if last_sig_price > 0:
                            price_diff = abs(curr_close - last_sig_price) / last_sig_price * 100
                        price_ok = (last_sig_price == 0.0) or (price_diff > self.price_filter)
                        
                        force_entry = last_trade_hit_sl
                        entry_valid = (time_ok or force_entry) and (price_ok or force_entry)
                        
                        if touch and is_bull and entry_valid:
                            # Setup Types (mirror)
                            setup_std = curr_low >= (z.bottom - curr_atr * 0.1)
                            setup_2b = curr_low < z.bottom  # Mirror: low breaks below bottom
                            
                            if setup_std or setup_2b:
                                new_signal = True
                                last_sig_idx = i
                                last_sig_price = curr_close
                                last_trade_hit_sl = False
                                
                                if setup_2b:
                                    signal_2b[i] = curr_low
                                else:
                                    signal_l[i] = curr_low
                                
                                # Create Trade (mirror: SL below, TP above)
                                sl_p = z.bottom - (curr_atr * self.sl_atr_mult)
                                # TP: Zero cost logic (Risk * 0.7/0.3)
                                risk = curr_close - sl_p
                                dist_zero = risk * (0.7 / 0.3)
                                tp_p = curr_close + dist_zero
                                
                                trade = LongTrade(
                                    entry_idx=i,
                                    entry_price=curr_close,
                                    sl_price=sl_p,
                                    tp_price=tp_p,
                                    active=True,
                                    zone_id=z.id
                                )
                                self.trades_.append(trade)
            
            # C. Trade Management (mirror logic)
            for t in self.trades_:
                if t.active:
                    # Check SL (mirror: close < sl_price or low < sl_price - atr)
                    sl_triggered = False
                    if self.use_close_sl:
                        if curr_close < t.sl_price:
                            sl_triggered = True
                        # Anti-wick hard stop
                        if curr_low < (t.sl_price - curr_atr * 1.0):
                            sl_triggered = True
                    else:
                        if curr_low <= t.sl_price:
                            sl_triggered = True
                    
                    if sl_triggered:
                        t.active = False
                        t.hit_sl = True
                        last_trade_hit_sl = True
                        trade_sl[i] = t.sl_price
                        
                        if t.zone_id >= 0 and t.zone_id < len(self.zones_):
                            self.zones_[t.zone_id].fail_count += 1
                    
                    # Check TP (mirror: high >= tp_price)
                    elif high[i] >= t.tp_price and not t.hit_tp:
                        t.hit_tp = True
                        trade_tp[i] = t.tp_price

        # Merge results back to original DF
        result_df = df.copy()
        if len(result_df) == length:
            result_df["signal_l"] = signal_l
            result_df["signal_2b"] = signal_2b
            result_df["trade_sl"] = trade_sl
            result_df["trade_tp"] = trade_tp
            result_df["atr"] = atr
        else:
            result_df["signal_l"] = pd.Series(signal_l, index=data.index)
            result_df["signal_2b"] = pd.Series(signal_2b, index=data.index)
            result_df["trade_sl"] = pd.Series(trade_sl, index=data.index)
            result_df["trade_tp"] = pd.Series(trade_tp, index=data.index)
            result_df["atr"] = pd.Series(atr, index=data.index)
        
        self.df_result_ = result_df
        return self.df_result_

    def plot(self, df: pd.DataFrame) -> List:
        """
        Generate mplfinance addplots for Support zones.
        """
        plots = []
        if self.zones_ is None:
            return plots
            
        # Plot Signals (mirror: Long signals)
        if "signal_l" in df.columns:
            series = df["signal_l"]
            if not series.isna().all():
                plots.append(mpf.make_addplot(
                    series, type='scatter', markersize=50, marker='^', color='#27AE60', panel=0  # Green up arrow
                ))
                
        if "signal_2b" in df.columns:
            series = df["signal_2b"]
            if not series.isna().all():
                plots.append(mpf.make_addplot(
                    series, type='scatter', markersize=80, marker='^', color='#9c27b0', panel=0  # Purple up arrow
                ))
            
        # Plot SL/TP events
        if "trade_sl" in df.columns:
            series = df["trade_sl"]
            if not series.isna().all():
                plots.append(mpf.make_addplot(
                    series, type='scatter', markersize=30, marker='x', color='gray', panel=0
                ))
                
        if "trade_tp" in df.columns:
            series = df["trade_tp"]
            if not series.isna().all():
                plots.append(mpf.make_addplot(
                    series, type='scatter', markersize=30, marker='*', color='#FFD700', panel=0
                ))

        return plots

    def get_fill_betweens(self, df: pd.DataFrame) -> List[Dict]:
        """
        Return a list of fill_between configurations for mpf.plot.
        Support zones are shown in green (active) or light blue (broken).
        """
        fills = []
        if self.zones_ is None:
            return fills

        idx = df.index
        
        for z in self.zones_:
            if z.end_idx < 0: continue
            
            # Calculate mask for this zone's lifespan
            start_t = df.index[max(0, z.start_idx)]
            end_t = df.index[min(len(df)-1, z.end_idx)]
            
            mask = (idx >= start_t) & (idx <= end_t)
            if not mask.any():
                continue

            # Construct partial series
            # Use plot_top / plot_bottom for visual consistency with TV
            upper = pd.Series(np.nan, index=idx)
            lower = pd.Series(np.nan, index=idx)
            
            upper.loc[mask] = z.plot_top
            lower.loc[mask] = z.plot_bottom

            # Support zones: Green (active) or LightSteelBlue (broken)
            color = "#27AE60" if not z.is_broken else "#b0c4de"  # Green for support
            alpha = 0.2 if not z.is_broken else 0.3

            fills.append(dict(
                y1=upper.values,
                y2=lower.values,
                color=color,
                alpha=alpha
            ))
            
        return fills

    @staticmethod
    def _prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        if isinstance(df.index, pd.DatetimeIndex):
            data = df.sort_index().copy()
        else:
            data = df.copy()
            if 'timestamp' in data.columns:
                data['timestamp'] = pd.to_datetime(data['timestamp'])
                data.set_index('timestamp', inplace=True)
            elif 'date' in data.columns:
                data['date'] = pd.to_datetime(data['date'])
                data.set_index('date', inplace=True)
                
        data.columns = [c.lower() for c in data.columns]
        return data

    @staticmethod
    def _pivot_low(values: np.ndarray, left: int, right: int) -> np.ndarray:
        """
        Returns array where result[i] = pivot_low_value IF a pivot confirmed at i.
        Mirror of _pivot_high: finds local minima.
        """
        length = len(values)
        res = np.full(length, np.nan)
        
        for i in range(left + right, length):
            pivot_idx = i - right
            candidate = values[pivot_idx]
            
            # Check left neighbors (must all be >= candidate)
            is_min = True
            for l in range(1, left + 1):
                if values[pivot_idx - l] <= candidate:
                    is_min = False
                    break
            if not is_min: continue
            
            # Check right neighbors (must all be >= candidate)
            for r in range(1, right + 1):
                if values[pivot_idx + r] <= candidate:
                    is_min = False
                    break
            
            if is_min:
                res[i] = candidate
                
        return res


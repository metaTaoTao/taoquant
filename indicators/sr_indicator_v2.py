from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import pandas as pd
import mplfinance as mpf

from utils.support_resistance import _average_true_range

@dataclass
class Zone:
    id: int
    top: float
    bottom: float
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
class Trade:
    entry_idx: int
    entry_price: float
    sl_price: float
    tp_price: float
    active: bool = True
    hit_sl: bool = False
    hit_tp: bool = False
    zone_id: int = -1

class SupportResistanceVolumeBoxesIndicatorV2:
    """
    Python implementation of 'SR Short Strategy V1' (Pine Script).
    Focuses on Resistance (Short) zones based on Pivot Highs.
    """

    def __init__(
        self,
        lookback: int = 90,      # leftLen
        confirmation: int = 10,  # rightLen
        merge_atr_factor: float = 3.5,
        break_tol_factor: float = 0.5,
        box_width_factor: float = 1.0, # Not strictly used as fixed width, but maybe for default
        sl_atr_mult: float = 1.0,
        max_retries: int = 3,
        cooldown: int = 30,
        min_touches: int = 1,
        price_filter: float = 1.5, # percent
        use_close_sl: bool = True,
        # Visuals
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
        
        self.zones_: List[Zone] = []
        self.trades_: List[Trade] = []
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

        # 2. Identify Pivot Highs
        pivot_highs = self._pivot_high(high, self.left_len, self.right_len)

        self.zones_ = []
        self.trades_ = []
        
        # Output Arrays
        signal_s = np.full(length, np.nan)
        signal_2b = np.full(length, np.nan)
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

            # A. Check for New Pivot (Creation / Merge)
            p_val = pivot_highs[i]
            if np.isfinite(p_val):
                pivot_idx = i - self.right_len
                p_high = high[pivot_idx]
                p_body = max(open_[pivot_idx], close[pivot_idx])
                
                curr_atr = atr[i]
                if (p_high - p_body) < (curr_atr * 0.2):
                    p_body = p_high - (curr_atr * 0.2)
                
                merged = False
                tolerance = curr_atr * self.merge_atr
                
                for z in self.zones_:
                    if not z.is_broken:
                        if (p_high <= z.top + tolerance) and (p_high >= z.bottom - tolerance):
                            # Update LOGIC bounds (for signals)
                            z.top = max(z.top, p_high)
                            z.bottom = min(z.bottom, p_body)
                            
                            # DO NOT update z.plot_top / z.plot_bottom 
                            # (keep visual size static, matching TV behavior)
                            
                            z.touches += 1
                            merged = True
                            break
                
                if not merged:
                    new_zone = Zone(
                        id=len(self.zones_),
                        top=p_high,
                        bottom=p_body,
                        plot_top=p_high,
                        plot_bottom=p_body,
                        start_idx=pivot_idx,
                        end_idx=i,
                        touches=1,
                        created_idx=i
                    )
                    self.zones_.append(new_zone)

            # B. Process Zones (Breakout / Signals)
            curr_atr = atr[i]
            curr_high = high[i]
            curr_close = close[i]
            curr_open = open_[i]
            
            new_signal = False
            
            for z in reversed(self.zones_):
                if curr_high >= z.bottom:
                    z.last_touch_idx = i
                    pass

                if not z.is_broken:
                    if curr_close > (z.top + curr_atr * self.break_tol):
                        z.is_broken = True
                        z.end_idx = i 
                        continue
                    
                    if z.touches >= self.min_touches and not new_signal and z.fail_count < self.max_retries:
                        touch = curr_high >= z.bottom
                        is_bear = curr_close < curr_open
                        time_ok = (i - last_sig_idx) > self.cooldown
                        
                        price_diff = 0.0
                        if last_sig_price > 0:
                            price_diff = abs(curr_close - last_sig_price) / last_sig_price * 100
                        price_ok = (last_sig_price == 0.0) or (price_diff > self.price_filter)
                        
                        force_entry = last_trade_hit_sl
                        entry_valid = (time_ok or force_entry) and (price_ok or force_entry)
                        
                        if touch and is_bear and entry_valid:
                            setup_std = curr_high <= (z.top + curr_atr * 0.1)
                            setup_2b = curr_high > z.top
                            
                            if setup_std or setup_2b:
                                new_signal = True
                                last_sig_idx = i
                                last_sig_price = curr_close
                                last_trade_hit_sl = False
                                
                                if setup_2b:
                                    signal_2b[i] = curr_high
                                else:
                                    signal_s[i] = curr_high
                                
                                sl_p = z.top + (curr_atr * self.sl_atr_mult)
                                risk = sl_p - curr_close
                                dist_zero = risk * (0.7 / 0.3)
                                tp_p = curr_close - dist_zero
                                
                                trade = Trade(
                                    entry_idx=i,
                                    entry_price=curr_close,
                                    sl_price=sl_p,
                                    tp_price=tp_p,
                                    active=True,
                                    zone_id=z.id
                                )
                                self.trades_.append(trade)
            
            # C. Trade Management
            for t in self.trades_:
                if t.active:
                    sl_triggered = False
                    if self.use_close_sl:
                        if curr_close > t.sl_price:
                            sl_triggered = True
                        if curr_high > (t.sl_price + curr_atr * 1.0):
                            sl_triggered = True
                    else:
                        if curr_high >= t.sl_price:
                            sl_triggered = True
                    
                    if sl_triggered:
                        t.active = False
                        t.hit_sl = True
                        last_trade_hit_sl = True
                        trade_sl[i] = t.sl_price
                        
                        if t.zone_id >= 0 and t.zone_id < len(self.zones_):
                            self.zones_[t.zone_id].fail_count += 1
                    
                    elif low[i] <= t.tp_price and not t.hit_tp:
                        t.hit_tp = True
                        trade_tp[i] = t.tp_price

        # Merge results back to original DF
        result_df = df.copy()
        if len(result_df) == length:
            result_df["signal_s"] = signal_s
            result_df["signal_2b"] = signal_2b
            result_df["trade_sl"] = trade_sl
            result_df["trade_tp"] = trade_tp
        else:
            result_df["signal_s"] = pd.Series(signal_s, index=data.index)
            result_df["signal_2b"] = pd.Series(signal_2b, index=data.index)
            result_df["trade_sl"] = pd.Series(trade_sl, index=data.index)
            result_df["trade_tp"] = pd.Series(trade_tp, index=data.index)
        
        self.df_result_ = result_df
        return self.df_result_

    def plot(self, df: pd.DataFrame) -> List:
        """
        Generate mplfinance addplots.
        """
        plots = []
        if self.zones_ is None:
            return plots
            
        # 2. Plot Signals
        if "signal_s" in df.columns:
            series = df["signal_s"]
            if not series.isna().all():
                plots.append(mpf.make_addplot(
                    series, type='scatter', markersize=50, marker='v', color='#d32f2f', panel=0
                ))
                
        if "signal_2b" in df.columns:
            series = df["signal_2b"]
            if not series.isna().all():
                plots.append(mpf.make_addplot(
                    series, type='scatter', markersize=80, marker='v', color='#9c27b0', panel=0
                ))
            
        # 3. Plot SL/TP events
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

            # Adjusted for dark background visibility
            # Active: Red
            # Broken: LightSteelBlue (#b0c4de) with higher alpha (0.3) for better contrast
            color = "#f23645" if not z.is_broken else "#b0c4de"
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
    def _pivot_high(values: np.ndarray, left: int, right: int) -> np.ndarray:
        length = len(values)
        res = np.full(length, np.nan)
        
        for i in range(left + right, length):
            pivot_idx = i - right
            candidate = values[pivot_idx]
            
            is_max = True
            for l in range(1, left + 1):
                if values[pivot_idx - l] >= candidate:
                    is_max = False
                    break
            if not is_max: continue
            
            for r in range(1, right + 1):
                if values[pivot_idx + r] >= candidate:
                    is_max = False
                    break
            
            if is_max:
                res[i] = candidate
                
        return res

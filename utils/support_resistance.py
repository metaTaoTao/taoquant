from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from utils.resample import resample_ohlcv
from utils.timeframes import timeframe_to_minutes


@dataclass
class SupportResistanceBox:
    """Data container for support or resistance zones."""

    box_type: str
    start: pd.Timestamp
    end: pd.Timestamp
    upper: float
    lower: float
    volume: float
    status: str
    break_time: Optional[pd.Timestamp]
    hold_time: Optional[pd.Timestamp]


def compute_sr_boxes(
    data: pd.DataFrame,
    target_timeframe: str = "4h",
    lookback: int = 20,
    volume_length: int = 2,
    box_width_factor: float = 1.0,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Compute support and resistance boxes on a higher timeframe and map them to the source timeframe.

    Parameters
    ----------
    data : pd.DataFrame
        Source OHLCV data with columns open, high, low, close, volume.
    target_timeframe : str
        Higher timeframe used for support and resistance detection (e.g. "4h").
    lookback : int
        Symmetric lookback for pivot detection.
    volume_length : int
        Rolling window for the signed volume filter.
    box_width_factor : float
        Multiplier applied to the ATR(200) to determine box height.

    Returns
    -------
    Tuple[pd.DataFrame, pd.DataFrame]
        DataFrame of boxes and DataFrame of events for plotting or further analysis.
    """
    data = data.copy()
    data.index = pd.to_datetime(data.index, utc=True)
    ht_data = resample_ohlcv(data, target_timeframe)
    if ht_data.empty:
        return pd.DataFrame(), pd.DataFrame()

    signed_volume = np.where(ht_data["close"] >= ht_data["open"], ht_data["volume"], -ht_data["volume"])
    vol_series = pd.Series(signed_volume, index=ht_data.index)
    vol_norm = vol_series / 2.5
    vol_hi = vol_norm.rolling(volume_length, min_periods=1).max()
    vol_lo = vol_norm.rolling(volume_length, min_periods=1).min()

    atr = _average_true_range(ht_data["high"], ht_data["low"], ht_data["close"], period=200)
    pivot_high = _pivot_series(ht_data["close"], lookback, mode="high")
    pivot_low = _pivot_series(ht_data["close"], lookback, mode="low")

    boxes: List[SupportResistanceBox] = []
    events: List[dict] = []
    active_support: List[SupportResistanceBox] = []
    active_resistance: List[SupportResistanceBox] = []

    prev_high: Optional[float] = None
    prev_low: Optional[float] = None

    for idx, (timestamp, row) in enumerate(ht_data.iterrows()):
        width = atr.iloc[idx] * box_width_factor if not np.isnan(atr.iloc[idx]) else np.nan
        if np.isnan(width) or width <= 0:
            width = 0.0

        vol_value = vol_norm.iloc[idx]
        pivot_low_value = pivot_low.iloc[idx]
        pivot_high_value = pivot_high.iloc[idx]

        start_offset_idx = max(0, idx - lookback)
        start_time = ht_data.index[start_offset_idx]
        end_time = timestamp

        if not np.isnan(pivot_low_value) and vol_value > vol_hi.iloc[idx]:
            box = SupportResistanceBox(
                box_type="support",
                start=start_time,
                end=end_time,
                upper=pivot_low_value,
                lower=pivot_low_value - width,
                volume=vol_series.iloc[idx],
                status="active",
                break_time=None,
                hold_time=None,
            )
            boxes.append(box)
            active_support.append(box)

        if not np.isnan(pivot_high_value) and vol_value < vol_lo.iloc[idx]:
            box = SupportResistanceBox(
                box_type="resistance",
                start=start_time,
                end=end_time,
                upper=pivot_high_value + width,
                lower=pivot_high_value,
                volume=vol_series.iloc[idx],
                status="active",
                break_time=None,
                hold_time=None,
            )
            boxes.append(box)
            active_resistance.append(box)

        for box in active_support + active_resistance:
            box.end = end_time

        if prev_high is not None and prev_low is not None:
            # Update support boxes
            for box in list(active_support):
                top = box.upper
                bottom = box.lower
                if prev_high >= bottom and row["high"] < bottom:
                    box.status = "broken"
                    box.break_time = timestamp
                    events.append({"time": timestamp, "type": "support_break", "price": bottom})
                    active_support.remove(box)
                    continue
                if prev_low <= top and row["low"] > top:
                    box.status = "hold"
                    box.hold_time = timestamp
                    events.append({"time": timestamp, "type": "support_hold", "price": top})

            # Update resistance boxes
            for box in list(active_resistance):
                top = box.upper
                base = box.lower
                if prev_low <= top and row["low"] > top:
                    box.status = "broken"
                    box.break_time = timestamp
                    events.append({"time": timestamp, "type": "resistance_break", "price": top})
                    active_resistance.remove(box)
                    continue
                if prev_high >= base and row["high"] < base:
                    box.status = "hold"
                    box.hold_time = timestamp
                    events.append({"time": timestamp, "type": "resistance_hold", "price": base})

        prev_high = row["high"]
        prev_low = row["low"]

    timeframe_minutes = timeframe_to_minutes(target_timeframe)
    duration = pd.Timedelta(minutes=timeframe_minutes)

    boxes_df = pd.DataFrame(
        [
            {
                "type": box.box_type,
                "start": box.start - duration,
                "end": box.end,
                "upper": box.upper,
                "lower": box.lower,
                "volume": box.volume,
                "status": box.status,
                "break_time": box.break_time,
                "hold_time": box.hold_time,
                "timeframe": target_timeframe,
                "duration": duration,
            }
            for box in boxes
        ]
    )

    events_df = pd.DataFrame(events)
    return boxes_df, events_df


def plot_sr_boxes(
    data: pd.DataFrame,
    boxes_df: pd.DataFrame,
    events_df: Optional[pd.DataFrame] = None,
    *,
    title: str = "Support/Resistance Boxes",
    height: int = 720,
) -> "go.Figure":
    """
    Visualize OHLCV candles alongside support/resistance boxes and events.

    Parameters
    ----------
    data : pd.DataFrame
        Source OHLCV dataframe (e.g. 15m candles) with open/high/low/close columns.
    boxes_df : pd.DataFrame
        Output from compute_sr_boxes describing zones.
    events_df : Optional[pd.DataFrame]
        Optional events dataframe returned by compute_sr_boxes.
    title : str
        Plot title.
    height : int
        Figure height in pixels.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    import plotly.graph_objects as go

    if data.empty:
        raise ValueError("Input OHLCV data is empty.")

    candles = data.copy()
    candles.index = pd.to_datetime(candles.index, utc=True)
    min_time = candles.index.min()
    max_time = candles.index.max()

    fig = go.Figure(
        data=[
            go.Candlestick(
                x=candles.index,
                open=candles["open"],
                high=candles["high"],
                low=candles["low"],
                close=candles["close"],
                name="Price",
            )
        ]
    )

    status_colors = {
        ("support", "active"): ("rgba(46, 204, 113, 0.15)", "rgba(39, 174, 96, 1)"),
        ("support", "hold"): ("rgba(46, 204, 113, 0.25)", "rgba(39, 174, 96, 1)"),
        ("support", "broken"): ("rgba(231, 76, 60, 0.20)", "rgba(192, 57, 43, 1)"),
        ("resistance", "active"): ("rgba(231, 76, 60, 0.15)", "rgba(192, 57, 43, 1)"),
        ("resistance", "hold"): ("rgba(231, 76, 60, 0.25)", "rgba(192, 57, 43, 1)"),
        ("resistance", "broken"): ("rgba(46, 204, 113, 0.20)", "rgba(39, 174, 96, 1)"),
    }

    if not boxes_df.empty:
        for _, box in boxes_df.iterrows():
            fill, line = status_colors.get(
                (box.get("type"), box.get("status")), ("rgba(189, 195, 199, 0.18)", "rgba(127, 140, 141, 1)")
            )
            start = pd.to_datetime(box.get("start"), utc=True)
            end = pd.to_datetime(box.get("end"), utc=True)
            if pd.isna(start) or pd.isna(end):
                continue
            if end < min_time:
                continue
            start = max(start, min_time)
            end = max(end, start + pd.Timedelta(minutes=1))
            if end > max_time + pd.Timedelta(minutes=1):
                end = max_time + pd.Timedelta(minutes=1)

            fig.add_shape(
                type="rect",
                xref="x",
                yref="y",
                x0=start,
                x1=end,
                y0=box.get("lower"),
                y1=box.get("upper"),
                fillcolor=fill,
                line=dict(color=line, width=2, dash="dash" if box.get("status") == "broken" else "solid"),
                layer="above",
            )

    if events_df is not None and not events_df.empty:
        events = events_df.copy()
        events["time"] = pd.to_datetime(events["time"], utc=True)
        color_map = {
            "support_break": "rgba(192, 57, 43, 0.9)",
            "support_hold": "rgba(39, 174, 96, 0.9)",
            "resistance_break": "rgba(39, 174, 96, 0.9)",
            "resistance_hold": "rgba(192, 57, 43, 0.9)",
        }
        fig.add_trace(
            go.Scatter(
                x=events["time"],
                y=events["price"],
                mode="markers",
                marker=dict(
                    size=8,
                    color=events["type"].map(color_map).fillna("rgba(127, 140, 141, 0.9)"),
                ),
                name="Events",
                text=events["type"].str.replace("_", " "),
                hovertemplate="%{text}<br>%{x|%Y-%m-%d %H:%M} @ %{y:.2f}<extra></extra>",
            )
        )

    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title="Price",
        template="plotly_white",
        height=height,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    return fig


def _average_true_range(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Compute Average True Range using a simple moving average."""
    high_low = high - low
    high_close = (high - close.shift(1)).abs()
    low_close = (low - close.shift(1)).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(window=period, min_periods=1).mean()
    return atr


def _pivot_series(series: pd.Series, length: int, mode: str) -> pd.Series:
    """Return pivot high or low series similar to TradingView pivots."""
    values = series.values
    result = np.full(len(values), np.nan)
    for i in range(length, len(values) - length):
        window = values[i - length : i + length + 1]
        center = values[i]
        if np.isnan(window).any():
            continue
        if mode == "high":
            if center == window.max() and np.isclose(center, window).sum() == 1:
                result[i] = center
        else:
            if center == window.min() and np.isclose(center, window).sum() == 1:
                result[i] = center
    return pd.Series(result, index=series.index)


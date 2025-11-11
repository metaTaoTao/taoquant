from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import mplfinance as mpf

from utils.support_resistance import _average_true_range


@dataclass
class _Box:
    box_id: int
    kind: str  # 'support' or 'resistance'
    start_idx: int
    end_idx: int
    upper: float
    lower: float
    width: float
    created_idx: int
    created_price: float
    volume: float
    status: str = "active"


class SupportResistanceVolumeBoxesIndicator:
    """
    逐 K 线迭代实现的支撑阻力盒子指标，基于收盘价枢轴，未引入角色互换。
    """

    def __init__(
        self,
        *,
        lookback: Optional[int] = None,
        lookback_period: Optional[int] = None,
        volume_length: Optional[int] = None,
        vol_len: int = 2,
        box_width_factor: Optional[float] = None,
        box_width_mult: float = 1.0,
        atr_len: int = 200,
        pivot_source: str = "close",
    ) -> None:
        resolved_lookback = lookback_period or lookback or 20
        if resolved_lookback < 1:
            raise ValueError("lookback_period must be >= 1")

        resolved_vol_len = volume_length or vol_len or 2
        resolved_box_mult = box_width_factor if box_width_factor is not None else box_width_mult

        self.lookback_period = int(resolved_lookback)
        self.vol_len = max(1, int(resolved_vol_len))
        self.box_width_mult = float(resolved_box_mult)
        self.atr_len = int(atr_len)
        self.pivot_source = pivot_source.lower()

        self.boxes_: pd.DataFrame | None = None
        self.params: Dict[str, float] = {
            "lookback_period": self.lookback_period,
            "vol_len": self.vol_len,
            "box_width_mult": self.box_width_mult,
            "atr_len": self.atr_len,
            "pivot_source": self.pivot_source,
        }

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        data = self._prepare_dataframe(df)
        if data.empty:
            self.boxes_ = pd.DataFrame()
            return data

        high = data["high"].values
        low = data["low"].values
        close = data["close"].values
        source_array = data.get(self.pivot_source, data["close"]).values
        length = len(data)

        atr_series = _average_true_range(data["high"], data["low"], data["close"], period=self.atr_len)
        atr_series = atr_series.fillna(method="bfill").fillna(method="ffill")
        box_width = atr_series * self.box_width_mult

        pivot_high = self._pivot(source_array, self.lookback_period, mode="high")
        pivot_low = self._pivot(source_array, self.lookback_period, mode="low")

        support_boxes: List[_Box] = []
        resistance_boxes: List[_Box] = []
        all_boxes: List[_Box] = []

        break_res = np.full(length, np.nan)
        break_sup = np.full(length, np.nan)
        res_hold = np.full(length, np.nan)
        sup_hold = np.full(length, np.nan)

        prev_high = np.nan
        prev_low = np.nan

        for i in range(length):
            width = box_width.iloc[i]
            if not np.isfinite(width) or width <= 0:
                width = abs(close[i]) * 0.001 if close[i] != 0 else 1e-6

            for box in support_boxes:
                box.end_idx = i
            for box in resistance_boxes:
                box.end_idx = i

            if np.isfinite(pivot_low[i]):
                lower = float(pivot_low[i])
                box = _Box(
                    box_id=len(all_boxes),
                    kind="support",
                    start_idx=i,
                    end_idx=i,
                    upper=lower,
                    lower=lower - width,
                    width=width,
                    created_idx=i,
                    created_price=lower,
                    volume=0.0,
                )
                support_boxes.append(box)
                all_boxes.append(box)

            if np.isfinite(pivot_high[i]):
                upper = float(pivot_high[i])
                box = _Box(
                    box_id=len(all_boxes),
                    kind="resistance",
                    start_idx=i,
                    end_idx=i,
                    upper=upper + width,
                    lower=upper,
                    width=width,
                    created_idx=i,
                    created_price=upper,
                    volume=0.0,
                )
                resistance_boxes.append(box)
                all_boxes.append(box)

            if i == 0:
                prev_high = high[i]
                prev_low = low[i]
                continue

            current_support = support_boxes[-1] if support_boxes else None
            current_resistance = resistance_boxes[-1] if resistance_boxes else None

            if current_resistance is not None:
                top = current_resistance.upper
                base = current_resistance.lower
                if prev_low < top and low[i] >= top:
                    break_res[i] = top
                if prev_high > base and high[i] <= base:
                    res_hold[i] = base

            if current_support is not None:
                top = current_support.upper
                bottom = current_support.lower
                if prev_high > bottom and high[i] <= bottom:
                    break_sup[i] = bottom
                if prev_low < top and low[i] >= top:
                    sup_hold[i] = top

            prev_high = high[i]
            prev_low = low[i]

        boxes_records = []
        for box in all_boxes:
            end_idx = min(box.end_idx, length - 1)
            boxes_records.append(
                {
                    "box_id": box.box_id,
                    "type": box.kind,
                    "start_idx": box.start_idx,
                    "end_idx": end_idx,
                    "start_time": data.index[box.start_idx],
                    "end_time": data.index[end_idx],
                    "upper": box.upper,
                    "lower": box.lower,
                    "width": box.width,
                    "created_idx": box.created_idx,
                    "created_time": data.index[box.created_idx],
                    "created_price": box.created_price,
                    "status": box.status,
                }
            )

        self.boxes_ = pd.DataFrame(boxes_records)

        result = data.copy()
        result["atr"] = atr_series
        result["pivot_high"] = pivot_high
        result["pivot_low"] = pivot_low
        result["break_res"] = break_res
        result["break_sup"] = break_sup
        result["res_hold"] = res_hold
        result["sup_hold"] = sup_hold

        return result

    def plot(self, df: pd.DataFrame) -> List:
        plots: List = []
        if self.boxes_ is None or self.boxes_.empty:
            return plots

        index = df.index
        for _, box in self.boxes_.iterrows():
            mask = (index >= box["start_time"]) & (index <= box["end_time"])
            if not mask.any():
                continue

            upper_series = pd.Series(np.nan, index=index)
            lower_series = pd.Series(np.nan, index=index)
            upper_series.loc[mask] = box["upper"]
            lower_series.loc[mask] = box["lower"]

            color = "#27AE60" if box["type"] == "support" else "#E74C3C"

            plots.append(
                mpf.make_addplot(
                    upper_series,
                    color=color,
                    linestyle="-",
                    width=1.0,
                    panel=0,
                )
            )
            plots.append(
                mpf.make_addplot(
                    lower_series,
                    color=color,
                    linestyle="-",
                    width=1.0,
                    panel=0,
                )
            )

        event_markers = [
            ("break_res", "^", "#2b6d2d", 60),
            ("break_sup", "v", "#7e1e1e", 60),
            ("res_hold", "D", "#e92929", 40),
            ("sup_hold", "D", "#20ca26", 40),
        ]

        for column, marker, color, size in event_markers:
            if column not in df.columns:
                continue
            series = df[column]
            if not isinstance(series, pd.Series):
                continue
            if series.dropna().empty:
                continue
            plots.append(
                mpf.make_addplot(
                    series,
                    type="scatter",
                    marker=marker,
                    markersize=size,
                    color=color,
                    panel=0,
                )
            )

        return plots

    @staticmethod
    def _prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame is missing required columns: {sorted(missing)}")

        if isinstance(df.index, pd.DatetimeIndex):
            data = df.sort_index().copy()
        elif "timestamp" in df.columns:
            data = df.sort_values("timestamp").set_index(pd.to_datetime(df["timestamp"]))
        else:
            data = df.copy()
            data = data.rename_axis("timestamp").reset_index()
            data["timestamp"] = pd.to_datetime(data["timestamp"])
            data.set_index("timestamp", inplace=True)

        data = data.astype(
            {
                "open": "float64",
                "high": "float64",
                "low": "float64",
                "close": "float64",
                "volume": "float64",
            }
        )
        return data

    @staticmethod
    def _pivot(values: np.ndarray, window: int, mode: str) -> np.ndarray:
        length = len(values)
        result = np.full(length, np.nan)
        for i in range(window, length - window):
            left = i - window
            right = i + window + 1
            window_slice = values[left:right]
            center = values[i]
            if mode == "high":
                if center == np.max(window_slice) and np.count_nonzero(window_slice == center) == 1:
                    result[i] = center
            else:
                if center == np.min(window_slice) and np.count_nonzero(window_slice == center) == 1:
                    result[i] = center
        return result

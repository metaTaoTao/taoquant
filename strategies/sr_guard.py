from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
import pandas as pd
from backtesting import Strategy

from indicators.sr_volume_boxes import SupportResistanceVolumeBoxesIndicator


@dataclass
class _GuardLevel:
    price: float
    activation_idx: int


class SRGuardRailStrategy(Strategy):
    """高频护栏震荡策略，基于支撑/阻力枢轴在区间内高抛低吸。"""

    lookback_period: int = 20
    box_width_mult: float = 1.0
    entry_buffer_pct: float = 0.001  # 0.1%
    stop_atr_multiple: float = 3.0
    trade_size: float = 1.0
    pivot_source: str = "close"

    def init(self) -> None:
        price_df = self.data.df[["Open", "High", "Low", "Close", "Volume"]].copy()
        price_df.columns = [col.lower() for col in price_df.columns]
        price_df.index = pd.to_datetime(price_df.index)

        indicator = SupportResistanceVolumeBoxesIndicator(
            lookback_period=self.lookback_period,
            box_width_mult=self.box_width_mult,
            pivot_source=self.pivot_source,
        )
        result = indicator.calculate(price_df)

        self._result = result
        self._atr = result["atr"].to_numpy()
        self._support_prices, self._resistance_prices = self._build_guardrails(result)
        self._order_log = []  # collect guard rail info for trades
        self.data.df["support_guard"] = self._support_prices
        self.data.df["resistance_guard"] = self._resistance_prices
        self.data.df["atr_guard"] = self._atr

    def _build_guardrails(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        n = len(df)
        support_prices = np.full(n, np.nan)
        resistance_prices = np.full(n, np.nan)
        future_supports: List[_GuardLevel] = []
        future_resistances: List[_GuardLevel] = []
        active_supports: List[_GuardLevel] = []
        active_resistances: List[_GuardLevel] = []

        close_vals = df["close"].to_numpy()
        pivot_low = df["pivot_low"].to_numpy()
        pivot_high = df["pivot_high"].to_numpy()

        for i in range(n):
            if np.isfinite(pivot_low[i]):
                future_supports.append(_GuardLevel(price=float(pivot_low[i]), activation_idx=i + self.lookback_period))
            if np.isfinite(pivot_high[i]):
                future_resistances.append(_GuardLevel(price=float(pivot_high[i]), activation_idx=i + self.lookback_period))

            active_supports.extend([level for level in future_supports if level.activation_idx <= i])
            future_supports = [level for level in future_supports if level.activation_idx > i]
            active_resistances.extend([level for level in future_resistances if level.activation_idx <= i])
            future_resistances = [level for level in future_resistances if level.activation_idx > i]

            below = [level.price for level in active_supports if level.price <= close_vals[i]]
            if below:
                support_prices[i] = max(below)

            above = [level.price for level in active_resistances if level.price >= close_vals[i]]
            if above:
                resistance_prices[i] = min(above)

        return support_prices, resistance_prices

    def next(self) -> None:
        i = len(self.data.Close) - 1
        if i < 0:
            return
        price = float(self.data.Close[-1])
        atr = float(self._atr[i]) if np.isfinite(self._atr[i]) else np.nan
        support = float(self._support_prices[i]) if np.isfinite(self._support_prices[i]) else np.nan
        resistance = float(self._resistance_prices[i]) if np.isfinite(self._resistance_prices[i]) else np.nan
        buffer_pct = self.entry_buffer_pct

        def within_buffer(level: float, reference: float) -> bool:
            if not np.isfinite(level):
                return False
            if level == 0:
                return False
            return abs(reference - level) / abs(level) <= buffer_pct

        support_ready = np.isfinite(support) and support <= price and within_buffer(support, price)
        resistance_ready = np.isfinite(resistance) and resistance >= price and within_buffer(resistance, price)

        if self.position.is_long:
            if resistance_ready:
                self._log_trade("reverse_short", float(self.data.Close[-1]), support, resistance, atr)
                self.position.close()
                stop_price = resistance + self.stop_atr_multiple * atr if np.isfinite(atr) else None
                if np.isfinite(resistance):
                    self.sell(size=self.trade_size, sl=stop_price)
                return

        elif self.position.is_short:
            if support_ready:
                self._log_trade("reverse_long", float(self.data.Close[-1]), support, resistance, atr)
                self.position.close()
                stop_price = support - self.stop_atr_multiple * atr if np.isfinite(atr) else None
                if np.isfinite(support):
                    self.buy(size=self.trade_size, sl=stop_price)
                return

        else:
            if support_ready:
                stop_price = support - self.stop_atr_multiple * atr if np.isfinite(atr) else None
                self._log_trade("entry_long", float(self.data.Close[-1]), support, resistance, atr)
                self.buy(size=self.trade_size, sl=stop_price)
                return
            if resistance_ready:
                stop_price = resistance + self.stop_atr_multiple * atr if np.isfinite(atr) else None
                self._log_trade("entry_short", float(self.data.Close[-1]), support, resistance, atr)
                self.sell(size=self.trade_size, sl=stop_price)
                return

    def _log_trade(self, action: str, price: float, support: float, resistance: float, atr: float) -> None:
        self._order_log.append(
            {
                "time": self.data.index[-1],
                "action": action,
                "price": price,
                "support": support,
                "resistance": resistance,
                "atr": atr,
            }
        )

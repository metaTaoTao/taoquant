from __future__ import annotations

from typing import ClassVar

from backtesting import Strategy  # type: ignore

from utils.indicators import rsi, sma


class TDXHDipStrategy(Strategy):
    """TDXH dip buying strategy skeleton."""

    trend_window: ClassVar[int] = 50
    dip_threshold: ClassVar[float] = 35.0

    def init(self) -> None:
        """Initialize helper indicators."""
        close = self.data.Close
        self.trend_sma = self.I(sma, close, self.trend_window)
        self.rsi = self.I(rsi, close, 14)

    def next(self) -> None:
        """Placeholder decision logic for TDXH strategy."""
        in_uptrend = self.data.Close[-1] > self.trend_sma[-1]
        dip_signal = self.rsi[-1] < self.dip_threshold

        if in_uptrend and dip_signal and not self.position.is_long:
            self.buy()

        if not in_uptrend and self.position.is_long:
            self.position.close()


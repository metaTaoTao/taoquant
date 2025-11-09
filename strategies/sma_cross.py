from __future__ import annotations

from backtesting import Strategy  # type: ignore

from utils.indicators import sma


class SmaCrossStrategy(Strategy):
    """Simple SMA crossover demonstration strategy."""

    short_window: int = 10
    long_window: int = 30

    def init(self) -> None:
        """Initialize indicators."""
        close = self.data.Close
        self.short_sma = self.I(sma, close, self.short_window)
        self.long_sma = self.I(sma, close, self.long_window)

    def next(self) -> None:
        """Execute strategy logic."""
        if self.short_sma[-2] < self.long_sma[-2] and self.short_sma[-1] > self.long_sma[-1]:
            self.buy()
        elif self.short_sma[-2] > self.long_sma[-2] and self.short_sma[-1] < self.long_sma[-1]:
            self.position.close()


from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import pandas as pd


class MarketDataSource(ABC):
    """Abstract base class for pluggable market data sources."""

    name: str

    @abstractmethod
    def get_klines(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Return OHLCV dataframe for given symbol and timeframe."""


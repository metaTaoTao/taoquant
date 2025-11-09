from __future__ import annotations

import math
import time
from datetime import datetime
from typing import List, Optional

import pandas as pd

from data.schemas import COLUMNS_OHLCV
from data.sources.base import MarketDataSource
from utils.timeframes import timeframe_to_minutes


class BinanceSDKDataSource(MarketDataSource):
    """Market data source utilizing python-binance client without credentials."""

    name = "binance_sdk"

    def __init__(
        self,
        request_delay: float = 0.3,
        limit_per_call: int = 1000,
    ) -> None:
        try:
            from binance.client import Client  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ImportError("python-binance package is required for BinanceSDKDataSource. Install via pip install python-binance.") from exc

        self._client = Client()
        self._request_delay = request_delay
        self._limit_per_call = limit_per_call

    def get_klines(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Fetch OHLCV data from Binance."""
        symbol_upper = symbol.upper().replace("/", "")
        start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000) if start else None
        end_ms = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000) if end else None
        bars_needed = self._estimate_total(timeframe, start, end)

        klines: List[List[float]] = []
        current_end = end_ms

        while len(klines) < bars_needed:
            limit = min(self._limit_per_call, bars_needed - len(klines))
            params = {"symbol": symbol_upper, "interval": timeframe, "limit": limit}
            if current_end is not None:
                params["endTime"] = current_end
            if start_ms is not None:
                params["startTime"] = start_ms

            batch = self._client.get_klines(**params)
            if not batch:
                break

            klines.extend(batch)
            current_end = batch[0][0] - 1
            time.sleep(self._request_delay)

            if start_ms is not None and current_end <= start_ms:
                break

        if not klines:
            return pd.DataFrame(columns=COLUMNS_OHLCV)

        frame = pd.DataFrame(
            klines,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_asset_volume",
                "number_of_trades",
                "taker_buy_base_volume",
                "taker_buy_quote_volume",
                "ignore",
            ],
        )

        frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
        for column in COLUMNS_OHLCV:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")

        frame = frame[["timestamp", *COLUMNS_OHLCV]]
        frame = frame.sort_values("timestamp").set_index("timestamp")

        if end is not None:
            frame = frame[frame.index <= pd.Timestamp(end, tz="UTC")]
        if start is not None:
            frame = frame[frame.index >= pd.Timestamp(start, tz="UTC")]

        return frame

    @staticmethod
    def _estimate_total(
        timeframe: str,
        start: Optional[datetime],
        end: Optional[datetime],
    ) -> int:
        default_total = 500
        if start is None or end is None:
            return default_total

        start_ts = pd.Timestamp(start, tz="UTC")
        end_ts = pd.Timestamp(end, tz="UTC")
        if end_ts <= start_ts:
            return default_total

        minutes = max((end_ts - start_ts).total_seconds() / 60, 1)
        per_bar = timeframe_to_minutes(timeframe)
        estimate = math.ceil(minutes / per_bar) + 5
        return max(100, min(2000, estimate))


from __future__ import annotations

import math
import time
from datetime import datetime
from typing import List, Optional

import pandas as pd

from data.schemas import COLUMNS_OHLCV
from data.sources.base import MarketDataSource
from utils.timeframes import timeframe_to_minutes


class OkxSDKDataSource(MarketDataSource):
    """Market data source powered by the official OKX SDK."""

    name = "okx_sdk"

    def __init__(
        self,
        flag: str = "0",
        inst_type: str = "SPOT",
        max_batch: int = 300,
        max_total: int = 3000,
        sleep_seconds: float = 0.2,
    ) -> None:
        self._fetch_method = None
        try:
            from okx.api import Market  # type: ignore

            self._market_api = Market(flag=flag)
            self._fetch_method = getattr(self._market_api, "get_candles", None)
        except ImportError:
            try:
                from okx.MarketData import MarketAPI  # type: ignore

                self._market_api = MarketAPI(flag=flag)
                self._fetch_method = getattr(self._market_api, "get_candlesticks", None)
            except ImportError as exc:  # pragma: no cover
                raise ImportError(
                    "okx package is required for OkxSDKDataSource. Install via pip install python-okx."
                ) from exc

        if self._fetch_method is None:
            raise AttributeError("Unable to locate candle fetch method on okx SDK.")

        self._inst_type = inst_type.upper()
        self._max_batch = max_batch
        self._max_total = max_total
        self._sleep_seconds = sleep_seconds

    def get_klines(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Fetch OHLCV data from OKX using the SDK."""
        inst_id = self._binance_to_okx_instid(symbol)
        bar = self._interval_to_okx(timeframe)
        total = self._estimate_total(timeframe, start, end)

        records: List[List[str]] = []
        fetched = 0
        next_after: Optional[str] = None

        while fetched < total:
            limit = min(self._max_batch, total - fetched)
            params = {"instId": inst_id, "bar": bar, "limit": str(limit)}
            if next_after is not None:
                params["after"] = next_after

            response = self._fetch_method(**params)
            batch = response.get("data", []) or []
            if not batch:
                break

            records.extend(batch)
            fetched += len(batch)
            oldest_ts = batch[-1][0]
            next_after = oldest_ts
            time.sleep(self._sleep_seconds)

            if start is not None:
                start_ms = int(self._to_utc(start).timestamp() * 1000)
                if int(oldest_ts) <= start_ms:
                    break

        if not records:
            return pd.DataFrame(columns=COLUMNS_OHLCV)

        frame = pd.DataFrame(
            records,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "volume_ccy",
                "volume_quote",
                "confirm",
            ],
        )

        frame["timestamp"] = pd.to_datetime(frame["timestamp"].astype("int64"), unit="ms", utc=True)
        for column in COLUMNS_OHLCV:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")

        frame = frame[["timestamp", *COLUMNS_OHLCV]]
        frame = frame.sort_values("timestamp").set_index("timestamp")

        if end is not None:
            frame = frame[frame.index <= self._to_utc(end)]
        if start is not None:
            frame = frame[frame.index >= self._to_utc(start)]

        return frame

    def _binance_to_okx_instid(self, symbol: str) -> str:
        upper = symbol.upper()
        if not upper.endswith("USDT"):
            raise ValueError(f"Only USDT pairs are supported for OKX SDK source. Received {symbol}.")
        base = upper[:-4]
        if self._inst_type == "SPOT":
            return f"{base}-USDT"
        if self._inst_type == "SWAP":
            return f"{base}-USDT-SWAP"
        raise ValueError(f"Unsupported OKX instrument type: {self._inst_type}")

    @staticmethod
    def _interval_to_okx(interval: str) -> str:
        mapping = {
            "1m": "1m",
            "3m": "3m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1H",
            "2h": "2H",
            "4h": "4H",
            "6h": "6H",
            "12h": "12H",
            "1d": "1D",
            "3d": "3D",
            "1w": "1W",
            "1mth": "1M",
            "1month": "1M",
        }
        key = interval.lower()
        if key not in mapping:
            raise ValueError(f"Unsupported OKX interval: {interval}")
        return mapping[key]

    def _estimate_total(
        self,
        timeframe: str,
        start: Optional[datetime],
        end: Optional[datetime],
    ) -> int:
        default_total = min(600, self._max_total)
        if start is None or end is None:
            return default_total

        start_ts = self._to_utc(start)
        end_ts = self._to_utc(end)
        if end_ts <= start_ts:
            return default_total

        minutes = max((end_ts - start_ts).total_seconds() / 60, 1)
        per_bar = timeframe_to_minutes(timeframe)
        estimate = math.ceil(minutes / per_bar) + 5
        return max(100, min(self._max_total, estimate))

    @staticmethod
    def _to_utc(dt: datetime) -> pd.Timestamp:
        """Convert datetime-like value to UTC timestamp."""
        ts = pd.Timestamp(dt)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return ts


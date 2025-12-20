"""
Bitget Market Data Source.

This module provides market data access using CCXT (Bitget).
"""

from __future__ import annotations

import math
import time
from datetime import datetime
from typing import Optional

import pandas as pd

from data.schemas import COLUMNS_OHLCV
from data.sources.base import MarketDataSource
from utils.timeframes import timeframe_to_minutes


class BitgetSDKDataSource(MarketDataSource):
    """Market data source powered by CCXT (Bitget)."""

    name = "bitget_sdk"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        max_batch: int = 200,
        max_total: int = 2000,
        sleep_seconds: float = 0.2,
        debug: bool = False,
    ) -> None:
        """
        Initialize Bitget SDK data source.

        Parameters
        ----------
        api_key : str, optional
            Bitget API key (not required for public market data)
        api_secret : str, optional
            Bitget API secret (not required for public market data)
        passphrase : str, optional
            Bitget API passphrase (not required for public market data)
        max_batch : int
            Maximum number of candles per API call
        max_total : int
            Maximum total candles to fetch
        sleep_seconds : float
            Sleep time between API calls
        debug : bool
            Enable debug logging
        """
        try:
            import ccxt  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "ccxt package is required for Bitget market data. Install via pip install ccxt."
            ) from exc

        # Initialize exchange (credentials optional for public data)
        params = {
            "enableRateLimit": True,
        }
        if api_key and api_secret and passphrase:
            params.update(
                {
                    "apiKey": api_key,
                    "secret": api_secret,
                    "password": passphrase,  # Bitget passphrase in CCXT
                }
            )

        self._exchange = ccxt.bitget(params)

        self._max_batch = max_batch
        self._max_total = max_total
        self._sleep_seconds = sleep_seconds
        self._debug = debug

    def get_klines(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Get historical kline data from Bitget.

        Parameters
        ----------
        symbol : str
            Trading symbol (e.g., "BTCUSDT")
        timeframe : str
            Timeframe (e.g., "1m", "5m", "1h", "1d")
        start : datetime, optional
            Start time
        end : datetime, optional
            End time

        Returns
        -------
        pd.DataFrame
            OHLCV data with timestamp index
        """
        # Convert symbol format to CCXT (BTCUSDT -> BTC/USDT)
        ccxt_symbol = self._convert_symbol(symbol)
        ccxt_timeframe = timeframe.lower()

        records = []
        fetched = 0
        # CCXT uses `since` (ms) as start time
        end_ms = int(self._to_utc(end).timestamp() * 1000) if end is not None else None
        since_ms = int(self._to_utc(start).timestamp() * 1000) if start is not None else None

        # Default: fetch recent bars
        if since_ms is None and end_ms is None:
            limit = min(self._max_batch, self._max_total)
            ohlcv = self._exchange.fetch_ohlcv(ccxt_symbol, timeframe=ccxt_timeframe, limit=limit)
            for ts_ms, o, h, l, c, v in ohlcv:
                records.append({"timestamp": int(ts_ms), "open": float(o), "high": float(h), "low": float(l), "close": float(c), "volume": float(v)})
        else:
            # Iterate forward from since_ms until end_ms.
            # Some exchanges may return OHLCV in descending order; we advance by the max timestamp.
            tf_min = timeframe_to_minutes(ccxt_timeframe)
            step_ms = int(tf_min * 60_000)
            cursor = since_ms

            # De-duplicate by timestamp
            seen_ts: set[int] = set()

            while fetched < self._max_total:
                limit = min(self._max_batch, self._max_total - fetched)
                if limit <= 0:
                    break

                try:
                    if self._debug:
                        print(f"[Bitget CCXT] fetch_ohlcv(symbol={ccxt_symbol}, tf={ccxt_timeframe}, since={cursor}, limit={limit})")

                    ohlcv = self._exchange.fetch_ohlcv(
                        ccxt_symbol,
                        timeframe=ccxt_timeframe,
                        since=cursor,
                        limit=limit,
                    )
                    if not ohlcv:
                        break

                    batch_ts_max = None
                    for ts_ms, o, h, l, c, v in ohlcv:
                        ts_ms_i = int(ts_ms)
                        if end_ms is not None and ts_ms_i > end_ms:
                            continue
                        if ts_ms_i in seen_ts:
                            continue
                        seen_ts.add(ts_ms_i)

                        records.append(
                            {
                                "timestamp": ts_ms_i,
                                "open": float(o),
                                "high": float(h),
                                "low": float(l),
                                "close": float(c),
                                "volume": float(v),
                            }
                        )
                        batch_ts_max = ts_ms_i if batch_ts_max is None else max(batch_ts_max, ts_ms_i)

                    fetched = len(records)
                    if batch_ts_max is None:
                        break

                    next_cursor = batch_ts_max + step_ms
                    if next_cursor <= cursor:
                        # No forward progress => stop to avoid infinite loop
                        break
                    cursor = next_cursor

                    if end_ms is not None and cursor > end_ms:
                        break

                    time.sleep(self._sleep_seconds)
                except Exception as e:
                    if self._debug:
                        print(f"[Bitget CCXT] Exception: {e}")
                        import traceback
                        traceback.print_exc()
                    break

        if not records:
            return pd.DataFrame(columns=COLUMNS_OHLCV)

        # Convert to DataFrame
        frame = pd.DataFrame(records)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)

        # Ensure numeric types
        for column in COLUMNS_OHLCV:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")

        frame = frame[["timestamp", *COLUMNS_OHLCV]]
        frame = frame.sort_values("timestamp").set_index("timestamp")

        # Filter by time range
        if end is not None:
            frame = frame[frame.index <= self._to_utc(end)]
        if start is not None:
            frame = frame[frame.index >= self._to_utc(start)]

        return frame

    def get_latest_bar(self, symbol: str, timeframe: str) -> Optional[dict]:
        """
        Get the latest completed kline bar.

        Parameters
        ----------
        symbol : str
            Trading symbol
        timeframe : str
            Timeframe

        Returns
        -------
        dict or None
            Latest bar data with keys: timestamp, open, high, low, close, volume
        """
        try:
            ccxt_symbol = self._convert_symbol(symbol)
            ccxt_timeframe = timeframe.lower()
            ohlcv = self._exchange.fetch_ohlcv(ccxt_symbol, timeframe=ccxt_timeframe, limit=2)
            if not ohlcv:
                return None

            ts_ms, o, h, l, c, v = ohlcv[-1]
            return {
                "timestamp": pd.Timestamp(int(ts_ms), unit="ms", tz="UTC"),
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "volume": float(v),
            }
        except Exception as e:
            if self._debug:
                print(f"[Bitget CCXT] Error getting latest bar: {e}")
            return None

        return None

    def _convert_symbol(self, symbol: str) -> str:
        """
        Convert symbol format to Bitget format.

        Parameters
        ----------
        symbol : str
            Symbol in format like "BTCUSDT"

        Returns
        -------
        str
            CCXT symbol format (e.g., BTC/USDT)
        """
        upper = symbol.upper()
        if "/" in upper:
            return upper.replace("-", "/")
        if upper.endswith("USDT") and len(upper) > 4:
            base = upper[:-4]
            return f"{base}/USDT"
        return upper

    @staticmethod
    def _to_utc(dt: datetime) -> pd.Timestamp:
        """Convert datetime-like value to UTC timestamp."""
        ts = pd.Timestamp(dt)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return ts

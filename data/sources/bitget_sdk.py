"""
Bitget Market Data Source.

This module provides market data access using the Bitget SDK.
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
    """Market data source powered by the official Bitget SDK."""

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
            from bitget import Client  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "bitget-python package is required for BitgetSDKDataSource. "
                "Install via pip install bitget-python."
            ) from exc

        # Initialize client (API credentials optional for market data)
        if api_key and api_secret and passphrase:
            self._client = Client(api_key, api_secret, passphrase=passphrase)
        else:
            # Public market data doesn't require credentials
            self._client = None

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
        # Initialize client if not already done
        if self._client is None:
            try:
                from bitget import Client  # type: ignore
                # Use empty credentials for public data
                self._client = Client("", "", passphrase="")
            except ImportError:
                raise ImportError("bitget-python package is required")

        # Convert symbol format (BTCUSDT -> BTCUSDT_SPBL for spot)
        bitget_symbol = self._convert_symbol(symbol)
        bitget_interval = self._interval_to_bitget(timeframe)

        records = []
        fetched = 0
        next_end_time = None

        if end is not None:
            end_ms = int(self._to_utc(end).timestamp() * 1000)
        else:
            end_ms = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)

        if start is not None:
            start_ms = int(self._to_utc(start).timestamp() * 1000)
        else:
            # Default: fetch last 1000 bars
            start_ms = None

        while fetched < self._max_total:
            limit = min(self._max_batch, self._max_total - fetched)
            if limit <= 0:
                break

            try:
                # Bitget API: get klines
                # Note: Bitget API may have different parameter names
                # This is a placeholder - actual API call may vary
                params = {
                    "symbol": bitget_symbol,
                    "granularity": bitget_interval,
                    "limit": str(limit),
                }

                if next_end_time is not None:
                    params["endTime"] = str(next_end_time)
                elif end_ms is not None:
                    params["endTime"] = str(end_ms)

                if self._debug:
                    print(f"[Bitget SDK] Request params: {params}")

                # Call Bitget market API
                # Note: Actual API method name may vary - check Bitget SDK documentation
                response = self._client.market.get_candles(**params)

                if self._debug:
                    print(f"[Bitget SDK] Response type: {type(response)}")

                # Parse response
                if isinstance(response, dict):
                    batch = response.get("data", []) or []
                    code = response.get("code", "")
                    if code and code != "00000":  # Bitget success code
                        if self._debug:
                            print(f"[Bitget SDK] API Error: {response}")
                        break
                elif isinstance(response, list):
                    batch = response
                else:
                    batch = []

                if not batch:
                    if self._debug:
                        print(f"[Bitget SDK] No more data. Fetched {fetched} bars.")
                    break

                if self._debug:
                    print(f"[Bitget SDK] Got {len(batch)} bars in this batch")

                # Convert to standard format
                for item in batch:
                    # Bitget format: [timestamp, open, high, low, close, volume, ...]
                    # Adjust based on actual Bitget response format
                    if isinstance(item, list) and len(item) >= 6:
                        ts_ms = int(item[0])
                        records.append({
                            "timestamp": ts_ms,
                            "open": float(item[1]),
                            "high": float(item[2]),
                            "low": float(item[3]),
                            "close": float(item[4]),
                            "volume": float(item[5]),
                        })
                    elif isinstance(item, dict):
                        # If Bitget returns dict format
                        records.append({
                            "timestamp": int(item.get("ts", item.get("time", 0))),
                            "open": float(item.get("open", 0)),
                            "high": float(item.get("high", 0)),
                            "low": float(item.get("low", 0)),
                            "close": float(item.get("close", 0)),
                            "volume": float(item.get("vol", item.get("volume", 0))),
                        })

                fetched += len(batch)

                # Update next_end_time to oldest timestamp in batch
                if records:
                    oldest_ts = records[-1]["timestamp"]
                    next_end_time = oldest_ts - 1  # Get older data

                # Check if we've reached start time
                if start_ms is not None and records:
                    oldest_ts = records[-1]["timestamp"]
                    if oldest_ts <= start_ms:
                        if self._debug:
                            print(f"[Bitget SDK] Reached start time. Fetched {fetched} bars.")
                        break

                time.sleep(self._sleep_seconds)

            except Exception as e:
                if self._debug:
                    print(f"[Bitget SDK] Exception: {e}")
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
            from bitget import Client  # type: ignore
            if self._client is None:
                self._client = Client("", "", passphrase="")
        except ImportError:
            return None

        bitget_symbol = self._convert_symbol(symbol)
        bitget_interval = self._interval_to_bitget(timeframe)

        try:
            # Get latest candle
            params = {
                "symbol": bitget_symbol,
                "granularity": bitget_interval,
                "limit": "1",
            }

            response = self._client.market.get_candles(**params)

            if isinstance(response, dict):
                data = response.get("data", [])
                code = response.get("code", "")
                if code != "00000" or not data:
                    return None
            elif isinstance(response, list):
                data = response
            else:
                return None

            if not data:
                return None

            item = data[0]
            if isinstance(item, list) and len(item) >= 6:
                return {
                    "timestamp": pd.Timestamp(int(item[0]), unit="ms", tz="UTC"),
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[5]),
                }
            elif isinstance(item, dict):
                return {
                    "timestamp": pd.Timestamp(int(item.get("ts", item.get("time", 0))), unit="ms", tz="UTC"),
                    "open": float(item.get("open", 0)),
                    "high": float(item.get("high", 0)),
                    "low": float(item.get("low", 0)),
                    "close": float(item.get("close", 0)),
                    "volume": float(item.get("vol", item.get("volume", 0))),
                }

        except Exception as e:
            if self._debug:
                print(f"[Bitget SDK] Error getting latest bar: {e}")
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
            Bitget symbol format
        """
        # Bitget spot format: BTCUSDT_SPBL
        # Adjust based on actual Bitget symbol format
        upper = symbol.upper()
        if upper.endswith("USDT"):
            return f"{upper}_SPBL"  # Spot
        return symbol

    @staticmethod
    def _interval_to_bitget(interval: str) -> str:
        """
        Convert timeframe to Bitget format.

        Parameters
        ----------
        interval : str
            Timeframe like "1m", "5m", "1h"

        Returns
        -------
        str
            Bitget interval format
        """
        mapping = {
            "1m": "1min",
            "3m": "3min",
            "5m": "5min",
            "15m": "15min",
            "30m": "30min",
            "1h": "1hour",
            "2h": "2hour",
            "4h": "4hour",
            "6h": "6hour",
            "12h": "12hour",
            "1d": "1day",
            "1w": "1week",
        }
        key = interval.lower()
        if key not in mapping:
            raise ValueError(f"Unsupported Bitget interval: {interval}")
        return mapping[key]

    @staticmethod
    def _to_utc(dt: datetime) -> pd.Timestamp:
        """Convert datetime-like value to UTC timestamp."""
        ts = pd.Timestamp(dt)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return ts

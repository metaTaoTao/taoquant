from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import pandas as pd
import requests

from core.config import default_config
from data.schemas import COLUMNS_OHLCV
from utils.csv_loader import load_csv_ohlcv
from utils.timeframes import timeframe_to_minutes


class DataManager:
    """Unified market data interface with caching support."""

    def __init__(self, config: Optional[Any] = None) -> None:
        self.config = config or default_config
        self.cache_config = self.config.cache

    def get_klines(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        source: str = "okx",
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Retrieve OHLCV data for a symbol from the chosen source."""
        source = source.lower()
        cache_path = self._cache_path(source, symbol, timeframe)
        if use_cache and cache_path.exists():
            cached_df = self._load_cache(cache_path)
            if start or end:
                cached_df = self._trim_timeframe(cached_df, start, end)
            if not cached_df.empty:
                return cached_df

        if source == "okx":
            data = self._fetch_okx(symbol, timeframe, start, end)
        elif source == "binance":
            data = self._fetch_binance(symbol, timeframe, start, end)
        elif source == "csv":
            data = load_csv_ohlcv(symbol=symbol, timeframe=timeframe, start=start, end=end)
        else:
            raise ValueError(f"Unsupported data source: {source}")

        if data.empty:
            raise ValueError(f"No data received for {symbol} {timeframe} via {source}.")

        if use_cache and self.cache_config.enabled:
            self._store_cache(cache_path, data)

        return data

    def _cache_path(self, source: str, symbol: str, timeframe: str) -> Path:
        """Return cache file path for given request."""
        safe_symbol = symbol.replace("/", "_").lower()
        cache_dir = self.cache_config.cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{source}_{safe_symbol}_{timeframe}.parquet"
        return cache_dir / filename

    def _store_cache(self, path: Path, data: pd.DataFrame) -> None:
        """Persist OHLCV data into parquet cache."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data.to_parquet(path)

    def _load_cache(self, path: Path) -> pd.DataFrame:
        """Load OHLCV data from parquet cache, respecting expiration if configured."""
        if not path.exists():
            return pd.DataFrame()
        if self.cache_config.expire_minutes:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if datetime.now(timezone.utc) - mtime > timedelta(minutes=self.cache_config.expire_minutes):
                return pd.DataFrame()
        df = pd.read_parquet(path)
        return self._normalize_dataframe(df)

    @staticmethod
    def _trim_timeframe(
        df: pd.DataFrame,
        start: Optional[datetime],
        end: Optional[datetime],
    ) -> pd.DataFrame:
        """Trim dataframe according to provided start and end."""
        if df.empty:
            return df
        if start:
            df = df[df.index >= DataManager._to_utc(start)]
        if end:
            df = df[df.index <= DataManager._to_utc(end)]
        return df

    def _fetch_okx(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime],
        end: Optional[datetime],
    ) -> pd.DataFrame:
        """Fetch OHLCV data from OKX REST API."""
        endpoint = "/api/v5/market/candles"
        params: Dict[str, Any] = {
            "instId": self._format_okx_symbol(symbol),
            "bar": timeframe,
            "limit": 100,
        }
        if end:
            params["before"] = int(self._to_utc(end).timestamp() * 1000)
        if start:
            params["after"] = int(self._to_utc(start).timestamp() * 1000)

        records: Iterable[pd.DataFrame] = []
        session = requests.Session()
        base_url = self.config.data_sources["okx"].base_url or "https://www.okx.com"
        fetched = 0
        max_records = 1500

        while fetched < max_records:
            response = session.get(f"{base_url}{endpoint}", params=params, timeout=10)
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != "0":
                raise RuntimeError(f"OKX error: {json.dumps(payload)}")
            data = payload.get("data", [])
            if not data:
                break
            df = self._normalize_okx(data)
            records.append(df)
            fetched += len(df)
            oldest_timestamp = df.index.min()
            params["before"] = int(oldest_timestamp.timestamp() * 1000)
            if start and oldest_timestamp <= pd.Timestamp(start, tz=timezone.utc):
                break

        if not records:
            return pd.DataFrame(columns=COLUMNS_OHLCV)

        combined = pd.concat(records).sort_index()
        combined = combined[~combined.index.duplicated(keep="first")]
        if start or end:
            combined = self._trim_timeframe(combined, start, end)
        return combined

    def _fetch_binance(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime],
        end: Optional[datetime],
    ) -> pd.DataFrame:
        """Fetch OHLCV data from Binance REST API."""
        endpoint = "/api/v3/klines"
        session = requests.Session()
        base_url = self.config.data_sources["binance"].base_url or "https://api.binance.com"

        limit = 1000
        params: Dict[str, Any] = {
            "symbol": symbol.upper().replace("/", ""),
            "interval": timeframe,
            "limit": limit,
        }

        if start:
            params["startTime"] = int(self._to_utc(start).timestamp() * 1000)
        if end:
            params["endTime"] = int(self._to_utc(end).timestamp() * 1000)

        records = []
        while True:
            response = session.get(f"{base_url}{endpoint}", params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            if not data:
                break
            df = self._normalize_binance(data)
            records.append(df)
            last_open = df.index.max()
            params["startTime"] = int(last_open.timestamp() * 1000) + timeframe_to_minutes(timeframe) * 60 * 1000
            if len(data) < limit:
                break

        if not records:
            return pd.DataFrame(columns=COLUMNS_OHLCV)

        combined = pd.concat(records).sort_index()
        combined = combined[~combined.index.duplicated(keep="first")]
        if start or end:
            combined = self._trim_timeframe(combined, start, end)
        return combined

    @staticmethod
    def _normalize_okx(raw_data: Iterable[Iterable[str]]) -> pd.DataFrame:
        """Transform OKX candle payload into standard OHLCV dataframe."""
        columns = ["ts", "open", "high", "low", "close", "volume", "volume_ccy"]
        df = pd.DataFrame(list(raw_data), columns=columns)
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df = df.set_index("ts")
        df = df.astype(
            {
                "open": "float64",
                "high": "float64",
                "low": "float64",
                "close": "float64",
                "volume": "float64",
            }
        )
        df = df[COLUMNS_OHLCV]
        return df

    @staticmethod
    def _normalize_binance(raw_data: Iterable[Iterable[Any]]) -> pd.DataFrame:
        """Transform Binance kline payload into standard OHLCV dataframe."""
        columns = [
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_asset_volume",
            "number_of_trades",
            "taker_buy_base",
            "taker_buy_quote",
            "ignore",
        ]
        df = pd.DataFrame(list(raw_data), columns=columns)
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df = df.set_index("open_time")
        df = df.astype(
            {
                "open": "float64",
                "high": "float64",
                "low": "float64",
                "close": "float64",
                "volume": "float64",
            }
        )
        df = df[COLUMNS_OHLCV]
        return df

    @staticmethod
    def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """Ensure dataframe conforms to schema and timezone."""
        if df.empty:
            return df
        if df.index.tz is None:
            df.index = df.index.tz_localize(timezone.utc)
        df.columns = [col.lower() for col in df.columns]
        df = df[COLUMNS_OHLCV]
        return df.sort_index()

    @staticmethod
    def _format_okx_symbol(symbol: str) -> str:
        """Convert generic symbol to OKX instrument identifier."""
        if "-" in symbol:
            return symbol.upper()
        if "/" in symbol:
            base, quote = symbol.upper().split("/")
            return f"{base}-{quote}"
        return f"{symbol.upper()}-USDT"

    @staticmethod
    def _to_utc(dt: datetime) -> pd.Timestamp:
        """Convert datetime-like object to UTC pandas timestamp."""
        ts = pd.Timestamp(dt)
        if ts.tzinfo is None:
            ts = ts.tz_localize(timezone.utc)
        else:
            ts = ts.tz_convert(timezone.utc)
        return ts


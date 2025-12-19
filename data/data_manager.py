from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import pandas as pd
import requests

from data.config import default_config
from data.schemas import COLUMNS_OHLCV
from data.sources import MarketDataSource
from utils.csv_loader import load_csv_ohlcv
from utils.timeframes import timeframe_to_minutes


class DataManager:
    """Unified market data interface with caching support."""

    EXTERNAL_SOURCE_MAP: Dict[str, Tuple[str, str]] = {
        "okx": ("data.sources.okx_sdk", "OkxSDKDataSource"),
        "binance": ("data.sources.binance_sdk", "BinanceSDKDataSource"),
        "okx_sdk": ("data.sources.okx_sdk", "OkxSDKDataSource"),
        "binance_sdk": ("data.sources.binance_sdk", "BinanceSDKDataSource"),
        "bitget": ("data.sources.bitget_sdk", "BitgetSDKDataSource"),
        "bitget_sdk": ("data.sources.bitget_sdk", "BitgetSDKDataSource"),
    }

    def __init__(self, config: Optional[Any] = None) -> None:
        self.config = config or default_config
        self.cache_config = self.config.cache
        self._external_sources: Dict[str, MarketDataSource] = {}

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
            if not cached_df.empty:
                # Check if cache covers the requested time range
                cache_start = cached_df.index[0]
                cache_end = cached_df.index[-1]
                request_start = DataManager._to_utc(start) if start else None
                request_end = DataManager._to_utc(end) if end else None
                
                # Cache covers the request if:
                # - No start requested OR cache starts before/at requested start
                # - No end requested OR cache ends after/at requested end
                # Note: For end time, we allow cache_end to be slightly before request_end
                # if the difference is less than one bar (to handle timezone/rounding issues)
                time_delta = pd.Timedelta(minutes=timeframe_to_minutes(timeframe))
                cache_covers = (
                    (request_start is None or cache_start <= request_start) and
                    (request_end is None or cache_end >= (request_end - time_delta))
                )
                
                if cache_covers:
                    # Cache fully covers the request, trim and return
                    if request_start or request_end:
                        cached_df = self._trim_timeframe(cached_df, start, end)
                    if not cached_df.empty:
                        print(f"[Cache] Using cached data: {len(cached_df)} bars from {cache_start} to {cache_end}")
                        return cached_df
                else:
                    print(f"[Cache] Cache exists but doesn't cover request range:")
                    print(f"  Cache: {cache_start} to {cache_end} ({len(cached_df)} bars)")
                    print(f"  Request: {request_start} to {request_end}")
                    print(f"  Fetching fresh data...")

        # Cache doesn't exist, expired, or doesn't cover the request - fetch fresh data
        if source in self.EXTERNAL_SOURCE_MAP:
            handler = self._load_external_source(source)
            data = handler.get_klines(symbol, timeframe, start=start, end=end)
        elif source == "csv":
            data = load_csv_ohlcv(symbol=symbol, timeframe=timeframe, start=start, end=end)
        else:
            raise ValueError(f"Unsupported data source: {source}")

        if data.empty:
            raise ValueError(f"No data received for {symbol} {timeframe} via {source}.")

        if self.cache_config.enabled:
            self._store_cache(cache_path, data)

        return data

    def get_funding_rates(
        self,
        symbol: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        source: str = "okx",
        use_cache: bool = True,
        allow_empty: bool = False,
    ) -> pd.DataFrame:
        """
        Retrieve perpetual funding rate history (time series).

        Architecture note:
        Funding rate is a data-layer concern; strategies should consume the returned
        time series (aligned/ffill to bar timestamps in orchestration/runner).

        Parameters
        ----------
        symbol : str
            Generic symbol, e.g. "BTCUSDT" or "BTC/USDT".
        start, end : Optional[datetime]
            UTC range to fetch (best effort; OKX pagination limitations apply).
        source : str
            Currently only "okx" is supported.
        use_cache : bool
            Whether to use parquet cache under data/cache.

        Returns
        -------
        pd.DataFrame
            Index: UTC timestamp
            Columns: ["funding_rate"]
        """
        source = source.lower()
        if source != "okx":
            raise ValueError(f"Unsupported funding rate source: {source}")

        cache_path = self._funding_cache_path(source, symbol)
        request_start = DataManager._to_utc(start) if start else None
        request_end = DataManager._to_utc(end) if end else None

        if use_cache and cache_path.exists():
            cached = pd.read_parquet(cache_path)
            if not cached.empty:
                cached["timestamp"] = pd.to_datetime(cached["timestamp"], utc=True)
                cached = cached.set_index("timestamp").sort_index()
                cache_start = cached.index.min()
                cache_end = cached.index.max()
                if (
                    (request_start is None or cache_start <= request_start)
                    and (request_end is None or cache_end >= request_end)
                ):
                    out = cached
                    if request_start:
                        out = out[out.index >= request_start]
                    if request_end:
                        out = out[out.index <= request_end]
                    return out[["funding_rate"]]

        df = self._fetch_okx_funding_rate_history(symbol=symbol, start=start, end=end)
        if df.empty:
            if allow_empty:
                return df
            raise ValueError(
                "No funding rate data returned from OKX for the requested time range. "
                "OKX public API often retains only a limited funding history window. "
                "Consider using OKX historical data downloads or storing funding snapshots during live runs."
            )

        if self.cache_config.enabled:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            df.reset_index().rename(columns={"index": "timestamp"}).to_parquet(cache_path, index=False)

        return df

    def _cache_path(self, source: str, symbol: str, timeframe: str) -> Path:
        """Return cache file path for given request."""
        safe_symbol = symbol.replace("/", "_").lower()
        cache_dir = self.cache_config.cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{source}_{safe_symbol}_{timeframe}.parquet"
        return cache_dir / filename

    def _funding_cache_path(self, source: str, symbol: str) -> Path:
        """Return cache file path for funding rates."""
        safe_symbol = symbol.replace("/", "_").replace("-", "_").lower()
        cache_dir = self.cache_config.cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{source}_{safe_symbol}_funding.parquet"
        return cache_dir / filename

    def _fetch_okx_funding_rate_history(
        self,
        symbol: str,
        start: Optional[datetime],
        end: Optional[datetime],
    ) -> pd.DataFrame:
        """
        Fetch funding rate history from OKX REST API.

        We try the historical endpoint first; if OKX changes the interface, we raise
        a clear error with the payload to help debugging.
        """
        # OKX instrument id for USDT perpetual swap, e.g. BTC-USDT-SWAP
        inst_id = self._format_okx_swap_instid(symbol)

        base_url = self.config.data_sources["okx"].base_url or "https://www.okx.com"
        session = requests.Session()

        # OKX provides latest funding via /api/v5/public/funding-rate and history via
        # /api/v5/public/funding-rate-history (documented in OKX API v5).
        endpoint = "/api/v5/public/funding-rate-history"
        params: Dict[str, Any] = {"instId": inst_id, "limit": 100}

        # OKX pagination for this endpoint uses "after" to page backwards in time (older data).
        # Empirically:
        # - no params / after=now -> returns most recent records
        # - before=now -> returns empty
        # So we use "after" as the cursor and move it to older timestamps each loop.
        if end:
            params["after"] = int(self._to_utc(end).timestamp() * 1000)

        start_ts = self._to_utc(start) if start else None
        records: list[pd.DataFrame] = []
        fetched = 0
        max_records = 10000  # safety cap

        while fetched < max_records:
            resp = session.get(f"{base_url}{endpoint}", params=params, timeout=10)
            if resp.status_code == 404:
                raise RuntimeError(
                    "OKX funding rate history endpoint not found (404). "
                    "Please verify OKX API path for funding history."
                )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("code") != "0":
                raise RuntimeError(f"OKX funding history error: {json.dumps(payload)}")

            data = payload.get("data", [])
            if not data:
                break

            # Expected fields include: fundingRate, fundingTime (ms)
            df = pd.DataFrame(data)
            if "fundingTime" not in df.columns or "fundingRate" not in df.columns:
                raise RuntimeError(f"OKX funding history unexpected payload: {json.dumps(payload)[:2000]}")

            df["timestamp"] = pd.to_datetime(df["fundingTime"].astype("int64"), unit="ms", utc=True)
            df["funding_rate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
            df = df[["timestamp", "funding_rate"]].dropna()
            df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
            df = df.set_index("timestamp")

            records.append(df)
            fetched += len(df)

            oldest = df.index.min()
            # page backwards: next "after" = oldest timestamp - 1ms
            params["after"] = int(oldest.timestamp() * 1000) - 1

            if start_ts is not None and oldest <= start_ts:
                break

        if not records:
            return pd.DataFrame(columns=["funding_rate"])

        out = pd.concat(records).sort_index()
        out = out[~out.index.duplicated(keep="first")]
        if start_ts is not None:
            out = out[out.index >= start_ts]
        if end:
            out = out[out.index <= self._to_utc(end)]
        return out

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
            "bar": self._map_okx_timeframe(timeframe),
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
        df = pd.DataFrame(list(raw_data))
        if df.empty:
            return pd.DataFrame(columns=COLUMNS_OHLCV)

        rename_map = {
            0: "ts",
            1: "open",
            2: "high",
            3: "low",
            4: "close",
            5: "volume",
        }
        df = df.rename(columns=rename_map)
        required_cols = ["ts", "open", "high", "low", "close", "volume"]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            raise ValueError(f"OKX payload missing required columns: {missing}")

        df["ts"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms", utc=True)
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
        upper = symbol.upper()
        if "-" in upper:
            return upper
        if "/" in upper:
            base, quote = upper.split("/")
            return f"{base}-{quote}"
        if upper.endswith("USDT"):
            base = upper[:-4]
            return f"{base}-USDT"
        return f"{upper}-USDT"

    @staticmethod
    def _format_okx_swap_instid(symbol: str) -> str:
        """
        Convert generic symbol to OKX USDT perpetual swap instrument id.

        Examples:
          - BTCUSDT -> BTC-USDT-SWAP
          - BTC/USDT -> BTC-USDT-SWAP
          - BTC-USDT -> BTC-USDT-SWAP
          - BTC-USDT-SWAP -> BTC-USDT-SWAP
        """
        upper = symbol.upper()
        if upper.endswith("-SWAP"):
            return upper
        if "-" in upper:
            # BTC-USDT or BTC-USDT-SWAP already handled above
            if upper.count("-") >= 1:
                base_quote = upper
                if base_quote.count("-") >= 2:
                    # something like BTC-USDT-SWAP already
                    return base_quote
                return f"{base_quote}-SWAP"
        if "/" in upper:
            base, quote = upper.split("/")
            return f"{base}-{quote}-SWAP"
        if upper.endswith("USDT"):
            base = upper[:-4]
            return f"{base}-USDT-SWAP"
        return f"{upper}-USDT-SWAP"

    @staticmethod
    def _to_utc(dt: datetime) -> pd.Timestamp:
        """Convert datetime-like object to UTC pandas timestamp."""
        ts = pd.Timestamp(dt)
        if ts.tzinfo is None:
            ts = ts.tz_localize(timezone.utc)
        else:
            ts = ts.tz_convert(timezone.utc)
        return ts

    def _load_external_source(self, name: str) -> MarketDataSource:
        """Dynamically load and cache external data source implementations."""
        if name in self._external_sources:
            return self._external_sources[name]
        module_name, class_name = self.EXTERNAL_SOURCE_MAP[name]
        try:
            module = __import__(module_name, fromlist=[class_name])
            cls = getattr(module, class_name)
        except ImportError as exc:  # pragma: no cover
            raise ImportError(f"Failed to import data source '{name}'. Ensure required package is installed.") from exc
        
        # Pass debug=False to OkxSDKDataSource to suppress debug output
        if class_name == "OkxSDKDataSource":
            instance = cls(debug=False)
        else:
            instance = cls()
        
        if not isinstance(instance, MarketDataSource):
            raise TypeError(f"Data source '{name}' must inherit from MarketDataSource.")
        self._external_sources[name] = instance
        return instance


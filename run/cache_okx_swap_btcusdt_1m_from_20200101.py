"""
将 OKX 合约（USDT 永续：BTC-USDT-SWAP）的 1m K 线从 2020-01-01 00:00 UTC 拉到现在，
并缓存到本地 parquet：data/cache/okx_swap_btcusdt_1m.parquet

特点：
- 分段拉取（默认每段 20 天），避免 SDK 内部 50k safety limit
- 支持断点续跑：如果 parquet 已存在，则从最后一根K线的下一分钟继续拉
- 输出实际覆盖范围，方便核对

用法：
    python run/cache_okx_swap_btcusdt_1m_from_20200101.py

缓存完成后，回测直接用：
    DataManager().get_klines("BTCUSDT", "1m", start=..., end=..., source="okx_swap")
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data.sources.okx_sdk import OkxSDKDataSource


SYMBOL = "BTCUSDT"
TIMEFRAME = "1m"
START = datetime(2020, 1, 1, 0, 0, tzinfo=timezone.utc)

# 30 days = 43200 bars, safely under the 50k cap.
CHUNK_DAYS = 30

# Periodically flush to disk (rewrite parquet) to avoid losing progress on network errors.
FLUSH_EVERY_CHUNKS = 10  # ~300 days per flush

# Retry settings for transient HTTP errors.
MAX_RETRIES_PER_CHUNK = 5
RETRY_BASE_SLEEP_SECONDS = 2.0

CACHE_PATH = Path("data/cache/okx_swap_btcusdt_1m.parquet")


def _floor_minute(ts: datetime) -> datetime:
    return ts.replace(second=0, microsecond=0)


def _load_existing() -> pd.DataFrame | None:
    if not CACHE_PATH.exists():
        return None
    df = pd.read_parquet(CACHE_PATH)
    if df.empty:
        return None
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Cache parquet must use DatetimeIndex.")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df = df.sort_index()
    return df


def main() -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    now_incl = _floor_minute(datetime.now(timezone.utc))
    end_excl = now_incl + timedelta(minutes=1)  # inclusive minute coverage target

    existing = _load_existing()
    if existing is not None:
        existing_start = existing.index.min()
        existing_end = existing.index.max()
        # resume from next minute
        resume_start = (existing_end + pd.Timedelta(minutes=1)).to_pydatetime()
        start = max(START, resume_start)
        print("=" * 80)
        print("Existing cache found, resume download")
        print("=" * 80)
        print(f"cache_path: {CACHE_PATH}")
        print(f"cached_range: {existing_start} -> {existing_end} (bars={len(existing)})")
        print(f"resume_from:  {start}")
        print()
    else:
        start = START
        print("=" * 80)
        print("No existing cache, start fresh download")
        print("=" * 80)
        print(f"cache_path: {CACHE_PATH}")
        print(f"start_from:  {start}")
        print()

    if start >= end_excl:
        print("Nothing to do: cache already covers up to current minute.")
        return

    frames: list[pd.DataFrame] = []
    if existing is not None:
        frames.append(existing)

    total_new = 0
    chunk = timedelta(days=int(CHUNK_DAYS))
    cur = start
    chunks_since_flush = 0

    def flush_to_disk() -> pd.DataFrame:
        nonlocal frames, chunks_since_flush
        combined_local = pd.concat(frames).sort_index()
        combined_local = combined_local[~combined_local.index.duplicated(keep="last")]
        combined_local.to_parquet(CACHE_PATH)
        frames = [combined_local]  # keep a single in-memory frame
        chunks_since_flush = 0
        return combined_local

    # Fetch forward in chunks, but each chunk request is bounded to avoid SDK safety limit.
    while cur < end_excl:
        nxt = min(cur + chunk, end_excl)
        # OkxSDKDataSource treats end as inclusive in its final filtering (<= end).
        # So we pass end_incl = nxt - 1 minute.
        end_incl = (pd.Timestamp(nxt).tz_convert("UTC") - pd.Timedelta(minutes=1)).to_pydatetime()
        start_dt = pd.Timestamp(cur).tz_convert("UTC").to_pydatetime()

        print(f"[FETCH] {start_dt} -> {end_incl} (target {CHUNK_DAYS}d chunk)")

        df = pd.DataFrame()
        for attempt in range(1, MAX_RETRIES_PER_CHUNK + 1):
            try:
                # Recreate SDK client each attempt to avoid long-lived HTTP2 issues.
                ds = OkxSDKDataSource(inst_type="SWAP", max_batch=300, sleep_seconds=0.25, debug=False)
                df = ds.get_klines(symbol=SYMBOL, timeframe=TIMEFRAME, start=start_dt, end=end_incl)
                break
            except Exception as exc:
                if attempt >= MAX_RETRIES_PER_CHUNK:
                    print(f"  [ERROR] chunk failed after {attempt} attempts: {exc}")
                    print("  Saving progress to disk and stopping.")
                    if frames:
                        _ = flush_to_disk()
                    return
                sleep_s = RETRY_BASE_SLEEP_SECONDS * (2 ** (attempt - 1))
                print(f"  [WARN] fetch failed (attempt {attempt}/{MAX_RETRIES_PER_CHUNK}): {exc}")
                print(f"  retrying after {sleep_s:.1f}s ...")
                import time

                time.sleep(sleep_s)

        if df.empty:
            print("  [WARN] empty chunk returned; saving progress and stopping.")
            if frames:
                _ = flush_to_disk()
            return

        df = df.sort_index()
        frames.append(df)
        total_new += len(df)
        print(f"  got {len(df)} bars: {df.index[0]} -> {df.index[-1]}")

        # advance to next minute after last bar we received
        cur = (df.index.max() + pd.Timedelta(minutes=1)).to_pydatetime()
        chunks_since_flush += 1

        if chunks_since_flush >= FLUSH_EVERY_CHUNKS:
            combined_local = flush_to_disk()
            print(f"[FLUSH] saved checkpoint: bars={len(combined_local)} range={combined_local.index.min()} -> {combined_local.index.max()}")

    combined = flush_to_disk()

    print()
    print("=" * 80)
    print("OKX SWAP 1m cache completed")
    print("=" * 80)
    print(f"cache_path: {CACHE_PATH}")
    print(f"bars:       {len(combined)}")
    print(f"range:      {combined.index.min()} -> {combined.index.max()}")
    print(f"new_bars:   {total_new}")
    print()
    print("Usage example:")
    print('  from data import DataManager')
    print('  dm = DataManager()')
    print('  df = dm.get_klines(\"BTCUSDT\", \"1m\", start=..., end=..., source=\"okx_swap\")')


if __name__ == "__main__":
    main()


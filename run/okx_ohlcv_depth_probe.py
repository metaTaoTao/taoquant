"""
探测 OKX OHLCV 可追溯深度（不依赖本地缓存）。

用途：
- 回答“OKX 1m 最早能拉到多早？”这个问题的实证依据
- 先用 1D 低成本探测最早日期，再可选用 1m 验证该日的分钟级数据是否存在

注意：
- 该脚本会直接调用 OKX 公共行情接口（通过 okx SDK），可能受到限频影响
- 默认探测 SPOT 的 BTC-USDT（对应通用符号 BTCUSDT）
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd

from data.sources.okx_sdk import OkxSDKDataSource


def main() -> None:
    symbol = "BTCUSDT"
    inst_type = "SPOT"  # change to SWAP if you want BTC-USDT-SWAP
    print("=" * 80)
    print("OKX OHLCV depth probe")
    print("=" * 80)
    print(f"symbol={symbol} inst_type={inst_type}")

    ds = OkxSDKDataSource(inst_type=inst_type, max_batch=300, sleep_seconds=0.2, debug=False)

    # 1) Probe with 1D to find earliest day quickly.
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start_probe = datetime(2016, 1, 1, tzinfo=timezone.utc)

    print()
    print("[1D] probing earliest daily candle...")
    df_1d = ds.get_klines(symbol=symbol, timeframe="1d", start=start_probe, end=end)
    if df_1d.empty:
        print("No 1D data returned.")
        return

    earliest_1d = df_1d.index.min()
    latest_1d = df_1d.index.max()
    print(f"1D bars={len(df_1d)} earliest={earliest_1d} latest={latest_1d}")

    # 2) Optional: validate minute-level existence on the earliest day.
    day_start = pd.Timestamp(earliest_1d).floor("D")
    day_end = day_start + pd.Timedelta(days=1)
    print()
    print(f"[1m] validating first day minutes: {day_start} -> {day_end}")
    df_1m = ds.get_klines(
        symbol=symbol,
        timeframe="1m",
        start=day_start.to_pydatetime(),
        end=day_end.to_pydatetime(),
    )
    if df_1m.empty:
        print("No 1m data returned for earliest 1D day (could be API retention or listing granularity).")
        return
    print(f"1m bars={len(df_1m)} earliest={df_1m.index.min()} latest={df_1m.index.max()}")


if __name__ == "__main__":
    main()


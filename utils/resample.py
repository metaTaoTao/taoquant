from __future__ import annotations

import pandas as pd


def resample_ohlcv(data: pd.DataFrame, target_timeframe: str) -> pd.DataFrame:
    """Resample OHLCV dataframe to a higher timeframe."""
    if data.empty:
        return data
    if data.index.tz is None:
        data = data.copy()
        data.index = data.index.tz_localize("UTC")
    ohlc_dict = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    resampled = data.resample(target_timeframe, label="right", closed="right").apply(ohlc_dict).dropna()
    if resampled.index.tz is None:
        resampled.index = resampled.index.tz_localize("UTC")
    else:
        resampled.index = resampled.index.tz_convert("UTC")
    return resampled


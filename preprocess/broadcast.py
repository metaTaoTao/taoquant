from __future__ import annotations

import pandas as pd


def broadcast_sr_to_1m(df1m: pd.DataFrame, df_ht_sr: pd.DataFrame) -> pd.DataFrame:
    """Merge confirmed higher timeframe support/resistance columns into 1m data via asof merge.

    Parameters
    ----------
    df1m : pd.DataFrame
        Base 1-minute OHLCV dataframe with DatetimeIndex.
    df_ht_sr : pd.DataFrame
        Output of `build_sr_range` on higher timeframe (15m, 1d, etc.) data containing support/resistance.

    Returns
    -------
    pd.DataFrame
        1-minute dataframe enriched with support, resistance, midline, range_valid, atr.
    """

    if not isinstance(df1m.index, pd.DatetimeIndex):
        raise TypeError("df1m must have a DatetimeIndex")
    if not isinstance(df_ht_sr.index, pd.DatetimeIndex):
        raise TypeError("df_ht_sr must have a DatetimeIndex")

    base = df1m.copy().sort_index()
    base.columns = [str(col).lower() for col in base.columns]

    sr = df_ht_sr.copy().sort_index()
    sr.columns = [str(col).lower() for col in sr.columns]

    columns_to_merge = [
        col
        for col in ["support", "resistance", "midline", "range_valid", "atr", "atr_short"]
        if col in sr.columns
    ]
    if not columns_to_merge:
        raise ValueError("df_ht_sr must contain support/resistance columns")

    merged = pd.merge_asof(
        base,
        sr[columns_to_merge],
        left_index=True,
        right_index=True,
        direction="backward",
    )

    return merged

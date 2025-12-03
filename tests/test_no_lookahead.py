from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from preprocess.broadcast import broadcast_sr_to_1m
from preprocess.build_sr_range import build_sr_range
from indicators import sr_volume_boxes


def _fake_indicator_output(data: pd.DataFrame) -> pd.DataFrame:
    out = data.copy()
    out["atr"] = 1.0
    out["pivot_low"] = np.nan
    out["pivot_high"] = np.nan
    out.loc[data.index[30], "pivot_low"] = 100.0
    out.loc[data.index[80], "pivot_high"] = 200.0
    return out


@pytest.fixture(autouse=True)
def patch_indicator(monkeypatch):
    monkeypatch.setattr(
        sr_volume_boxes.SupportResistanceVolumeBoxesIndicator,
        "calculate",
        lambda self, df: _fake_indicator_output(df),
    )


def test_support_resistance_no_lookahead():
    idx15 = pd.date_range("2025-01-01", periods=120, freq="15T")
    df15 = pd.DataFrame(
        {
            "open": np.linspace(100, 120, len(idx15)),
            "high": np.linspace(101, 121, len(idx15)),
            "low": np.linspace(99, 119, len(idx15)),
            "close": np.linspace(100, 120, len(idx15)),
            "volume": 1000,
        },
        index=idx15,
    )

    sr15 = build_sr_range(df15)

    assert pd.isna(sr15.loc[idx15[49], "support"])
    assert sr15.loc[idx15[50], "support"] == 100.0
    assert pd.isna(sr15.loc[idx15[49], "resistance"])

    idx1m = pd.date_range(idx15[0], idx15[-1], freq="1T")
    df1m = pd.DataFrame(
        {
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100,
            "volume": 10,
        },
        index=idx1m,
    )

    merged = broadcast_sr_to_1m(df1m, sr15)

    before = idx15[50] - pd.Timedelta(minutes=1)
    assert pd.isna(merged.loc[before, "support"])
    assert merged.loc[idx15[50], "support"] == 100.0
    assert merged.loc[idx15[51], "support"] == 100.0

"""
Breakout risk factors for range/grid strategies.

Purpose:
  Detect "near-boundary + directional pressure" regimes where a range strategy
  is most vulnerable (inventory accumulation / left-tail).

All functions are pure (no I/O, no side effects).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_breakout_risk(
    close: pd.Series,
    atr: pd.Series,
    support: float,
    resistance: float,
    trend_score: pd.Series | None = None,
    band_atr_mult: float = 1.5,
    band_pct: float = 0.003,
    trend_weight: float = 0.7,
) -> pd.DataFrame:
    """
    Compute upper/lower breakout risk (0..1) for a fixed S/R range.

    Intuition:
      - Risk increases as price approaches a boundary within a "danger band".
      - Trend direction can amplify risk (e.g., negative trend near support).
      - ATR provides volatility-aware scaling of the danger band.

    Parameters
    ----------
    close : pd.Series
        Close price series.
    atr : pd.Series
        ATR series (same index).
    support : float
        Range support.
    resistance : float
        Range resistance.
    trend_score : pd.Series | None
        Optional trend score in [-1, 1]. Negative implies downtrend.
    band_atr_mult : float
        Danger band width in ATR multiples.
    band_pct : float
        Minimum danger band width as percentage of price (fallback when ATR small).
    trend_weight : float
        Weight of trend component in risk. 0 disables trend contribution.

    Returns
    -------
    pd.DataFrame
        Columns:
          - breakout_risk_down: 0..1
          - breakout_risk_up: 0..1
    """
    if support >= resistance:
        raise ValueError("support must be < resistance")
    if band_atr_mult <= 0:
        raise ValueError("band_atr_mult must be > 0")
    if band_pct <= 0:
        raise ValueError("band_pct must be > 0")
    if not (0.0 <= trend_weight <= 1.0):
        raise ValueError("trend_weight must be in [0, 1]")

    close_f = close.astype(float)
    atr_f = atr.astype(float)

    # Danger band width (USD): max(ATR band, pct band)
    band_usd = np.maximum(band_atr_mult * atr_f, band_pct * close_f)

    # Distance to boundaries (USD)
    dist_to_support = (close_f - float(support)).clip(lower=0.0)
    dist_to_res = (float(resistance) - close_f).clip(lower=0.0)

    # Proximity scores: 1 at boundary, 0 outside danger band
    prox_down = (1.0 - (dist_to_support / band_usd.replace(0.0, np.nan))).clip(lower=0.0, upper=1.0)
    prox_up = (1.0 - (dist_to_res / band_usd.replace(0.0, np.nan))).clip(lower=0.0, upper=1.0)

    if trend_score is None:
        trend = pd.Series(0.0, index=close.index)
    else:
        trend = trend_score.astype(float).clip(lower=-1.0, upper=1.0).fillna(0.0)

    # Directional pressure: downtrend raises downside risk, uptrend raises upside risk
    down_pressure = (-trend).clip(lower=0.0, upper=1.0)
    up_pressure = (trend).clip(lower=0.0, upper=1.0)

    breakout_risk_down = (prox_down * (1.0 - trend_weight) + prox_down * down_pressure * trend_weight).clip(0.0, 1.0)
    breakout_risk_up = (prox_up * (1.0 - trend_weight) + prox_up * up_pressure * trend_weight).clip(0.0, 1.0)

    return pd.DataFrame(
        {
            "breakout_risk_down": breakout_risk_down.fillna(0.0),
            "breakout_risk_up": breakout_risk_up.fillna(0.0),
        },
        index=close.index,
    )



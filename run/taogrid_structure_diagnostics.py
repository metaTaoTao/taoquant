"""
TaoGrid 均值回归结构诊断（策略研究用，不改交易逻辑）。

输出核心“因子/结构”指标，用于回答：
  - 1m 下是否真的存在可交易的均值回归？回归速度（half-life）有多快？
  - 价格是否大部分时间驻留在均值附近？（time-in-band）
  - 偏离后能否回归？成功率与耗时分布（reversion success / time-to-revert）
  - 更偏趋势还是均值回归？（Hurst / Variance Ratio）

用法：
  python run/taogrid_structure_diagnostics.py
  python run/taogrid_structure_diagnostics.py --output run/results_lean_taogrid

说明：
  - 依赖 DataManager 的缓存数据（okx）
  - 为避免 Windows 控制台编码问题，仅打印英文/ASCII 摘要
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data import DataManager  # noqa: E402


@dataclass(frozen=True)
class DiagnosticsConfig:
    symbol: str = "BTCUSDT"
    timeframe: str = "1m"
    start: datetime = datetime(2025, 7, 10, tzinfo=timezone.utc)
    end: datetime = datetime(2025, 8, 10, tzinfo=timezone.utc)
    support: float = 111_000.0
    resistance: float = 123_000.0
    z_lookback: int = 240  # 4h on 1m
    z_entry_levels: Tuple[float, ...] = (1.5, 2.0)
    z_exit: float = 0.5
    revert_horizon_bars: int = 3 * 24 * 60  # 3 days
    vr_lags: Tuple[int, ...] = (2, 5, 10, 30, 60)
    hurst_lags: Tuple[int, ...] = (2, 4, 8, 16, 32, 64, 128)


def _safe_float(x) -> float:
    try:
        v = float(x)
        if np.isfinite(v):
            return v
        return 0.0
    except Exception:
        return 0.0


def _ar1_half_life(x: pd.Series) -> Dict[str, float]:
    """
    Estimate AR(1): x_t = a + b x_{t-1} + e
    Half-life = -ln(2) / ln(b) for 0 < b < 1
    """
    s = x.dropna().astype(float)
    if len(s) < 50:
        return {"ar1_b": 0.0, "half_life_bars": 0.0}

    x1 = s.shift(1).dropna()
    y = s.loc[x1.index]
    X = np.vstack([np.ones(len(x1)), x1.values]).T
    beta, *_ = np.linalg.lstsq(X, y.values, rcond=None)
    b = float(beta[1])

    if 0.0 < b < 1.0:
        half_life = float(-np.log(2.0) / np.log(b))
    else:
        half_life = float("inf")

    return {
        "ar1_b": b,
        "half_life_bars": half_life if np.isfinite(half_life) else 0.0,
    }


def _hurst_exponent_from_diffs(log_price: pd.Series, lags: Tuple[int, ...]) -> Dict[str, float]:
    """
    Rough Hurst estimate: std(Δ logP over lag) ~ lag^H
    Fit log(std) vs log(lag) slope.
    """
    s = log_price.dropna().astype(float)
    if len(s) < max(lags) + 10:
        return {"hurst": 0.0}

    xs: List[float] = []
    ys: List[float] = []
    for lag in lags:
        dif = s.diff(lag).dropna()
        if len(dif) < 50:
            continue
        std = float(dif.std())
        if std <= 0:
            continue
        xs.append(np.log(float(lag)))
        ys.append(np.log(std))

    if len(xs) < 3:
        return {"hurst": 0.0}

    X = np.vstack([np.ones(len(xs)), np.array(xs)]).T
    beta, *_ = np.linalg.lstsq(X, np.array(ys), rcond=None)
    hurst = float(beta[1])
    return {"hurst": hurst}


def _variance_ratio(log_price: pd.Series, q_list: Tuple[int, ...]) -> Dict[str, float]:
    """
    Variance Ratio VR(q) for log returns:
      r_t = Δ logP
      VR(q) = Var(sum_{i=0..q-1} r_{t-i}) / (q * Var(r_t))
    Interpretation:
      VR(q) < 1 : mean reversion
      VR(q) > 1 : momentum
    """
    s = log_price.dropna().astype(float)
    r = s.diff().dropna()
    if len(r) < 500:
        return {f"vr_{q}": 0.0 for q in q_list}

    var1 = float(r.var())
    out: Dict[str, float] = {}
    for q in q_list:
        if q <= 1 or len(r) < q + 10 or var1 <= 0:
            out[f"vr_{q}"] = 0.0
            continue
        rq = r.rolling(window=q).sum().dropna()
        out[f"vr_{q}"] = float(rq.var() / (q * var1))
    return out


def _time_in_band(close: pd.Series, support: float, resistance: float) -> Dict[str, float]:
    s = close.dropna().astype(float)
    width = resistance - support
    if width <= 0 or len(s) == 0:
        return {}

    pos = (s - support) / width
    bins = np.linspace(0.0, 1.0, 11)  # 10 bins
    cats = pd.cut(pos, bins=bins, include_lowest=True)
    dist = cats.value_counts(normalize=True).sort_index()

    out: Dict[str, float] = {}
    for k, v in dist.items():
        out[f"band_{k.left:.1f}_{k.right:.1f}"] = float(v)

    out["in_band_ratio"] = float(((s >= support) & (s <= resistance)).mean())
    out["mid_zone_ratio_45_55"] = float(((pos >= 0.45) & (pos <= 0.55)).mean())
    return out


def _zscore(series: pd.Series, lookback: int) -> pd.Series:
    s = series.astype(float)
    mu = s.rolling(lookback, min_periods=max(20, lookback // 4)).mean()
    sd = s.rolling(lookback, min_periods=max(20, lookback // 4)).std(ddof=0)
    return (s - mu) / sd.replace(0.0, np.nan)


def _reversion_success(
    z: pd.Series,
    entry_abs: float,
    exit_abs: float,
    horizon_bars: int,
    minutes_per_bar: int,
) -> Dict[str, float]:
    """
    Event study:
      - entry when |z| >= entry_abs
      - success when later |z| <= exit_abs within horizon_bars
    """
    zs = z.dropna()
    if len(zs) < 500:
        return {
            "events": 0.0,
            "success_rate": 0.0,
            "median_time_to_revert_hours": 0.0,
            "p90_time_to_revert_hours": 0.0,
        }

    idx = zs.index
    zv = zs.values
    n = len(zv)
    i = 0
    times: List[float] = []
    events = 0
    successes = 0

    while i < n:
        if abs(zv[i]) >= entry_abs:
            events += 1
            j_end = min(n - 1, i + horizon_bars)
            j = i + 1
            hit = False
            while j <= j_end:
                if abs(zv[j]) <= exit_abs:
                    hit = True
                    break
                j += 1
            if hit:
                successes += 1
                dt_bars = j - i
                dt_hours = dt_bars * minutes_per_bar / 60.0
                times.append(float(dt_hours))
                i = j  # skip until revert point to reduce overlap
            else:
                i = j_end  # jump
        i += 1

    if events == 0:
        return {
            "events": 0.0,
            "success_rate": 0.0,
            "median_time_to_revert_hours": 0.0,
            "p90_time_to_revert_hours": 0.0,
        }

    times_arr = np.array(times) if times else np.array([])
    median = float(np.median(times_arr)) if len(times_arr) else 0.0
    p90 = float(np.quantile(times_arr, 0.9)) if len(times_arr) else 0.0

    return {
        "events": float(events),
        "success_rate": float(successes / events),
        "median_time_to_revert_hours": median,
        "p90_time_to_revert_hours": p90,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=str, default="run/results_lean_taogrid")
    args = parser.parse_args()

    cfg = DiagnosticsConfig()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    dm = DataManager()
    data = dm.get_klines(
        symbol=cfg.symbol,
        timeframe=cfg.timeframe,
        start=cfg.start,
        end=cfg.end,
        source="okx",
    )
    if data.empty:
        raise ValueError("No data returned by DataManager")

    close = data["close"].astype(float)
    logp = np.log(close)

    # Build a mean-reverting component around rolling mean (helps interpret half-life)
    mr_component = logp - logp.rolling(cfg.z_lookback, min_periods=max(20, cfg.z_lookback // 4)).mean()

    hl = _ar1_half_life(mr_component.dropna())
    hurst = _hurst_exponent_from_diffs(logp, cfg.hurst_lags)
    vr = _variance_ratio(logp, cfg.vr_lags)
    tib = _time_in_band(close, cfg.support, cfg.resistance)

    # Z-score reversion
    z = _zscore(logp, cfg.z_lookback)
    minutes_per_bar = 1  # timeframe="1m"
    reversion: Dict[str, Dict[str, float]] = {}
    for entry in cfg.z_entry_levels:
        key = f"z_entry_{entry:.1f}_exit_{cfg.z_exit:.1f}_H_{cfg.revert_horizon_bars}"
        reversion[key] = _reversion_success(
            z=z,
            entry_abs=float(entry),
            exit_abs=float(cfg.z_exit),
            horizon_bars=int(cfg.revert_horizon_bars),
            minutes_per_bar=minutes_per_bar,
        )

    # Basic drift/vol
    r = logp.diff().dropna()
    drift_per_day = float(r.mean() * 1440.0)
    vol_per_day = float(r.std(ddof=0) * np.sqrt(1440.0))

    out = {
        "config": {
            **asdict(cfg),
            "start": cfg.start.isoformat(),
            "end": cfg.end.isoformat(),
        },
        "data": {
            "bars": int(len(data)),
            "start": str(data.index.min()),
            "end": str(data.index.max()),
        },
        "mr_structure": {
            **hl,
            **hurst,
            **vr,
            "drift_per_day": drift_per_day,
            "vol_per_day": vol_per_day,
        },
        "time_in_band": tib,
        "reversion": reversion,
    }

    (out_dir / "structure_diagnostics.json").write_text(
        json.dumps(out, indent=2, default=_safe_float),
        encoding="utf-8",
    )

    # Markdown report (ASCII to be safe)
    md_lines: List[str] = []
    md_lines.append("# TaoGrid Structure Diagnostics")
    md_lines.append("")
    md_lines.append(f"Results dir: `{out_dir.as_posix()}`")
    md_lines.append("")
    md_lines.append("## Mean Reversion Structure")
    md_lines.append(f"- AR(1) b: {hl.get('ar1_b', 0.0):.4f}")
    md_lines.append(f"- Half-life (bars): {hl.get('half_life_bars', 0.0):.1f}")
    md_lines.append(f"- Hurst (rough): {hurst.get('hurst', 0.0):.3f}")
    md_lines.append(f"- Drift per day (log): {drift_per_day:.6f}")
    md_lines.append(f"- Vol per day (log): {vol_per_day:.6f}")
    md_lines.append("")
    md_lines.append("## Variance Ratio (VR)")
    for q in cfg.vr_lags:
        md_lines.append(f"- VR({q}): {vr.get(f'vr_{q}', 0.0):.3f}")
    md_lines.append("")
    md_lines.append("## Time In Band")
    md_lines.append(f"- In [support,resistance] ratio: {tib.get('in_band_ratio', 0.0):.3f}")
    md_lines.append(f"- Mid zone ratio (45%-55%): {tib.get('mid_zone_ratio_45_55', 0.0):.3f}")
    md_lines.append("")
    md_lines.append("## Z-score Reversion")
    for k, v in reversion.items():
        md_lines.append(f"- {k}: events={v['events']:.0f}, success={v['success_rate']:.3f}, median_h={v['median_time_to_revert_hours']:.1f}, p90_h={v['p90_time_to_revert_hours']:.1f}")
    md_lines.append("")

    (out_dir / "structure_diagnostics.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print("Structure diagnostics generated:")
    print(f"  - {out_dir / 'structure_diagnostics.json'}")
    print(f"  - {out_dir / 'structure_diagnostics.md'}")


if __name__ == "__main__":
    main()



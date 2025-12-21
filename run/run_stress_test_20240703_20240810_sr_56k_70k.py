"""
压力测试：2024-07-03 ~ 2024-08-10（UTC，含尾端），S=56k, R=70k

- 使用 OKX 合约（okx_swap）本地 1m 缓存，不再 call 交易所
- 同一份 bars 复用，控制变量跑 4 个策略：
  - NEUTRAL_RANGE
  - BULLISH_RANGE
  - BEARISH_RANGE（默认 short overlay）
  - BEARISH_RANGE long-only（对照）
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from data import DataManager
from algorithms.taogrid.config import TaoGridLeanConfig
from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner


SUPPORT = 56_000.0
RESISTANCE = 70_000.0
START = datetime(2024, 7, 3, tzinfo=timezone.utc)
END_INCL = datetime(2024, 8, 10, tzinfo=timezone.utc)
END_EXCL = END_INCL + timedelta(days=1)  # include 08-10 full day


def _run(cfg: TaoGridLeanConfig, data, out: Path, title: str) -> dict:
    print("=" * 80)
    print(title)
    print("=" * 80)
    runner = SimpleLeanRunner(
        config=cfg,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=START,
        end_date=END_EXCL,
        data=data,
        verbose=True,
        progress_every=5000,
        output_dir=out,
    )
    res = runner.run()
    runner.print_summary(res)
    runner.save_results(res, out)
    return res


def _row(name: str, m: dict) -> str:
    return (
        f"{name:26s}  "
        f"ret={m['total_return']:+7.2%}  "
        f"maxDD={m['max_drawdown']:+7.2%}  "
        f"sharpe={m['sharpe_ratio']:6.2f}  "
        f"calmar={m.get('calmar_ratio', 0.0):6.2f}  "
        f"ulcer={m.get('ulcer_index', 0.0):6.2f}  "
        f"trades={int(m.get('total_trades', 0)):5d}"
    )


def main() -> None:
    dm = DataManager()
    print("=" * 80)
    print("Loading bars once for stress test (okx_swap cache)")
    print("=" * 80)
    data = dm.get_klines(
        symbol="BTCUSDT",
        timeframe="1m",
        start=START,
        end=END_EXCL,
        source="okx_swap",
        use_cache=True,
    )
    print(f"  Loaded {len(data)} bars from {data.index[0]} to {data.index[-1]}")
    print()

    base = TaoGridLeanConfig(
        name="Stress test (20240703-20240810, 56k-70k)",
        description="4 strategies stress window",
        support=SUPPORT,
        resistance=RESISTANCE,
        regime="NEUTRAL_RANGE",
        grid_layers_buy=40,
        grid_layers_sell=40,
        weight_k=0.0,
        spacing_multiplier=1.0,
        min_return=0.0012,
        maker_fee=0.0002,
        volatility_k=0.2,
        inventory_skew_k=0.5,
        inventory_capacity_threshold_pct=1.0,
        leverage=5.0,
        risk_budget_pct=1.0,
        enable_throttling=True,
        initial_cash=100000.0,
        # 风控：全开
        enable_mr_trend_factor=True,
        enable_breakout_risk_factor=True,
        enable_range_pos_asymmetry_v2=True,
        enable_funding_factor=True,
        enable_vol_regime_factor=True,
        enable_mm_risk_zone=True,
        max_risk_inventory_pct=0.80,
        max_risk_loss_pct=0.30,
        # P0：保持开启
        inventory_use_equity_floor=True,
        enable_regime_inventory_scaling=True,
        inventory_regime_gamma=1.2,
        enable_cost_basis_risk_zone=True,
        cost_risk_trigger_pct=0.03,
        cost_risk_buy_mult=0.0,
        enable_console_log=False,
    )

    cfg_neutral = replace(base, regime="NEUTRAL_RANGE", enable_short_in_bearish=False)
    cfg_bullish = replace(base, regime="BULLISH_RANGE", enable_short_in_bearish=False)
    cfg_bearish = replace(base, regime="BEARISH_RANGE", enable_short_in_bearish=True)  # default bearish
    cfg_bearish_longonly = replace(base, regime="BEARISH_RANGE", enable_short_in_bearish=False)

    tag = "20240703_20240810_sr_56k_70k"
    r_neu = _run(cfg_neutral, data, Path(f"run/results_neutral_{tag}"), "NEUTRAL_RANGE")
    r_bul = _run(cfg_bullish, data, Path(f"run/results_bullish_{tag}"), "BULLISH_RANGE")
    r_bear = _run(cfg_bearish, data, Path(f"run/results_bearish_short_{tag}"), "BEARISH_RANGE (with short overlay)")
    r_bear_lo = _run(cfg_bearish_longonly, data, Path(f"run/results_bearish_longonly_{tag}"), "BEARISH_RANGE (long-only)")

    m_neu = r_neu["metrics"]
    m_bul = r_bul["metrics"]
    m_bear = r_bear["metrics"]
    m_bear_lo = r_bear_lo["metrics"]

    print()
    print("=" * 80)
    print("压力测试汇总（同样本 bars）")
    print("=" * 80)
    print(_row("NEUTRAL_RANGE", m_neu))
    print(_row("BULLISH_RANGE", m_bul))
    print(_row("BEARISH_RANGE(short)", m_bear))
    print("-" * 80)
    print(_row("BEARISH_LONGONLY", m_bear_lo))
    print("=" * 80)


if __name__ == "__main__":
    main()


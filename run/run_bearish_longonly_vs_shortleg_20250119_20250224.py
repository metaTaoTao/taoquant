"""
对比实验：BEARISH regime 下
- long-only（默认：SELL 仅减多，不开空）
- 开启 short leg（仅 BEARISH 允许：SELL 开空，BUY 回补）

窗口：2025-01-19 ~ 2025-02-24
S/R：90k / 108k
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.config import TaoGridLeanConfig
from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner
from data import DataManager


def _run(cfg: TaoGridLeanConfig, data, out: Path, title: str) -> dict:
    print("=" * 80)
    print(title)
    print("=" * 80)
    runner = SimpleLeanRunner(
        config=cfg,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 1, 19, tzinfo=timezone.utc),
        end_date=datetime(2025, 2, 24, tzinfo=timezone.utc),
        data=data,  # IMPORTANT: reuse identical bars for A/B fairness
        verbose=True,
        progress_every=5000,
        output_dir=out,
    )
    res = runner.run()
    runner.print_summary(res)
    runner.save_results(res, out)
    return res


def main() -> None:
    # Load data ONCE to ensure A/B uses the exact same bars.
    dm = DataManager()
    start = datetime(2025, 1, 19, tzinfo=timezone.utc)
    end = datetime(2025, 2, 24, tzinfo=timezone.utc)
    print("=" * 80)
    print("Loading bars once for A/B comparison")
    print("=" * 80)
    data = dm.get_klines(
        symbol="BTCUSDT",
        timeframe="1m",
        start=start,
        end=end,
        source="okx_swap",
    )
    print(f"  Loaded {len(data)} bars from {data.index[0]} to {data.index[-1]}")
    print()

    base = TaoGridLeanConfig(
        name="BEARISH compare long-only vs short-leg",
        description="BEARISH comparison",
        support=90000.0,
        resistance=108000.0,
        regime="BEARISH_RANGE",
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

    long_only = replace(base, enable_short_in_bearish=False)
    short_leg = replace(base, enable_short_in_bearish=True)

    r1 = _run(long_only, data, Path("run/results_bearish_longonly_20250119_20250224"), "BEARISH long-only (no short leg)")
    r2 = _run(short_leg, data, Path("run/results_bearish_shortleg_20250119_20250224"), "BEARISH with short leg enabled")

    m1 = r1["metrics"]
    m2 = r2["metrics"]
    print()
    print("=" * 80)
    print("对比汇总（BEARISH）")
    print("=" * 80)
    print(f"LONG-ONLY: total_return={m1['total_return']:.2%} max_dd={m1['max_drawdown']:.2%} sharpe={m1['sharpe_ratio']:.2f} trades={m1['total_trades']}")
    print(f"SHORT-LEG: total_return={m2['total_return']:.2%} max_dd={m2['max_drawdown']:.2%} sharpe={m2['sharpe_ratio']:.2f} trades={m2['total_trades']}")
    print("=" * 80)


if __name__ == "__main__":
    main()


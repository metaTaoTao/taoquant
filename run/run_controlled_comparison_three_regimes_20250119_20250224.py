"""
控制变量对比回测：三种 regime（BULLISH / NEUTRAL / BEARISH）

时间段：2025-01-19 ~ 2025-02-24
S/R：S=90,000  R=108,000

目的：
在完全相同参数下，仅比较 regime 分配（70/30、50/50、30/70）对收益与回撤的影响。
用户预期：BEARISH_RANGE 在该窗口表现最好（震荡看空）。
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


def _run_one(*, config: TaoGridLeanConfig, output_dir: Path, title: str) -> dict:
    print("=" * 80)
    print(title)
    print("=" * 80)
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 1, 19, tzinfo=timezone.utc),
        end_date=datetime(2025, 2, 24, tzinfo=timezone.utc),
        verbose=True,
        progress_every=5000,
        output_dir=output_dir,
    )
    results = runner.run()
    runner.print_summary(results)
    runner.save_results(results, output_dir)
    return results


def _fmt_pct(x: float) -> str:
    return f"{x:.2%}"


def _fmt_num(x: float) -> str:
    return f"{x:.2f}"


def main() -> None:
    # Base config (controlled variables)
    base = TaoGridLeanConfig(
        name="TaoGrid Controlled Comparison (3 Regimes)",
        description="Controlled comparison across BULLISH/NEUTRAL/BEARISH regimes",
        support=90000.0,
        resistance=108000.0,
        grid_layers_buy=40,
        grid_layers_sell=40,
        weight_k=0.0,
        spacing_multiplier=1.0,
        min_return=0.0012,
        maker_fee=0.0002,
        volatility_k=0.2,
        inventory_skew_k=0.5,
        inventory_capacity_threshold_pct=1.0,
        # 风控：全开
        enable_mr_trend_factor=True,
        enable_breakout_risk_factor=True,
        enable_range_pos_asymmetry_v2=True,
        enable_funding_factor=True,
        enable_vol_regime_factor=True,
        enable_mm_risk_zone=True,
        max_risk_inventory_pct=0.80,
        max_risk_loss_pct=0.30,
        leverage=5.0,
        risk_budget_pct=1.0,
        enable_throttling=True,
        initial_cash=100000.0,
        # P0 风控：保持开启
        inventory_use_equity_floor=True,
        enable_regime_inventory_scaling=True,
        inventory_regime_gamma=1.2,
        enable_cost_basis_risk_zone=True,
        cost_risk_trigger_pct=0.03,
        cost_risk_buy_mult=0.0,
        enable_forced_deleverage=False,
        enable_console_log=False,
    )

    configs = [
        ("BULLISH_RANGE", Path("run/results_bullish_controlled_20250119_20250224"), "CONTROL: BULLISH_RANGE (70/30)"),
        ("NEUTRAL_RANGE", Path("run/results_neutral_controlled_20250119_20250224"), "CONTROL: NEUTRAL_RANGE (50/50)"),
        ("BEARISH_RANGE", Path("run/results_bearish_controlled_20250119_20250224"), "CONTROL: BEARISH_RANGE (30/70)"),
    ]

    results_by_regime: dict[str, dict] = {}
    for regime, outdir, title in configs:
        cfg = replace(base, regime=regime, name=f"{base.name} - {regime}")
        results_by_regime[regime] = _run_one(config=cfg, output_dir=outdir, title=title)

    # Summary table
    print()
    print("=" * 80)
    print("三种 Regime 对比汇总（2025-01-19 ~ 2025-02-24）")
    print("=" * 80)
    header = (
        "REGIME".ljust(14)
        + "TOTAL_RET".rjust(10)
        + "MAX_DD".rjust(10)
        + "SHARPE".rjust(10)
        + "SORTINO".rjust(10)
        + "CALMAR".rjust(10)
        + "ULCER".rjust(10)
        + "TRADES".rjust(10)
    )
    print(header)
    print("-" * len(header))
    for regime, _, _ in configs:
        m = results_by_regime[regime]["metrics"]
        line = (
            regime.ljust(14)
            + _fmt_pct(float(m.get("total_return", 0.0))).rjust(10)
            + _fmt_pct(float(m.get("max_drawdown", 0.0))).rjust(10)
            + _fmt_num(float(m.get("sharpe_ratio", 0.0))).rjust(10)
            + _fmt_num(float(m.get("sortino_ratio", 0.0))).rjust(10)
            + _fmt_num(float(m.get("calmar_ratio", 0.0))).rjust(10)
            + _fmt_num(float(m.get("ulcer_index", 0.0))).rjust(10)
            + str(int(m.get("total_trades", 0))).rjust(10)
        )
        print(line)
    print("=" * 80)


if __name__ == "__main__":
    main()


"""
控制变量对比回测（应用 P0 风控修复）

对比：
- NEUTRAL_RANGE (50/50)
- BULLISH_RANGE (70/30)

控制变量：
- 同一时间段、同一 S/R、同一网格参数、同一风控开关
- 唯一变量：regime（预算分配）

目标：
验证 P0 修复是否显著降低 BULLISH 回撤，同时保留更高收益的优势。
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


def _run_one(
    *,
    config: TaoGridLeanConfig,
    output_dir: Path,
    title: str,
) -> dict:
    print("=" * 80)
    print(title)
    print("=" * 80)
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2024, 12, 30, tzinfo=timezone.utc),
        end_date=datetime(2025, 1, 20, tzinfo=timezone.utc),
        verbose=True,
        progress_every=5000,
        output_dir=output_dir,
    )
    results = runner.run()
    runner.print_summary(results)
    runner.save_results(results, output_dir)
    return results


def main() -> None:
    base = TaoGridLeanConfig(
        name="TaoGrid Controlled Comparison (P0 Fix)",
        description="Controlled comparison: NEUTRAL vs BULLISH with P0 risk fixes enabled",
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
        # 风控：全开（与对比文档一致）
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
        # P0 fixes: keep defaults but explicit for clarity
        inventory_use_equity_floor=True,
        enable_regime_inventory_scaling=True,
        inventory_regime_gamma=1.2,
        enable_cost_basis_risk_zone=True,
        cost_risk_trigger_pct=0.03,
        cost_risk_buy_mult=0.0,
        # NOTE: Forced deleverage (market sell) is intentionally disabled here.
        # We prefer preventing inventory accumulation via regime-scaled caps (P0) rather than
        # realizing losses (P1), unless explicitly desired.
        enable_forced_deleverage=False,
        enable_console_log=False,
    )

    neutral = replace(base, regime="NEUTRAL_RANGE", name=base.name + " - NEUTRAL")
    bullish = replace(base, regime="BULLISH_RANGE", name=base.name + " - BULLISH")

    neutral_out = Path("run/results_neutral_controlled_p0fix")
    bullish_out = Path("run/results_bullish_controlled_p0fix")

    neutral_results = _run_one(
        config=neutral,
        output_dir=neutral_out,
        title="CONTROL TEST (P0 FIX): NEUTRAL_RANGE (50/50)",
    )
    bullish_results = _run_one(
        config=bullish,
        output_dir=bullish_out,
        title="CONTROL TEST (P0 FIX): BULLISH_RANGE (70/30)",
    )

    # Side-by-side summary
    n = neutral_results["metrics"]
    b = bullish_results["metrics"]
    print()
    print("=" * 80)
    print("对比汇总（P0 FIX）")
    print("=" * 80)
    print(f"NEUTRAL  total_return={n['total_return']:.2%}  max_dd={n['max_drawdown']:.2%}  sharpe={n['sharpe_ratio']:.2f}  trades={n['total_trades']}")
    print(f"BULLISH  total_return={b['total_return']:.2%}  max_dd={b['max_drawdown']:.2%}  sharpe={b['sharpe_ratio']:.2f}  trades={b['total_trades']}")
    print("=" * 80)


if __name__ == "__main__":
    main()


"""
Ablation: compare Sharpe with/without funding factor on a specified window.

User request:
  - window: 2025-09-09 ~ 2025-10-09 (UTC) (funding available on OKX public API)
  - S=107k, R=123k
  - keep other factors unchanged (breakout winner + range_pos v2 winner, MR+Trend off)
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.config import TaoGridLeanConfig  # noqa: E402
from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner  # noqa: E402


def _run(cfg: TaoGridLeanConfig, out_dir: Path) -> dict:
    runner = SimpleLeanRunner(
        config=cfg,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 9, tzinfo=timezone.utc),
        end_date=datetime(2025, 10, 9, tzinfo=timezone.utc),
        output_dir=out_dir,
        verbose=False,
        progress_every=10000,
    )
    results = runner.run()
    runner.save_results(results, out_dir)
    return results["metrics"]


def main() -> None:
    out_root = Path("run/results_lean_taogrid_funding_ablation_2025-09-09_to_2025-10-09")
    out_root.mkdir(parents=True, exist_ok=True)

    base = TaoGridLeanConfig(
        name="TaoGrid Funding Ablation 2025-09-09_to_2025-10-09",
        description="Funding factor ON/OFF ablation (2025-09-09~2025-10-09)",
        support=107000.0,
        resistance=123000.0,
        regime="NEUTRAL_RANGE",
        grid_layers_buy=40,
        grid_layers_sell=40,
        weight_k=0.0,
        spacing_multiplier=1.0,
        min_return=0.0012,
        maker_fee=0.0002,
        inventory_skew_k=0.5,
        inventory_capacity_threshold_pct=1.0,
        risk_budget_pct=1.0,
        enable_throttling=True,
        initial_cash=100000.0,
        leverage=50.0,
        sharpe_annualization_days=365,
        enable_mr_trend_factor=False,
        # Breakout factor ON (winner params)
        enable_breakout_risk_factor=True,
        breakout_band_atr_mult=1.0,
        breakout_band_pct=0.008,
        breakout_trend_weight=0.7,
        breakout_buy_k=2.0,
        breakout_buy_floor=0.5,
        breakout_block_threshold=0.9,
        # RangePos v2 ON (winner params)
        enable_range_pos_asymmetry_v2=True,
        range_top_band_start=0.45,
        range_buy_k=0.2,
        range_buy_floor=0.2,
        range_sell_k=1.5,
        range_sell_cap=1.5,
        # Funding factor defaults ON; will toggle below
        enable_funding_factor=True,
        funding_apply_to_buy=False,
        funding_apply_to_sell=True,
        enable_funding_time_gate=True,
        # Keep the best Sharpe gate from sweep
        funding_gate_minutes=90,
        # Vol regime defaults ON; will toggle in ablation script for clean comparison
        enable_vol_regime_factor=True,
    )

    cfg_off = replace(base, enable_funding_factor=False, name="Funding OFF")
    cfg_on = replace(base, enable_funding_factor=True, name="Funding ON")

    m_off = _run(cfg_off, out_root / "off")
    m_on = _run(cfg_on, out_root / "on")

    rows = [
        {"variant": "off", **m_off},
        {"variant": "on", **m_on},
    ]
    df = pd.DataFrame(rows)[
        [
            "variant",
            "sharpe_ratio",
            "sortino_ratio",
            "max_drawdown",
            "total_return",
            "total_trades",
            "avg_holding_period_hours",
            "sharpe_annualization_days",
        ]
    ]
    df.to_csv(out_root / "summary.csv", index=False)
    print(df.to_string(index=False))
    print(f"Saved: {out_root / 'summary.csv'}")


if __name__ == "__main__":
    main()



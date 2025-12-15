"""
Ablation: compare Sharpe with/without MR+Trend factor.

Runs two backtests with identical settings except:
  - enable_mr_trend_factor: False vs True

Outputs:
  run/results_lean_taogrid_factor_ablation/off/
  run/results_lean_taogrid_factor_ablation/on/
  run/results_lean_taogrid_factor_ablation/summary.csv
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
        start_date=datetime(2025, 7, 10, tzinfo=timezone.utc),
        end_date=datetime(2025, 8, 10, tzinfo=timezone.utc),
        output_dir=out_dir,
        verbose=False,
        progress_every=5000,
    )
    results = runner.run()
    runner.save_results(results, out_dir)
    return results["metrics"]


def main() -> None:
    out_root = Path("run/results_lean_taogrid_factor_ablation")
    out_root.mkdir(parents=True, exist_ok=True)

    base = TaoGridLeanConfig(
        name="TaoGrid Factor Ablation",
        description="Compare Sharpe with/without MR+Trend factor",
        support=111000.0,
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
    )

    cfg_off = replace(base, enable_mr_trend_factor=False, name="Ablation OFF")
    cfg_on = replace(base, enable_mr_trend_factor=True, name="Ablation ON")

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



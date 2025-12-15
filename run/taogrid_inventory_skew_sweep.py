"""
Sweep inventory_skew_k for TaoGrid (market-making style).

We keep:
  - leverage = 5x
  - risk_budget_pct = 1.0
  - inventory_capacity_threshold_pct = 1.0
  - fixed S/R
  - maker fee = 0.02% per side, slippage = 0

We sweep:
  - inventory_skew_k in [0.0, 0.5, 1.0, 1.5, 2.0]

Outputs:
  run/results_lean_taogrid_inventory_skew_sweep/summary.csv
  run/results_lean_taogrid_inventory_skew_sweep/k_*/ (metrics/trades/orders/equity + metrics_panel.*)
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


def main() -> None:
    ks = [0.0, 0.5, 1.0, 1.5, 2.0]

    support = 111_000.0
    resistance = 123_000.0
    start = datetime(2025, 7, 10, tzinfo=timezone.utc)
    end = datetime(2025, 8, 10, tzinfo=timezone.utc)

    out_root = Path("run/results_lean_taogrid_inventory_skew_sweep")
    out_root.mkdir(parents=True, exist_ok=True)

    base = TaoGridLeanConfig(
        name="TaoGrid Inventory Skew Sweep",
        description="Sweep inventory_skew_k under 5x leverage for max ROE",
        support=support,
        resistance=resistance,
        regime="NEUTRAL_RANGE",
        grid_layers_buy=40,
        grid_layers_sell=40,
        weight_k=0.0,
        spacing_multiplier=1.0,
        min_return=0.0012,
        maker_fee=0.0002,
        risk_budget_pct=1.0,
        enable_throttling=True,
        leverage=5.0,
        inventory_capacity_threshold_pct=1.0,
        inventory_skew_k=1.0,
    )

    rows: list[dict] = []
    for k in ks:
        cfg = replace(base, inventory_skew_k=float(k))
        run_dir = out_root / f"k_{k:.1f}"

        runner = SimpleLeanRunner(
            config=cfg,
            symbol="BTCUSDT",
            timeframe="1m",
            start_date=start,
            end_date=end,
            output_dir=run_dir,
            verbose=False,
            progress_every=5000,
        )
        results = runner.run()
        runner.save_results(results, run_dir)

        # Generate metrics panel files for this run
        import subprocess

        subprocess.run(
            [sys.executable, "run/taogrid_metrics_panel.py", "--input", str(run_dir)],
            cwd=project_root,
            check=False,
        )

        metrics = results["metrics"]
        rows.append(
            {
                "inventory_skew_k": k,
                "total_return": float(metrics.get("total_return", 0.0)),
                "total_pnl": float(metrics.get("total_pnl", 0.0)),
                "max_drawdown": float(metrics.get("max_drawdown", 0.0)),
                "sharpe_ratio": float(metrics.get("sharpe_ratio", 0.0)),
                "sortino_ratio": float(metrics.get("sortino_ratio", 0.0)),
                "total_trades": float(metrics.get("total_trades", 0.0)),
                "avg_holding_period_hours": float(metrics.get("avg_holding_period_hours", 0.0)),
                "output_dir": str(run_dir),
            }
        )

    df = pd.DataFrame(rows).sort_values(by=["sharpe_ratio"], ascending=False)
    df.to_csv(out_root / "summary.csv", index=False)

    print("Inventory skew sweep done. Top rows:")
    print(df.head(10).to_string(index=False))
    print(f"Saved: {out_root / 'summary.csv'}")


if __name__ == "__main__":
    main()



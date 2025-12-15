"""
Sweep funding_gate_minutes (time gate around funding settlement) to optimize Sharpe.

Window (user real-data preference):
  2025-09-09 ~ 2025-10-09 (UTC) where OKX funding history is available.

Fixed strategy settings:
  - S=107k, R=123k
  - 50x leverage
  - breakout winner + range_pos v2 winner
  - MR+Trend OFF
  - funding factor ON, SELL-only, time-gated
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
        progress_every=15000,
    )
    results = runner.run()
    runner.save_results(results, out_dir)
    return results["metrics"]


def main() -> None:
    gate_minutes_choices = [15, 30, 45, 60, 90, 120, 180]

    out_root = Path("run/results_lean_taogrid_funding_gate_sweep_2025-09-09_to_2025-10-09")
    out_root.mkdir(parents=True, exist_ok=True)

    base = TaoGridLeanConfig(
        name="TaoGrid Funding Gate Sweep",
        description="Sweep funding_gate_minutes for Sharpe (real funding window)",
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
        # Funding factor: SELL-only, time gated
        enable_funding_factor=True,
        funding_apply_to_buy=False,
        funding_apply_to_sell=True,
        enable_funding_time_gate=True,
        funding_gate_minutes=60,
    )

    rows: list[dict] = []
    for gm in gate_minutes_choices:
        cfg = replace(base, funding_gate_minutes=int(gm), name=f"FundingGate {gm}m")
        out_dir = out_root / f"gate_{gm:03d}"
        metrics = _run(cfg, out_dir)
        rows.append(
            {
                "funding_gate_minutes": gm,
                "sharpe_ratio": float(metrics.get("sharpe_ratio", 0.0)),
                "sortino_ratio": float(metrics.get("sortino_ratio", 0.0)),
                "max_drawdown": float(metrics.get("max_drawdown", 0.0)),
                "total_return": float(metrics.get("total_return", 0.0)),
                "total_trades": float(metrics.get("total_trades", 0.0)),
                "avg_holding_period_hours": float(metrics.get("avg_holding_period_hours", 0.0)),
                "output_dir": str(out_dir),
            }
        )

    df = pd.DataFrame(rows).sort_values(by=["sharpe_ratio", "total_return"], ascending=False)
    df.to_csv(out_root / "summary.csv", index=False)

    # Also provide a filtered view for MaxDD<=20% if needed
    df_ok = df[df["max_drawdown"] >= -0.20].copy()
    if not df_ok.empty:
        df_ok.to_csv(out_root / "summary_maxdd_le_20pct.csv", index=False)

    print("Top results (all):")
    print(df.head(10).to_string(index=False))
    if not df_ok.empty:
        print()
        print("Top results (MaxDD<=20%):")
        print(df_ok.head(10).to_string(index=False))
    print(f"Saved: {out_root / 'summary.csv'}")


if __name__ == "__main__":
    main()



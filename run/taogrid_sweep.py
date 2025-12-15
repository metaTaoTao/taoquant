"""
TaoGrid 参数扫描（用于在固定区间内提高 ROE/Turnover 的折中）。

用法：
  python run/taogrid_sweep.py

输出：
  run/results_lean_taogrid_sweep/sweep_summary.csv
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.config import TaoGridLeanConfig
from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner


def _compute_derived_metrics(metrics: dict, days: float) -> dict:
    total_return = float(metrics.get("total_return", 0.0))
    max_drawdown = float(metrics.get("max_drawdown", 0.0))
    total_trades = float(metrics.get("total_trades", 0.0))
    avg_holding = float(metrics.get("avg_holding_period_hours", 0.0))

    trades_per_day = total_trades / days if days > 0 else 0.0
    # 简单年化（不追求严谨，只用于排序对比）
    annualized_return = (1.0 + total_return) ** (365.0 / days) - 1.0 if days > 0 else 0.0
    dd_abs = abs(max_drawdown) if max_drawdown != 0 else 0.0
    calmar_like = annualized_return / dd_abs if dd_abs > 0 else 0.0

    return {
        "trades_per_day": trades_per_day,
        "annualized_return": annualized_return,
        "calmar_like": calmar_like,
        "avg_holding_period_hours": avg_holding,
    }


def main() -> None:
    # 固定回测区间（你当前讨论的区间）
    support = 111_000.0
    resistance = 123_000.0

    # 固定回测时间（和现有缓存一致，避免重复下载）
    start = datetime(2025, 7, 10, tzinfo=timezone.utc)
    end = datetime(2025, 8, 10, tzinfo=timezone.utc)
    days = (end - start).total_seconds() / 86400.0

    base_config = TaoGridLeanConfig(
        name="TaoGrid Sweep",
        description="Parameter sweep for ROE/Turnover tradeoff",
        support=support,
        resistance=resistance,
        regime="NEUTRAL_RANGE",
        weight_k=0.5,
        spacing_multiplier=1.0,
        maker_fee=0.0002,
        volatility_k=0.6,
        cushion_multiplier=0.8,
        risk_budget_pct=0.6,
        enable_throttling=False,
        initial_cash=100000.0,
        leverage=1.0,
        grid_layers_buy=10,
        grid_layers_sell=10,
        min_return=0.001,
    )

    # 扫描空间（基于 perp maker fee=0.02%，可把 min_return 下探得更低）
    # 注意：min_return 是“净收益目标”，spacing 下界会保证 >= min_return + 2*fee (+2*slippage)
    min_returns = [0.0003, 0.0005, 0.0008, 0.0012]  # 0.03%, 0.05%, 0.08%, 0.12% (net)
    grid_layers = [20, 30, 40]
    risk_budgets = [0.3, 0.6]
    spacing_multipliers = [1.0]

    out_root = Path("run/results_lean_taogrid_sweep")
    out_root.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []

    run_id = 0
    for mr in min_returns:
        for gl in grid_layers:
            for rb in risk_budgets:
                for sm in spacing_multipliers:
                    run_id += 1
                    cfg = replace(
                        base_config,
                        min_return=mr,
                        grid_layers_buy=gl,
                        grid_layers_sell=gl,
                        risk_budget_pct=rb,
                        spacing_multiplier=sm,
                    )

                    run_dir = out_root / f"mr_{mr:.4f}_gl_{gl}_rb_{rb:.1f}_sm_{sm:.2f}"

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

                    metrics = results["metrics"]
                    derived = _compute_derived_metrics(metrics, days=days)

                    rows.append(
                        {
                            "run_id": run_id,
                            "support": support,
                            "resistance": resistance,
                            "min_return": mr,
                            "grid_layers": gl,
                            "risk_budget_pct": rb,
                            "spacing_multiplier": sm,
                            "total_return": float(metrics.get("total_return", 0.0)),
                            "total_pnl": float(metrics.get("total_pnl", 0.0)),
                            "max_drawdown": float(metrics.get("max_drawdown", 0.0)),
                            "total_trades": float(metrics.get("total_trades", 0.0)),
                            "win_rate": float(metrics.get("win_rate", 0.0)),
                            **derived,
                            "output_dir": str(run_dir),
                        }
                    )

    df = pd.DataFrame(rows)

    # 排序：优先 turnover + 风险调整收益（你要 ROE + 频率）
    df_sorted = df.sort_values(
        by=["calmar_like", "trades_per_day", "total_return"],
        ascending=[False, False, False],
    )

    summary_path = out_root / "sweep_summary.csv"
    df_sorted.to_csv(summary_path, index=False)

    # 控制台输出 Top 5（避免中文编码问题，这里用英文）
    top = df_sorted.head(5)[
        [
            "min_return",
            "grid_layers",
            "risk_budget_pct",
            "spacing_multiplier",
            "total_return",
            "max_drawdown",
            "total_trades",
            "trades_per_day",
            "avg_holding_period_hours",
            "calmar_like",
            "output_dir",
        ]
    ]
    print("Top 5 configs (sorted by calmar_like, trades_per_day, total_return):")
    print(top.to_string(index=False))
    print(f"\nSaved sweep summary to: {summary_path}")


if __name__ == "__main__":
    main()



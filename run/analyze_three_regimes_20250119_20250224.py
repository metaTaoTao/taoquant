"""
归因分析：三种 regime 的持仓/交易分布差异

输入目录：
- run/results_bullish_controlled_20250119_20250224
- run/results_neutral_controlled_20250119_20250224
- run/results_bearish_controlled_20250119_20250224
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def _analyze_one(regime: str, p: Path) -> dict:
    eq = pd.read_csv(p / "equity_curve.csv")
    eq["timestamp"] = pd.to_datetime(eq["timestamp"], utc=True)

    out: dict[str, float | int | str] = {"regime": regime, "bars": int(len(eq))}
    out["start"] = str(eq["timestamp"].iloc[0])
    out["end"] = str(eq["timestamp"].iloc[-1])
    out["equity_min"] = float(eq["equity"].min())
    out["equity_max"] = float(eq["equity"].max())
    out["equity_end"] = float(eq["equity"].iloc[-1])

    if "holdings" in eq.columns and "holdings_value" in eq.columns:
        h = eq["holdings"].astype(float)
        hv = eq["holdings_value"].astype(float)
        out["holdings_max_btc"] = float(h.max())
        out["holdings_p95_btc"] = float(h.quantile(0.95))
        out["holdings_avg_btc"] = float(h.mean())
        out["holdings_time_nonzero_pct"] = float((h.abs() > 1e-9).mean())
        out["holdings_value_max"] = float(hv.max())
        out["holdings_value_p95"] = float(hv.quantile(0.95))
    else:
        out["holdings_max_btc"] = 0.0
        out["holdings_p95_btc"] = 0.0
        out["holdings_avg_btc"] = 0.0
        out["holdings_time_nonzero_pct"] = 0.0
        out["holdings_value_max"] = 0.0
        out["holdings_value_p95"] = 0.0

    trades = pd.read_csv(p / "trades.csv")
    out["trades"] = int(len(trades))
    if len(trades) > 0:
        out["pnl_sum"] = float(trades["pnl"].sum())
        out["pnl_mean"] = float(trades["pnl"].mean())
        out["pnl_p5"] = float(trades["pnl"].quantile(0.05))
        out["pnl_min"] = float(trades["pnl"].min())
        out["return_pct_mean"] = float(trades["return_pct"].mean())
        out["return_pct_p5"] = float(trades["return_pct"].quantile(0.05))
        out["return_pct_min"] = float(trades["return_pct"].min())
        out["holding_hours_mean"] = float(trades["holding_period"].mean())
        out["holding_hours_p95"] = float(trades["holding_period"].quantile(0.95))
    else:
        out["pnl_sum"] = 0.0
        out["pnl_mean"] = 0.0
        out["pnl_p5"] = 0.0
        out["pnl_min"] = 0.0
        out["return_pct_mean"] = 0.0
        out["return_pct_p5"] = 0.0
        out["return_pct_min"] = 0.0
        out["holding_hours_mean"] = 0.0
        out["holding_hours_p95"] = 0.0

    orders = pd.read_csv(p / "orders.csv")
    out["orders_total"] = int(len(orders))
    if "direction" in orders.columns:
        out["orders_buy"] = int((orders["direction"] == "buy").sum())
        out["orders_sell"] = int((orders["direction"] == "sell").sum())
    else:
        out["orders_buy"] = 0
        out["orders_sell"] = 0

    return out


def main() -> None:
    base = Path("d:/Projects/PythonProjects/taoquant/run")
    paths = {
        "BULLISH_RANGE": base / "results_bullish_controlled_20250119_20250224",
        "NEUTRAL_RANGE": base / "results_neutral_controlled_20250119_20250224",
        "BEARISH_RANGE": base / "results_bearish_controlled_20250119_20250224",
    }

    rows = [_analyze_one(r, p) for r, p in paths.items()]
    df = pd.DataFrame(rows).set_index("regime")

    cols = [
        "start",
        "end",
        "bars",
        "equity_min",
        "equity_end",
        "holdings_max_btc",
        "holdings_p95_btc",
        "holdings_avg_btc",
        "holdings_time_nonzero_pct",
        "holdings_value_max",
        "trades",
        "orders_total",
        "orders_buy",
        "orders_sell",
        "pnl_sum",
        "pnl_min",
        "return_pct_mean",
        "return_pct_min",
        "holding_hours_mean",
        "holding_hours_p95",
    ]
    print(df[cols].to_string())


if __name__ == "__main__":
    main()


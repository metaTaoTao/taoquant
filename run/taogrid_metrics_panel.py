"""
TaoGrid 机构式指标面板（从回测结果目录生成 JSON + Markdown）。

用法：
  python run/taogrid_metrics_panel.py
  python run/taogrid_metrics_panel.py --input run/results_lean_taogrid

输出：
  <input>/metrics_panel.json
  <input>/metrics_panel.md

说明：
  - 仅做分析，不修改回测结果
  - 为避免 Windows 控制台编码问题，脚本默认只打印英文/ASCII
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd


def _read_inputs(results_dir: Path) -> Tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    metrics = json.loads((results_dir / "metrics.json").read_text(encoding="utf-8"))
    equity = pd.read_csv(results_dir / "equity_curve.csv")
    orders = pd.read_csv(results_dir / "orders.csv")
    trades = pd.read_csv(results_dir / "trades.csv")

    equity["timestamp"] = pd.to_datetime(equity["timestamp"], utc=True)
    orders["timestamp"] = pd.to_datetime(orders["timestamp"], utc=True)
    if not trades.empty:
        trades["entry_timestamp"] = pd.to_datetime(trades["entry_timestamp"], utc=True)
        trades["exit_timestamp"] = pd.to_datetime(trades["exit_timestamp"], utc=True)

    return metrics, equity, orders, trades


def _inventory_time_metrics(equity: pd.DataFrame) -> Dict[str, float]:
    # Exposure-time using holdings_value (USD) and dt in hours
    eq = equity.sort_values("timestamp").reset_index(drop=True)
    dt_hours = eq["timestamp"].diff().dt.total_seconds().fillna(0.0) / 3600.0

    holdings_value = eq["holdings_value"].astype(float)
    equity_value = eq["equity"].astype(float)

    # Trapezoid integral for exposure-time
    hv_prev = holdings_value.shift(1).fillna(holdings_value.iloc[0])
    exposure_time_usd_hours = float(((hv_prev + holdings_value) / 2.0 * dt_hours).sum())

    # Normalized by equity-time
    ev_prev = equity_value.shift(1).fillna(equity_value.iloc[0])
    equity_time_usd_hours = float(((ev_prev + equity_value) / 2.0 * dt_hours).sum())

    # Peaks
    peak_holdings_value = float(holdings_value.max())
    peak_inventory_ratio = float((holdings_value / equity_value.replace(0, np.nan)).max())

    avg_inventory_ratio = float((holdings_value / equity_value.replace(0, np.nan)).mean())

    return {
        "exposure_time_usd_hours": exposure_time_usd_hours,
        "equity_time_usd_hours": equity_time_usd_hours,
        "peak_holdings_value_usd": peak_holdings_value,
        "peak_inventory_ratio": peak_inventory_ratio if np.isfinite(peak_inventory_ratio) else 0.0,
        "avg_inventory_ratio": avg_inventory_ratio if np.isfinite(avg_inventory_ratio) else 0.0,
    }


def _orders_metrics(orders: pd.DataFrame) -> Dict[str, float]:
    if orders.empty:
        return {
            "buy_orders": 0.0,
            "sell_orders": 0.0,
            "sell_buy_ratio": 0.0,
        }

    buy_orders = float((orders["direction"] == "buy").sum())
    sell_orders = float((orders["direction"] == "sell").sum())
    sell_buy_ratio = float(sell_orders / buy_orders) if buy_orders > 0 else 0.0

    return {
        "buy_orders": buy_orders,
        "sell_orders": sell_orders,
        "sell_buy_ratio": sell_buy_ratio,
    }


def _holding_distribution(trades: pd.DataFrame) -> Dict[str, float]:
    if trades.empty or "holding_period" not in trades.columns:
        return {
            "holding_avg_hours": 0.0,
            "holding_p50_hours": 0.0,
            "holding_p75_hours": 0.0,
            "holding_p90_hours": 0.0,
            "holding_p95_hours": 0.0,
            "holding_max_hours": 0.0,
        }

    hp = trades["holding_period"].astype(float)
    return {
        "holding_avg_hours": float(hp.mean()),
        "holding_p50_hours": float(hp.quantile(0.50)),
        "holding_p75_hours": float(hp.quantile(0.75)),
        "holding_p90_hours": float(hp.quantile(0.90)),
        "holding_p95_hours": float(hp.quantile(0.95)),
        "holding_max_hours": float(hp.max()),
    }


def _turnover_metrics(results_dir: Path, equity: pd.DataFrame, trades: pd.DataFrame) -> Dict[str, float]:
    start = equity["timestamp"].min()
    end = equity["timestamp"].max()
    days = (end - start).total_seconds() / 86400.0 if pd.notna(start) and pd.notna(end) else 0.0

    total_trades = float(len(trades)) if not trades.empty else 0.0
    trades_per_day = float(total_trades / days) if days > 0 else 0.0

    # Volume proxy: sum of traded BTC sizes
    volume_btc = float(trades["size"].astype(float).sum()) if (not trades.empty and "size" in trades.columns) else 0.0
    volume_btc_per_day = float(volume_btc / days) if days > 0 else 0.0

    return {
        "backtest_days": float(days),
        "trades_per_day": trades_per_day,
        "volume_btc": volume_btc,
        "volume_btc_per_day": volume_btc_per_day,
    }


def build_panel(results_dir: Path) -> Dict[str, Any]:
    metrics, equity, orders, trades = _read_inputs(results_dir)

    inv = _inventory_time_metrics(equity)
    ordm = _orders_metrics(orders)
    hold = _holding_distribution(trades)
    turn = _turnover_metrics(results_dir, equity, trades)

    total_pnl = float(metrics.get("total_pnl", 0.0))
    exposure_time = float(inv["exposure_time_usd_hours"])
    pnl_per_exposure_usd_hour = float(total_pnl / exposure_time) if exposure_time > 0 else 0.0
    pnl_per_exposure_usd_day = pnl_per_exposure_usd_hour * 24.0

    panel: Dict[str, Any] = {
        "summary": {
            "total_return": float(metrics.get("total_return", 0.0)),
            "total_pnl": total_pnl,
            "max_drawdown": float(metrics.get("max_drawdown", 0.0)),
            "sharpe_ratio": float(metrics.get("sharpe_ratio", 0.0)),
            "sortino_ratio": float(metrics.get("sortino_ratio", 0.0)),
            "total_trades": float(metrics.get("total_trades", len(trades) if not trades.empty else 0.0)),
            "win_rate": float(metrics.get("win_rate", 0.0)),
            "final_equity": float(metrics.get("final_equity", equity["equity"].iloc[-1] if not equity.empty else 0.0)),
        },
        "turnover": turn,
        "orders": ordm,
        "holding": hold,
        "inventory": inv,
        "efficiency": {
            "pnl_per_exposure_usd_hour": pnl_per_exposure_usd_hour,
            "pnl_per_exposure_usd_day": pnl_per_exposure_usd_day,
        },
        "notes": {
            "sell_buy_ratio_hint": "If << 1, sells are scarce vs buys -> inventory can accumulate and holding time rises.",
            "pnl_per_exposure_hint": "Proxy for capital efficiency: total_pnl divided by integral of holdings_value over time.",
        },
    }
    return panel


def _panel_to_markdown(panel: Dict[str, Any], results_dir: Path) -> str:
    s = panel["summary"]
    t = panel["turnover"]
    o = panel["orders"]
    h = panel["holding"]
    inv = panel["inventory"]
    eff = panel["efficiency"]

    def pct(x: float) -> str:
        return f"{x*100:.2f}%"

    lines = []
    lines.append("# TaoGrid Institutional Metrics Panel")
    lines.append("")
    lines.append(f"Results dir: `{results_dir.as_posix()}`")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- **Total Return**: {pct(float(s['total_return']))}")
    lines.append(f"- **Total PnL**: ${float(s['total_pnl']):,.2f}")
    lines.append(f"- **Max Drawdown**: {pct(float(s['max_drawdown']))}")
    lines.append(f"- **Sharpe (annualized)**: {float(s['sharpe_ratio']):.3f}")
    lines.append(f"- **Sortino (annualized)**: {float(s['sortino_ratio']):.3f}")
    lines.append(f"- **Total Trades**: {int(float(s['total_trades']))}")
    lines.append(f"- **Win Rate**: {pct(float(s['win_rate']))}")
    lines.append("")
    lines.append("## Turnover")
    lines.append(f"- **Backtest Days**: {float(t['backtest_days']):.2f}")
    lines.append(f"- **Trades / Day**: {float(t['trades_per_day']):.3f}")
    lines.append(f"- **Volume (BTC)**: {float(t['volume_btc']):.4f}")
    lines.append(f"- **Volume (BTC) / Day**: {float(t['volume_btc_per_day']):.4f}")
    lines.append("")
    lines.append("## Orders (Balance)")
    lines.append(f"- **Buy Orders**: {int(float(o['buy_orders']))}")
    lines.append(f"- **Sell Orders**: {int(float(o['sell_orders']))}")
    lines.append(f"- **Sell/Buy Ratio**: {float(o['sell_buy_ratio']):.3f}")
    lines.append("")
    lines.append("## Holding (Distribution)")
    lines.append(f"- **Avg Holding**: {float(h['holding_avg_hours']):.1f} hours")
    lines.append(f"- **P50 / P75 / P90 / P95**: {float(h['holding_p50_hours']):.1f} / {float(h['holding_p75_hours']):.1f} / {float(h['holding_p90_hours']):.1f} / {float(h['holding_p95_hours']):.1f} hours")
    lines.append(f"- **Max Holding**: {float(h['holding_max_hours']):.1f} hours")
    lines.append("")
    lines.append("## Inventory (Exposure)")
    lines.append(f"- **Peak Holdings Value**: ${float(inv['peak_holdings_value_usd']):,.2f}")
    lines.append(f"- **Peak Inventory Ratio (holdings_value/equity)**: {float(inv['peak_inventory_ratio']):.3f}")
    lines.append(f"- **Avg Inventory Ratio (holdings_value/equity)**: {float(inv['avg_inventory_ratio']):.3f}")
    lines.append("")
    lines.append("## Efficiency")
    lines.append(f"- **PnL per Exposure USD-Day**: {float(eff['pnl_per_exposure_usd_day']):.6f}")
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, default="run/results_lean_taogrid")
    args = parser.parse_args()

    results_dir = Path(args.input)
    if not results_dir.exists():
        raise FileNotFoundError(f"results dir not found: {results_dir}")

    panel = build_panel(results_dir)

    (results_dir / "metrics_panel.json").write_text(
        json.dumps(panel, indent=2),
        encoding="utf-8",
    )
    (results_dir / "metrics_panel.md").write_text(
        _panel_to_markdown(panel, results_dir),
        encoding="utf-8",
    )

    # Print a short ASCII summary
    print("Metrics panel generated:")
    print(f"  - {results_dir / 'metrics_panel.json'}")
    print(f"  - {results_dir / 'metrics_panel.md'}")


if __name__ == "__main__":
    main()



from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Type

import pandas as pd

from core.config import ProjectConfig, default_config

try:
    from backtesting import Backtest, Strategy  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise ImportError("Backtesting.py package is required. Install via pip install backtesting.") from exc


def run_backtest(
    data: pd.DataFrame,
    strategy_cls: Type[Strategy],
    config: Optional[ProjectConfig] = None,
    output_dir: Path = Path("backtest/results"),
    strategy_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run backtest and export results."""
    cfg = config or default_config
    output_dir.mkdir(parents=True, exist_ok=True)
    strategy_params = strategy_params or {}

    bt = Backtest(
        data,
        strategy_cls,
        cash=cfg.backtest.initial_capital,
        commission=cfg.backtest.commission,
        trade_on_close=False,
        hedging=False,
    )

    stats = bt.run(**strategy_params)

    trades_path = output_dir / "trades.csv"
    equity_path = output_dir / "equity_curve.csv"

    stats["_trades"].to_csv(trades_path, index=False)
    stats["_equity_curve"].to_csv(equity_path, index=False)

    summary = {
        "win_rate": stats.get("Win Rate [%]", 0.0),
        "profit_factor": stats.get("Profit Factor", 0.0),
        "expectancy": stats.get("Expectancy [%]", 0.0),
        "max_drawdown": stats.get("Max Drawdown [%]", 0.0),
        "trades_path": str(trades_path),
        "equity_curve_path": str(equity_path),
    }

    _print_summary(summary)
    return summary


def _print_summary(summary: Dict[str, Any]) -> None:
    """Print concise backtest summary."""
    print("Backtest Summary")
    print("================")
    print(f"Win Rate        : {summary['win_rate']:.2f}%")
    print(f"Profit Factor   : {summary['profit_factor']:.2f}")
    print(f"Expectancy      : {summary['expectancy']:.2f}%")
    print(f"Max Drawdown    : {summary['max_drawdown']:.2f}%")
    print(f"Trades CSV      : {summary['trades_path']}")
    print(f"Equity Curve CSV: {summary['equity_curve_path']}")


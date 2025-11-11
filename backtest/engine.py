from __future__ import annotations

import math
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

    dataset = _prepare_dataset(data)

    bt = Backtest(
        dataset,
        strategy_cls,
        cash=cfg.backtest.initial_capital,
        commission=cfg.backtest.commission,
        trade_on_close=False,
        hedging=False,
    )

    stats = bt.run(**strategy_params)

    trades_path = output_dir / "trades.csv"
    equity_path = output_dir / "equity_curve.csv"
    plot_path = output_dir / "backtest_plot.html"
    guard_path = output_dir / "guard_rails.csv"
    guard_orders_path = output_dir / "guard_orders.csv"

    stats["_trades"].to_csv(trades_path, index=False)
    stats["_equity_curve"].to_csv(equity_path, index=False)
    bt.plot(open_browser=False, filename=str(plot_path))

    strategy_instance = stats.get("_strategy")
    guard_columns = []
    guard_written = False
    orders_written = False
    if strategy_instance is not None and hasattr(strategy_instance, "data"):
        guard_df = strategy_instance.data.df.copy()
        guard_columns = [col for col in ["support_guard", "resistance_guard", "atr_guard"] if col in guard_df.columns]
        if guard_columns:
            guard_export = guard_df[guard_columns].reset_index().rename(columns={"index": "Time"})
            guard_export.to_csv(guard_path, index=False)
            guard_written = True
        if hasattr(strategy_instance, "_order_log"):
            orders_df = pd.DataFrame(strategy_instance._order_log)
            if not orders_df.empty:
                orders_df.to_csv(guard_orders_path, index=False)
                orders_written = True

    summary = {
        "win_rate": _safe_metric(stats, "Win Rate [%]"),
        "profit_factor": _safe_metric(stats, "Profit Factor"),
        "expectancy": _safe_metric(stats, "Expectancy [%]"),
        "max_drawdown": _safe_drawdown(stats),
        "trades_path": str(trades_path),
        "equity_curve_path": str(equity_path),
        "plot_path": str(plot_path),
        "guard_rails_path": str(guard_path) if guard_written else None,
        "guard_orders_path": str(guard_orders_path) if orders_written else None,
    }

    _print_summary(stats, summary)
    return summary


def _print_summary(stats: Dict[str, Any], summary_paths: Dict[str, Any]) -> None:
    """Print extended backtest summary."""
    metrics = [
        ("Start", stats.get("Start")),
        ("End", stats.get("End")),
        ("Duration", stats.get("Duration")),
        ("Exposure Time [%]", _safe_metric(stats, "Exposure Time [%]")),
        ("Equity Final [$]", _safe_metric(stats, "Equity Final [$]")),
        ("Equity Peak [$]", _safe_metric(stats, "Equity Peak [$]")),
        ("Return [%]", _safe_metric(stats, "Return [%]")),
        ("Buy & Hold Return [%]", _safe_metric(stats, "Buy & Hold Return [%]")),
        ("Return (Ann.) [%]", _safe_metric(stats, "Return (Ann.) [%]")),
        ("Volatility (Ann.) [%]", _safe_metric(stats, "Volatility (Ann.) [%]")),
        ("Sharpe Ratio", _safe_metric(stats, "Sharpe Ratio")),
        ("Sortino Ratio", _safe_metric(stats, "Sortino Ratio")),
        ("Calmar Ratio", _safe_metric(stats, "Calmar Ratio")),
        ("Max Drawdown [%]", -_safe_drawdown(stats)),
        ("Avg. Drawdown [%]", _safe_metric(stats, "Avg. Drawdown [%]")),
        ("Max Drawdown Duration", stats.get("Max. Drawdown Duration")),
        ("Avg. Drawdown Duration", stats.get("Avg. Drawdown Duration")),
        ("# Trades", _safe_metric(stats, "# Trades")),
        ("Win Rate [%]", _safe_metric(stats, "Win Rate [%]")),
        ("Best Trade [%]", _safe_metric(stats, "Best Trade [%]")),
        ("Worst Trade [%]", _safe_metric(stats, "Worst Trade [%]")),
        ("Avg. Trade [%]", _safe_metric(stats, "Avg. Trade [%]")),
        ("Max Trade Duration", stats.get("Max. Trade Duration")),
        ("Avg. Trade Duration", stats.get("Avg. Trade Duration")),
        ("Profit Factor", _safe_metric(stats, "Profit Factor")),
        ("Expectancy [%]", _safe_metric(stats, "Expectancy [%]")),
        ("SQN", _safe_metric(stats, "SQN")),
    ]

    print("Backtest Summary")
    print("================")
    for label, value in metrics:
        if isinstance(value, (pd.Timestamp, pd.Timedelta)):
            print(f"{label:<24}: {value}")
        elif isinstance(value, (int, float)):
            print(f"{label:<24}: {value:.6g}")
        elif value is None:
            print(f"{label:<24}: -")
        else:
            print(f"{label:<24}: {value}")

    print("----------------")
    print(f"Trades CSV      : {summary_paths['trades_path']}")
    print(f"Equity Curve CSV: {summary_paths['equity_curve_path']}")
    print(f"Plot HTML       : {summary_paths['plot_path']}")


def _safe_metric(stats: Dict[str, Any], key: str) -> float:
    """Return stat value or zero if missing/NaN."""
    value = stats.get(key, 0.0)
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(numeric):
        return 0.0
    return numeric


def _safe_drawdown(stats: Dict[str, Any]) -> float:
    """Return absolute max drawdown percentage, handling alternate keys."""
    primary = _safe_metric(stats, "Max Drawdown [%]")
    if primary == 0.0:
        primary = _safe_metric(stats, "Max. Drawdown [%]")
    return abs(primary)


def _prepare_dataset(data: pd.DataFrame) -> pd.DataFrame:
    """Ensure dataframe conforms to Backtesting.py requirements."""
    if data.empty:
        raise ValueError("Input data for backtest is empty.")

    required_columns = ["open", "high", "low", "close"]
    lower_columns = [col.lower() for col in data.columns]
    missing = [col for col in required_columns if col not in lower_columns]
    if missing:
        raise ValueError(f"Input data missing required columns: {missing}")

    df = data.copy()
    rename_map = {col: col.title() for col in df.columns}
    df = df.rename(columns=rename_map)

    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)

    return df


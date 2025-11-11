from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Type

import pandas as pd

from backtest.engine import run_backtest
from backtesting import Strategy  # type: ignore
from core.config import default_config
from data import DataManager
from strategies import STRATEGY_REGISTRY

REQUIRED_KEYS = ("symbol", "timeframe", "strategy")

run_config: Dict[str, Any] = {
    "symbol": "BTCUSDT",
    "timeframe": "15m",
    "strategy": "sr_guard",
    "source": "okx",
    "start": None,
    "end": None,
    "lookback_days": 30,
    "output": "backtest/results",
    "strategy_params": {
        "lookback_period": 20,
        "box_width_mult": 1.0,
        "entry_buffer_pct": 0.001,
        "stop_atr_multiple": 3.0,
        "trade_size": 1.0,
    },
}


def run_backtest_with_config(config: Dict[str, Any]) -> None:
    """Run a backtest using the provided configuration dictionary."""
    normalized = _normalize_config(config)
    _execute(normalized)


def _normalize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize configuration entries."""
    missing = [key for key in REQUIRED_KEYS if key not in config]
    if missing:
        raise ValueError(f"Missing required config keys: {', '.join(missing)}")

    normalized = {
        "symbol": config["symbol"],
        "timeframe": config["timeframe"],
        "strategy": config["strategy"],
        "source": config.get("source", "okx"),
        "start": config.get("start"),
        "end": config.get("end"),
        "lookback_days": config.get("lookback_days"),
        "output": config.get("output", "backtest/results"),
        "strategy_params": config.get("strategy_params", {}),
    }
    if not normalized["start"] and not normalized["end"]:
        lookback_days = normalized.get("lookback_days") or 30
        start, end = _default_time_range(int(lookback_days))
        normalized["start"] = start
        normalized["end"] = end
    return normalized


def _execute(config: Dict[str, Any]) -> None:
    """Execute the backtest with normalized configuration."""
    manager = DataManager(default_config)
    start = _parse_datetime(config.get("start"))
    end = _parse_datetime(config.get("end"))
    data = manager.get_klines(
        config["symbol"],
        config["timeframe"],
        start=start,
        end=end,
        source=config["source"],
    )

    strategy_cls = _resolve_strategy(config["strategy"])
    output_dir = Path(config["output"])
    run_backtest(
        data,
        strategy_cls,
        config=default_config,
        output_dir=output_dir,
        strategy_params=config.get("strategy_params", {}),
    )


def _resolve_strategy(name: str) -> Type[Strategy]:
    """Resolve strategy class by registry key."""
    key = name.lower()
    if key not in STRATEGY_REGISTRY:
        raise ValueError(f"Strategy {name} not found in registry.")
    return STRATEGY_REGISTRY[key]


def _parse_datetime(value: Optional[str]) -> Optional[pd.Timestamp]:
    """Parse ISO formatted datetime string to pandas timestamp."""
    if value is None:
        return None
    return pd.to_datetime(value, utc=True)


def _default_time_range(days: int) -> tuple[str, str]:
    """Return ISO formatted start/end covering the trailing number of days."""
    end = pd.Timestamp.utcnow().floor("min").tz_convert("UTC")
    start = end - pd.Timedelta(days=days)
    return start.isoformat(), end.isoformat()


def main() -> None:
    """Main entry point for running a backtest with the predefined configuration."""
    run_backtest_with_config(run_config.copy())


if __name__ == "__main__":
    main()


__all__ = ["run_config", "run_backtest_with_config", "main"]


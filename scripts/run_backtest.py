from __future__ import annotations

import argparse
from pathlib import Path
from typing import Type

import pandas as pd

from backtest.engine import run_backtest
from core.config import default_config
from data import DataManager
from strategies import STRATEGY_REGISTRY
from backtesting import Strategy  # type: ignore


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Run quantitative backtests.")
    parser.add_argument("--symbol", required=True, help="Trading symbol, e.g. BTCUSDT or BTC/USDT.")
    parser.add_argument("--tf", required=True, help="Timeframe, e.g. 4h.")
    parser.add_argument("--strategy", required=True, help="Strategy key in registry, e.g. tdxh.")
    parser.add_argument("--source", default="okx", help="Data source identifier.")
    parser.add_argument("--start", help="Start time in ISO format.")
    parser.add_argument("--end", help="End time in ISO format.")
    parser.add_argument("--output", default="backtest/results", help="Output directory for results.")
    return parser.parse_args()


def resolve_strategy(name: str) -> Type[Strategy]:
    """Resolve strategy class by registry key."""
    key = name.lower()
    if key not in STRATEGY_REGISTRY:
        raise ValueError(f"Strategy {name} not found in registry.")
    return STRATEGY_REGISTRY[key]


def main() -> None:
    """Execute backtest via CLI."""
    args = parse_args()
    manager = DataManager(default_config)

    start = pd.to_datetime(args.start, utc=True) if args.start else None
    end = pd.to_datetime(args.end, utc=True) if args.end else None

    data = manager.get_klines(args.symbol, args.tf, start=start, end=end, source=args.source)
    strategy_cls = resolve_strategy(args.strategy)
    output_dir = Path(args.output)

    run_backtest(data, strategy_cls, config=default_config, output_dir=output_dir)


if __name__ == "__main__":
    main()


from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Iterable

import pandas as pd
from backtesting import Backtest

from preprocess.build_sr_range import build_support_resistance
from strategies.structure_weighted_grid import StructureWeightedGrid

DATA_PATH_DEFAULT = Path("data/btcusdt_15m.csv")


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    required = {"open", "high", "low", "close", "volume"}
    if set(df.columns.str.lower()) >= required:
        return df
    rename_map = {c: c.lower() for c in df.columns}
    df = df.rename(columns=rename_map)
    if set(df.columns) < required:
        raise ValueError(f"CSV missing required columns: {sorted(required - set(df.columns))}")
    return df


def single_run(df: pd.DataFrame) -> Dict[str, float]:
    dataset = build_support_resistance(df)
    bt = Backtest(
        dataset,
        StructureWeightedGrid,
        commission=StructureWeightedGrid.maker_commission,
        trade_on_close=False,
        exclusive_orders=False,
        hedging=False,
    )
    stats = bt.run()
    print("Single Run Summary\n====================")
    print(stats)
    return stats


def grid_search(df: pd.DataFrame) -> Dict[str, float]:
    dataset = build_support_resistance(df)
    bt = Backtest(
        dataset,
        StructureWeightedGrid,
        commission=StructureWeightedGrid.maker_commission,
        trade_on_close=False,
        exclusive_orders=False,
        hedging=False,
    )
    optimization = bt.optimize(
        grid_gap_pct=[0.0015, 0.0018, 0.0022],
        alpha=[1.5, 2.0, 2.5],
        max_levels_side=[6, 8, 10],
        constraint=lambda p: p.max_levels_side >= 4,
        maximize="Return [%]",
    )
    print("Grid Search Best\n=================")
    print(optimization)
    return optimization


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Structure-Weighted Grid backtest")
    parser.add_argument("--csv", type=Path, default=DATA_PATH_DEFAULT, help="Path to 15m BTC CSV")
    parser.add_argument("--scan", action="store_true", help="Run parameter grid search")
    args = parser.parse_args()

    df = load_csv(args.csv)
    stats = single_run(df)
    if args.scan:
        grid_search(df)


if __name__ == "__main__":
    main()

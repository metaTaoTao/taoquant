from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from data import DataManager


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for data fetching."""
    parser = argparse.ArgumentParser(description="Fetch market data and store as CSV.")
    parser.add_argument("--symbol", required=True, help="Trading symbol, e.g. BTC/USDT.")
    parser.add_argument("--tf", required=True, help="Timeframe, e.g. 4h.")
    parser.add_argument("--source", default="okx", help="Data source to use.")
    parser.add_argument("--start", help="Start time in ISO format.")
    parser.add_argument("--end", help="End time in ISO format.")
    parser.add_argument("--output", help="Optional CSV output path.")
    return parser.parse_args()


def main() -> None:
    """Fetch data from source and export to CSV."""
    args = parse_args()
    manager = DataManager()

    start = pd.to_datetime(args.start, utc=True) if args.start else None
    end = pd.to_datetime(args.end, utc=True) if args.end else None

    df = manager.get_klines(args.symbol, args.tf, start=start, end=end, source=args.source)

    if args.output:
        output_path = Path(args.output)
    else:
        safe_symbol = args.symbol.replace("/", "_").lower()
        output_path = Path("data/raw") / f"{safe_symbol}_{args.tf}.csv"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path)
    print(f"Saved OHLCV data to {output_path}")


if __name__ == "__main__":
    main()


"""
Bitget Live Trading Runner - Command Line Interface.

Usage:
    python algorithms/taogrid/run_bitget_live.py \
        --symbol BTCUSDT \
        --api-key YOUR_API_KEY \
        --api-secret YOUR_API_SECRET \
        --passphrase YOUR_PASSPHRASE \
        --subaccount-uid SUBACCOUNT_UID

    # Dry run mode
    python algorithms/taogrid/run_bitget_live.py \
        --symbol BTCUSDT \
        --dry-run \
        --api-key YOUR_API_KEY \
        --api-secret YOUR_API_SECRET \
        --passphrase YOUR_PASSPHRASE

    # With config file
    python algorithms/taogrid/run_bitget_live.py \
        --symbol BTCUSDT \
        --config-file config.json \
        --api-key YOUR_API_KEY \
        --api-secret YOUR_API_SECRET \
        --passphrase YOUR_PASSPHRASE
"""

from __future__ import annotations

import sys
import json
import argparse
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.bitget_live_runner import BitgetLiveRunner
from algorithms.taogrid.config import TaoGridLeanConfig


def load_config_from_file(config_file: str) -> TaoGridLeanConfig:
    """
    Load configuration from JSON file.

    Parameters
    ----------
    config_file : str
        Path to config file

    Returns
    -------
    TaoGridLeanConfig
        Configuration object
    """
    config_path = Path(config_file)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")

    with open(config_path, "r", encoding="utf-8") as f:
        config_data = json.load(f)

    # Extract strategy config
    strategy_config = config_data.get("strategy", {})
    execution_config = config_data.get("execution", {})

    # Create config object with all parameters from JSON
    # Required parameters
    config = TaoGridLeanConfig(
        name=strategy_config.get("name", "TaoGrid Live"),
        support=float(strategy_config.get("support", 104000.0)),
        resistance=float(strategy_config.get("resistance", 126000.0)),
        regime=strategy_config.get("regime", "NEUTRAL_RANGE"),
        grid_layers_buy=int(strategy_config.get("grid_layers_buy", 5)),
        grid_layers_sell=int(strategy_config.get("grid_layers_sell", 5)),
        initial_cash=float(strategy_config.get("initial_cash", 1000.0)),
    )

    # Optional parameters (override defaults if provided)
    if "min_return" in strategy_config:
        config.min_return = float(strategy_config["min_return"])
    if "spacing_multiplier" in strategy_config:
        config.spacing_multiplier = float(strategy_config["spacing_multiplier"])
    if "risk_budget_pct" in strategy_config:
        config.risk_budget_pct = float(strategy_config["risk_budget_pct"])
    if "maker_fee" in strategy_config:
        config.maker_fee = float(strategy_config["maker_fee"])
    if "volatility_k" in strategy_config:
        config.volatility_k = float(strategy_config["volatility_k"])
    if "cushion_multiplier" in strategy_config:
        config.cushion_multiplier = float(strategy_config["cushion_multiplier"])
    if "atr_period" in strategy_config:
        config.atr_period = int(strategy_config["atr_period"])
    if "weight_k" in strategy_config:
        config.weight_k = float(strategy_config["weight_k"])
    if "leverage" in strategy_config:
        config.leverage = float(strategy_config["leverage"])
    if "enable_throttling" in strategy_config:
        config.enable_throttling = bool(strategy_config["enable_throttling"])
    if "enable_mm_risk_zone" in strategy_config:
        config.enable_mm_risk_zone = bool(strategy_config["enable_mm_risk_zone"])
    if "enable_console_log" in strategy_config:
        config.enable_console_log = bool(strategy_config["enable_console_log"])

    return config


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Bitget Live Trading Runner for TaoGrid Strategy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python run_bitget_live.py --symbol BTCUSDT \\
      --api-key YOUR_KEY --api-secret YOUR_SECRET --passphrase YOUR_PASSPHRASE

  # Dry run mode
  python run_bitget_live.py --symbol BTCUSDT --dry-run \\
      --api-key YOUR_KEY --api-secret YOUR_SECRET --passphrase YOUR_PASSPHRASE

  # With subaccount
  python run_bitget_live.py --symbol BTCUSDT \\
      --api-key YOUR_KEY --api-secret YOUR_SECRET --passphrase YOUR_PASSPHRASE \\
      --subaccount-uid SUBACCOUNT_UID

  # With config file
  python run_bitget_live.py --symbol BTCUSDT --config-file config.json \\
      --api-key YOUR_KEY --api-secret YOUR_SECRET --passphrase YOUR_PASSPHRASE
        """,
    )

    # Required arguments
    parser.add_argument(
        "--symbol",
        required=True,
        help="Trading symbol (e.g., BTCUSDT)",
    )

    parser.add_argument(
        "--api-key",
        required=False,
        default=None,
        help="Bitget API Key (or set env BITGET_API_KEY)",
    )

    parser.add_argument(
        "--api-secret",
        required=False,
        default=None,
        help="Bitget API Secret (or set env BITGET_API_SECRET)",
    )

    parser.add_argument(
        "--passphrase",
        required=False,
        default=None,
        help="Bitget API Passphrase (or set env BITGET_PASSPHRASE)",
    )

    # Optional arguments
    parser.add_argument(
        "--subaccount-uid",
        help="Subaccount UID (optional)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode - don't place actual orders",
    )

    parser.add_argument(
        "--config-file",
        help="Path to strategy config file (JSON)",
    )

    parser.add_argument(
        "--log-dir",
        default="logs/bitget_live",
        help="Log directory (default: logs/bitget_live)",
    )

    args = parser.parse_args()

    # Resolve credentials (prefer CLI, fallback to env)
    api_key = args.api_key or os.getenv("BITGET_API_KEY")
    api_secret = args.api_secret or os.getenv("BITGET_API_SECRET")
    passphrase = args.passphrase or os.getenv("BITGET_PASSPHRASE")

    if not api_key or not api_secret or not passphrase:
        print("Error: Bitget API credentials are required.")
        print("Provide via CLI flags (--api-key/--api-secret/--passphrase) or set env:")
        print("  - BITGET_API_KEY")
        print("  - BITGET_API_SECRET")
        print("  - BITGET_PASSPHRASE")
        sys.exit(2)

    # Load configuration
    try:
        if args.config_file:
            print(f"Loading configuration from {args.config_file}...")
            config = load_config_from_file(args.config_file)
        else:
            print("Using default configuration...")
            config = TaoGridLeanConfig(
                name="TaoGrid Live (Bitget)",
                support=104000.0,
                resistance=126000.0,
                regime="NEUTRAL_RANGE",
            )
    except Exception as e:
        print(f"Error loading configuration: {e}")
        sys.exit(1)

    # Create runner
    try:
        print("\n" + "=" * 80)
        print("Bitget Live Trading Runner")
        print("=" * 80)
        print(f"Symbol: {args.symbol}")
        print(f"Dry Run: {args.dry_run}")
        if args.subaccount_uid:
            print(f"Subaccount UID: {args.subaccount_uid}")
        print("=" * 80 + "\n")

        runner = BitgetLiveRunner(
            config=config,
            symbol=args.symbol,
            bitget_api_key=api_key,
            bitget_api_secret=api_secret,
            bitget_passphrase=passphrase,
            subaccount_uid=args.subaccount_uid,
            dry_run=args.dry_run,
            log_dir=args.log_dir,
        )

        # Run
        runner.run()

    except KeyboardInterrupt:
        print("\n\nStopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

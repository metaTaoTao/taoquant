"""
Deployment script for StandardGridV2 live trading on Bitget.

Quick start:
1. Set environment variables:
   - BITGET_API_KEY
   - BITGET_API_SECRET
   - BITGET_PASSPHRASE

2. Run:
   python deploy_standard_grid_v2.py --dry-run  # Test first
   python deploy_standard_grid_v2.py            # Live trading
"""

import os
import sys
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.standard_grid_v2_live import StandardGridV2Live, LiveGridConfig


def main():
    """Deploy StandardGridV2 to Bitget."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Deploy StandardGridV2 to Bitget")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no real orders)"
    )
    parser.add_argument(
        "--support",
        type=float,
        default=76000.0,
        help="Support level (default: 76000)"
    )
    parser.add_argument(
        "--resistance",
        type=float,
        default=97000.0,
        help="Resistance level (default: 97000)"
    )
    parser.add_argument(
        "--balance",
        type=float,
        default=100.0,
        help="Initial balance in USDT (default: 100)"
    )
    parser.add_argument(
        "--leverage",
        type=float,
        default=10.0,
        help="Leverage (default: 10)"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTCUSDT",
        help="Trading symbol (default: BTCUSDT)"
    )

    args = parser.parse_args()

    # Load API credentials
    api_key = os.getenv("BITGET_API_KEY")
    api_secret = os.getenv("BITGET_API_SECRET")
    passphrase = os.getenv("BITGET_PASSPHRASE")

    if not all([api_key, api_secret, passphrase]):
        print("\n[ERROR] Missing API credentials!")
        print("Please set environment variables:")
        print("  - BITGET_API_KEY")
        print("  - BITGET_API_SECRET")
        print("  - BITGET_PASSPHRASE")
        print("\nExample (Windows):")
        print("  set BITGET_API_KEY=your_key_here")
        print("  set BITGET_API_SECRET=your_secret_here")
        print("  set BITGET_PASSPHRASE=your_passphrase_here")
        print("\nExample (Linux/Mac):")
        print("  export BITGET_API_KEY=your_key_here")
        print("  export BITGET_API_SECRET=your_secret_here")
        print("  export BITGET_PASSPHRASE=your_passphrase_here")
        sys.exit(1)

    # Create configuration
    config = LiveGridConfig(
        support=args.support,
        resistance=args.resistance,
        initial_cash=args.balance,
        leverage=args.leverage,
        mode="geometric",
        min_return=0.005,
        maker_fee=0.0002,
        volatility_k=0.6,
        atr_period=14,
        poll_interval_seconds=10,
        max_position_usd=args.balance * args.leverage * 5,  # 5x safety margin
        max_drawdown_pct=0.20,
    )

    # Print configuration
    print("\n" + "=" * 80)
    print("StandardGridV2 Deployment Configuration")
    print("=" * 80)
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE TRADING'}")
    print(f"Symbol: {args.symbol}")
    print(f"Support: ${config.support:,.0f}")
    print(f"Resistance: ${config.resistance:,.0f}")
    print(f"Initial Balance: ${config.initial_cash:,.2f}")
    print(f"Leverage: {config.leverage}X")
    print(f"Total Investment: ${config.initial_cash * config.leverage:,.2f}")
    print(f"Max Position: ${config.max_position_usd:,.2f}")
    print(f"Max Drawdown: {config.max_drawdown_pct:.1%}")
    print("=" * 80)

    if not args.dry_run:
        print("\n[WARNING] You are about to start LIVE TRADING!")
        print("This will place REAL orders on Bitget exchange.")
        response = input("\nType 'YES' to confirm: ")
        if response != "YES":
            print("Deployment cancelled.")
            sys.exit(0)

    # Create runner
    runner = StandardGridV2Live(
        config=config,
        symbol=args.symbol,
        bitget_api_key=api_key,
        bitget_api_secret=api_secret,
        bitget_passphrase=passphrase,
        dry_run=args.dry_run,
    )

    # Run
    try:
        runner.run()
    except KeyboardInterrupt:
        print("\n\nDeployment stopped by user.")
    except Exception as e:
        print(f"\n\n[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

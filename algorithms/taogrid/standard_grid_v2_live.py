"""
Bitget Live Trading Runner for StandardGridV2.

Simplified live trading implementation for exchange-compliant neutral grid.
- Uses StandardGridV2 (exchange-compliant: 1 order per grid)
- Auto-calculates grid count from ATR spacing
- Real-time order placement and monitoring
- Safety checks and error handling
"""

from __future__ import annotations

import sys
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

import pandas as pd
import numpy as np

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.standard_grid_v2 import StandardGridV2, GridOrder, GridOrderStatus
from data.sources.bitget_sdk import BitgetSDKDataSource
from execution.engines.bitget_engine import BitgetExecutionEngine
from analytics.indicators.volatility import calculate_atr
from analytics.indicators.grid_generator import calculate_grid_spacing


@dataclass
class LiveGridConfig:
    """Configuration for live grid trading."""

    # Grid range
    support: float
    resistance: float

    # Capital and leverage
    initial_cash: float = 100.0
    leverage: float = 10.0

    # ATR spacing parameters
    min_return: float = 0.005
    maker_fee: float = 0.0002
    volatility_k: float = 0.6
    atr_period: int = 14

    # Grid mode
    mode: str = "geometric"  # "geometric" or "arithmetic"

    # Safety limits
    max_position_usd: float = 10000.0  # Maximum position value
    max_drawdown_pct: float = 0.20  # Shutdown at 20% drawdown

    # API parameters
    poll_interval_seconds: int = 5  # How often to check for fills

    def validate(self):
        """Validate configuration."""
        if self.support >= self.resistance:
            raise ValueError("support must be < resistance")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be > 0")
        if self.leverage < 1 or self.leverage > 100:
            raise ValueError("leverage must be in [1, 100]")
        if self.mode not in ["geometric", "arithmetic"]:
            raise ValueError("mode must be 'geometric' or 'arithmetic'")


class StandardGridV2Live:
    """
    Live trading runner for StandardGridV2 on Bitget.

    Features:
    - Auto-calculates grid count from ATR spacing
    - Real-time order placement and monitoring
    - Position tracking and safety checks
    - Dry-run mode for testing
    """

    def __init__(
        self,
        config: LiveGridConfig,
        symbol: str,
        bitget_api_key: str,
        bitget_api_secret: str,
        bitget_passphrase: str,
        dry_run: bool = False,
    ):
        """
        Initialize live grid runner.

        Parameters
        ----------
        config : LiveGridConfig
            Grid configuration
        symbol : str
            Trading symbol (e.g., "BTCUSDT")
        bitget_api_key : str
            Bitget API key
        bitget_api_secret : str
            Bitget API secret
        bitget_passphrase : str
            Bitget API passphrase
        dry_run : bool
            If True, don't place actual orders
        """
        config.validate()

        self.config = config
        self.symbol = symbol
        self.dry_run = dry_run

        # Initialize Bitget data source (for market data)
        self.data_source = BitgetSDKDataSource(
            api_key=bitget_api_key,
            api_secret=bitget_api_secret,
            passphrase=bitget_passphrase,
        )

        # Initialize Bitget execution engine (for order placement)
        self.execution_engine = BitgetExecutionEngine(
            api_key=bitget_api_key,
            api_secret=bitget_api_secret,
            passphrase=bitget_passphrase,
            debug=False,
            market_type="spot",
        )

        # Grid will be initialized in run()
        self.grid: Optional[StandardGridV2] = None

        # Track Bitget order IDs
        self.grid_to_bitget_order_id: Dict[tuple, str] = {}  # (grid_index, direction) -> order_id

        # Safety tracking
        self.initial_equity = config.initial_cash
        self.shutdown = False
        self.shutdown_reason = ""

        print(f"\n{'=' * 80}")
        print(f"StandardGridV2 Live Runner - {'DRY RUN' if dry_run else 'LIVE TRADING'}")
        print(f"{'=' * 80}")
        print(f"Symbol: {symbol}")
        print(f"Range: ${config.support:,.0f} - ${config.resistance:,.0f}")
        print(f"Initial Cash: ${config.initial_cash:,.2f}")
        print(f"Leverage: {config.leverage}X")
        print(f"Mode: {config.mode}")
        print(f"{'=' * 80}\n")

    def _calculate_auto_grid_count(self, avg_spacing: float) -> int:
        """Auto-calculate grid count from spacing."""
        ratio = self.config.resistance / self.config.support
        grid_count = int(np.log(ratio) / np.log(1 + avg_spacing))
        return max(2, min(200, grid_count))

    def _fetch_recent_data(self, lookback_bars: int = 500) -> pd.DataFrame:
        """Fetch recent OHLCV data for ATR calculation."""
        print(f"Fetching {lookback_bars} bars of 15m data...")

        end_time = datetime.now(timezone.utc)

        data = self.data_source.get_klines(
            symbol=self.symbol,
            timeframe="15m",
            limit=lookback_bars,
        )

        if data.empty:
            raise RuntimeError("Failed to fetch market data")

        print(f"Loaded {len(data)} bars")
        print(f"Price range: ${data['close'].min():,.0f} - ${data['close'].max():,.0f}")

        return data

    def _initialize_grid(self) -> StandardGridV2:
        """Initialize grid with auto-calculated grid count."""
        # Fetch data
        data = self._fetch_recent_data()

        # Calculate ATR spacing
        print("\nCalculating ATR spacing...")
        atr = calculate_atr(
            data['high'],
            data['low'],
            data['close'],
            period=self.config.atr_period
        )

        spacing_series = calculate_grid_spacing(
            atr=atr,
            min_return=self.config.min_return,
            maker_fee=self.config.maker_fee,
            volatility_k=self.config.volatility_k,
        )

        avg_spacing = spacing_series.mean()
        print(f"Average spacing: {avg_spacing:.4%}")

        # Auto-calculate grid count
        grid_count = self._calculate_auto_grid_count(avg_spacing)
        print(f"Auto-calculated grid count: {grid_count}")

        # Create grid
        total_investment = self.config.initial_cash * self.config.leverage

        grid = StandardGridV2(
            lower_price=self.config.support,
            upper_price=self.config.resistance,
            grid_count=grid_count,
            mode=self.config.mode,
            total_investment=total_investment,
            leverage=self.config.leverage,
            maker_fee=self.config.maker_fee,
        )

        # Initialize at current price
        current_price = data['close'].iloc[-1]
        print(f"\nCurrent price: ${current_price:,.2f}")

        grid.initialize_grid(current_price=current_price)

        stats = grid.get_statistics()
        print(f"\nGrid initialized:")
        print(f"  Active buy orders: {stats['active_buy_orders']}")
        print(f"  Active sell orders: {stats['active_sell_orders']}")
        print(f"  Total grids: {stats['grid_count']}")

        return grid

    def _place_order_on_exchange(
        self,
        side: str,
        price: float,
        size: float,
    ) -> Optional[str]:
        """
        Place limit order on Bitget.

        Returns order ID if successful, None otherwise.
        """
        if self.dry_run:
            print(f"  [DRY RUN] Would place {side} order: {size:.6f} BTC @ ${price:,.2f}")
            return f"dry_run_{int(time.time() * 1000)}"

        try:
            # Place limit order via Bitget execution engine
            order_result = self.execution_engine.place_limit_order(
                symbol=self.symbol,
                side=side.lower(),
                price=price,
                quantity=size,
            )

            if not order_result:
                print(f"  [ERROR] Failed to place {side} order (no response)")
                return None

            order_id = order_result.get("order_id")
            print(f"  Placed {side} order: {size:.6f} BTC @ ${price:,.2f} (ID: {order_id})")

            return order_id

        except Exception as e:
            print(f"  [ERROR] Failed to place {side} order: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _cancel_order_on_exchange(self, order_id: str) -> bool:
        """Cancel order on Bitget."""
        if self.dry_run:
            print(f"  [DRY RUN] Would cancel order {order_id}")
            return True

        try:
            success = self.execution_engine.cancel_order(symbol=self.symbol, order_id=order_id)
            if success:
                print(f"  Cancelled order {order_id}")
            else:
                print(f"  [WARNING] Failed to cancel order {order_id}")
            return success
        except Exception as e:
            print(f"  [ERROR] Failed to cancel order {order_id}: {e}")
            return False

    def _sync_orders_to_exchange(self):
        """Sync grid orders to exchange."""
        if self.grid is None:
            return

        print("\n[SYNC] Syncing orders to exchange...")

        # Cancel all existing orders first
        for order_id in list(self.grid_to_bitget_order_id.values()):
            self._cancel_order_on_exchange(order_id)
        self.grid_to_bitget_order_id.clear()

        # Place new orders
        for grid_level in self.grid.grid_levels:
            # Place buy order if exists
            if grid_level.buy_order:
                order_id = self._place_order_on_exchange(
                    side="buy",
                    price=grid_level.price,
                    size=grid_level.buy_order.size,
                )
                if order_id:
                    self.grid_to_bitget_order_id[(grid_level.index, "buy")] = order_id

            # Place sell order if exists
            if grid_level.sell_order:
                order_id = self._place_order_on_exchange(
                    side="sell",
                    price=grid_level.price,
                    size=grid_level.sell_order.size,
                )
                if order_id:
                    self.grid_to_bitget_order_id[(grid_level.index, "sell")] = order_id

        print(f"[SYNC] Placed {len(self.grid_to_bitget_order_id)} orders on exchange")

    def _check_fills(self) -> List[GridOrder]:
        """
        Check for filled orders on exchange.

        Returns list of filled grid orders.
        """
        if self.grid is None:
            return []

        filled_orders = []

        if self.dry_run:
            # In dry-run, simulate fills using current price
            data = self._fetch_recent_data(lookback_bars=1)
            current_price = data['close'].iloc[-1]
            timestamp = datetime.now(timezone.utc)

            # Check each grid order
            for grid_level in self.grid.grid_levels:
                # Check buy fills
                if grid_level.buy_order and current_price <= grid_level.price:
                    order = grid_level.buy_order
                    order.status = GridOrderStatus.FILLED
                    order.filled_time = timestamp
                    order.fill_price = grid_level.price
                    filled_orders.append(order)
                    self.grid._on_buy_filled(grid_level.index, order, timestamp)

                # Check sell fills
                if grid_level.sell_order and current_price >= grid_level.price:
                    order = grid_level.sell_order
                    order.status = GridOrderStatus.FILLED
                    order.filled_time = timestamp
                    order.fill_price = grid_level.price
                    filled_orders.append(order)
                    self.grid._on_sell_filled(grid_level.index, order, timestamp)

        else:
            # In live mode, query exchange for order status
            try:
                # Check each tracked order
                to_remove = []

                for (grid_idx, direction), bitget_order_id in list(self.grid_to_bitget_order_id.items()):
                    # Get order status
                    order_status = self.execution_engine.get_order_status(
                        symbol=self.symbol,
                        order_id=bitget_order_id,
                    )

                    if not order_status:
                        continue

                    # Check if order is filled
                    status = order_status.get("status", "").lower()
                    if status == "closed" or status == "filled":
                        grid_level = self.grid.grid_levels[grid_idx]
                        timestamp = datetime.now(timezone.utc)

                        if direction == "buy" and grid_level.buy_order:
                            order = grid_level.buy_order
                            order.status = GridOrderStatus.FILLED
                            order.filled_time = timestamp
                            order.fill_price = order_status.get("average_price", grid_level.price)
                            filled_orders.append(order)
                            self.grid._on_buy_filled(grid_idx, order, timestamp)
                            to_remove.append((grid_idx, direction))

                        elif direction == "sell" and grid_level.sell_order:
                            order = grid_level.sell_order
                            order.status = GridOrderStatus.FILLED
                            order.filled_time = timestamp
                            order.fill_price = order_status.get("average_price", grid_level.price)
                            filled_orders.append(order)
                            self.grid._on_sell_filled(grid_idx, order, timestamp)
                            to_remove.append((grid_idx, direction))

                # Remove filled orders from tracking
                for key in to_remove:
                    del self.grid_to_bitget_order_id[key]

            except Exception as e:
                print(f"[ERROR] Failed to check fills: {e}")
                import traceback
                traceback.print_exc()

        return filled_orders

    def _check_safety_limits(self) -> bool:
        """
        Check safety limits.

        Returns True if safe to continue, False if should shutdown.
        """
        if self.grid is None:
            return True

        stats = self.grid.get_statistics()

        # Check drawdown
        current_equity = self.initial_equity + stats['net_pnl']
        drawdown = (current_equity - self.initial_equity) / self.initial_equity

        if drawdown < -self.config.max_drawdown_pct:
            self.shutdown = True
            self.shutdown_reason = f"Max drawdown exceeded: {drawdown:.2%}"
            return False

        # Check position size
        data = self._fetch_recent_data(lookback_bars=1)
        current_price = data['close'].iloc[-1]
        position_value = abs(stats['net_position_btc'] * current_price)

        if position_value > self.config.max_position_usd:
            self.shutdown = True
            self.shutdown_reason = f"Max position exceeded: ${position_value:,.2f}"
            return False

        return True

    def _print_status(self):
        """Print current status."""
        if self.grid is None:
            return

        stats = self.grid.get_statistics()
        data = self._fetch_recent_data(lookback_bars=1)
        current_price = data['close'].iloc[-1]

        current_equity = self.initial_equity + stats['net_pnl']
        pnl_pct = (current_equity - self.initial_equity) / self.initial_equity

        print(f"\n{'=' * 80}")
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Status")
        print(f"{'=' * 80}")
        print(f"Current Price: ${current_price:,.2f}")
        print(f"Equity: ${current_equity:,.2f} ({pnl_pct:+.2%})")
        print(f"Net PnL: ${stats['net_pnl']:,.2f}")
        print(f"Total Trades: {stats['total_trades']}")
        print(f"Position: {stats['net_position_btc']:.6f} BTC")
        print(f"Active Orders: {stats['active_buy_orders']} buy, {stats['active_sell_orders']} sell")
        print(f"{'=' * 80}\n")

    def run(self):
        """
        Run live trading loop.

        Main loop:
        1. Initialize grid
        2. Sync orders to exchange
        3. Poll for fills
        4. Update grid state
        5. Check safety limits
        6. Repeat
        """
        try:
            # Initialize grid
            print("\n[INIT] Initializing grid...")
            self.grid = self._initialize_grid()

            # Sync orders to exchange
            self._sync_orders_to_exchange()

            # Main loop
            print(f"\n[LIVE] Starting trading loop (poll every {self.config.poll_interval_seconds}s)...")
            iteration = 0

            while not self.shutdown:
                iteration += 1

                # Check for fills
                filled_orders = self._check_fills()

                if filled_orders:
                    print(f"\n[FILL] {len(filled_orders)} orders filled!")
                    # Re-sync orders after fills
                    self._sync_orders_to_exchange()

                # Check safety limits
                if not self._check_safety_limits():
                    print(f"\n[SHUTDOWN] {self.shutdown_reason}")
                    break

                # Print status every 10 iterations
                if iteration % 10 == 0:
                    self._print_status()

                # Sleep
                time.sleep(self.config.poll_interval_seconds)

        except KeyboardInterrupt:
            print("\n[STOP] Interrupted by user")

        except Exception as e:
            print(f"\n[ERROR] Fatal error: {e}")
            import traceback
            traceback.print_exc()

        finally:
            # Cancel all orders on shutdown
            print("\n[CLEANUP] Cancelling all orders...")
            for order_id in list(self.grid_to_bitget_order_id.values()):
                self._cancel_order_on_exchange(order_id)

            # Print final stats
            if self.grid:
                print("\n[FINAL] Final statistics:")
                self._print_status()


def main():
    """Example usage."""
    import os

    # Load API credentials from environment
    api_key = os.getenv("BITGET_API_KEY")
    api_secret = os.getenv("BITGET_API_SECRET")
    passphrase = os.getenv("BITGET_PASSPHRASE")

    if not all([api_key, api_secret, passphrase]):
        print("Error: Set BITGET_API_KEY, BITGET_API_SECRET, BITGET_PASSPHRASE environment variables")
        return

    # Configuration
    config = LiveGridConfig(
        support=76000.0,
        resistance=97000.0,
        initial_cash=100.0,
        leverage=10.0,
        mode="geometric",
        poll_interval_seconds=10,
    )

    # Create runner (dry-run by default)
    runner = StandardGridV2Live(
        config=config,
        symbol="BTCUSDT",
        bitget_api_key=api_key,
        bitget_api_secret=api_secret,
        bitget_passphrase=passphrase,
        dry_run=True,  # Set to False for live trading
    )

    # Run
    runner.run()


if __name__ == "__main__":
    main()

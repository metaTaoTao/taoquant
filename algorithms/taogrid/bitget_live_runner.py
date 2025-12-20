"""
Bitget Live Trading Runner.

This module provides real-time execution of TaoGrid strategy on Bitget exchange.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.algorithm import TaoGridLeanAlgorithm
from algorithms.taogrid.config import TaoGridLeanConfig
from algorithms.taogrid.live_logger import LiveLogger
from data.sources.bitget_sdk import BitgetSDKDataSource
from execution.engines.bitget_engine import BitgetExecutionEngine


class BitgetLiveRunner:
    """Bitget live trading runner."""

    def __init__(
        self,
        config: TaoGridLeanConfig,
        symbol: str,
        bitget_api_key: str,
        bitget_api_secret: str,
        bitget_passphrase: str,
        subaccount_uid: Optional[str] = None,
        dry_run: bool = False,
        log_dir: str = "logs/bitget_live",
    ):
        """
        Initialize Bitget live runner.

        Parameters
        ----------
        config : TaoGridLeanConfig
            Strategy configuration
        symbol : str
            Trading symbol (e.g., "BTCUSDT")
        bitget_api_key : str
            Bitget API key
        bitget_api_secret : str
            Bitget API secret
        bitget_passphrase : str
            Bitget API passphrase
        subaccount_uid : str, optional
            Subaccount UID
        dry_run : bool
            If True, don't place actual orders
        log_dir : str
            Log directory
        """
        self.config = config
        self.symbol = symbol
        self.dry_run = dry_run
        self.subaccount_uid = subaccount_uid

        # Initialize logger
        self.logger = LiveLogger(log_dir=log_dir, name=f"bitget_live_{symbol}")

        # Initialize data source
        self.data_source = BitgetSDKDataSource(
            api_key=bitget_api_key,
            api_secret=bitget_api_secret,
            passphrase=bitget_passphrase,
            debug=True,
        )

        # Initialize execution engine
        self.execution_engine = BitgetExecutionEngine(
            api_key=bitget_api_key,
            api_secret=bitget_api_secret,
            passphrase=bitget_passphrase,
            subaccount_uid=subaccount_uid,
            debug=True,
        )

        # Initialize algorithm
        self.algorithm = TaoGridLeanAlgorithm(config)

        # Track last processed bar timestamp
        self.last_bar_timestamp: Optional[datetime] = None

        # Track pending orders (order_id -> order_info)
        self.pending_orders: Dict[str, Dict[str, Any]] = {}

        # Initialize strategy
        self._initialize_strategy()

    def _initialize_strategy(self):
        """Initialize strategy with historical data."""
        self.logger.log_info("=" * 80)
        self.logger.log_info("Initializing TaoGrid Strategy")
        self.logger.log_info("=" * 80)

        # Get historical data for grid setup (use 1m to match backtest)
        # Use 30 days to get more stable ATR calculation
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30)

        self.logger.log_info(f"Fetching historical data from {start_date} to {end_date}...")
        self.logger.log_info("Using 1m timeframe to match backtest")

        try:
            historical_data = self.data_source.get_klines(
                symbol=self.symbol,
                timeframe="1m",  # Match backtest timeframe
                start=start_date,
                end=end_date,
            )

            if historical_data.empty:
                raise ValueError("No historical data retrieved")

            self.logger.log_info(f"Retrieved {len(historical_data)} bars")

            # Initialize algorithm
            self.algorithm.initialize(
                symbol=self.symbol,
                start_date=start_date,
                end_date=end_date,
                historical_data=historical_data,
            )

            self.logger.log_info("Strategy initialized successfully")
            self.logger.log_info("=" * 80)

        except Exception as e:
            self.logger.log_error(f"Failed to initialize strategy: {e}", exc_info=True)
            raise

    def _get_portfolio_state(self, current_price: float) -> Dict[str, Any]:
        """
        Get current portfolio state.

        Returns
        -------
        dict
            Portfolio state with equity, cash, holdings, etc.
        """
        try:
            balance = self.execution_engine.get_account_balance()
            positions = self.execution_engine.get_positions(self.symbol)

            # Calculate total equity
            available_balance = float(balance.get("available_balance", 0.0) or 0.0)
            frozen_balance = float(balance.get("frozen_balance", 0.0) or 0.0)

            # Get holdings for the symbol
            holdings = 0.0
            for pos in positions:
                if pos.get("symbol") == self.symbol or pos.get("currency") == self.symbol.replace("USDT", ""):
                    holdings = pos.get("quantity", 0.0)
                    break

            # Spot equity approximation in USDT:
            # equity ~= USDT_cash + base_holdings * current_price
            total_equity = (available_balance + frozen_balance) + float(holdings or 0.0) * float(current_price)

            # Calculate unrealized PnL (simplified - would need current price)
            unrealized_pnl = 0.0

            return {
                "equity": total_equity,
                "cash": available_balance,
                "holdings": holdings,
                "unrealized_pnl": unrealized_pnl,
                "daily_pnl": 0.0,  # Will be updated by algorithm
            }

        except Exception as e:
            self.logger.log_error(f"Error getting portfolio state: {e}", exc_info=True)
            # Return default state
            return {
                "equity": self.config.initial_cash,
                "cash": self.config.initial_cash,
                "holdings": 0.0,
                "unrealized_pnl": 0.0,
                "daily_pnl": 0.0,
            }

    def _process_filled_orders(self):
        """Process filled orders and update strategy state."""
        try:
            # Get current open orders from exchange
            open_orders = self.execution_engine.get_open_orders(self.symbol)
            open_order_ids = {str(order.get("order_id", "")) for order in open_orders}

            # Check pending orders
            filled_orders = []
            for order_id, order_info in list(self.pending_orders.items()):
                if order_id not in open_order_ids:
                    # Order is no longer open - check if it's filled
                    order_status = self.execution_engine.get_order_status(
                        self.symbol, order_id
                    )

                    if order_status:
                        status = order_status.get("status", "").lower()
                        if status in ["filled", "partially_filled"]:
                            # Order is filled
                            filled_quantity = order_status.get("filled_quantity", 0)
                            if filled_quantity > 0:
                                filled_order = {
                                    "direction": order_info.get("side", "").lower(),
                                    "price": order_status.get("price", 0),
                                    "quantity": filled_quantity,
                                    "level": order_info.get("level", -1),
                                    "timestamp": datetime.now(timezone.utc),
                                }
                                filled_orders.append(filled_order)

                                # Update strategy
                                self.algorithm.on_order_filled(filled_order)

                                self.logger.log_order(
                                    order_id=order_id,
                                    status="filled",
                                    price=filled_order["price"],
                                    quantity=filled_order["quantity"],
                                )

                                # Remove from pending
                                del self.pending_orders[order_id]

            return filled_orders

        except Exception as e:
            self.logger.log_error(f"Error processing filled orders: {e}", exc_info=True)
            return []

    def run(self):
        """Main execution loop."""
        self.logger.log_info("=" * 80)
        self.logger.log_info("Starting Live Trading Runner")
        self.logger.log_info(f"Symbol: {self.symbol}")
        self.logger.log_info(f"Dry Run: {self.dry_run}")
        if self.subaccount_uid:
            self.logger.log_info(f"Subaccount UID: {self.subaccount_uid}")
        self.logger.log_info("=" * 80)

        try:
            while True:
                try:
                    # Get latest bar (use 1m to match grid calculation timeframe)
                    latest_bar = self.data_source.get_latest_bar(self.symbol, "1m")

                    if latest_bar is None:
                        self.logger.log_warning("Failed to get latest bar, retrying...")
                        time.sleep(5)
                        continue

                    bar_timestamp = latest_bar["timestamp"]

                    # Skip if we've already processed this bar
                    if self.last_bar_timestamp is not None:
                        if bar_timestamp <= self.last_bar_timestamp:
                            # Wait for new bar
                            time.sleep(10)
                            continue

                    self.last_bar_timestamp = bar_timestamp

                    # Get portfolio state
                    portfolio_state = self._get_portfolio_state(current_price=float(latest_bar["close"]))

                    # Log portfolio state periodically
                    self.logger.log_portfolio(
                        equity=portfolio_state["equity"],
                        cash=portfolio_state["cash"],
                        holdings=portfolio_state["holdings"],
                        unrealized_pnl=portfolio_state["unrealized_pnl"],
                    )

                    # Process filled orders first
                    self._process_filled_orders()

                    # Prepare bar data
                    bar_data = {
                        "open": latest_bar["open"],
                        "high": latest_bar["high"],
                        "low": latest_bar["low"],
                        "close": latest_bar["close"],
                        "volume": latest_bar["volume"],
                    }

                    # Set current bar index for algorithm (use 0 for live trading)
                    self.algorithm._current_bar_index = 0  # Live trading doesn't use bar index

                    # Call strategy
                    order_signal = self.algorithm.on_data(
                        current_time=bar_timestamp,
                        bar_data=bar_data,
                        portfolio_state=portfolio_state,
                    )

                    # Execute order if signal generated
                    if order_signal and not self.dry_run:
                        order_result = self.execution_engine.place_limit_order(
                            symbol=self.symbol,
                            side=order_signal["direction"],
                            price=order_signal["price"],
                            quantity=order_signal["quantity"],
                        )

                        if order_result:
                            order_id = order_result.get("order_id")
                            if order_id:
                                # Store pending order
                                self.pending_orders[order_id] = {
                                    "side": order_signal["direction"],
                                    "price": order_signal["price"],
                                    "quantity": order_signal["quantity"],
                                    "level": order_signal.get("level", -1),
                                }

                                self.logger.log_signal(
                                    signal_type=order_signal["direction"],
                                    price=order_signal["price"],
                                    quantity=order_signal["quantity"],
                                    level=order_signal.get("level"),
                                    reason=order_signal.get("reason"),
                                )

                                self.logger.log_order(
                                    order_id=order_id,
                                    status="placed",
                                    price=order_signal["price"],
                                    quantity=order_signal["quantity"],
                                )
                        else:
                            self.logger.log_warning(
                                f"Failed to place order: {order_signal}"
                            )

                    elif order_signal and self.dry_run:
                        # Log signal in dry run mode
                        self.logger.log_signal(
                            signal_type=order_signal["direction"],
                            price=order_signal["price"],
                            quantity=order_signal["quantity"],
                            level=order_signal.get("level"),
                            reason="DRY RUN - Order not placed",
                        )

                    # Wait for next minute
                    # Calculate sleep time to align with minute boundary
                    now = datetime.now(timezone.utc)
                    next_minute = (now.replace(second=0, microsecond=0) + timedelta(minutes=1))
                    sleep_seconds = (next_minute - now).total_seconds()
                    if sleep_seconds > 0:
                        time.sleep(min(sleep_seconds, 60))

                except KeyboardInterrupt:
                    self.logger.log_info("Received interrupt signal, stopping...")
                    break
                except Exception as e:
                    self.logger.log_error(f"Error in main loop: {e}", exc_info=True)
                    time.sleep(10)  # Wait before retrying

        except Exception as e:
            self.logger.log_error(f"Fatal error: {e}", exc_info=True)
            raise
        finally:
            self.logger.log_info("=" * 80)
            self.logger.log_info("Live Trading Runner Stopped")
            self.logger.log_info("=" * 80)

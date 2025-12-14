"""
TaoGrid Lean Algorithm - Event-Driven Implementation.

This is the main algorithm class for TaoGrid strategy using QuantConnect's Lean framework.
It provides event-driven execution with real-time throttling support.

References:
    - VectorBT version: strategies/signal_based/taogrid_strategy.py
    - Implementation plan: docs/strategies/taogrid_lean_migration_plan.md
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add taoquant to path
taoquant_root = Path(__file__).parent.parent.parent
if str(taoquant_root) not in sys.path:
    sys.path.insert(0, str(taoquant_root))

from algorithms.taogrid.config import TaoGridLeanConfig
from algorithms.taogrid.helpers.grid_manager import GridManager


class TaoGridLeanAlgorithm:
    """
    TaoGrid strategy implemented for Lean framework.

    This is an event-driven implementation that supports:
    1. Real-time grid order execution
    2. Dynamic inventory tracking
    3. Throttling (Inventory/Profit/Volatility)
    4. Position management

    Workflow:
    1. Initialize() - Setup data, grid, risk management
    2. OnData() - Called every bar, check grid triggers
    3. Place orders based on grid levels and throttling

    Attributes
    ----------
    config : TaoGridLeanConfig
        Strategy configuration
    grid_manager : GridManager
        Manages grid state and throttling
    symbol : str
        Trading symbol (e.g., "BTCUSDT")
    """

    def __init__(self, config: TaoGridLeanConfig = None):
        """
        Initialize TaoGrid Lean algorithm.

        Parameters
        ----------
        config : TaoGridLeanConfig, optional
            Strategy configuration, by default uses default config
        """
        self.config = config or TaoGridLeanConfig()
        self.grid_manager = GridManager(self.config)

        # Trading state
        self.symbol = None
        self.initialized = False
        self.start_date = None
        self.end_date = None

        # Daily tracking
        self.daily_start_equity = self.config.initial_cash
        self.daily_pnl = 0.0
        self.risk_budget = self.config.initial_cash * self.config.risk_budget_pct

        # Order tracking
        self.pending_orders = {}
        self.filled_orders = []

        print(f"TaoGrid Lean Algorithm initialized: {self.config.name}")

    def initialize(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        historical_data=None,
    ):
        """
        Initialize algorithm with symbol and date range.

        This sets up:
        1. Trading symbol
        2. Date range
        3. Grid levels (using historical data for ATR)
        4. Initial state

        Parameters
        ----------
        symbol : str
            Trading symbol (e.g., "BTCUSDT")
        start_date : datetime
            Backtest start date
        end_date : datetime
            Backtest end date
        historical_data : pd.DataFrame, optional
            Historical OHLCV data for grid setup
        """
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date

        print(f"\n{'='*80}")
        print(f"TaoGrid Lean Algorithm - Initialization")
        print(f"{'='*80}")
        print(f"Symbol: {symbol}")
        print(f"Period: {start_date.date()} to {end_date.date()}")
        print(f"Initial Cash: ${self.config.initial_cash:,.0f}")
        print(f"Leverage: {self.config.leverage}x")
        print()

        # Setup grid using historical data
        if historical_data is not None:
            print("Setting up grid...")
            self.grid_manager.setup_grid(historical_data)

            # Print grid info
            grid_info = self.grid_manager.get_grid_info()
            print("\nGrid Configuration:")
            print("-" * 80)
            for key, value in grid_info.items():
                print(f"{key}: {value}")
            print("-" * 80)
            print()

        self.initialized = True
        print("Initialization complete!")
        print(f"{'='*80}\n")

    def on_data(self, current_time: datetime, bar_data: dict, portfolio_state: dict):
        """
        Called every bar to process market data.

        This is the main event handler. It:
        1. Checks for grid triggers
        2. Calculates order size with throttling
        3. Places orders
        4. Updates inventory

        Parameters
        ----------
        current_time : datetime
            Current bar timestamp
        bar_data : dict
            OHLCV data for current bar
            Expected keys: open, high, low, close, volume
        portfolio_state : dict
            Current portfolio state
            Expected keys: equity, positions, daily_pnl

        Returns
        -------
        dict or None
            Order details if order should be placed, None otherwise
            Order format: {
                'symbol': str,
                'direction': 'buy' or 'sell',
                'quantity': float,
                'price': float,
                'level': int,
                'reason': str
            }
        """
        if not self.initialized:
            print("ERROR: Algorithm not initialized!")
            return None

        # Extract bar data
        current_price = bar_data.get("close")
        prev_price = getattr(self, '_prev_price', None)
        bar_high = bar_data.get("high")
        bar_low = bar_data.get("low")
        
        if current_price is None:
            return None

        # Update daily tracking
        self._update_daily_state(current_time, portfolio_state)

        # Check if any pending limit order is triggered
        # Use bar index to avoid duplicate triggers (we'll pass it from runner)
        triggered_order = self.grid_manager.check_limit_order_triggers(
            current_price=current_price,
            prev_price=prev_price,
            bar_high=bar_high,
            bar_low=bar_low,
            bar_index=getattr(self, '_current_bar_index', None)
        )
        
        if triggered_order is None:
            # No limit order triggered, save current price for next bar
            self._prev_price = current_price
            return None  # No trigger, do nothing

        direction = triggered_order['direction']
        level_index = triggered_order['level_index']
        level_price = triggered_order['price']

        # Calculate order size with throttling
        equity = portfolio_state.get("equity", self.config.initial_cash)
        size, throttle_status = self.grid_manager.calculate_order_size(
            direction=direction,
            level_index=level_index,
            level_price=level_price,
            equity=equity,
            daily_pnl=self.daily_pnl,
            risk_budget=self.risk_budget,
        )

        # Check if order should be placed
        if size == 0:
            print(
                f"[{current_time}] Order blocked - {direction.upper()} L{level_index+1} "
                f"@ ${level_price:,.0f}: {throttle_status.reason}"
            )
            # Reset triggered flag so limit order can trigger again later
            # (when throttle conditions improve)
            triggered_order['triggered'] = False
            triggered_order['last_checked_bar'] = None
            return None

        # Log order
        inventory_state = self.grid_manager.get_inventory_state()
        if throttle_status.size_multiplier < 1.0:
            print(
                f"[{current_time}] Order throttled ({throttle_status.size_multiplier:.0%}) - "
                f"{direction.upper()} L{level_index+1} @ ${level_price:,.0f}: "
                f"{throttle_status.reason}"
            )
        else:
            print(
                f"[{current_time}] Order triggered - {direction.upper()} L{level_index+1} "
                f"@ ${level_price:,.0f}, Size: {size:.4f} BTC"
            )

        print(
            f"  Inventory: Long {inventory_state['long_exposure']:.2f} "
            f"({inventory_state['long_pct']:.0%}), "
            f"Short {inventory_state['short_exposure']:.2f} "
            f"({inventory_state['short_pct']:.0%})"
        )

        # Create order
        order = {
            "symbol": self.symbol,
            "direction": direction,
            "quantity": size,
            "price": level_price,
            "level": level_index,
            "reason": throttle_status.reason,
            "timestamp": current_time,
        }
        
        # Save current price for next bar (for cross detection)
        self._prev_price = current_price

        return order

    def on_order_filled(self, order: dict):
        """
        Called when an order is filled.

        Updates inventory tracker and grid positions.

        Parameters
        ----------
        order : dict
            Filled order details
        """
        direction = order["direction"]
        size = order["quantity"]
        level = order["level"]
        price = order["price"]

        # Update inventory
        self.grid_manager.update_inventory(direction, size, level)
        
        # Update grid positions (for pairing)
        if direction == "buy":
            self.grid_manager.add_buy_position(
                buy_level_index=level,
                size=size,
                buy_price=price
            )
            # Remove filled buy limit order
            self.grid_manager.remove_pending_order('buy', level)
            # Place sell limit order at target sell level
            target_sell_level = level  # buy[i] -> sell[i] (1x spacing)
            if self.grid_manager.sell_levels is not None and target_sell_level < len(self.grid_manager.sell_levels):
                target_sell_price = self.grid_manager.sell_levels[target_sell_level]
                self.grid_manager.place_pending_order('sell', target_sell_level, target_sell_price)
                print(f"  Placed sell limit order at L{target_sell_level+1} @ ${target_sell_price:,.0f}")
            # IMPORTANT: Re-place buy limit order immediately (grid strategy: continuous orders)
            # Don't wait for sell - keep buying at this level as long as price is in range
            # Reset filled_levels to allow immediate re-entry
            buy_level_key = f"buy_L{level + 1}"
            if buy_level_key in self.grid_manager.filled_levels:
                del self.grid_manager.filled_levels[buy_level_key]
            # Re-place buy limit order at same level
            if self.grid_manager.buy_levels is not None and level < len(self.grid_manager.buy_levels):
                buy_level_price = self.grid_manager.buy_levels[level]
                self.grid_manager.place_pending_order('buy', level, buy_level_price)
                print(f"  Re-placed buy limit order at L{level+1} @ ${buy_level_price:,.0f} (continuous grid)")
        elif direction == "sell":
            # Remove filled sell limit order
            self.grid_manager.remove_pending_order('sell', level)
            # Reset filled level to allow re-entry (grid strategy: sell -> buy again)
            buy_level_key = f"buy_L{level + 1}"
            if buy_level_key in self.grid_manager.filled_levels:
                del self.grid_manager.filled_levels[buy_level_key]
            # Place new buy limit order at the same buy level (re-entry for grid strategy)
            # Find which buy level corresponds to this sell level
            # Since sell[i] is paired with buy[i], we place buy order at buy[i]
            if self.grid_manager.buy_levels is not None and level < len(self.grid_manager.buy_levels):
                buy_level_price = self.grid_manager.buy_levels[level]
                self.grid_manager.place_pending_order('buy', level, buy_level_price)
                print(f"  Placed buy limit order at L{level+1} @ ${buy_level_price:,.0f} (re-entry)")

        # Track filled order
        self.filled_orders.append(order)
        
        # Reset triggered flag for all orders (in case order was removed before reset)
        self.grid_manager.reset_triggered_orders()

        print(
            f"  Order filled - {direction.upper()} {size:.4f} BTC @ ${price:,.0f} (L{level+1})"
        )

    def _update_daily_state(self, current_time: datetime, portfolio_state: dict):
        """
        Update daily tracking (PnL, equity reset).

        Parameters
        ----------
        current_time : datetime
            Current timestamp
        portfolio_state : dict
            Portfolio state with equity, daily_pnl
        """
        # Reset daily tracking at market open (assuming UTC)
        if current_time.hour == 0 and current_time.minute == 0:
            self.daily_start_equity = portfolio_state.get(
                "equity", self.daily_start_equity
            )
            self.daily_pnl = 0.0
        else:
            # Update daily PnL
            current_equity = portfolio_state.get("equity", self.daily_start_equity)
            self.daily_pnl = current_equity - self.daily_start_equity

    def get_statistics(self) -> dict:
        """
        Get algorithm statistics.

        Returns
        -------
        dict
            Statistics including total orders, inventory state, etc.
        """
        inventory_state = self.grid_manager.get_inventory_state()

        return {
            "total_orders": len(self.filled_orders),
            "long_exposure": inventory_state["long_exposure"],
            "short_exposure": inventory_state["short_exposure"],
            "net_exposure": inventory_state["net_exposure"],
            "long_pct": inventory_state["long_pct"],
            "short_pct": inventory_state["short_pct"],
            "daily_pnl": self.daily_pnl,
        }


# ============================================================================
# Standalone Backtest Runner (for testing without Lean)
# ============================================================================


def run_simple_backtest(
    symbol: str = "BTCUSDT",
    start_date: datetime = None,
    end_date: datetime = None,
    config: TaoGridLeanConfig = None,
):
    """
    Run a simple backtest without full Lean framework.

    This is a lightweight test to verify the algorithm logic works.
    For full Lean integration, use Lean's backtesting engine.

    Parameters
    ----------
    symbol : str
        Trading symbol
    start_date : datetime
        Start date
    end_date : datetime
        End date
    config : TaoGridLeanConfig
        Algorithm configuration
    """
    import pandas as pd
    from data import DataManager

    print("\n" + "=" * 80)
    print("TaoGrid Simple Backtest (Standalone)")
    print("=" * 80 + "\n")

    # Default dates
    if start_date is None:
        start_date = pd.Timestamp("2025-10-01", tz="UTC")
    if end_date is None:
        end_date = pd.Timestamp("2025-12-01", tz="UTC")

    # Default config
    if config is None:
        config = TaoGridLeanConfig(
            name="TaoGrid Lean Test",
            support=104000.0,
            resistance=126000.0,
            regime="NEUTRAL_RANGE",
            enable_throttling=True,
        )

    # Load data
    print("Loading data...")
    data_manager = DataManager()
    data = data_manager.get_klines(
        symbol=symbol,
        timeframe="15m",
        start=start_date,
        end=end_date,
        source="okx",
    )
    print(f"Loaded {len(data)} bars from {data.index[0]} to {data.index[-1]}\n")

    # Initialize algorithm
    algo = TaoGridLeanAlgorithm(config)
    algo.initialize(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        historical_data=data.iloc[:100],  # Use first 100 bars for grid setup
    )

    # Run backtest
    print("Running backtest...\n")
    orders_placed = []
    equity = config.initial_cash

    for i, (timestamp, row) in enumerate(data.iterrows()):
        bar_data = {
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
        }

        portfolio_state = {"equity": equity, "daily_pnl": 0.0}

        # Process bar
        order = algo.on_data(timestamp, bar_data, portfolio_state)

        if order is not None:
            # Simulate order fill
            algo.on_order_filled(order)
            orders_placed.append(order)

            # Update equity (simplified - assume instant fill at level price)
            # In reality, this would be handled by portfolio management
            pass

    # Print results
    print("\n" + "=" * 80)
    print("Backtest Results")
    print("=" * 80 + "\n")

    stats = algo.get_statistics()
    print(f"Total Orders: {stats['total_orders']}")
    print(f"Long Exposure: {stats['long_exposure']:.4f} BTC ({stats['long_pct']:.0%})")
    print(
        f"Short Exposure: {stats['short_exposure']:.4f} BTC ({stats['short_pct']:.0%})"
    )
    print(f"Net Exposure: {stats['net_exposure']:.4f} BTC")
    print()

    if len(orders_placed) > 0:
        print("Sample Orders:")
        for i, order in enumerate(orders_placed[:5]):
            print(
                f"  {i+1}. [{order['timestamp']}] {order['direction'].upper()} "
                f"{order['quantity']:.4f} BTC @ ${order['price']:,.0f}"
            )
        if len(orders_placed) > 5:
            print(f"  ... and {len(orders_placed) - 5} more orders")

    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    # Run standalone test
    run_simple_backtest()

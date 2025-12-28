"""
Neutral Grid Trading Bot.

100% replication of exchange-style neutral grid (Binance/OKX).

Key Features:
1. Geometric (等比) or Arithmetic (等差) grid spacing
2. Adjacent grid pairing (buy[i] -> sell[i+1])
3. Automatic re-entry after fills
4. Initial position establishment at current price

Design Principles:
- Simple and correct first, optimize later
- No complex risk management (that comes in phase 2)
- Clear separation of concerns (grid generation, order management, position tracking)
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import numpy as np

from algorithms.taogrid.neutral_grid_config import NeutralGridConfig


@dataclass
class GridOrder:
    """Represents a pending grid order."""

    grid_index: int  # Index in grid_prices array
    direction: str  # "buy" or "sell"
    price: float  # Limit price
    size: float  # Order size in base currency (BTC)
    placed_time: Optional[datetime] = None
    order_id: Optional[str] = None  # For live trading
    triggered: bool = False  # Whether order was triggered in current bar


@dataclass
class GridPosition:
    """Represents a filled position."""

    grid_index: int
    direction: str  # "buy" or "sell" (direction of entry)
    entry_price: float
    size: float  # Position size in base currency
    entry_time: datetime
    paired_grid_index: Optional[int] = None  # Target exit grid index


class NeutralGridManager:
    """
    Manages neutral grid trading logic.

    Workflow:
    1. setup_grid(current_price) - Generate grid prices and place initial orders
    2. on_bar(bar_data) - Check for order triggers
    3. on_order_filled(order) - Update state and place new orders

    Attributes
    ----------
    config : NeutralGridConfig
        Grid configuration
    grid_prices : List[float]
        All grid price levels (sorted ascending)
    pending_orders : List[GridOrder]
        Orders waiting to be filled
    positions : List[GridPosition]
        Currently held positions
    total_pnl : float
        Cumulative realized PnL
    """

    def __init__(self, config: NeutralGridConfig):
        """
        Initialize neutral grid manager.

        Parameters
        ----------
        config : NeutralGridConfig
            Grid configuration
        """
        self.config = config

        # Grid state
        self.grid_prices: List[float] = []
        self.grid_initialized: bool = False

        # Order and position tracking
        self.pending_orders: List[GridOrder] = []
        self.positions: List[GridPosition] = []

        # PnL tracking
        self.total_pnl: float = 0.0
        self.total_fees: float = 0.0
        self.total_trades: int = 0

        # Statistics
        self.total_buy_volume: float = 0.0
        self.total_sell_volume: float = 0.0

    def _log(self, message: str) -> None:
        """Log message if console logging is enabled."""
        if self.config.enable_console_log:
            print(message)

    # ========================================================================
    # Grid Generation
    # ========================================================================

    def generate_grid_prices(self) -> List[float]:
        """
        Generate grid price levels.

        Returns
        -------
        List[float]
            Grid prices (sorted ascending)

        Notes
        -----
        Geometric grid (等比):
            price[i] = lower * (upper / lower) ^ (i / N)
            Maintains constant percentage spacing

        Arithmetic grid (等差):
            price[i] = lower + i * (upper - lower) / N
            Maintains constant absolute spacing
        """
        lower = self.config.lower_price
        upper = self.config.upper_price
        N = self.config.grid_count

        if self.config.mode == "geometric":
            # Geometric spacing (等比)
            ratio = (upper / lower) ** (1.0 / N)
            prices = [lower * (ratio ** i) for i in range(N + 1)]
        else:
            # Arithmetic spacing (等差)
            step = (upper - lower) / N
            prices = [lower + i * step for i in range(N + 1)]

        return prices

    def calculate_grid_allocation(self) -> List[float]:
        """
        Calculate investment allocation per grid level.

        Returns
        -------
        List[float]
            Investment amount (USD) for each grid level

        Notes
        -----
        - "equal" mode: Equal USD per grid
        - "neutral" mode: Adjust for geometric grids to maintain equal BTC amounts
        """
        total = self.config.total_investment
        num_grids = len(self.grid_prices)

        if self.config.investment_mode == "equal":
            # Equal USD per grid
            return [total / num_grids] * num_grids
        else:
            # Neutral mode: maintain equal position sizes for geometric grids
            # For arithmetic grids, this is equivalent to equal mode
            if self.config.mode == "geometric":
                # Weight by 1/price to maintain equal BTC amounts
                weights = [1.0 / p for p in self.grid_prices]
                total_weight = sum(weights)
                return [total * (w / total_weight) for w in weights]
            else:
                return [total / num_grids] * num_grids

    def setup_grid(self, current_price: float) -> None:
        """
        Initialize grid and place initial orders.

        This method:
        1. Generates grid prices
        2. Finds current price position in grid
        3. Places buy orders below current price
        4. Places sell orders above current price
        5. Optionally establishes initial position

        Parameters
        ----------
        current_price : float
            Current market price

        Raises
        ------
        ValueError
            If current_price is outside grid range
        """
        if current_price < self.config.lower_price:
            raise ValueError(
                f"current_price ({current_price}) is below grid lower_price ({self.config.lower_price})"
            )
        if current_price > self.config.upper_price:
            raise ValueError(
                f"current_price ({current_price}) is above grid upper_price ({self.config.upper_price})"
            )

        # Generate grid prices
        self.grid_prices = self.generate_grid_prices()
        allocations = self.calculate_grid_allocation()

        self._log("\n" + "=" * 80)
        self._log("Neutral Grid Setup")
        self._log("=" * 80)
        self._log(f"Mode: {self.config.mode}")
        self._log(f"Range: ${self.config.lower_price:,.0f} - ${self.config.upper_price:,.0f}")
        self._log(f"Grid Count: {self.config.grid_count} ({len(self.grid_prices)} price points)")
        self._log(f"Current Price: ${current_price:,.2f}")
        self._log(f"Total Investment: ${self.config.total_investment:,.2f}")
        self._log("")

        # Find current grid position
        current_grid_index = self._find_grid_index(current_price)
        self._log(f"Current price is at grid index {current_grid_index} (${self.grid_prices[current_grid_index]:,.2f})")
        self._log("")

        # Calculate order sizes
        order_sizes = []
        for i, (price, allocation) in enumerate(zip(self.grid_prices, allocations)):
            # Size in BTC = USD allocation / price
            size_btc = allocation / price
            order_sizes.append(size_btc)

        # Place buy orders below current price
        buy_count = 0
        for i in range(current_grid_index):
            price = self.grid_prices[i]
            size = order_sizes[i]

            # Check minimum order size
            if size * price < self.config.min_order_size_usd:
                self._log(f"[WARNING] Buy order at grid {i} (${price:,.2f}) below min size, skipping")
                continue

            order = GridOrder(
                grid_index=i,
                direction="buy",
                price=price,
                size=size,
            )
            self.pending_orders.append(order)
            buy_count += 1

        # Place sell orders above current price
        sell_count = 0
        for i in range(current_grid_index + 1, len(self.grid_prices)):
            price = self.grid_prices[i]
            size = order_sizes[i]

            # Check minimum order size
            if size * price < self.config.min_order_size_usd:
                self._log(f"[WARNING] Sell order at grid {i} (${price:,.2f}) below min size, skipping")
                continue

            order = GridOrder(
                grid_index=i,
                direction="sell",
                price=price,
                size=size,
            )
            self.pending_orders.append(order)
            sell_count += 1

        # Establish initial position (if configured)
        if self.config.initial_position_pct > 0:
            self._establish_initial_position(
                current_grid_index=current_grid_index,
                current_price=current_price,
                order_sizes=order_sizes,
            )

        self._log(f"Placed {buy_count} buy orders below current price")
        self._log(f"Placed {sell_count} sell orders above current price")
        self._log(f"Total pending orders: {len(self.pending_orders)}")
        self._log("=" * 80 + "\n")

        self.grid_initialized = True

    def _find_grid_index(self, price: float) -> int:
        """
        Find the grid index for a given price.

        Returns the index of the grid level closest to (but not exceeding) the price.

        Parameters
        ----------
        price : float
            Price to locate

        Returns
        -------
        int
            Grid index
        """
        for i in range(len(self.grid_prices) - 1, -1, -1):
            if price >= self.grid_prices[i]:
                return i
        return 0

    def _establish_initial_position(
        self,
        current_grid_index: int,
        current_price: float,
        order_sizes: List[float],
    ) -> None:
        """
        Establish initial position at current price.

        Standard grid behavior: buy some coins at current price to have inventory
        for selling when price rises.

        Parameters
        ----------
        current_grid_index : int
            Current grid index
        current_price : float
            Current market price
        order_sizes : List[float]
            Pre-calculated order sizes per grid
        """
        # Calculate how many grids below current price to fill
        grids_below = current_grid_index
        grids_to_fill = int(grids_below * self.config.initial_position_pct)

        if grids_to_fill == 0:
            self._log("No initial position (initial_position_pct too small or at grid boundary)")
            return

        self._log(f"Establishing initial position: filling {grids_to_fill} grids below current price")

        total_cost = 0.0
        total_btc = 0.0

        for i in range(current_grid_index - grids_to_fill, current_grid_index):
            price = self.grid_prices[i]
            size = order_sizes[i]

            # Add position
            position = GridPosition(
                grid_index=i,
                direction="buy",
                entry_price=price,
                size=size,
                entry_time=datetime.now(),
                paired_grid_index=i + 1,  # Will sell at next grid level
            )
            self.positions.append(position)

            total_cost += price * size
            total_btc += size

            # Place corresponding sell order at next grid level
            # IMPORTANT: Only place sell order if price is above current price
            if i + 1 < len(self.grid_prices):
                sell_price = self.grid_prices[i + 1]
                # Only add sell order if it's above current price
                if sell_price > current_price:
                    sell_order = GridOrder(
                        grid_index=i + 1,
                        direction="sell",
                        price=sell_price,
                        size=size,
                    )
                    # Check if sell order already exists
                    if not any(o.grid_index == i + 1 and o.direction == "sell" for o in self.pending_orders):
                        self.pending_orders.append(sell_order)

        avg_price = total_cost / total_btc if total_btc > 0 else 0
        self._log(f"Initial position: {total_btc:.6f} BTC @ avg ${avg_price:,.2f} (total ${total_cost:,.2f})")

    # ========================================================================
    # Order Triggering and Execution
    # ========================================================================

    def check_order_triggers(
        self,
        bar_high: float,
        bar_low: float,
        bar_index: Optional[int] = None,
    ) -> Optional[GridOrder]:
        """
        Check if any pending order is triggered by price movement.

        Limit order fill logic:
        - Buy limit fills if bar_low <= limit_price
        - Sell limit fills if bar_high >= limit_price

        Parameters
        ----------
        bar_high : float
            Bar high price
        bar_low : float
            Bar low price
        bar_index : Optional[int]
            Current bar index (to prevent duplicate triggers)

        Returns
        -------
        Optional[GridOrder]
            Triggered order, or None
        """
        if not self.pending_orders:
            return None

        for order in self.pending_orders:
            # Skip already triggered orders
            if order.triggered:
                continue

            # Check trigger condition
            triggered = False
            if order.direction == "buy":
                triggered = bar_low <= order.price
            else:  # sell
                triggered = bar_high >= order.price

            if triggered:
                # Mark as triggered
                order.triggered = True
                return order

        return None

    def on_order_filled(
        self,
        filled_order: GridOrder,
        fill_price: Optional[float] = None,
        fill_time: Optional[datetime] = None,
    ) -> None:
        """
        Handle order fill event.

        This is the core grid re-entry logic:
        1. Record position (if buy) or close position (if sell)
        2. Place opposite order at adjacent grid level (pairing)
        3. Re-place same order at current grid level (re-entry)

        Parameters
        ----------
        filled_order : GridOrder
            The order that was filled
        fill_price : Optional[float]
            Actual fill price (defaults to order.price)
        fill_time : Optional[datetime]
            Fill timestamp
        """
        if fill_price is None:
            fill_price = filled_order.price
        if fill_time is None:
            fill_time = datetime.now()

        direction = filled_order.direction
        grid_index = filled_order.grid_index
        size = filled_order.size

        # Calculate fees
        fee = fill_price * size * self.config.maker_fee
        self.total_fees += fee
        self.total_trades += 1

        # CRITICAL: Remove filled order BEFORE handling fill
        # This ensures re-entry logic can correctly check for existing orders
        self.pending_orders = [o for o in self.pending_orders if o != filled_order]

        if direction == "buy":
            self._handle_buy_fill(filled_order, fill_price, fill_time, fee)
        else:
            self._handle_sell_fill(filled_order, fill_price, fill_time, fee)

        # Reset triggered flags
        for order in self.pending_orders:
            order.triggered = False

    def _handle_buy_fill(
        self,
        order: GridOrder,
        fill_price: float,
        fill_time: datetime,
        fee: float,
    ) -> None:
        """
        Handle buy order fill.

        Logic:
        1. Add position (we bought coins)
        2. Place sell order at next grid level (grid_index + 1)
        3. Re-place buy order at current level (re-entry)
        """
        grid_index = order.grid_index
        size = order.size

        # 1. Add position
        position = GridPosition(
            grid_index=grid_index,
            direction="buy",
            entry_price=fill_price,
            size=size,
            entry_time=fill_time,
            paired_grid_index=grid_index + 1,  # Will sell at next grid
        )
        self.positions.append(position)
        self.total_buy_volume += size

        self._log(f"[BUY FILLED] Grid {grid_index} @ ${fill_price:,.2f}, size={size:.6f} BTC, fee=${fee:.2f}")

        # 2. Place sell order at next grid level (if exists)
        if grid_index + 1 < len(self.grid_prices):
            sell_price = self.grid_prices[grid_index + 1]
            sell_order = GridOrder(
                grid_index=grid_index + 1,
                direction="sell",
                price=sell_price,
                size=size,
                placed_time=fill_time,
            )

            # Check if sell order already exists
            existing_sell = next(
                (o for o in self.pending_orders if o.grid_index == grid_index + 1 and o.direction == "sell"),
                None
            )
            if existing_sell:
                # Order already exists - don't duplicate
                # Standard grid: each level has fixed size, no accumulation
                self._log(f"  -> Sell order already exists at grid {grid_index + 1} (size={existing_sell.size:.6f} BTC)")
            else:
                self.pending_orders.append(sell_order)
                self._log(f"  -> Placed SELL order at grid {grid_index + 1} @ ${sell_price:,.2f}")

        # 3. Re-place buy order at current level (re-entry)
        # IMPORTANT: Check if buy order already exists at this grid
        # This prevents duplicate orders in same bar
        existing_buy_at_same_grid = next(
            (o for o in self.pending_orders if o.grid_index == grid_index and o.direction == "buy"),
            None
        )
        if not existing_buy_at_same_grid:
            buy_order = GridOrder(
                grid_index=grid_index,
                direction="buy",
                price=order.price,
                size=size,
                placed_time=fill_time,
            )
            self.pending_orders.append(buy_order)
            self._log(f"  -> Re-placed BUY order at grid {grid_index} @ ${order.price:,.2f} (re-entry)")
        else:
            self._log(f"  -> Buy order already exists at grid {grid_index}, skip re-entry")

    def _handle_sell_fill(
        self,
        order: GridOrder,
        fill_price: float,
        fill_time: datetime,
        fee: float,
    ) -> None:
        """
        Handle sell order fill.

        Logic:
        1. Close position (we sold coins)
        2. Calculate realized PnL
        3. Place buy order at previous grid level (grid_index - 1)
        4. Re-place sell order at current level (re-entry)
        """
        grid_index = order.grid_index
        size = order.size

        # 1. Close position (FIFO matching)
        matched_position = self._match_position_for_sell(grid_index, size)

        if matched_position:
            # Calculate PnL
            buy_price = matched_position.entry_price
            sell_price = fill_price
            gross_pnl = (sell_price - buy_price) * size
            net_pnl = gross_pnl - fee - (buy_price * size * self.config.maker_fee)  # Buy fee
            self.total_pnl += net_pnl

            pnl_pct = (sell_price - buy_price) / buy_price * 100

            self._log(
                f"[SELL FILLED] Grid {grid_index} @ ${fill_price:,.2f}, size={size:.6f} BTC, "
                f"PnL=${net_pnl:.2f} ({pnl_pct:+.2f}%), fee=${fee:.2f}"
            )
        else:
            # No matching position (selling from initial position or orphaned sell)
            self._log(
                f"[SELL FILLED] Grid {grid_index} @ ${fill_price:,.2f}, size={size:.6f} BTC "
                f"(no matching buy position)"
            )

        self.total_sell_volume += size

        # 2. Place buy order at previous grid level (if exists)
        if grid_index - 1 >= 0:
            buy_price = self.grid_prices[grid_index - 1]
            buy_order = GridOrder(
                grid_index=grid_index - 1,
                direction="buy",
                price=buy_price,
                size=size,
                placed_time=fill_time,
            )

            # Check if buy order already exists
            existing_buy = next(
                (o for o in self.pending_orders if o.grid_index == grid_index - 1 and o.direction == "buy"),
                None
            )
            if existing_buy:
                # Order already exists - don't duplicate
                # Standard grid: each level has fixed size, no accumulation
                self._log(f"  -> Buy order already exists at grid {grid_index - 1} (size={existing_buy.size:.6f} BTC)")
            else:
                self.pending_orders.append(buy_order)
                self._log(f"  -> Placed BUY order at grid {grid_index - 1} @ ${buy_price:,.2f}")

        # 3. Re-place sell order at current level (re-entry)
        # IMPORTANT: Check if sell order already exists at this grid
        # This prevents duplicate orders in same bar
        existing_sell_at_same_grid = next(
            (o for o in self.pending_orders if o.grid_index == grid_index and o.direction == "sell"),
            None
        )
        if not existing_sell_at_same_grid:
            sell_order = GridOrder(
                grid_index=grid_index,
                direction="sell",
                price=order.price,
                size=size,
                placed_time=fill_time,
            )
            self.pending_orders.append(sell_order)
            self._log(f"  -> Re-placed SELL order at grid {grid_index} @ ${order.price:,.2f} (re-entry)")
        else:
            self._log(f"  -> Sell order already exists at grid {grid_index}, skip re-entry")

    def _match_position_for_sell(
        self,
        sell_grid_index: int,
        sell_size: float,
    ) -> Optional[GridPosition]:
        """
        Match a sell order against existing positions (FIFO).

        Parameters
        ----------
        sell_grid_index : int
            Grid index of sell order
        sell_size : float
            Size being sold

        Returns
        -------
        Optional[GridPosition]
            Matched position (or None if no match)
        """
        # Find positions that target this sell grid
        for i, pos in enumerate(self.positions):
            if pos.paired_grid_index == sell_grid_index and pos.direction == "buy":
                # Match found
                matched_size = min(sell_size, pos.size)

                # Update or remove position
                pos.size -= matched_size
                if pos.size < 1e-8:  # Position fully closed
                    self.positions.pop(i)

                return pos

        # No match found (selling from initial position or orphaned sell)
        return None

    # ========================================================================
    # Status and Statistics
    # ========================================================================

    def get_statistics(self) -> Dict:
        """
        Get grid trading statistics.

        Returns
        -------
        Dict
            Statistics including PnL, positions, orders, etc.
        """
        total_position_value = sum(p.size * p.entry_price for p in self.positions)
        total_position_btc = sum(p.size for p in self.positions)

        return {
            "total_pnl": self.total_pnl,
            "total_fees": self.total_fees,
            "net_pnl": self.total_pnl - self.total_fees,
            "total_trades": self.total_trades,
            "total_buy_volume": self.total_buy_volume,
            "total_sell_volume": self.total_sell_volume,
            "pending_orders_count": len(self.pending_orders),
            "positions_count": len(self.positions),
            "total_position_value_usd": total_position_value,
            "total_position_btc": total_position_btc,
            "grid_count": len(self.grid_prices),
            "grid_mode": self.config.mode,
        }

    def get_current_state(self) -> Dict:
        """
        Get current grid state (for debugging/monitoring).

        Returns
        -------
        Dict
            Current state including orders and positions
        """
        return {
            "grid_prices": self.grid_prices,
            "pending_orders": [
                {
                    "grid_index": o.grid_index,
                    "direction": o.direction,
                    "price": o.price,
                    "size": o.size,
                }
                for o in self.pending_orders
            ],
            "positions": [
                {
                    "grid_index": p.grid_index,
                    "direction": p.direction,
                    "entry_price": p.entry_price,
                    "size": p.size,
                }
                for p in self.positions
            ],
        }

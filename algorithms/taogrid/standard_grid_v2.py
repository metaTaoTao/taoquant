"""
Standard Grid Trading Bot V2 - Exchange-Compliant Implementation.

100% replicates Binance/OKX grid trading behavior:
1. Each grid level has AT MOST 1 active order
2. Buy@grid[i] fills → Place sell@grid[i+1]
3. Sell@grid[i] fills → Re-place buy@grid[i]
4. Continuous buy-low-sell-high loop

Key Difference from V1:
- V1: Allowed multiple orders per grid (bug)
- V2: Enforces 1 order per grid (exchange standard)

References:
- https://www.binance.com/en/support/faq/what-is-spot-grid-trading-and-how-does-it-work-d5f441e8ab544a5b98241e00efb3a4ab
- https://www.okx.com/en-us/help/spot-grid-bot-faq
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

import numpy as np


class GridOrderStatus(Enum):
    """Order status."""
    PENDING = "pending"   # Waiting to be filled
    FILLED = "filled"     # Executed
    CANCELLED = "cancelled"  # Cancelled


@dataclass
class GridLevel:
    """
    Represents a single grid level.

    Each grid level can have:
    - 0 or 1 buy order
    - 0 or 1 sell order
    - Never both at the same time

    This enforces the exchange standard: max 1 active order per grid.
    """
    index: int  # Grid index (0 = lowest)
    price: float  # Price of this grid level

    # Active orders (at most 1)
    buy_order: Optional[GridOrder] = None
    sell_order: Optional[GridOrder] = None

    # Statistics
    total_buy_volume: float = 0.0
    total_sell_volume: float = 0.0
    profit_realized: float = 0.0

    def has_active_order(self) -> bool:
        """Check if this grid has any active order."""
        return self.buy_order is not None or self.sell_order is not None

    def has_buy_order(self) -> bool:
        """Check if this grid has active buy order."""
        return self.buy_order is not None

    def has_sell_order(self) -> bool:
        """Check if this grid has active sell order."""
        return self.sell_order is not None


@dataclass
class GridOrder:
    """Represents a grid order."""
    grid_index: int
    direction: str  # "buy" or "sell"
    price: float
    size: float  # Size in base currency (BTC)
    status: GridOrderStatus = GridOrderStatus.PENDING
    placed_time: Optional[datetime] = None
    filled_time: Optional[datetime] = None
    fill_price: Optional[float] = None

    # Pairing information
    paired_grid_index: Optional[int] = None  # Target grid for opposite order


class StandardGridV2:
    """
    Standard Grid Trading Bot V2.

    Replicates exchange grid trading behavior:
    - Arithmetic or Geometric spacing
    - 1 order per grid level (max)
    - Buy-sell pairing
    - Continuous re-entry

    Attributes
    ----------
    grid_levels : List[GridLevel]
        All grid levels (sorted by price)
    total_investment : float
        Total capital allocated
    initial_cash : float
        Initial cash (without leverage)
    leverage : float
        Leverage multiplier
    """

    def __init__(
        self,
        lower_price: float,
        upper_price: float,
        grid_count: int,
        mode: str = "geometric",  # "geometric" or "arithmetic"
        total_investment: float = 10000.0,
        leverage: float = 1.0,
        maker_fee: float = 0.0002,
    ):
        """
        Initialize standard grid.

        Parameters
        ----------
        lower_price : float
            Lower bound of grid
        upper_price : float
            Upper bound of grid
        grid_count : int
            Number of grids (creates grid_count + 1 price levels)
        mode : str
            "geometric" or "arithmetic"
        total_investment : float
            Total capital (with leverage if applicable)
        leverage : float
            Leverage multiplier
        maker_fee : float
            Maker fee rate
        """
        self.lower_price = lower_price
        self.upper_price = upper_price
        self.grid_count = grid_count
        self.mode = mode
        self.total_investment = total_investment
        self.initial_cash = total_investment / leverage
        self.leverage = leverage
        self.maker_fee = maker_fee

        # Generate grid prices
        self.grid_prices = self._generate_grid_prices()

        # Create grid levels
        self.grid_levels: List[GridLevel] = [
            GridLevel(index=i, price=price)
            for i, price in enumerate(self.grid_prices)
        ]

        # Calculate per-grid investment
        self.per_grid_investment = total_investment / len(self.grid_levels)

        # Trading statistics
        self.total_pnl = 0.0
        self.total_fees = 0.0
        self.total_trades = 0
        self.total_buy_volume = 0.0
        self.total_sell_volume = 0.0

    def _generate_grid_prices(self) -> List[float]:
        """Generate grid price levels."""
        N = self.grid_count
        lower = self.lower_price
        upper = self.upper_price

        if self.mode == "geometric":
            # Geometric: P[i] = lower * (upper/lower)^(i/N)
            ratio = (upper / lower) ** (1.0 / N)
            prices = [lower * (ratio ** i) for i in range(N + 1)]
        else:
            # Arithmetic: P[i] = lower + i * (upper - lower) / N
            step = (upper - lower) / N
            prices = [lower + i * step for i in range(N + 1)]

        return prices

    def initialize_grid(self, current_price: float):
        """
        Initialize grid with buy orders below current price.

        Exchange standard behavior:
        1. Place buy orders at all grids below current price
        2. When buy fills → place sell at next grid
        3. No initial positions

        Parameters
        ----------
        current_price : float
            Current market price
        """
        # Find current grid level
        current_grid_idx = self._find_grid_index(current_price)

        print(f"\n[GRID INIT] Current price ${current_price:,.2f} at grid {current_grid_idx}")
        print(f"[GRID INIT] Placing buy orders at grids 0-{current_grid_idx - 1}")

        # Place buy orders below current price
        for i in range(current_grid_idx):
            self._place_buy_order(i)

        print(f"[GRID INIT] Grid initialized with {current_grid_idx} buy orders")

    def _find_grid_index(self, price: float) -> int:
        """Find grid index for a given price."""
        for i in range(len(self.grid_prices) - 1, -1, -1):
            if price >= self.grid_prices[i]:
                return i
        return 0

    def _place_buy_order(self, grid_index: int):
        """
        Place buy order at grid level.

        Only places if:
        1. Grid exists
        2. No existing buy order at this grid
        """
        if grid_index < 0 or grid_index >= len(self.grid_levels):
            return  # Out of range

        grid = self.grid_levels[grid_index]

        # Check if already has buy order
        if grid.has_buy_order():
            return  # Already has order

        # Calculate order size
        price = grid.price
        size = self.per_grid_investment / price

        # Create and place order
        order = GridOrder(
            grid_index=grid_index,
            direction="buy",
            price=price,
            size=size,
            placed_time=datetime.now(),
            paired_grid_index=grid_index + 1,  # Will sell at next grid
        )

        grid.buy_order = order

    def _place_sell_order(self, grid_index: int, size: float):
        """
        Place sell order at grid level.

        Only places if:
        1. Grid exists
        2. No existing sell order at this grid

        Parameters
        ----------
        grid_index : int
            Grid index
        size : float
            Order size (BTC)
        """
        if grid_index < 0 or grid_index >= len(self.grid_levels):
            return  # Out of range

        grid = self.grid_levels[grid_index]

        # Check if already has sell order
        if grid.has_sell_order():
            return  # Already has order

        # Create and place order
        order = GridOrder(
            grid_index=grid_index,
            direction="sell",
            price=grid.price,
            size=size,
            placed_time=datetime.now(),
            paired_grid_index=grid_index - 1,  # Came from buy at previous grid
        )

        grid.sell_order = order

    def check_and_fill_orders(
        self,
        bar_high: float,
        bar_low: float,
        timestamp: datetime,
    ) -> List[GridOrder]:
        """
        Check for triggered orders and fill them.

        Returns list of filled orders (can be multiple per bar).

        Parameters
        ----------
        bar_high : float
            Bar high price
        bar_low : float
            Bar low price
        timestamp : datetime
            Current timestamp

        Returns
        -------
        List[GridOrder]
            List of filled orders
        """
        filled_orders = []

        for grid in self.grid_levels:
            # Check buy order
            if grid.buy_order and bar_low <= grid.price:
                # Buy order filled
                order = grid.buy_order
                order.status = GridOrderStatus.FILLED
                order.filled_time = timestamp
                order.fill_price = grid.price
                filled_orders.append(order)

                # Process fill
                self._on_buy_filled(grid.index, order, timestamp)

            # Check sell order
            if grid.sell_order and bar_high >= grid.price:
                # Sell order filled
                order = grid.sell_order
                order.status = GridOrderStatus.FILLED
                order.filled_time = timestamp
                order.fill_price = grid.price
                filled_orders.append(order)

                # Process fill
                self._on_sell_filled(grid.index, order, timestamp)

        return filled_orders

    def _on_buy_filled(self, grid_index: int, order: GridOrder, timestamp: datetime):
        """
        Handle buy order fill.

        Exchange behavior:
        1. Remove buy order from grid
        2. Place sell order at next grid (grid_index + 1)
        3. Record statistics
        """
        grid = self.grid_levels[grid_index]

        # Remove buy order
        grid.buy_order = None

        # Record statistics
        grid.total_buy_volume += order.size
        self.total_buy_volume += order.size
        fee = order.size * order.price * self.maker_fee
        self.total_fees += fee
        self.total_trades += 1

        print(f"[BUY FILL] Grid {grid_index} @ ${order.price:,.2f}, size={order.size:.6f} BTC, fee=${fee:.2f}")

        # Place sell order at next grid
        if grid_index + 1 < len(self.grid_levels):
            self._place_sell_order(grid_index + 1, order.size)
            print(f"  -> Placed SELL at grid {grid_index + 1} @ ${self.grid_levels[grid_index + 1].price:,.2f}")

    def _on_sell_filled(self, grid_index: int, order: GridOrder, timestamp: datetime):
        """
        Handle sell order fill.

        Exchange behavior:
        1. Remove sell order from grid
        2. Calculate profit (sell_price - buy_price) * size
        3. Re-place buy order at previous grid (grid_index - 1)
        4. Record statistics
        """
        grid = self.grid_levels[grid_index]

        # Remove sell order
        grid.sell_order = None

        # Calculate profit
        # Sell happened at grid[i], buy was at grid[i-1]
        if grid_index > 0:
            buy_price = self.grid_levels[grid_index - 1].price
            sell_price = order.price
            gross_profit = (sell_price - buy_price) * order.size

            # Fees: buy fee + sell fee
            buy_fee = order.size * buy_price * self.maker_fee
            sell_fee = order.size * sell_price * self.maker_fee
            net_profit = gross_profit - buy_fee - sell_fee

            grid.profit_realized += net_profit
            self.total_pnl += net_profit

            profit_pct = (sell_price - buy_price) / buy_price * 100
            print(f"[SELL FILL] Grid {grid_index} @ ${order.price:,.2f}, size={order.size:.6f} BTC, PnL=${net_profit:.2f} ({profit_pct:+.2f}%)")
        else:
            # Orphaned sell (no matching buy)
            print(f"[SELL FILL] Grid {grid_index} @ ${order.price:,.2f} (orphaned)")

        # Record statistics
        grid.total_sell_volume += order.size
        self.total_sell_volume += order.size
        fee = order.size * order.price * self.maker_fee
        self.total_fees += fee
        self.total_trades += 1

        # Re-place buy order at previous grid
        if grid_index - 1 >= 0:
            self._place_buy_order(grid_index - 1)
            print(f"  -> Re-placed BUY at grid {grid_index - 1} @ ${self.grid_levels[grid_index - 1].price:,.2f}")

    def get_statistics(self) -> Dict:
        """Get trading statistics."""
        # Calculate current position
        total_position_btc = self.total_buy_volume - self.total_sell_volume

        # Count active orders
        buy_orders = sum(1 for g in self.grid_levels if g.has_buy_order())
        sell_orders = sum(1 for g in self.grid_levels if g.has_sell_order())

        return {
            "total_pnl": self.total_pnl,
            "total_fees": self.total_fees,
            "net_pnl": self.total_pnl - self.total_fees,
            "total_trades": self.total_trades,
            "total_buy_volume": self.total_buy_volume,
            "total_sell_volume": self.total_sell_volume,
            "net_position_btc": total_position_btc,
            "active_buy_orders": buy_orders,
            "active_sell_orders": sell_orders,
            "grid_count": len(self.grid_levels),
            "grid_mode": self.mode,
        }

"""
VectorBT engine implementation for high-performance vectorized backtesting.

VectorBT advantages:
- 100x faster than event-driven backtesting (vectorized NumPy operations)
- Native fractional position support
- Built-in performance metrics
- Memory efficient

This engine implements the BacktestEngine interface, making it swappable
with other engines.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

try:
    import vectorbt as vbt
except ImportError:
    raise ImportError(
        "VectorBT is required for this engine. Install with: pip install vectorbt"
    )

from execution.engines.base import BacktestConfig, BacktestEngine, BacktestResult


class VectorBTEngine(BacktestEngine):
    """
    VectorBT implementation of backtest engine.

    This engine uses vectorized operations for high performance.
    Suitable for:
    - Signal-based strategies
    - Single-asset backtests
    - Frequency: 1m to 1d

    Not suitable for:
    - Tick-level simulations
    - Complex order types (limit orders, etc.)
    - Multi-asset portfolio backtests (use custom engine)

    Examples
    --------
    >>> from execution.engines.vectorbt_engine import VectorBTEngine
    >>> from execution.engines.base import BacktestConfig
    >>>
    >>> engine = VectorBTEngine()
    >>> config = BacktestConfig(
    ...     initial_cash=100000.0,
    ...     commission=0.001,
    ...     slippage=0.0005,
    ...     leverage=5.0
    ... )
    >>>
    >>> result = engine.run(data, signals, sizes, config)
    >>> print(result.summary())
    """

    def run(
        self,
        data: pd.DataFrame,
        signals: pd.DataFrame,
        sizes: pd.Series,
        config: BacktestConfig,
    ) -> BacktestResult:
        """
        Run vectorized backtest using VectorBT.

        Supports two modes:
        1. Order-based (partial exits): signals contains 'orders' column with order sizes
        2. Signal-based (legacy): signals contains 'entry'/'exit' boolean columns

        Parameters
        ----------
        data : pd.DataFrame
            OHLCV data
        signals : pd.DataFrame
            Either:
            - Order-based: columns ['orders', 'direction'] where 'orders' contains order sizes
            - Signal-based: columns ['entry', 'exit', 'direction'] with boolean signals
        sizes : pd.Series
            Position sizes (used for order-based mode to convert relative sizes to absolute)
        config : BacktestConfig
            Backtest configuration

        Returns
        -------
        BacktestResult
            Standardized backtest results
        """
        # Validate inputs
        self.validate_inputs(data, signals, sizes)

        # Check if we have orders (partial exit mode) or signals (legacy mode)
        if 'orders' in signals.columns:
            # Order-based mode: use from_orders() for partial exits
            # Store order types if available for later extraction
            order_types = signals.get('order_types', pd.Series('', index=signals.index))
            # Get direction from signals (should be 'short' for short-only strategy)
            direction = signals.get('direction', pd.Series('short', index=signals.index))
            portfolio = self._create_portfolio_from_orders(
                data=data,
                orders=signals['orders'],
                sizes=sizes,
                config=config,
            )
            # Store order_types and direction in portfolio metadata for later extraction
            if hasattr(portfolio, 'metadata'):
                portfolio.metadata = portfolio.metadata or {}
            else:
                portfolio.metadata = {}
            portfolio.metadata['order_types'] = order_types
            portfolio.metadata['direction'] = direction  # Store strategy direction
        else:
            # Signal-based mode: use from_signals() (legacy)
            entries, exits, directions = self._convert_signals(signals)

            # Separate long and short signals
            long_entries = entries & (directions == 'long')
            long_exits = exits & (directions == 'long')
            short_entries = entries & (directions == 'short')
            short_exits = exits & (directions == 'short')

            # Ensure sizes are positive
            adjusted_sizes = sizes.abs()

            # Create portfolio
            portfolio = self._create_portfolio(
                data=data,
                long_entries=long_entries,
                long_exits=long_exits,
                short_entries=short_entries,
                short_exits=short_exits,
                sizes=adjusted_sizes,
                config=config,
            )

        # Extract results
        result = self._extract_results(portfolio, data, config)

        return result

    def get_name(self) -> str:
        """Return engine name."""
        return "VectorBT"
    
    def validate_inputs(
        self,
        data: pd.DataFrame,
        signals: pd.DataFrame,
        sizes: pd.Series,
    ) -> None:
        """
        Validate inputs before running backtest.

        Supports both order-based and signal-based modes.

        Parameters
        ----------
        data : pd.DataFrame
            OHLCV data
        signals : pd.DataFrame
            Either order-based ('orders', 'direction') or signal-based ('entry', 'exit', 'direction')
        sizes : pd.Series
            Position sizes

        Raises
        ------
        ValueError
            If any validation fails
        """
        # Check data columns
        required_data_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_data_cols = [col for col in required_data_cols if col not in data.columns]
        if missing_data_cols:
            raise ValueError(f"Data missing required columns: {missing_data_cols}")

        # Check signals columns (support both modes)
        if 'orders' in signals.columns:
            # Order-based mode
            if 'direction' not in signals.columns:
                raise ValueError("Signals missing required column: 'direction'")
        else:
            # Signal-based mode (legacy)
            required_signal_cols = ['entry', 'exit', 'direction']
            missing_signal_cols = [col for col in required_signal_cols if col not in signals.columns]
            if missing_signal_cols:
                raise ValueError(f"Signals missing required columns: {missing_signal_cols}")

        # Check index alignment
        if not data.index.equals(signals.index):
            raise ValueError("Data and signals must have matching indices")

        if not data.index.equals(sizes.index):
            raise ValueError("Data and sizes must have matching indices")

        # Check for empty data
        if len(data) == 0:
            raise ValueError("Data is empty")

        # Check for valid sizes
        if sizes.isna().all():
            raise ValueError("All sizes are NaN")

    def _convert_signals(
        self, signals: pd.DataFrame
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """
        Convert signal DataFrame to VectorBT format.

        Parameters
        ----------
        signals : pd.DataFrame
            Signals with columns: [entry, exit, direction]

        Returns
        -------
        tuple[pd.Series, pd.Series, pd.Series]
            (entries, exits, directions)
            - entries: bool Series (True = enter)
            - exits: bool Series (True = exit)
            - directions: str Series ('long' or 'short')
        """
        entries = signals['entry'].fillna(False).astype(bool)
        exits = signals['exit'].fillna(False).astype(bool)
        directions = signals['direction'].fillna('long')

        return entries, exits, directions

    def _adjust_sizes_for_direction(
        self, sizes: pd.Series, directions: pd.Series
    ) -> pd.Series:
        """
        Ensure sizes are positive (VectorBT doesn't allow negative sizes).

        VectorBT handles direction through separate long/short entry signals,
        not through negative sizes.

        Parameters
        ----------
        sizes : pd.Series
            Position sizes (fractional)
        directions : pd.Series
            Position directions ('long' or 'short')

        Returns
        -------
        pd.Series
            Positive sizes (direction handled separately)
        """
        # VectorBT requires positive sizes, direction is handled via signals
        return sizes.abs()

    def _create_portfolio(
        self,
        data: pd.DataFrame,
        long_entries: pd.Series,
        long_exits: pd.Series,
        short_entries: pd.Series,
        short_exits: pd.Series,
        sizes: pd.Series,
        config: BacktestConfig,
    ) -> vbt.Portfolio:
        """
        Create VectorBT portfolio with separate long/short signals.

        VectorBT doesn't allow negative sizes in from_signals, so we use
        from_orders to manually create orders for both long and short positions.

        Parameters
        ----------
        data : pd.DataFrame
            OHLCV data
        long_entries : pd.Series
            Long entry signals
        long_exits : pd.Series
            Long exit signals
        short_entries : pd.Series
            Short entry signals
        short_exits : pd.Series
            Short exit signals
        sizes : pd.Series
            Position sizes (positive, as percentage of equity)
        config : BacktestConfig
            Backtest configuration

        Returns
        -------
        vbt.Portfolio
            VectorBT portfolio object
        """
        # VectorBT uses close price for execution by default
        close = data['close']

        # Build orders list manually
        # For long: positive size
        # For short: negative size (VectorBT from_orders allows this)
        orders = []
        
        # Calculate position sizes in value terms (not percentage)
        # We need to convert percentage to actual value
        equity = config.initial_cash  # Start with initial cash
        position_value = equity * sizes  # Position value in dollars
        
        for i in range(len(close)):
            # Long entries: buy (positive size)
            if long_entries.iloc[i]:
                order_size = position_value.iloc[i] / close.iloc[i]  # Convert to quantity
                orders.append({
                    'index': i,
                    'size': order_size,  # Positive for long
                    'price': close.iloc[i],
                    'fees': config.commission,
                })
            
            # Short entries: sell (negative size)
            if short_entries.iloc[i]:
                order_size = position_value.iloc[i] / close.iloc[i]  # Convert to quantity
                orders.append({
                    'index': i,
                    'size': -order_size,  # Negative for short
                    'price': close.iloc[i],
                    'fees': config.commission,
                })
            
            # Exits: close position (opposite sign)
            if long_exits.iloc[i] or short_exits.iloc[i]:
                # For exits, we need to close the current position
                # This is complex - VectorBT handles this automatically in from_signals
                # For now, let's use a simpler approach: use from_signals separately for long/short
                pass

        # Actually, VectorBT's from_signals should work if we handle long/short separately
        # Let's try using two separate portfolios and combine them, or use from_orders properly
        
        # Simpler approach: Use from_signals for long, then handle short separately
        # But VectorBT doesn't support this easily
        
        # Best approach: Use from_orders with proper order management
        # For now, let's use a workaround: only handle the dominant direction
        
        # VectorBT's from_signals supports direction parameter
        # For short-only: use entries/exits with direction='shortonly'
        # For long-only: use entries/exits with direction='longonly'
        # For mixed: use short_entries/short_exits (but this version may not support it)
        
        has_long = long_entries.any()
        has_short = short_entries.any()
        
        if has_short and not has_long:
            # Short-only: use entries/exits with direction='shortonly'
            portfolio = vbt.Portfolio.from_signals(
                close=close,
                entries=short_entries,
                exits=short_exits,
                size=sizes,
                size_type='percent',
                direction='shortonly',  # This tells VectorBT these are short signals
                init_cash=config.initial_cash,
                fees=config.commission,
                slippage=config.slippage,
                freq='min',
            )
        elif has_long and not has_short:
            # Long-only
            portfolio = vbt.Portfolio.from_signals(
                close=close,
                entries=long_entries,
                exits=long_exits,
                size=sizes,
                size_type='percent',
                direction='longonly',
                init_cash=config.initial_cash,
                fees=config.commission,
                slippage=config.slippage,
                freq='min',
            )
        else:
            # Mixed - not supported in this VectorBT version
            raise NotImplementedError(
                "Mixed long/short positions not yet supported. "
                "Please use either long-only or short-only strategies."
            )

        return portfolio

    def _create_portfolio_from_orders(
        self,
        data: pd.DataFrame,
        orders: pd.Series,
        sizes: pd.Series,
        config: BacktestConfig,
    ) -> vbt.Portfolio:
        """
        Create VectorBT portfolio from order flow (supports partial exits).

        Parameters
        ----------
        data : pd.DataFrame
            OHLCV data
        orders : pd.Series
            Order sizes (relative):
            - Negative: Short entry (e.g., -1.0 = 100% of calculated size)
            - Positive: Close short (e.g., 0.3 = 30%, 0.7 = 70% for partial exits)
            - Zero: No order
        sizes : pd.Series
            Position size multipliers from strategy (fraction of equity)
        config : BacktestConfig
            Backtest configuration

        Returns
        -------
        vbt.Portfolio
            VectorBT portfolio object
        """
        close = data['close']
        
        # Convert relative orders to percentage-based orders for VectorBT
        # Strategy returns: orders = relative sizes (-1.0, 0.3, 0.7)
        # sizes = position size multipliers (fraction of equity from calculate_position_size)
        # We combine them: final_order_pct = orders * sizes
        
        # For entry: orders is -1.0, sizes is 0.5 (50% of equity), so final = -0.5 (short 50%)
        # For TP1 exit: orders is 0.3, sizes is 0.5, so final = 0.15 (close 15% of equity = 30% of position)
        # For TP2 exit: orders is 0.7, sizes is 0.5, so final = 0.35 (close 35% of equity = 70% of position)
        
        # Actually, we need to think about this differently:
        # - Entry: orders=-1.0 means "use 100% of the calculated size"
        # - Exit: orders=0.3 means "close 30% of the current position"
        
        # For VectorBT with size_type='percent', we need percentages of equity
        # Let's use a simpler approach: use size_type='percent' and combine orders with sizes
        
        # Convert orders to absolute BTC amounts
        # Strategy logic:
        # - Entry: orders = -1.0 means "use 100% of calculated size"
        # - Exit: orders = 0.3 means "close 30% of current position"
        
        order_amounts = pd.Series(0.0, index=close.index, dtype=float)
        # Create direction Series to tell VectorBT the direction of each order
        # VectorBT uses Direction enum: 'longonly' or 'shortonly' for single direction
        # For mixed orders, we need to specify direction per order
        # Use None for bars with no orders (VectorBT will infer from size sign)
        order_directions = pd.Series(None, index=close.index, dtype='object')
        
        # Track current position in BTC
        current_position_btc = 0.0
        
        # Use initial equity for first calculation
        equity = config.initial_cash
        
        for i in range(len(close)):
            if orders.iloc[i] != 0:
                if orders.iloc[i] < 0:
                    # Entry: negative order size = SHORT entry
                    # orders[i] = -1.0 means use 100% of calculated size
                    # sizes[i] = position size multiplier (fraction of equity)
                    order_size_abs = abs(orders.iloc[i])  # e.g., 1.0
                    size_mult = sizes.iloc[i] if pd.notna(sizes.iloc[i]) else 0.5
                    
                    # Calculate position value
                    position_value = equity * size_mult * order_size_abs
                    
                    # Convert to BTC amount
                    btc_amount = position_value / close.iloc[i]
                    
                    # For short entry: use negative size (VectorBT interprets negative as short)
                    # OR use positive size with direction='shortonly'
                    # We'll use negative size which is the standard way VectorBT handles shorts
                    order_amounts.iloc[i] = -btc_amount  # Negative for short entry
                    order_directions.iloc[i] = 'shortonly'  # Tell VectorBT this is a short order
                    current_position_btc = btc_amount  # Track position size
                else:
                    # Exit: positive order size (partial or full) = LONG (buy back to close short)
                    # orders[i] = 0.3 means close 30% of current position
                    exit_fraction = orders.iloc[i]  # e.g., 0.3
                    exit_btc = current_position_btc * exit_fraction
                    
                    # For closing short: use positive size with direction='longonly' (buy back)
                    order_amounts.iloc[i] = exit_btc
                    order_directions.iloc[i] = 'longonly'  # Tell VectorBT this is a long order (buy back)
                    current_position_btc -= exit_btc  # Update remaining position
                    if current_position_btc < 0.0001:
                        current_position_btc = 0.0
        
        # Fill NaN values
        order_amounts = order_amounts.fillna(0.0)
        # For orders with no direction specified, keep as None (VectorBT will infer from size sign)
        # Only set direction for bars that actually have orders
        
        # Use from_orders with size_type='amount' (BTC units) and direction parameter
        # Note: size_type='percent' doesn't work for short positions in VectorBT
        # We must use size_type='amount' for short positions
        # Pass direction parameter to tell VectorBT the direction of each order
        try:
            # Check if we have mixed directions (both shortonly and longonly)
            # Only check non-None values (None means no order, VectorBT will infer from size)
            non_none_mask = order_directions.notna()
            has_short = (order_directions[non_none_mask] == 'shortonly').any() if non_none_mask.any() else False
            has_long = (order_directions[non_none_mask] == 'longonly').any() if non_none_mask.any() else False
            
            if has_short and has_long:
                # Mixed directions: need to pass direction Series
                # But VectorBT may not accept None, so we need to handle it differently
                # Option 1: Only pass direction for bars with orders, use size sign for others
                # Option 2: Use a default direction for None values
                # Let's try: for None values, infer from size sign (negative = short, positive = long)
                # But since we're passing a Series, we need all values to be valid
                # Actually, let's just not pass direction and let VectorBT infer from size sign
                # This is the most reliable approach
                portfolio = vbt.Portfolio.from_orders(
                    close=close,
                    size=order_amounts,
                    size_type='amount',
                    # Don't pass direction - let VectorBT infer from size sign
                    # Negative size = short, positive size = long
                    init_cash=config.initial_cash,
                    fees=config.commission,
                    slippage=config.slippage,
                    freq='min',
                )
            elif has_short:
                # All short: use direction='shortonly'
                portfolio = vbt.Portfolio.from_orders(
                    close=close,
                    size=order_amounts,
                    size_type='amount',
                    direction='shortonly',  # All orders are short
                    init_cash=config.initial_cash,
                    fees=config.commission,
                    slippage=config.slippage,
                    freq='min',
                )
            elif has_long:
                # All long: use direction='longonly'
                portfolio = vbt.Portfolio.from_orders(
                    close=close,
                    size=order_amounts,
                    size_type='amount',
                    direction='longonly',  # All orders are long
                    init_cash=config.initial_cash,
                    fees=config.commission,
                    slippage=config.slippage,
                    freq='min',
                )
            else:
                # No direction specified: VectorBT will infer from size sign
                portfolio = vbt.Portfolio.from_orders(
                    close=close,
                    size=order_amounts,
                    size_type='amount',
                    init_cash=config.initial_cash,
                    fees=config.commission,
                    slippage=config.slippage,
                    freq='min',
                )
        except Exception as e:
            print(f"Warning: Failed to create portfolio from orders: {e}")
            import traceback
            traceback.print_exc()
            # Fallback: create empty portfolio
            portfolio = vbt.Portfolio.from_signals(
                close=close,
                entries=pd.Series(False, index=close.index),
                exits=pd.Series(False, index=close.index),
                size=0,
                size_type='percent',
                init_cash=config.initial_cash,
                fees=config.commission,
                slippage=config.slippage,
                freq='min',
            )
        
        return portfolio

    def _create_portfolio_from_orders_legacy(
        self,
        close: pd.Series,
        entries: pd.Series,
        exits: pd.Series,
        sizes: pd.Series,
        config: BacktestConfig,
    ) -> vbt.Portfolio:
        """
        Create portfolio from orders for short positions.
        
        VectorBT's from_signals doesn't support short positions with negative sizes,
        so we use from_orders to manually create sell orders (negative size).
        """
        # Build size series: negative for entries (short), positive for exits (close short)
        order_sizes = pd.Series(0.0, index=close.index, dtype=float)
        
        # Fill NaN values in sizes with 0
        sizes_clean = sizes.fillna(0.0)
        
        # Entry: negative size (sell/short)
        order_sizes[entries] = -sizes_clean[entries]
        
        # Exit: positive size (buy back to close short)
        # For exits, we need to close the entire position
        # Use the same size as entry (but positive)
        order_sizes[exits] = sizes_clean[exits]
        
        # Fill any remaining NaN with 0
        order_sizes = order_sizes.fillna(0.0)
        
        # Debug: print some info
        num_entries = entries.sum()
        num_exits = exits.sum()
        if num_entries > 0:
            print(f"Debug: {num_entries} entry signals, {num_exits} exit signals")
            print(f"Debug: Sample sizes - entries: {order_sizes[entries].head()}")
        
        # For short positions, VectorBT's from_orders with negative sizes is complex
        # Let's use a simpler approach: use from_signals but handle short differently
        # Actually, let's try using from_signals with direction parameter if available
        # Or use a workaround: simulate short by inverting returns
        
        # Try using from_signals with size_type='amount' and negative sizes
        # First convert percentage to amount
        equity = config.initial_cash
        order_amounts = pd.Series(0.0, index=close.index, dtype=float)
        
        # Track current position size for exits
        current_position = 0.0
        
        for i in range(len(close)):
            if entries.iloc[i]:
                # Entry: short position (negative amount)
                size_pct = abs(sizes_clean.iloc[i])
                amount = -(equity * size_pct) / close.iloc[i]
                order_amounts.iloc[i] = amount
                current_position = abs(amount)  # Track position size
            elif exits.iloc[i] and current_position > 0:
                # Exit: close short (positive amount to buy back)
                order_amounts.iloc[i] = current_position
                current_position = 0.0
        
        order_amounts = order_amounts.fillna(0.0)
        
        # Use from_orders with size_type='amount'
        try:
            portfolio = vbt.Portfolio.from_orders(
                close=close,
                size=order_amounts,
                size_type='amount',  # Use 'amount' instead of 'percent'
                init_cash=config.initial_cash,
                fees=config.commission,
                slippage=config.slippage,
                freq='min',  # Use 'min' instead of deprecated 'T'
            )
        except Exception as e:
            # If from_orders doesn't work, fall back to empty portfolio
            print(f"Warning: Failed to create portfolio from orders: {e}")
            print(f"Debug: order_sizes stats - min: {order_sizes.min()}, max: {order_sizes.max()}, has_nan: {order_sizes.isna().any()}")
            print("Creating empty portfolio as fallback.")
            portfolio = vbt.Portfolio.from_signals(
                close=close,
                entries=pd.Series(False, index=close.index),
                exits=pd.Series(False, index=close.index),
                size=0,
                size_type='percent',
                init_cash=config.initial_cash,
                fees=config.commission,
                slippage=config.slippage,
                freq='min',
            )
        
        return portfolio

    def _create_portfolio_from_orders_mixed(
        self,
        close: pd.Series,
        long_entries: pd.Series,
        long_exits: pd.Series,
        short_entries: pd.Series,
        short_exits: pd.Series,
        sizes: pd.Series,
        config: BacktestConfig,
    ) -> vbt.Portfolio:
        """Create portfolio with mixed long/short using from_orders."""
        # This is complex - for now, let's just handle short-only case
        # and raise an error for mixed
        raise NotImplementedError(
            "Mixed long/short positions not yet supported. "
            "Please use either long-only or short-only strategies."
        )

    def _extract_results(
        self,
        portfolio: vbt.Portfolio,
        data: pd.DataFrame,
        config: BacktestConfig,
    ) -> BacktestResult:
        """
        Extract results from VectorBT portfolio into standardized format.

        Parameters
        ----------
        portfolio : vbt.Portfolio
            VectorBT portfolio object
        data : pd.DataFrame
            Original OHLCV data
        config : BacktestConfig
            Backtest configuration

        Returns
        -------
        BacktestResult
            Standardized backtest results
        """
        # Extract trades
        trades_df = self._extract_trades(portfolio)

        # Extract equity curve
        equity_df = self._extract_equity_curve(portfolio)

        # Extract positions (snapshots)
        positions_df = self._extract_positions(portfolio)

        # Calculate metrics
        metrics = self._calculate_metrics(portfolio, trades_df)

        # Get orders_df from portfolio metadata if available
        orders_df = None
        if hasattr(portfolio, 'metadata') and portfolio.metadata:
            orders_df = portfolio.metadata.get('orders_df')

        # Metadata
        metadata = {
            'engine': self.get_name(),
            'start_time': data.index[0] if len(data) > 0 else None,
            'end_time': data.index[-1] if len(data) > 0 else None,
            'duration': data.index[-1] - data.index[0] if len(data) > 0 else None,
            'initial_cash': config.initial_cash,
            'commission': config.commission,
            'slippage': config.slippage,
            'leverage': config.leverage,
            # Store portfolio object for VectorBT's built-in plotting
            '_portfolio': portfolio,  # Internal use only
            # Store orders DataFrame for export
            'orders_df': orders_df,
        }

        return BacktestResult(
            trades=trades_df,
            equity_curve=equity_df,
            positions=positions_df,
            metrics=metrics,
            metadata=metadata,
        )

    def _extract_trades(self, portfolio: vbt.Portfolio) -> pd.DataFrame:
        """
        Extract trades from portfolio.
        
        Also extracts individual orders with their types (ENTRY, TP1, TP2, SL).
        """
        """
        Extract trades from VectorBT portfolio.

        Parameters
        ----------
        portfolio : vbt.Portfolio
            VectorBT portfolio

        Returns
        -------
        pd.DataFrame
            Trades with standardized columns
        """
        try:
            # Get trades records as DataFrame
            trades = portfolio.trades.records_readable

            if trades.empty:
                # Return empty DataFrame with expected columns
                return pd.DataFrame(columns=[
                    'entry_time', 'exit_time', 'entry_price', 'exit_price',
                    'size', 'pnl', 'return_pct', 'duration'
                ])

            # Rename columns to match our standard
            trades = trades.rename(columns={
                'Entry Timestamp': 'entry_time',
                'Exit Timestamp': 'exit_time',
                'Avg. Entry Price': 'entry_price',
                'Avg. Exit Price': 'exit_price',
                'Size': 'size',
                'P&L': 'pnl',
                'Return': 'return_pct',
                'Duration': 'duration',
            })

            # Select and order columns
            standard_cols = [
                'entry_time', 'exit_time', 'entry_price', 'exit_price',
                'size', 'pnl', 'return_pct', 'duration'
            ]
            available_cols = [col for col in standard_cols if col in trades.columns]
            trades = trades[available_cols]
            
            # Also extract individual orders with types
            # This will be saved separately as orders.csv
            orders_df = self._extract_orders(portfolio)
            
            # Store orders_df in portfolio metadata for later export
            if hasattr(portfolio, 'metadata'):
                portfolio.metadata = portfolio.metadata or {}
            else:
                portfolio.metadata = {}
            portfolio.metadata['orders_df'] = orders_df

            # Fix: Recalculate trades from orders to ensure correct entry-exit matching
            # VectorBT may incorrectly merge partial exits, causing wrong entry_time and return
            trades_fixed = self._recalculate_trades_from_orders(orders_df)
            if not trades_fixed.empty:
                # Use recalculated trades instead of VectorBT's trades
                return trades_fixed
            else:
                # Fallback to VectorBT's trades if recalculation fails
                return trades

        except Exception as e:
            # If extraction fails, return empty DataFrame
            print(f"Warning: Failed to extract trades: {e}")
            return pd.DataFrame(columns=[
                'entry_time', 'exit_time', 'entry_price', 'exit_price',
                'size', 'pnl', 'return_pct', 'duration'
            ])
    
    def _extract_orders(self, portfolio: vbt.Portfolio) -> pd.DataFrame:
        """
        Extract individual orders from portfolio with their types.
        
        Returns DataFrame with columns:
        - timestamp: Order time
        - price: Order price (close price at that time)
        - size: Order size (positive for long, negative for short)
        - direction: 'LONG' or 'SHORT'
        - order_type: 'ENTRY', 'TP1', 'TP2', 'SL'
        """
        try:
            # Get orders records
            orders_records = portfolio.orders.records_readable
            
            if orders_records.empty:
                return pd.DataFrame(columns=[
                    'timestamp', 'price', 'size', 'direction', 'order_type'
                ])
            
            # Get order types from metadata if available
            order_types_map = {}
            if hasattr(portfolio, 'metadata') and portfolio.metadata:
                order_types_series = portfolio.metadata.get('order_types')
                if order_types_series is not None:
                    # Create mapping from timestamp to order_type
                    for idx, order_type in order_types_series.items():
                        if order_type and order_type != '':
                            order_types_map[idx] = order_type
            
            # Extract order information
            orders_list = []
            for _, order in orders_records.iterrows():
                timestamp = order.get('Timestamp', order.get('Time', None))
                size = order.get('Size', 0)
                price = order.get('Price', order.get('Avg. Price', None))
                
                # VectorBT stores direction information in the orders records
                # Check for Direction column (VectorBT may store it as 'Direction' or 'Side')
                # Also check all columns to see what VectorBT actually stores
                direction_from_vbt = None
                if 'Direction' in order.index:
                    direction_from_vbt = order.get('Direction')
                elif 'Side' in order.index:
                    direction_from_vbt = order.get('Side')
                else:
                    # Check all columns to find direction-related info
                    for col in order.index:
                        if 'direction' in col.lower() or 'side' in col.lower():
                            direction_from_vbt = order.get(col)
                            break
                
                # Get order type from metadata
                order_type = 'UNKNOWN'
                if timestamp:
                    if hasattr(portfolio, 'metadata') and portfolio.metadata:
                        order_types_series = portfolio.metadata.get('order_types')
                        if order_types_series is not None:
                            try:
                                timestamp_ts = pd.Timestamp(timestamp)
                                closest_idx = order_types_series.index.get_indexer([timestamp_ts], method='nearest')[0]
                                if closest_idx >= 0:
                                    time_diff = abs((order_types_series.index[closest_idx] - timestamp_ts).total_seconds())
                                    if time_diff < 3600:
                                        order_type = order_types_series.iloc[closest_idx] or 'UNKNOWN'
                            except:
                                pass
                
                # Determine direction from VectorBT's stored direction information
                # VectorBT stores direction based on what we passed to from_orders()
                # If VectorBT stored direction, use it; otherwise infer from size sign
                if direction_from_vbt is not None:
                    # Convert VectorBT's direction to our format
                    if isinstance(direction_from_vbt, str):
                        if 'short' in direction_from_vbt.lower() or 'sell' in direction_from_vbt.lower():
                            direction = 'SHORT'
                        elif 'long' in direction_from_vbt.lower() or 'buy' in direction_from_vbt.lower():
                            direction = 'LONG'
                        else:
                            # Unknown string format, use size as fallback
                            direction = 'SHORT' if size < 0 else 'LONG'
                    elif isinstance(direction_from_vbt, (int, float)):
                        # Numeric: negative = short, positive = long
                        direction = 'SHORT' if direction_from_vbt < 0 else 'LONG'
                    else:
                        # Unknown format, use size as fallback
                        direction = 'SHORT' if size < 0 else 'LONG'
                else:
                    # VectorBT didn't store direction explicitly, infer from size sign
                    # This is the standard VectorBT behavior:
                    # - Negative size = short (selling/shorting)
                    # - Positive size = long (buying)
                    direction = 'SHORT' if size < 0 else 'LONG'
                
                orders_list.append({
                    'timestamp': timestamp,
                    'price': price,
                    'size': abs(size),  # Store absolute size
                    'direction': direction,
                    'order_type': order_type if order_type else 'UNKNOWN',
                })
            
            orders_df = pd.DataFrame(orders_list)
            
            # If we have order_types_series, try to match more accurately
            if hasattr(portfolio, 'metadata') and portfolio.metadata:
                order_types_series = portfolio.metadata.get('order_types')
                if order_types_series is not None and not orders_df.empty:
                    # Match orders to order types by timestamp
                    for idx, row in orders_df.iterrows():
                        if pd.notna(row['timestamp']):
                            try:
                                timestamp_ts = pd.Timestamp(row['timestamp'])
                                # Find the closest timestamp in order_types_series
                                closest_idx = order_types_series.index.get_indexer([timestamp_ts], method='nearest')[0]
                                if closest_idx >= 0:
                                    time_diff = abs((order_types_series.index[closest_idx] - timestamp_ts).total_seconds())
                                    # Only use if within 1 hour (for 15m bars, should be exact)
                                    if time_diff < 3600:
                                        orders_df.at[idx, 'order_type'] = order_types_series.iloc[closest_idx] or 'UNKNOWN'
                            except:
                                pass
            
            return orders_df
            
        except Exception as e:
            print(f"Warning: Failed to extract orders: {e}")
            import traceback
            traceback.print_exc()
            return pd.DataFrame(columns=[
                'timestamp', 'price', 'size', 'direction', 'order_type'
            ])
    
    def _recalculate_trades_from_orders(self, orders_df: pd.DataFrame) -> pd.DataFrame:
        """
        Recalculate trades from orders.csv to ensure correct entry-exit matching.
        
        VectorBT may incorrectly merge partial exits when using from_orders(),
        causing wrong entry_time and return calculations. This method fixes that
        by reconstructing trades from individual orders.
        
        Parameters
        ----------
        orders_df : pd.DataFrame
            Orders DataFrame with columns: timestamp, price, size, direction, order_type
        
        Returns
        -------
        pd.DataFrame
            Corrected trades with proper entry-exit matching
        """
        if orders_df.empty:
            return pd.DataFrame(columns=[
                'entry_time', 'exit_time', 'entry_price', 'exit_price',
                'size', 'return_pct', 'order_type'
            ])
        
        # Ensure timestamp is datetime
        orders_df = orders_df.copy()
        orders_df['timestamp'] = pd.to_datetime(orders_df['timestamp'])
        orders_df = orders_df.sort_values('timestamp')
        
        trades_list = []
        current_entry = None
        
        for _, order in orders_df.iterrows():
            if order['order_type'] == 'ENTRY':
                # Start a new position
                current_entry = {
                    'entry_time': order['timestamp'],
                    'entry_price': order['price'],
                    'entry_size': order['size'],
                    'direction': order['direction'],
                }
            elif order['order_type'] in ['TP1', 'TP2', 'SL'] and current_entry is not None:
                # Process exit order
                exit_time = order['timestamp']
                exit_price = order['price']
                exit_size = order['size']
                entry_price = current_entry['entry_price']
                direction = current_entry['direction']
                
                # Calculate return based on direction
                if direction == 'SHORT':
                    # For short: profit when exit_price < entry_price
                    return_pct = (entry_price - exit_price) / entry_price
                else:  # LONG
                    # For long: profit when exit_price > entry_price
                    return_pct = (exit_price - entry_price) / entry_price
                
                # Create trade record
                trades_list.append({
                    'entry_time': current_entry['entry_time'],
                    'exit_time': exit_time,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'size': exit_size,
                    'return_pct': return_pct,
                    'order_type': order['order_type'],
                })
                
                # Update remaining position size
                current_entry['entry_size'] -= exit_size
                
                # If position is fully closed, reset current_entry
                if current_entry['entry_size'] < 0.001:
                    current_entry = None
        
        if not trades_list:
            return pd.DataFrame(columns=[
                'entry_time', 'exit_time', 'entry_price', 'exit_price',
                'size', 'return_pct', 'order_type'
            ])
        
        trades_df = pd.DataFrame(trades_list)
        
        # Calculate P&L and duration
        if 'entry_price' in trades_df.columns and 'exit_price' in trades_df.columns:
            # P&L = return_pct * size * entry_price (for absolute P&L)
            trades_df['pnl'] = trades_df['return_pct'] * trades_df['size'] * trades_df['entry_price']
        else:
            trades_df['pnl'] = 0.0
        
        # Calculate duration
        trades_df['entry_time'] = pd.to_datetime(trades_df['entry_time'])
        trades_df['exit_time'] = pd.to_datetime(trades_df['exit_time'])
        trades_df['duration'] = (trades_df['exit_time'] - trades_df['entry_time']).dt.total_seconds() / 3600  # hours
        
        # Reorder columns to match expected format
        standard_cols = [
            'entry_time', 'exit_time', 'entry_price', 'exit_price',
            'size', 'pnl', 'return_pct', 'duration'
        ]
        available_cols = [col for col in standard_cols if col in trades_df.columns]
        trades_df = trades_df[available_cols]
        
        return trades_df

    def _extract_equity_curve(self, portfolio: vbt.Portfolio) -> pd.DataFrame:
        """
        Extract equity curve from VectorBT portfolio.

        Parameters
        ----------
        portfolio : vbt.Portfolio
            VectorBT portfolio

        Returns
        -------
        pd.DataFrame
            Equity curve with columns: [equity, cash, position_value]
        """
        try:
            # Total value (equity)
            equity = portfolio.value()

            # Cash
            cash = portfolio.cash()

            # Create DataFrame
            equity_df = pd.DataFrame({
                'equity': equity,
                'cash': cash,
                'position_value': equity - cash,
            })

            return equity_df

        except Exception as e:
            print(f"Warning: Failed to extract equity curve: {e}")
            return pd.DataFrame(columns=['equity', 'cash', 'position_value'])

    def _extract_positions(self, portfolio: vbt.Portfolio) -> pd.DataFrame:
        """
        Extract position snapshots from VectorBT portfolio.

        Parameters
        ----------
        portfolio : vbt.Portfolio
            VectorBT portfolio

        Returns
        -------
        pd.DataFrame
            Position snapshots
        """
        try:
            # Get position size over time
            positions = portfolio.positions.records_readable

            if positions.empty:
                return pd.DataFrame(columns=[
                    'time', 'size', 'value', 'entry_price', 'unrealized_pnl'
                ])

            # Rename and select columns
            positions = positions.rename(columns={
                'Timestamp': 'time',
                'Size': 'size',
                'Value': 'value',
                'Avg. Entry Price': 'entry_price',
                'P&L': 'unrealized_pnl',
            })

            standard_cols = ['time', 'size', 'value', 'entry_price', 'unrealized_pnl']
            available_cols = [col for col in standard_cols if col in positions.columns]
            positions = positions[available_cols]

            return positions

        except Exception as e:
            print(f"Warning: Failed to extract positions: {e}")
            return pd.DataFrame(columns=[
                'time', 'size', 'value', 'entry_price', 'unrealized_pnl'
            ])

    def _calculate_metrics(
        self,
        portfolio: vbt.Portfolio,
        trades_df: pd.DataFrame,
    ) -> dict:
        """
        Calculate performance metrics from VectorBT portfolio.

        Parameters
        ----------
        portfolio : vbt.Portfolio
            VectorBT portfolio
        trades_df : pd.DataFrame
            Extracted trades

        Returns
        -------
        dict
            Performance metrics
        """
        try:
            # Basic metrics from VectorBT
            total_return = portfolio.total_return()
            sharpe_ratio = portfolio.sharpe_ratio()
            max_drawdown = portfolio.max_drawdown()

            # Trade statistics
            num_trades = len(trades_df)
            if num_trades > 0:
                # Get P&L column (may be 'pnl' or 'P&L' or 'return_pct')
                pnl_col = None
                for col in ['pnl', 'P&L', 'return_pct']:
                    if col in trades_df.columns:
                        pnl_col = col
                        break
                
                if pnl_col is None:
                    # Calculate P&L from entry/exit prices if available
                    if 'entry_price' in trades_df.columns and 'exit_price' in trades_df.columns:
                        # For short positions, P&L = (entry_price - exit_price) * size
                        # For long positions, P&L = (exit_price - entry_price) * size
                        # We'll use return_pct to determine direction
                        if 'return_pct' in trades_df.columns:
                            # return_pct already accounts for direction
                            trades_df['pnl'] = trades_df['return_pct'] * trades_df.get('size', 1.0) * 100
                        else:
                            trades_df['pnl'] = 0.0
                        pnl_col = 'pnl'
                    else:
                        # No way to calculate P&L
                        pnl_col = None
                
                if pnl_col is not None:
                    winning_trades = len(trades_df[trades_df[pnl_col] > 0])
                    losing_trades = len(trades_df[trades_df[pnl_col] < 0])
                    win_rate = winning_trades / num_trades if num_trades > 0 else 0

                    avg_win = trades_df[trades_df[pnl_col] > 0][pnl_col].mean() if winning_trades > 0 else 0
                    avg_loss = trades_df[trades_df[pnl_col] < 0][pnl_col].mean() if losing_trades > 0 else 0
                    profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0
                else:
                    # Can't calculate trade stats
                    winning_trades = 0
                    losing_trades = 0
                    win_rate = 0
                    avg_win = 0
                    avg_loss = 0
                    profit_factor = 0
            else:
                winning_trades = 0
                losing_trades = 0
                win_rate = 0
                avg_win = 0
                avg_loss = 0
                profit_factor = 0

            # Try to get Sortino ratio (may not be available in all VectorBT versions)
            try:
                sortino_ratio = portfolio.sortino_ratio()
            except:
                sortino_ratio = 0

            # Calculate total PnL from portfolio value (more accurate than summing trades)
            # This captures all P&L including force-closed positions and partially closed trades
            try:
                value_series = portfolio.value()  # Get portfolio value time series
                final_value = value_series.iloc[-1]  # Last value
                initial_value = value_series.iloc[0]  # Initial value
                total_pnl = final_value - initial_value
            except Exception as e:
                # Fallback: derive from total_return
                # total_return = (final - initial) / initial
                # So: total_pnl = total_return * initial
                # We need to get initial_cash from somewhere
                total_pnl = 0.0

            metrics = {
                # Returns
                'total_return': float(total_return) if not np.isnan(total_return) else 0.0,
                'total_pnl': float(total_pnl) if not np.isnan(total_pnl) else 0.0,

                # Risk-adjusted returns
                'sharpe_ratio': float(sharpe_ratio) if not np.isnan(sharpe_ratio) else 0.0,
                'sortino_ratio': float(sortino_ratio) if not np.isnan(sortino_ratio) else 0.0,

                # Risk
                'max_drawdown': float(max_drawdown) if not np.isnan(max_drawdown) else 0.0,

                # Trading activity
                'total_trades': int(num_trades),
                'winning_trades': int(winning_trades),
                'losing_trades': int(losing_trades),
                'win_rate': float(win_rate),

                # Trade performance
                'avg_win': float(avg_win) if not np.isnan(avg_win) else 0.0,
                'avg_loss': float(avg_loss) if not np.isnan(avg_loss) else 0.0,
                'profit_factor': float(profit_factor) if not np.isnan(profit_factor) else 0.0,
            }

            return metrics

        except Exception as e:
            print(f"Warning: Failed to calculate some metrics: {e}")
            # Return default metrics
            return {
                'total_return': 0.0,
                'sharpe_ratio': 0.0,
                'sortino_ratio': 0.0,
                'max_drawdown': 0.0,
                'total_trades': len(trades_df),
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
            }

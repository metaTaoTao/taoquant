"""
Backtest runner for orchestrating complete backtest workflows.

This module implements the Facade pattern to hide complexity:
- DataManager → loads data
- Strategy → generates signals
- BacktestEngine → executes backtest
- Results → exports and visualizes

Users only need to provide configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from data import DataManager
from execution.engines.base import BacktestConfig, BacktestEngine, BacktestResult
from strategies.base_strategy import BaseStrategy


@dataclass
class BacktestRunConfig:
    """
    Configuration for a complete backtest run.

    Data Parameters
    ---------------
    symbol : str
        Trading symbol (e.g., 'BTCUSDT')
    timeframe : str
        Data timeframe (e.g., '15m', '1h', '4h')
    start : datetime
        Backtest start time
    end : datetime
        Backtest end time
    source : str
        Data source ('okx', 'binance', 'csv')

    Strategy Parameters
    -------------------
    strategy : BaseStrategy
        Strategy instance (configured)

    Execution Parameters
    --------------------
    engine : BacktestEngine
        Backtest engine (VectorBT, custom, etc.)
    backtest_config : BacktestConfig
        Backtest execution configuration

    Output Parameters
    -----------------
    output_dir : Path
        Directory to save results
    save_results : bool
        Whether to save results to disk
    save_trades : bool
        Whether to save trades CSV
    save_equity : bool
        Whether to save equity curve CSV
    save_metrics : bool
        Whether to save metrics JSON
    save_plot : bool
        Whether to generate and save interactive plot (HTML)
    """

    # Data
    symbol: str
    timeframe: str
    start: datetime
    end: datetime
    source: str = 'okx'

    # Strategy
    strategy: BaseStrategy = None

    # Execution
    engine: BacktestEngine = None
    backtest_config: BacktestConfig = None

    # Output
    output_dir: Path = None  # Will be set to project root / run / results
    save_results: bool = True
    save_trades: bool = True
    save_equity: bool = True
    save_metrics: bool = True
    save_plot: bool = True


class BacktestRunner:
    """
    Orchestrates complete backtest workflow (Facade pattern).

    This class hides the complexity of coordinating multiple components:
    1. Load data from DataManager
    2. Run strategy to generate signals
    3. Run backtest engine
    4. Export results and generate visualizations

    Examples
    --------
    >>> from data import DataManager
    >>> from strategies.signal_based.sr_short import SRShortStrategy, SRShortConfig
    >>> from execution.engines.vectorbt_engine import VectorBTEngine
    >>> from execution.engines.base import BacktestConfig
    >>> from orchestration.backtest_runner import BacktestRunner, BacktestRunConfig
    >>>
    >>> # Initialize components
    >>> data_manager = DataManager()
    >>> strategy = SRShortStrategy(SRShortConfig(name="SR Short", description="..."))
    >>> engine = VectorBTEngine()
    >>>
    >>> # Create runner
    >>> runner = BacktestRunner(data_manager)
    >>>
    >>> # Run backtest
    >>> result = runner.run(BacktestRunConfig(
    ...     symbol="BTCUSDT",
    ...     timeframe="15m",
    ...     start=pd.Timestamp("2025-10-01", tz="UTC"),
    ...     end=pd.Timestamp("2025-12-01", tz="UTC"),
    ...     source="okx",
    ...     strategy=strategy,
    ...     engine=engine,
    ...     backtest_config=BacktestConfig(
    ...         initial_cash=100000,
    ...         commission=0.001,
    ...         slippage=0.0005,
    ...         leverage=5.0
    ...     ),
        ...     output_dir=None,  # Will default to project_root/run/results
    ...     save_results=True
    ... ))
    >>>
    >>> print(result.summary())
    """

    def __init__(self, data_manager: Optional[DataManager] = None):
        """
        Initialize backtest runner.

        Parameters
        ----------
        data_manager : Optional[DataManager]
            Data manager instance (creates default if None)
        """
        self.data_manager = data_manager or DataManager()
        self._data_with_indicators = None  # Store for visualization

    def run(self, config: BacktestRunConfig) -> BacktestResult:
        """
        Run complete backtest workflow.

        Steps:
        1. Load data from DataManager
        2. Run strategy to generate signals
        3. Run backtest engine
        4. Export results (if configured)
        5. Print summary

        Parameters
        ----------
        config : BacktestRunConfig
            Backtest run configuration

        Returns
        -------
        BacktestResult
            Backtest results

        Raises
        ------
        ValueError
            If configuration is invalid
        """
        # Validate configuration
        self._validate_config(config)

        # Print header
        self._print_header(config)

        # Step 1: Load data
        print("[Data] Loading data...")
        data = self._load_data(config)
        print(f"   [OK] Loaded {len(data)} bars from {data.index[0]} to {data.index[-1]}")

        # Step 2: Run strategy
        print(f"[Strategy] Running strategy: {config.strategy.get_name()}...")
        data_with_indicators, signals, sizes = config.strategy.run(
            data,
            initial_equity=config.backtest_config.initial_cash
        )
        
        # Support both order-based and signal-based modes
        if 'orders' in signals.columns:
            # Order-based mode (partial exits)
            num_orders = (signals['orders'] != 0).sum()
            entry_orders = (signals['orders'] < 0).sum()
            exit_orders = (signals['orders'] > 0).sum()
            print(f"   [OK] Generated {num_orders} orders ({entry_orders} entries, {exit_orders} exits)")
        else:
            # Signal-based mode (legacy)
            num_signals = signals['entry'].sum() if 'entry' in signals.columns else 0
            print(f"   [OK] Generated {num_signals} entry signals")
        
        # Store data_with_indicators for visualization (contains zones)
        self._data_with_indicators = data_with_indicators

        # Step 3: Run backtest
        print(f"[Backtest] Running backtest with {config.engine.get_name()}...")
        result = config.engine.run(
            data=data_with_indicators,
            signals=signals,
            sizes=sizes,
            config=config.backtest_config,
        )
        print(f"   [OK] Executed {len(result.trades)} trades")

        # Step 4: Export results
        if config.save_results:
            print(f"[Results] Saving results to {config.output_dir}...")
            self._export_results(result, config)

        # Step 5: Print summary
        print("\n" + result.summary())

        return result

    def _validate_config(self, config: BacktestRunConfig) -> None:
        """Validate configuration."""
        if config.strategy is None:
            raise ValueError("Strategy is required")

        if config.engine is None:
            raise ValueError("Engine is required")

        if config.backtest_config is None:
            raise ValueError("Backtest config is required")

        if config.start >= config.end:
            raise ValueError("Start time must be before end time")

    def _print_header(self, config: BacktestRunConfig) -> None:
        """Print backtest header."""
        print("\n" + "=" * 80)
        print("BACKTEST RUN")
        print("=" * 80)
        print(f"Strategy:      {config.strategy.get_name()}")
        print(f"Symbol:        {config.symbol}")
        print(f"Timeframe:     {config.timeframe}")
        print(f"Period:        {config.start} to {config.end}")
        print(f"Data Source:   {config.source}")
        print(f"Engine:        {config.engine.get_name()}")
        print(f"Initial Cash:  ${config.backtest_config.initial_cash:,.2f}")
        print(f"Commission:    {config.backtest_config.commission * 100:.2f}%")
        print(f"Leverage:      {config.backtest_config.leverage}x")
        print("=" * 80 + "\n")

    def _load_data(self, config: BacktestRunConfig) -> pd.DataFrame:
        """
        Load data from DataManager.

        Parameters
        ----------
        config : BacktestRunConfig
            Run configuration

        Returns
        -------
        pd.DataFrame
            OHLCV data
        """
        data = self.data_manager.get_klines(
            symbol=config.symbol,
            timeframe=config.timeframe,
            start=config.start,
            end=config.end,
            source=config.source,
            use_cache=True,
        )

        if data.empty:
            raise ValueError(f"No data received for {config.symbol} {config.timeframe}")

        return data

    def _export_results(self, result: BacktestResult, config: BacktestRunConfig) -> None:
        """
        Export results to files.

        Parameters
        ----------
        result : BacktestResult
            Backtest results
        config : BacktestRunConfig
            Run configuration
        """
        # Set default output directory if not provided
        if config.output_dir is None:
            from utils.paths import get_results_dir
            config.output_dir = get_results_dir()
        
        # Create output directory
        config.output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename prefix
        prefix = f"{config.strategy.get_name()}_{config.symbol}_{config.timeframe}"

        # Export trades
        if config.save_trades and not result.trades.empty:
            trades_path = config.output_dir / f"{prefix}_trades.csv"
            result.trades.to_csv(trades_path, index=False)
            print(f"   [OK] Saved trades: {trades_path}")
        
        # Save individual orders if available
        if hasattr(result, 'metadata') and result.metadata:
            orders_df = result.metadata.get('orders_df')
            if orders_df is not None and not orders_df.empty:
                orders_path = config.output_dir / f"{prefix}_orders.csv"
                orders_df.to_csv(orders_path, index=False)
                print(f"   [OK] Saved orders: {orders_path}")

        # Export equity curve
        if config.save_equity and not result.equity_curve.empty:
            equity_path = config.output_dir / f"{prefix}_equity.csv"
            result.equity_curve.to_csv(equity_path)
            print(f"   [OK] Saved equity curve: {equity_path}")

        # Export metrics
        if config.save_metrics:
            import json
            metrics_path = config.output_dir / f"{prefix}_metrics.json"
            with open(metrics_path, 'w') as f:
                json.dump(result.metrics, f, indent=2)
            print(f"   [OK] Saved metrics: {metrics_path}")

        # Generate and save plots
        if config.save_plot:
            # 1. Custom visualization (K线图 + 交易标记 + 阻力区)
            try:
                from execution.visualization import plot_backtest_results
                
                # Extract zones data if available
                zones_data = None
                if hasattr(self, '_data_with_indicators'):
                    zones_cols = ['zone_top', 'zone_bottom', 'zone_touches', 'zone_is_broken']
                    if all(col in self._data_with_indicators.columns for col in zones_cols):
                        zones_data = self._data_with_indicators[zones_cols]
                
                plot_path = config.output_dir / f"{prefix}_plot.html"
                title = f"{config.strategy.get_name()} - {config.symbol} {config.timeframe}"
                
                # Prepare data for plotting (ensure volume column exists)
                plot_data_cols = ['open', 'high', 'low', 'close']
                if 'volume' in self._data_with_indicators.columns:
                    plot_data_cols.append('volume')
                
                # Get orders data if available (for more accurate trade markers)
                orders_data = None
                if hasattr(result, 'metadata') and result.metadata:
                    orders_df = result.metadata.get('orders_df')
                    if orders_df is not None and not orders_df.empty:
                        orders_data = orders_df
                
                # Use original data (not data_with_indicators) for candlesticks
                plot_backtest_results(
                    result=result,
                    data=self._data_with_indicators[plot_data_cols],
                    zones_data=zones_data,
                    orders_data=orders_data,  # Pass orders data for accurate markers
                    output_path=plot_path,
                    title=title,
                )
            except Exception as e:
                print(f"   [Warning] Failed to generate custom plot: {e}")
            
            # 2. VectorBT built-in performance plots (权益曲线、回撤、性能指标)
            # Note: VectorBT plots require anywidget for interactive plots
            try:
                portfolio = result.metadata.get('_portfolio')
                if portfolio is not None:
                    vbt_plot_path = config.output_dir / f"{prefix}_vbt_performance.html"
                    
                    # Generate VectorBT's built-in performance plots
                    # This includes: equity curve, drawdowns, trades, returns, etc.
                    # Use plots() method which returns a regular Figure, not FigureWidget
                    fig = portfolio.plots(
                        subplots=['value', 'drawdowns', 'trades', 'trade_pnl', 'cum_returns'],
                        subplot_settings=dict(
                            value=dict(title='Equity Curve'),
                            drawdowns=dict(title='Drawdowns'),
                            trades=dict(title='Trades'),
                            trade_pnl=dict(title='Trade P&L'),
                            cum_returns=dict(title='Cumulative Returns'),
                        ),
                        make_subplots_kwargs=dict(
                            vertical_spacing=0.1,
                            row_heights=[0.3, 0.2, 0.2, 0.15, 0.15],
                        ),
                    )
                    
                    if fig is not None:
                        fig.write_html(str(vbt_plot_path))
                        print(f"   [OK] Saved VectorBT performance plots: {vbt_plot_path}")
            except Exception as e:
                # VectorBT plots require anywidget - this is optional
                if "anywidget" in str(e).lower() or "FigureWidget" in str(e):
                    print(f"   [Warning] VectorBT interactive plots require anywidget. Install with: pip install anywidget")
                else:
                    print(f"   [Warning] Failed to generate VectorBT plots: {e}")

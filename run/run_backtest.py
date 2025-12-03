"""
Generic backtest runner for strategies.

This script provides a flexible interface to run backtests with different strategies.
Simply modify the configuration section to change symbol, timeframe, date range, etc.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Type

import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy

from data.data_manager import DataManager


def run_strategy_backtest(
    strategy_class: Type[Strategy],
    symbol: str,
    timeframe: str,
    start_time: Optional[pd.Timestamp] = None,
    end_time: Optional[pd.Timestamp] = None,
    days: int = 200,
    source: str = "okx",
    cash: float = 10000,
    commission: float = 0.001,
    trade_on_close: bool = True,
    exclusive_orders: bool = False,
    strategy_params: Optional[dict] = None,
    output_dir: Optional[Path] = None,
    plot: bool = True,
    # Parameters for 4H S/R data (only used for SRShort4HResistance)
    htf_lookback_days: Optional[int] = None,  # If None, uses default 200 days
    htf_start_time: Optional[pd.Timestamp] = None,  # If provided, overrides lookback_days
    htf_end_time: Optional[pd.Timestamp] = None,  # If None, uses backtest end_time
) -> dict:
    """
    Run a backtest with the specified strategy.
    
    Parameters
    ----------
    strategy_class : Type[Strategy]
        Strategy class to backtest (must inherit from backtesting.Strategy)
    symbol : str
        Trading symbol (e.g., 'BTCUSDT')
    timeframe : str
        Data timeframe (e.g., '15m', '4h', '1d')
    start_time : Optional[pd.Timestamp]
        Start time for backtest. If None, calculated from end_time - days
    end_time : Optional[pd.Timestamp]
        End time for backtest. If None, uses current time
    days : int
        Number of days to backtest (used if start_time is None)
    source : str
        Data source ('okx' or 'binance')
    cash : float
        Initial capital
    commission : float
        Commission rate (e.g., 0.001 = 0.1%)
    trade_on_close : bool
        Whether to trade on bar close
    exclusive_orders : bool
        Whether to allow multiple concurrent orders
    strategy_params : Optional[dict]
        Strategy-specific parameters to pass to strategy.run()
    output_dir : Optional[Path]
        Directory to save results. If None, uses run/scripts/backtest/results/
    plot : bool
        Whether to generate and save plot
    
    Returns
    -------
    dict
        Backtest statistics
    """
    # Initialize data manager
    manager = DataManager()
    
    # Set default end time if not provided
    if end_time is None:
        end_time = pd.Timestamp.utcnow().floor("min")
    
    # Set default start time if not provided
    if start_time is None:
        start_time = end_time - pd.Timedelta(days=days)
    
    print(f"=" * 80)
    print(f"Backtest Configuration")
    print(f"=" * 80)
    print(f"Strategy: {strategy_class.__name__}")
    print(f"Symbol: {symbol}")
    print(f"Timeframe: {timeframe}")
    print(f"Start: {start_time}")
    print(f"End: {end_time}")
    print(f"Source: {source}")
    print(f"Initial Capital: ${cash:,.2f}")
    print(f"Commission: {commission*100:.2f}%")
    print(f"=" * 80)
    
    # For SR Short strategy, we need to load 4H data separately for S/R detection
    # This avoids fetching massive amounts of 15m data
    htf_data = None
    if strategy_class.__name__ == "SRShort4HResistance":
        # Load 4H data for S/R zone detection
        htf_timeframe = "4h"
        
        # Determine 4H data range
        # Priority: htf_start_time > htf_lookback_days > default (200 days)
        if htf_start_time is not None:
            # Use explicitly provided start time
            htf_data_start = htf_start_time
        elif htf_lookback_days is not None:
            # Use lookback days from backtest start time
            htf_data_start = start_time - pd.Timedelta(days=htf_lookback_days)
        else:
            # Default: 200 days lookback
            htf_data_start = start_time - pd.Timedelta(days=300)
        
        # Use provided htf_end_time or default to backtest end_time
        htf_end_time = htf_end_time if htf_end_time is not None else end_time
        
        print(f"\nLoading {symbol} {htf_timeframe} data for S/R detection...")
        print(f"  4H Range: {htf_data_start} to {htf_end_time}")
        print(f"  (Independent from 15m backtest range: {start_time} to {end_time})")
        try:
            htf_df = manager.get_klines(
                symbol=symbol,
                timeframe=htf_timeframe,
                start=htf_data_start,
                end=htf_end_time,
                source=source,
                use_cache=True,  # Use cache to avoid re-fetching on multiple runs
            )
            
            if htf_df.empty:
                raise ValueError(f"No 4H data received for {symbol}")
            
            # CRITICAL: Truncate 4H data to end_time to avoid lookahead bias
            # We can only use 4H data up to the end of the backtest period
            htf_df = htf_df[htf_df.index <= end_time]
            
            # Ensure column names are lowercase (for strategy compatibility)
            htf_df = htf_df.copy()
            column_mapping_htf = {
                "Open": "open",
                "High": "high", 
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
            htf_df.rename(columns={k: v for k, v in column_mapping_htf.items() if k in htf_df.columns}, inplace=True)
            
            # Ensure timezone-aware index
            if htf_df.index.tz is None:
                htf_df.index = htf_df.index.tz_localize('UTC')
            
            htf_data = htf_df
            print(f"  Loaded {len(htf_data)} 4H bars from {htf_data.index[0]} to {htf_data.index[-1]}")
            print(f"  Truncated to backtest end_time: {end_time}")
            
        except Exception as e:
            print(f"Warning: Failed to load 4H data: {e}")
            print("  Falling back to resampling from 15m data")
            htf_data = None
    
    # Load 15m data for backtesting
    print(f"\nLoading {symbol} {timeframe} data from {source}...")
    try:
        # Use cache to avoid re-fetching on multiple runs
        df = manager.get_klines(
            symbol=symbol,
            timeframe=timeframe,
            start=start_time,
            end=end_time,
            source=source,
            use_cache=True,  # Use cache to avoid re-fetching on multiple runs
        )
        
        if df.empty:
            raise ValueError(f"No data received for {symbol} {timeframe}")
        
        print(f"Loaded {len(df)} bars from {df.index[0]} to {df.index[-1]}")
        
        # Ensure column names match backtesting.py requirements
        # DataManager returns lowercase columns, backtesting.py expects Capitalized
        df = df.copy()
        column_mapping = {
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
        df.rename(columns=column_mapping, inplace=True)
        
        # Ensure we have all required columns
        required_cols = ["Open", "High", "Low", "Close", "Volume"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
    except Exception as e:
        print(f"Error loading data: {e}")
        raise
    
    # Create backtest instance
    print(f"\nInitializing backtest...")
    bt = Backtest(
        df,
        strategy_class,
        cash=cash,
        commission=commission,
        trade_on_close=trade_on_close,
        exclusive_orders=exclusive_orders,
    )
    
    # Run backtest
    print(f"Running backtest...")
    strategy_params = strategy_params or {}
    
    # If we loaded 4H data, pass it to the strategy
    if htf_data is not None:
        strategy_params['htf_data'] = htf_data
    
    stats = bt.run(**strategy_params)
    
    # Print results
    print(f"\n" + "=" * 80)
    print(f"Backtest Results")
    print(f"=" * 80)
    print(stats)
    print(f"=" * 80)
    
    # Save results
    if output_dir is None:
        output_dir = Path(__file__).parent / "scripts" / "backtest" / "results"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save trades
    trades_path = output_dir / f"{strategy_class.__name__}_{symbol}_{timeframe}_trades.csv"
    if hasattr(stats, "_trades") and stats._trades is not None:
        stats._trades.to_csv(trades_path, index=False)
        print(f"\nTrades saved to: {trades_path}")
    
    # Save equity curve
    equity_path = output_dir / f"{strategy_class.__name__}_{symbol}_{timeframe}_equity.csv"
    if hasattr(stats, "_equity_curve") and stats._equity_curve is not None:
        stats._equity_curve.to_csv(equity_path, index=False)
        print(f"Equity curve saved to: {equity_path}")
    
    # Save active zones log if available
    strategy_instance = stats.get("_strategy")
    if strategy_instance and hasattr(strategy_instance, "active_zones_log"):
        active_zones_df = pd.DataFrame(strategy_instance.active_zones_log)
        if not active_zones_df.empty:
            active_zones_path = output_dir / f"{strategy_class.__name__}_{symbol}_{timeframe}_active_zones.csv"
            active_zones_df.to_csv(active_zones_path, index=False)
            print(f"Active zones log saved to: {active_zones_path}")
    
    # Generate plot
    if plot:
        plot_path = output_dir / f"{strategy_class.__name__}_{symbol}_{timeframe}_plot.html"
        # Generate backtest plot
        bt.plot(filename=str(plot_path), open_browser=False)
        print(f"Plot saved to: {plot_path}")
        
    # Generate 4H timeframe plot if strategy has htf_data
    strategy_instance = stats.get("_strategy")
    if strategy_instance and hasattr(strategy_instance, "htf_data_for_plot"):
        htf_data = strategy_instance.htf_data_for_plot
        zones = getattr(strategy_instance, "zones_for_plot", [])
        debug_pivots = getattr(strategy_instance, "debug_pivots", [])
        
        # Ensure all zones have end_time set correctly for visualization
        # TV visualization: zones extend from pivot bar to end of data (or until broken)
        if zones and not htf_data.empty:
            max_time = htf_data.index.max()
            for zone in zones:
                # Update end_time: active zones extend to end, broken zones keep their break time
                if hasattr(zone, 'end_time'):
                    if not zone.is_broken:
                        # Active zones extend to end of data (like TV: box.set_right(z.id, bar_index + 10))
                        zone.end_time = max_time
                    # For broken zones, end_time should already be set to break time
                else:
                    # If no end_time, set to max_time for active zones
                    if not zone.is_broken:
                        zone.end_time = max_time
        
        if not htf_data.empty:
            _generate_htf_plot(
                htf_data=htf_data,
                zones=zones,
                zone_history=[],  # Not using history list anymore
                debug_pivots=debug_pivots,
                strategy_name=strategy_class.__name__,
                symbol=symbol,
                timeframe=timeframe,
                output_dir=output_dir,
            )
    
    return stats


def _generate_htf_plot(
    htf_data: pd.DataFrame,
    zones: list,
    zone_history: list,
    debug_pivots: list,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    output_dir: Path,
) -> None:
    """
    Generate a 4H timeframe plot with S/R zones using Bokeh.
    
    Parameters
    ----------
    htf_data : pd.DataFrame
        4H OHLCV data with lowercase column names
    zones : list
        List of Zone objects to plot
    zone_history : list
        List of zone history dicts with start_time, end_time, etc.
    debug_pivots : list
        List of raw pivot dicts {time, price}
    strategy_name : str
        Name of the strategy
    symbol : str
        Trading symbol
    timeframe : str
        Original timeframe (for filename)
    output_dir : Path
        Output directory for the plot
    """
    try:
        from bokeh.plotting import figure, output_file, save
        from bokeh.models import ColumnDataSource, HoverTool, BoxAnnotation, Label, NumeralTickFormatter, Circle
        from bokeh.layouts import column
        
        # Convert column names if needed
        htf_plot_data = htf_data.copy()
        if "open" in htf_plot_data.columns:
            # Already lowercase, use as is
            pass
        else:
            # Convert from Capitalized to lowercase
            column_mapping = {
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
            htf_plot_data.rename(columns={k: v for k, v in column_mapping.items() if k in htf_plot_data.columns}, inplace=True)
        
        # Ensure we have all required columns
        required_cols = ["open", "high", "low", "close", "volume"]
        missing_cols = [col for col in required_cols if col not in htf_plot_data.columns]
        if missing_cols:
            print(f"Warning: Missing columns for 4H plot: {missing_cols}")
            return
        
        # Convert index to datetime if needed
        if not isinstance(htf_plot_data.index, pd.DatetimeIndex):
            htf_plot_data.index = pd.to_datetime(htf_plot_data.index)
        
        # Prepare data for Bokeh
        htf_plot_data = htf_plot_data.copy()
        htf_plot_data['date'] = htf_plot_data.index
        htf_plot_data['color'] = ['#26a69a' if close >= open else '#ef5350' 
                                   for close, open in zip(htf_plot_data['close'], htf_plot_data['open'])]
        
        # Create ColumnDataSource
        source = ColumnDataSource(htf_plot_data)
        
        # Calculate bar width (use 80% of the time interval)
        # For datetime x-axis, Bokeh expects width in milliseconds
        if len(htf_plot_data) > 1:
            time_delta_ms = (htf_plot_data.index[1] - htf_plot_data.index[0]).total_seconds() * 1000  # milliseconds
            bar_width = time_delta_ms * 0.8
        else:
            bar_width = pd.Timedelta(hours=4).total_seconds() * 1000 * 0.8  # Default to 4H in milliseconds
        
        # Create price chart with wider width for fullscreen
        p1 = figure(
            x_axis_type="datetime",
            width=1800,  # Increased width for better fullscreen experience
            height=600,
            title=f"{strategy_name} - {symbol} 4H Chart with S/R Zones",
            tools="pan,wheel_zoom,box_zoom,reset,save,hover",
            toolbar_location="above",
            background_fill_color="#ffffff",
            sizing_mode="scale_width",  # Allow responsive sizing
        )
        p1.xaxis.axis_label = "Time"
        p1.yaxis.axis_label = "Price"
        p1.yaxis.axis_label_text_font_size = "12pt"
        p1.xaxis.axis_label_text_font_size = "12pt"
        p1.title.text_font_size = "14pt"
        # Format y-axis to avoid scientific notation
        p1.yaxis.formatter = NumeralTickFormatter(format="0,0")
        
        # Add candlestick: segments for high-low
        p1.segment('date', 'high', 'date', 'low', color="black", source=source, line_width=1)
        
        # Add candlestick: vbars for open-close
        p1.vbar(
            'date', 
            bar_width, 
            'open', 
            'close', 
            fill_color='color', 
            line_color="black", 
            source=source,
            line_width=1,
        )
        
        # Add hover tool
        hover1 = HoverTool(
            tooltips=[
                ("Time", "@date{%F %H:%M}"),
                ("Open", "@open{0.2f}"),
                ("High", "@high{0.2f}"),
                ("Low", "@low{0.2f}"),
                ("Close", "@close{0.2f}"),
                ("Volume", "@volume{0.2f}"),
            ],
            formatters={
                '@date': 'datetime',
            },
            mode='vline'
        )
        p1.add_tools(hover1)
        
        # Plot S/R zones as rectangles
        min_time = htf_plot_data.index.min()
        max_time = htf_plot_data.index.max()
        
        # Use zone_history if available (more complete), otherwise use zones list
        zones_to_plot = zone_history if zone_history else []
        
        if not zones_to_plot and zones:
            # Convert Zone objects to dict format
            # TV visualization: zones extend from pivot bar to end of data (or until broken)
            print(f"Converting {len(zones)} Zone objects to dict format...")
            for zone in zones:
                # Zone start_time should be the pivot bar time
                zone_start = zone.start_time if hasattr(zone, "start_time") else min_time
                
                # If start_time is a Timestamp, use it; if it's an index, convert it
                if isinstance(zone_start, pd.Timestamp):
                    start_time = zone_start
                elif isinstance(zone_start, (int, np.integer)):
                    # It's a numeric index, get the corresponding timestamp
                    if zone_start < len(htf_plot_data):
                        start_time = htf_plot_data.index[zone_start]
                    else:
                        start_time = min_time
                else:
                    start_time = min_time
                
                # Zone end_time: extend to max_time if not broken, or use actual end_time if broken
                if zone.is_broken and hasattr(zone, "end_time"):
                    zone_end = zone.end_time
                    if isinstance(zone_end, pd.Timestamp):
                        end_time = zone_end
                    else:
                        end_time = max_time
                else:
                    # Active zones extend to end of data (like TV: box.set_right(z.id, bar_index + 10))
                    end_time = max_time
                
                zones_to_plot.append({
                    "start_time": start_time,
                    "end_time": end_time,
                    "top": zone.top,
                    "bottom": zone.bottom,
                    "is_broken": zone.is_broken if hasattr(zone, "is_broken") else False,
                    "touches": zone.touches if hasattr(zone, "touches") else 1,
                    "fail_count": zone.fail_count if hasattr(zone, "fail_count") else 0,
                })
        
        if zones_to_plot:
            print(f"Plotting {len(zones_to_plot)} S/R zones...")
            for zone_data in zones_to_plot:
                start_time = zone_data["start_time"]
                end_time = zone_data["end_time"]
                
                # Convert to datetime if needed
                if not isinstance(start_time, pd.Timestamp):
                    start_time = pd.to_datetime(start_time)
                if not isinstance(end_time, pd.Timestamp):
                    end_time = pd.to_datetime(end_time)
                
                # Ensure times are within range
                if start_time > max_time or end_time < min_time:
                    continue
                
                start_time = max(start_time, min_time)
                end_time = min(end_time, max_time)
                
                top = zone_data["top"]
                bottom = zone_data["bottom"]
                
                # Determine zone color based on status
                if zone_data.get("is_broken", False):
                    fill_color = "#e0e0e0"  # Broken zones: light gray (visible but subtle)
                    line_color = "#808080"  # Gray border
                    line_width = 1
                    line_dash = "dashed"
                    fill_alpha = 0.3        # Increased opacity to be visible
                    line_alpha = 0.5
                else:
                    fill_color = "#f23645"  # Active resistance: red
                    line_color = "#f23645"  # Red border
                    line_width = 2
                    line_dash = "solid"
                    fill_alpha = 0.25
                    line_alpha = 0.5
                
                # Add rectangle for zone (TradingView box style)
                zone_box = BoxAnnotation(
                    left=start_time,
                    right=end_time,
                    top=top,
                    bottom=bottom,
                    fill_color=fill_color,
                    line_color=line_color,
                    line_width=line_width,
                    line_dash=line_dash,
                    fill_alpha=fill_alpha,
                    line_alpha=line_alpha,
                )
                p1.add_layout(zone_box)
                
                # Add label
                touches = zone_data.get("touches", 1)
                fail_count = zone_data.get("fail_count", 0)
                if not zone_data.get("is_broken", False):
                    label_text = str(touches) if touches > 1 else ""
                    if fail_count > 0:
                        label_text = f"{touches} (F:{fail_count})"
                    
                    if label_text:
                        zone_label = Label(
                            x=start_time,
                            y=top,
                            text=label_text,
                            text_font_size="10pt",
                            text_color=line_color,
                            background_fill_color="#ffffff",
                            background_fill_alpha=0.8,
                            border_line_color=line_color,
                            border_line_width=1,
                            x_offset=5,
                            y_offset=-5,
                        )
                        p1.add_layout(zone_label)
        else:
            print("Warning: No zones to plot!")
        
        # Create volume chart with matching width
        p2 = figure(
            x_axis_type="datetime",
            width=1800,  # Match price chart width
            height=200,
            x_range=p1.x_range,  # Share x-axis with price chart
            tools="pan,wheel_zoom,box_zoom,reset,save",
            toolbar_location=None,
            background_fill_color="#ffffff",
            sizing_mode="scale_width",  # Allow responsive sizing
        )
        p2.xaxis.axis_label = "Time"
        p2.yaxis.axis_label = "Volume"
        p2.yaxis.axis_label_text_font_size = "12pt"
        p2.xaxis.axis_label_text_font_size = "12pt"
        # Format y-axis to avoid scientific notation
        p2.yaxis.formatter = NumeralTickFormatter(format="0,0")
        
        # Add volume bars
        p2.vbar(
            'date',
            bar_width,
            'volume',
            fill_color='color',
            line_color="black",
            source=source,
            line_width=0.5,
            alpha=0.6,
        )
        
        # Combine plots
        layout = column(p1, p2)
        
        # Save plot as interactive HTML
        htf_plot_path = output_dir / f"{strategy_name}_{symbol}_{timeframe}_4H_plot.html"
        output_file(str(htf_plot_path))
        save(layout)
        print(f"4H timeframe interactive plot with S/R zones saved to: {htf_plot_path}")
        
    except ImportError:
        print("Warning: bokeh not available. Install with: pip install bokeh")
        print("Falling back to basic visualization...")
    except Exception as e:
        print(f"Warning: Could not generate 4H plot: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # =====================================================================
    # CONFIGURATION - Modify these parameters for your backtest
    # =====================================================================
    
    # Import your strategy here
    from strategies.sr_short_4h_resistance import SRShort4HResistance
    
    # Trading parameters
    SYMBOL = "BTCUSDT"
    TIMEFRAME = "15m"  # Input timeframe (strategy will resample to 4H internally)
    
    # Date range (modify as needed)
    END_TIME = pd.Timestamp.utcnow().floor("min")
    DAYS = 30  # Increased to 200 days to ensure sufficient data for 4H pivot detection (need ~17 days min)
    START_TIME = END_TIME - pd.Timedelta(days=DAYS)
    
    # Or specify exact dates:
    START_TIME = pd.Timestamp("2025-10-01", tz="UTC")
    END_TIME = pd.Timestamp("2025-12-01", tz="UTC")
    
    # Data source
    SOURCE = "okx"  # 'okx' or 'binance'
    
    # Backtest settings
    INITIAL_CAPITAL = 1000000  # Increased for BTC (1 BTC ~ $60k+)
    COMMISSION = 0.001  # 0.1%
    TRADE_ON_CLOSE = True
    EXCLUSIVE_ORDERS = False  # Set to False to allow multiple positions
    
    # Strategy-specific parameters (modify based on your strategy)
    STRATEGY_PARAMS = {
        # SR Short 4H Resistance parameters
        "left_len": 90,
        "right_len": 10,
        "merge_atr_mult": 3.5,
        "break_tol_atr": 0.5,
        "min_touches": 1,
        "max_retries": 3,
        "global_cd": 30,
        "price_filter_pct": 1.5,
        "min_position_distance_pct": 1.5,
        "max_positions": 5,
        "risk_per_trade_pct": 0.5,
        "leverage": 5.0,
        "strategy_sl_percent": 2.0,
        "breakeven_ratio": 2.33,
        "breakeven_close_pct": 30.0,
        "tp1_atr_mult": 3.0,
        "tp1_close_pct": 40.0,
        "tp2_atr_mult": 5.0,
        "tp2_close_pct": 40.0,
        "tp3_atr_mult": 8.0,
        "tp3_close_pct": 20.0,
    }
    
    # Output settings
    OUTPUT_DIR = None  # None = use default (run/scripts/backtest/results/)
    PLOT = True
    
    # =====================================================================
    # Run backtest
    # =====================================================================
    
    # 4H S/R data settings (only used for SRShort4HResistance)
    # Option 1: Use lookback days (from backtest start time)
    HTF_LOOKBACK_DAYS = 200  # 4H数据回溯天数（默认200天）
    
    # Option 2: Specify exact 4H data range (overrides lookback_days)
    # HTF_START_TIME = pd.Timestamp("2025-01-01", tz="UTC")  # 4H数据开始时间
    # HTF_END_TIME = pd.Timestamp("2025-12-01", tz="UTC")    # 4H数据结束时间
    
    stats = run_strategy_backtest(
        strategy_class=SRShort4HResistance,
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start_time=START_TIME,
        end_time=END_TIME,
        source=SOURCE,
        cash=INITIAL_CAPITAL,
        commission=COMMISSION,
        trade_on_close=TRADE_ON_CLOSE,
        exclusive_orders=EXCLUSIVE_ORDERS,
        strategy_params=STRATEGY_PARAMS,
        output_dir=OUTPUT_DIR,
        plot=PLOT,
        # 4H S/R data parameters
        htf_lookback_days=HTF_LOOKBACK_DAYS,  # 修改这里来改变4H数据长度
        # htf_start_time=HTF_START_TIME,       # 或者使用精确时间范围
        # htf_end_time=HTF_END_TIME,
    )
    
    print("\nBacktest completed!")


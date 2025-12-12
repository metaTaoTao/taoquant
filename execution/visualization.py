"""
Backtest visualization module.

Creates interactive plots similar to backtesting.py using Bokeh:
- Candlestick charts with price data
- Trade entry/exit markers
- Support/Resistance zones
- Equity curve
- Drawdown visualization
- Volume bars

Uses Bokeh for interactive HTML charts, mimicking backtesting.py's style.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

from execution.engines.base import BacktestResult

try:
    from bokeh.plotting import figure, output_file, save
    from bokeh.models import (
        ColumnDataSource,
        HoverTool,
        BoxAnnotation,
        Label,
        NumeralTickFormatter,
        DatetimeTickFormatter,
        Span,
        Legend,
        LegendItem,
    )
    from bokeh.layouts import column, gridplot
    from bokeh.io import curdoc
    BOKEH_AVAILABLE = True
except ImportError:
    BOKEH_AVAILABLE = False


def plot_backtest_results(
    result: BacktestResult,
    data: pd.DataFrame,
    zones_data: Optional[pd.DataFrame] = None,
    orders_data: Optional[pd.DataFrame] = None,
    output_path: Optional[Path] = None,
    title: str = "Backtest Results",
    show_trades: bool = True,
) -> None:
    """
    Create interactive backtest visualization with candlesticks, trades, and zones using Bokeh.

    Similar to backtesting.py's plot() method, using Bokeh for interactivity.

    Parameters
    ----------
    result : BacktestResult
        Backtest results from engine
    data : pd.DataFrame
        OHLCV data used in backtest
    zones_data : Optional[pd.DataFrame]
        DataFrame with zone columns (zone_top, zone_bottom, zone_touches, zone_is_broken)
        If provided, will plot support/resistance zones
    output_path : Optional[Path]
        Path to save HTML file. If None, returns without saving.
    title : str
        Plot title
    show_trades : bool
        Whether to show trade markers on the chart

    Examples
    --------
    >>> from execution.visualization import plot_backtest_results
    >>> plot_backtest_results(result, data, zones_data, output_path="backtest_plot.html")
    """
    if not BOKEH_AVAILABLE:
        raise ImportError(
            "Bokeh is required for plotting. Install with: pip install bokeh"
        )

    # Prepare data
    plot_data = data.copy()
    
    # Ensure index is DatetimeIndex
    if not isinstance(plot_data.index, pd.DatetimeIndex):
        plot_data.index = pd.to_datetime(plot_data.index)
    
    # Ensure column names are lowercase
    column_mapping = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    for old_col, new_col in column_mapping.items():
        if old_col in plot_data.columns and new_col not in plot_data.columns:
            plot_data.rename(columns={old_col: new_col}, inplace=True)
    
    # Required columns
    required_cols = ["open", "high", "low", "close"]
    missing_cols = [col for col in required_cols if col not in plot_data.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
    
    # Prepare data for Bokeh
    plot_data = plot_data.copy()
    plot_data['date'] = plot_data.index
    plot_data['color'] = [
        '#26a69a' if close >= open else '#ef5350'
        for close, open in zip(plot_data['close'], plot_data['open'])
    ]
    
    # Ensure volume column exists and is numeric
    if 'volume' not in plot_data.columns:
        # Try to find volume in different case
        volume_cols = [col for col in plot_data.columns if col.lower() == 'volume']
        if volume_cols:
            plot_data['volume'] = plot_data[volume_cols[0]]
        else:
            # Create dummy volume column if missing
            plot_data['volume'] = 0
    elif not pd.api.types.is_numeric_dtype(plot_data['volume']):
        # Convert to numeric if possible
        plot_data['volume'] = pd.to_numeric(plot_data['volume'], errors='coerce').fillna(0)
    
    # Calculate bar width (80% of time interval in milliseconds)
    if len(plot_data) > 1:
        time_delta_ms = (plot_data.index[1] - plot_data.index[0]).total_seconds() * 1000
        bar_width = time_delta_ms * 0.8
    else:
        bar_width = pd.Timedelta(hours=1).total_seconds() * 1000 * 0.8  # Default
    
    # Create ColumnDataSource
    source = ColumnDataSource(plot_data)
    
    # ============================================================================
    # 1. Price Chart with Candlesticks
    # ============================================================================
    
    # Create figure without any default tools that might show index
    # We'll add tools manually to have full control
    p1 = figure(
        x_axis_type="datetime",
        width=1400,
        height=600,
        title=title,
        tools=[],  # Start with empty tools list
        toolbar_location="above",
        background_fill_color="#ffffff",
        sizing_mode="scale_width",
    )
    # Add only the tools we want (no hover/inspect by default)
    from bokeh.models import PanTool, WheelZoomTool, BoxZoomTool, ResetTool, SaveTool
    p1.add_tools(PanTool(), WheelZoomTool(), BoxZoomTool(), ResetTool(), SaveTool())
    p1.xaxis.axis_label = "Time"
    p1.yaxis.axis_label = "Price"
    p1.yaxis.formatter = NumeralTickFormatter(format="0,0")
    p1.xaxis.formatter = DatetimeTickFormatter(
        days="%d %b",
        months="%b %Y",
    )
    
    # Add candlestick: segments for high-low (no hover on this)
    segment_renderer = p1.segment('date', 'high', 'date', 'low', color="black", source=source, line_width=1)
    
    # Add candlestick: vbars for open-close (hover only on this)
    vbar_renderer = p1.vbar(
        'date',
        bar_width,
        'open',
        'close',
        fill_color='color',
        line_color="black",
        source=source,
        line_width=1,
        hatch_pattern=None,  # Explicitly disable hatch to avoid errors
        hatch_alpha=0,
    )
    
    # Add hover tool for candlesticks (only on vbar, not segment)
    # Similar to TradingView: show time and OHLC data, no index
    hover1 = HoverTool(
        tooltips=[
            ("Time", "@date{%Y-%m-%d %H:%M}"),
            ("Open", "@open{0,0.00}"),
            ("High", "@high{0,0.00}"),
            ("Low", "@low{0,0.00}"),
            ("Close", "@close{0,0.00}"),
            ("Volume", "@volume{0,0.00 a}"),
        ],
        formatters={
            '@date': 'datetime',
        },
        mode='vline',  # Show tooltip for all bars at the same x position (like TradingView)
        renderers=[vbar_renderer],  # Only show hover on vbar, not segment
        show_arrow=False,  # Don't show arrow
    )
    # Remove default hover tool if it exists and add our custom one
    # This ensures only our custom tooltip is shown (no index)
    # First, remove any existing hover tools and inspect tools
    hover_tools = [tool for tool in p1.tools if isinstance(tool, HoverTool)]
    for tool in hover_tools:
        p1.tools.remove(tool)
    # Disable default inspect tool completely
    p1.toolbar.active_inspect = None
    # Add our custom hover tool
    p1.add_tools(hover1)
    # Set it as the active inspect tool
    p1.toolbar.active_inspect = hover1
    # Ensure no other inspect tools are active
    for tool in p1.tools:
        if isinstance(tool, HoverTool) and tool != hover1:
            p1.tools.remove(tool)
    
    # Plot support/resistance zones if provided
    if zones_data is not None:
        _plot_zones_bokeh(p1, zones_data, plot_data.index)
    
    # Plot trade entries and exits
    # Use orders_data if available (more accurate for partial exits), otherwise use trades
    if show_trades:
        if orders_data is not None and not orders_data.empty:
            # Plot from orders.csv (includes all individual orders including entries)
            _plot_orders_bokeh(p1, orders_data, plot_data)
        elif not result.trades.empty:
            # Fallback to trades.csv (may miss some entries due to partial exits)
            _plot_trades_bokeh(p1, result.trades, plot_data)
    
    # ============================================================================
    # 2. Volume Chart (moved before Equity Curve)
    # ============================================================================
    
    p3 = None
    # Check if volume exists and has valid data
    has_volume = "volume" in plot_data.columns and plot_data["volume"].notna().any() and (plot_data["volume"] > 0).any()
    if has_volume:
        # Calculate volume range for better scaling
        volume_max = plot_data["volume"].max()
        volume_min = plot_data["volume"].min()
        # Use a more compact range: from 0 to 110% of max volume
        volume_y_range = (0, volume_max * 1.1) if volume_max > 0 else None
        
        p3 = figure(
            x_axis_type="datetime",
            width=1400,
            height=150,
            x_range=p1.x_range,  # Share x-axis with price chart
            y_range=volume_y_range,  # Set compact y-axis range
            tools="pan,wheel_zoom,box_zoom,reset,save",
            toolbar_location=None,
            background_fill_color="#ffffff",
            sizing_mode="scale_width",
        )
        p3.xaxis.axis_label = "Time"
        p3.yaxis.axis_label = "Volume"
        # Use more compact formatter (e.g., "1.5K" instead of "1,500")
        p3.yaxis.formatter = NumeralTickFormatter(format="0.0a")  # "a" suffix for K, M, etc.
        
        # Add volume bars with hover tool
        volume_renderer = p3.vbar(
            'date',
            bar_width,
            'volume',
            fill_color='color',
            line_color="black",
            source=source,
            line_width=0.5,
            alpha=0.6,
            hatch_pattern=None,  # Explicitly disable hatch to avoid errors
            hatch_alpha=0,
        )
        
        hover3 = HoverTool(
            tooltips=[
                ("Time", "@date{%F %H:%M}"),
                ("Volume", "@volume{0,0}"),
            ],
            formatters={
                '@date': 'datetime',
            },
            mode='mouse',  # Use 'mouse' to avoid duplicate tooltips
            renderers=[volume_renderer],
        )
        p3.add_tools(hover3)
    
    # ============================================================================
    # 3. Equity Curve
    # ============================================================================
    
    p2 = None
    if not result.equity_curve.empty:
        equity = result.equity_curve["equity"]
        
        # Normalize equity to percentage (starting from 100%)
        initial_equity = equity.iloc[0]
        equity_pct = (equity / initial_equity) * 100
        
        # Calculate drawdown
        peak = equity_pct.expanding().max()
        drawdown_pct = equity_pct - peak
        
        # Prepare equity data
        equity_data = pd.DataFrame({
            'date': equity.index,
            'equity': equity_pct.values,
            'drawdown': drawdown_pct.values,
        })
        equity_source = ColumnDataSource(equity_data)
        
        p2 = figure(
            x_axis_type="datetime",
            width=1400,
            height=200,
            x_range=p1.x_range,  # Share x-axis with price chart
            tools="pan,wheel_zoom,box_zoom,reset,save,crosshair",
            toolbar_location=None,
            background_fill_color="#ffffff",
            sizing_mode="scale_width",
        )
        p2.xaxis.axis_label = "Time"
        p2.yaxis.axis_label = "Equity / Drawdown %"
        p2.yaxis.formatter = NumeralTickFormatter(format="0.00")
        
        # Plot equity curve
        equity_line = p2.line(
            'date',
            'equity',
            source=equity_source,
            line_color="#1f77b4",
            line_width=1.5,
            legend_label="Equity",
        )
        
        # Plot drawdown (filled area)
        # Note: When using source, all color parameters must be literals (not field references)
        # or all must be field references. Since we're using a literal color, we don't need hatch.
        # For Bokeh 3.8+, we need to explicitly set hatch parameters to avoid validation errors
        p2.patch(
            x='date',
            y='drawdown',
            source=equity_source,
            fill_color="#ffcb66",
            fill_alpha=0.2,
            line_color="#ffcb66",
            line_alpha=0.3,
            legend_label="Drawdown",
        )
        
        # Add hover tool for equity
        hover2 = HoverTool(
            tooltips=[
                ("Time", "@date{%F %H:%M}"),
                ("Equity", "@equity{0.00}%"),
                ("Drawdown", "@drawdown{0.00}%"),
            ],
            formatters={
                '@date': 'datetime',
            },
            mode='vline',
            renderers=[equity_line],
        )
        p2.add_tools(hover2)
        
        # Add reference line at 100%
        p2.line(
            [equity.index[0], equity.index[-1]],
            [100, 100],
            line_color="red",
            line_width=2,
            line_dash="dashed",
            legend_label="Initial (100%)",
        )
        
        # Add max drawdown marker
        max_dd_idx = drawdown_pct.idxmin()
        max_dd_value = drawdown_pct.min()
        if pd.notna(max_dd_idx) and pd.notna(max_dd_value):
            max_dd_marker = p2.scatter(
                [max_dd_idx],
                [max_dd_value],
                size=8,
                color="red",
                legend_label=f"Max Dd ({max_dd_value:.2f}%)",
            )
        
        p2.legend.location = "top_left"
        p2.legend.label_text_font_size = "8pt"
    
    # ============================================================================
    # Combine plots and save
    # ============================================================================
    
    # Create layout: Price -> Volume -> Equity
    plots = [p1]
    if p3 is not None:  # Volume chart (before equity)
        plots.append(p3)
    if p2 is not None:  # Equity chart (after volume)
        plots.append(p2)
    
    layout = column(*plots, sizing_mode="scale_width")
    
    # Save if path provided
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_file(str(output_path))
        save(layout)
        print(f"[Plot] Plot saved to: {output_path}")
    else:
        # Return layout for display (e.g., in notebook)
        return layout


def _plot_zones_bokeh(
    p: figure,
    zones_data: pd.DataFrame,
    data_index: pd.DatetimeIndex,
) -> None:
    """
    Plot support/resistance zones on the Bokeh chart.

    Parameters
    ----------
    p : figure
        Bokeh figure to add zones to
    zones_data : pd.DataFrame
        Data with zone columns (zone_top, zone_bottom, zone_touches, zone_is_broken)
    data_index : pd.DatetimeIndex
        Time index of the data
    """
    if "zone_top" not in zones_data.columns or "zone_bottom" not in zones_data.columns:
        return
    
    min_time = data_index.min()
    max_time = data_index.max()
    
    # Group consecutive zones
    zones = []
    current_zone = None
    
    for i, (idx, row_data) in enumerate(zones_data.iterrows()):
        if pd.notna(row_data.get("zone_top")) and pd.notna(row_data.get("zone_bottom")):
            zone_top = row_data["zone_top"]
            zone_bottom = row_data["zone_bottom"]
            is_broken = row_data.get("zone_is_broken", False)
            touches = row_data.get("zone_touches", 1)
            
            # Check if this is a continuation of previous zone
            if (
                current_zone is not None
                and abs(zone_top - current_zone["top"]) / current_zone["top"] < 0.01
                and abs(zone_bottom - current_zone["bottom"]) / current_zone["bottom"] < 0.01
            ):
                # Extend current zone
                current_zone["end_time"] = idx
                current_zone["touches"] = max(current_zone["touches"], touches)
                if is_broken:
                    current_zone["is_broken"] = True
            else:
                # Save previous zone and start new one
                if current_zone is not None:
                    zones.append(current_zone)
                
                current_zone = {
                    "start_time": idx,
                    "end_time": idx,
                    "top": zone_top,
                    "bottom": zone_bottom,
                    "is_broken": is_broken,
                    "touches": touches,
                }
    
    # Add last zone
    if current_zone is not None:
        zones.append(current_zone)
    
    # Plot zones as rectangles (similar to backtesting.py style)
    for zone in zones:
        start_time = zone["start_time"]
        end_time = zone["end_time"]
        
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
        
        top = zone["top"]
        bottom = zone["bottom"]
        
        # Determine zone color based on status
        # Active zones: Red (warning - active resistance)
        # Broken zones: Light blue (clearly visible on white background, cool color indicates inactive)
        if zone.get("is_broken", False):
            fill_color = "#b3d9ff"  # Broken zones: light blue (clearly visible on white)
            line_color = "#4da6ff"  # Medium blue border (good contrast, not too dark)
            line_width = 1
            line_dash = "dashed"  # Dashed to indicate it's no longer active
            fill_alpha = 0.4  # Slightly more opaque for better visibility
            line_alpha = 0.7  # More visible border
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
        p.add_layout(zone_box)
        
        # Add label (touches count)
        touches = zone.get("touches", 1)
        fail_count = zone.get("fail_count", 0)
        if not zone.get("is_broken", False):
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
                p.add_layout(zone_label)


def _plot_orders_bokeh(
    p: figure,
    orders: pd.DataFrame,
    data: pd.DataFrame,
) -> None:
    """
    Plot order entry and exit points from orders.csv (more accurate than trades.csv for partial exits).
    Also supports grid strategy orders (buy/sell with direction).

    Parameters
    ----------
    p : figure
        Bokeh figure to add orders to
    orders : pd.DataFrame
        Orders DataFrame with timestamp, price, size, direction, order_type
        For grid strategy: direction='buy' or 'sell', order_type='ENTRY' or 'EXIT'
    data : pd.DataFrame
        OHLCV data
    """
    if orders.empty:
        return
    
    # Prepare order data
    buy_times = []
    buy_prices = []
    sell_times = []
    sell_prices = []
    buy_sizes = []
    sell_sizes = []
    
    # Ensure timestamp is datetime
    if 'timestamp' in orders.columns:
        orders['timestamp'] = pd.to_datetime(orders['timestamp'])
    elif 'time' in orders.columns:
        orders['timestamp'] = pd.to_datetime(orders['time'])
    
    # Check if this is grid strategy format (has 'direction' column)
    is_grid_strategy = 'direction' in orders.columns
    
    for _, order in orders.iterrows():
        timestamp = order.get("timestamp") or order.get("time")
        price = order.get("price")
        size = abs(order.get("size", 0))  # Use absolute size
        direction = order.get("direction", "")
        order_type = order.get("order_type", "")
        
        if pd.isna(timestamp) or pd.isna(price) or price <= 0:
            continue
        
        timestamp_ts = pd.Timestamp(timestamp)
        
        if is_grid_strategy:
            # Grid strategy: use direction directly
            if direction == 'buy':
                buy_times.append(timestamp)
                buy_prices.append(price)
                buy_sizes.append(size)
            elif direction == 'sell':
                sell_times.append(timestamp)
                sell_prices.append(price)
                sell_sizes.append(size)
        else:
            # Traditional strategy: use order_type
            if order_type in ["ENTRY", "2B_ENTRY"]:
                # Entry orders
                if direction == 'buy' or size > 0:
                    buy_times.append(timestamp)
                    buy_prices.append(price)
                    buy_sizes.append(size)
                else:
                    sell_times.append(timestamp)
                    sell_prices.append(price)
                    sell_sizes.append(size)
            elif order_type in ["TP1", "TP2", "SL", "EXIT"]:
                # Exit orders
                if direction == 'sell' or size < 0:
                    sell_times.append(timestamp)
                    sell_prices.append(price)
                    sell_sizes.append(abs(size))
                else:
                    buy_times.append(timestamp)
                    buy_prices.append(price)
                    buy_sizes.append(size)
    
    # Plot buy markers (green upward triangles)
    if buy_times:
        buy_source = ColumnDataSource({
            'date': buy_times,
            'price': buy_prices,
            'size': buy_sizes[:len(buy_times)],
        })
        buy_markers = p.scatter(
            x='date',
            y='price',
            source=buy_source,
            size=12,
            marker="triangle",
            color="#26a69a",  # Green for buy
            fill_alpha=0.8,
            line_color="#ffffff",
            line_width=1.5,
            legend_label="买入",
        )
        
        # Add hover tool for buy orders
        buy_hover = HoverTool(
            tooltips=[
                ("时间", "@date{%Y-%m-%d %H:%M}"),
                ("价格", "@price{0,0.00}"),
                ("数量", "@size{0,0.0000}"),
            ],
            formatters={
                '@date': 'datetime',
            },
            mode='mouse',
            renderers=[buy_markers],
        )
        p.add_tools(buy_hover)
    
    # Plot sell markers (red downward triangles)
    if sell_times:
        sell_source = ColumnDataSource({
            'date': sell_times,
            'price': sell_prices,
            'size': sell_sizes[:len(sell_times)],
        })
        sell_markers = p.scatter(
            x='date',
            y='price',
            source=sell_source,
            size=12,
            marker="inverted_triangle",
            color="#ef5350",  # Red for sell
            fill_alpha=0.8,
            line_color="#ffffff",
            line_width=1.5,
            legend_label="卖出",
        )
        
        # Add hover tool for sell orders
        sell_hover = HoverTool(
            tooltips=[
                ("时间", "@date{%Y-%m-%d %H:%M}"),
                ("价格", "@price{0,0.00}"),
                ("数量", "@size{0,0.0000}"),
            ],
            formatters={
                '@date': 'datetime',
            },
            mode='mouse',
            renderers=[sell_markers],
        )
        p.add_tools(sell_hover)


def _plot_trades_bokeh(
    p: figure,
    trades: pd.DataFrame,
    data: pd.DataFrame,
) -> None:
    """
    Plot trade entry and exit points on the Bokeh chart.

    Parameters
    ----------
    p : figure
        Bokeh figure to add trades to
    trades : pd.DataFrame
        Trades DataFrame with entry_time, exit_time, entry_price, exit_price, pnl
    data : pd.DataFrame
        OHLCV data
    """
    if trades.empty:
        return
    
    # Prepare trade data
    entry_times = []
    entry_prices = []
    exit_times = []
    exit_prices = []
    pnl_values = []
    trade_sizes = []
    
    # Ensure entry_time and exit_time are datetime
    if 'entry_time' in trades.columns:
        trades['entry_time'] = pd.to_datetime(trades['entry_time'])
    if 'exit_time' in trades.columns:
        trades['exit_time'] = pd.to_datetime(trades['exit_time'])
    
    # Track unique entries to avoid duplicates (for partial exits, same entry appears multiple times)
    seen_entries = set()
    
    for _, trade in trades.iterrows():
        entry_time = trade.get("entry_time")
        exit_time = trade.get("exit_time")
        entry_price = trade.get("entry_price")
        exit_price = trade.get("exit_price")
        pnl = trade.get("pnl", 0)
        size = trade.get("size", 0)
        
        # If entry_price or exit_price are missing, get from data
        if pd.notna(entry_time):
            # Check if we've already added this entry (for partial exits)
            entry_key = pd.Timestamp(entry_time)
            if entry_key not in seen_entries:
                if pd.isna(entry_price) or entry_price == 0:
                    # Try to find price from data at entry_time
                    try:
                        entry_time_ts = pd.Timestamp(entry_time)
                        # Find the closest bar to entry_time
                        entry_idx = data.index.get_indexer([entry_time_ts], method='nearest')[0]
                        if entry_idx >= 0 and entry_idx < len(data):
                            entry_price = data.iloc[entry_idx]['close']
                    except Exception as e:
                        # Silently skip if we can't find the price
                        pass
                
                if pd.notna(entry_price) and entry_price > 0:
                    entry_times.append(entry_time)
                    entry_prices.append(entry_price)
                    trade_sizes.append(size)
                    seen_entries.add(entry_key)
                else:
                    # Debug: entry_price is still missing or zero
                    print(f"Debug: Skipping entry at {entry_time} - entry_price={entry_price}")
        
        if pd.notna(exit_time):
            if pd.isna(exit_price) or exit_price == 0:
                # Try to find price from data at exit_time
                try:
                    exit_time_ts = pd.Timestamp(exit_time)
                    # Find the closest bar to exit_time
                    exit_idx = data.index.get_indexer([exit_time_ts], method='nearest')[0]
                    if exit_idx >= 0 and exit_idx < len(data):
                        exit_price = data.iloc[exit_idx]['close']
                except Exception as e:
                    print(f"Warning: Could not find exit price for {exit_time}: {e}")
                    continue
            
            if pd.notna(exit_price) and exit_price > 0:
                exit_times.append(exit_time)
                exit_prices.append(exit_price)
                # Calculate P&L if not available
                if pd.isna(pnl) or pnl == 0:
                    # For short: profit when exit_price < entry_price
                    # Find corresponding entry_price - match by entry_time
                    matching_entry_idx = None
                    for i, et in enumerate(entry_times):
                        if pd.Timestamp(et) == pd.Timestamp(entry_time):  # Same entry_time means same trade
                            matching_entry_idx = i
                            break
                    
                    if matching_entry_idx is not None and matching_entry_idx < len(entry_prices):
                        entry_price_for_exit = entry_prices[matching_entry_idx]
                        # For short: return = (entry_price - exit_price) / entry_price
                        pnl = (entry_price_for_exit - exit_price) / entry_price_for_exit * 100
                    elif 'return_pct' in trade:
                        pnl = trade['return_pct'] * 100
                pnl_values.append(pnl)
    
    # Plot entry points (triangle-down for short entry, matching backtesting.py style)
    print(f"Debug: Found {len(entry_times)} entry points to plot")
    if entry_times:
        entry_source = ColumnDataSource({
            'date': entry_times,
            'price': entry_prices,
            'size': trade_sizes[:len(entry_times)],
        })
        
        entry_markers = p.scatter(
            'date',
            'price',
            source=entry_source,
            size=15,  # Increased size for better visibility
            marker="inverted_triangle",
            color="#ef5350",  # Red for short entry
            fill_alpha=0.9,  # More opaque for better visibility
            line_color="white",
            line_width=2,
            legend_label="Entry (Short)",
        )
        
        # Add hover tool for entries
        entry_hover = HoverTool(
            tooltips=[
                ("Time", "@date{%F %H:%M}"),
                ("Price", "@price{0,0.00}"),
                ("Size", "@size{0,0}"),
            ],
            formatters={
                '@date': 'datetime',
            },
            mode='mouse',
            renderers=[entry_markers],
        )
        p.add_tools(entry_hover)
    
    # Plot exit points (triangle-up, colored by P&L)
    if exit_times:
        exit_colors = ["#26a69a" if pnl > 0 else "#ef5350" for pnl in pnl_values]
        
        exit_source = ColumnDataSource({
            'date': exit_times,
            'price': exit_prices,
            'pnl': pnl_values,
            'color': exit_colors,  # Add colors to source for proper referencing
        })
        
        exit_markers = p.scatter(
            'date',
            'price',
            source=exit_source,
            size=15,  # Increased size for better visibility
            marker="triangle",
            color='color',  # Reference color from source
            fill_alpha=0.9,  # More opaque for better visibility
            line_color="white",
            line_width=2,
            legend_label="Exit",
        )
        
        # Add hover tool for exits
        exit_hover = HoverTool(
            tooltips=[
                ("Time", "@date{%F %H:%M}"),
                ("Price", "@price{0,0.00}"),
                ("P&L", "@pnl{0,0.00}"),
            ],
            formatters={
                '@date': 'datetime',
            },
            mode='mouse',
            renderers=[exit_markers],
        )
        p.add_tools(exit_hover)
        
        # Draw lines connecting entry to exit (matching backtesting.py style)
        # Match entries and exits by index (assuming they're in order)
        # For partial exits, there may be multiple exits per entry
        entry_idx = 0
        for i, (exit_time, exit_price) in enumerate(zip(exit_times, exit_prices)):
            # Find the corresponding entry (most recent entry before this exit)
            while entry_idx < len(entry_times) and entry_times[entry_idx] <= exit_time:
                entry_idx += 1
            if entry_idx > 0:
                # Use the entry just before this exit
                matching_entry_idx = entry_idx - 1
                entry_time = entry_times[matching_entry_idx]
                entry_price = entry_prices[matching_entry_idx]
                
                pnl = pnl_values[i] if i < len(pnl_values) else 0
                line_color = "#26a69a" if pnl > 0 else "#ef5350"
                line_alpha = 0.3 if pnl < 0 else 0.5
                
                p.line(
                    [entry_time, exit_time],
                    [entry_price, exit_price],
                    line_color=line_color,
                    line_width=2,
                    line_dash="dotted",
                    alpha=line_alpha,
                )
    
    # Add legend only if there are legend items
    if p.legend:
        p.legend.location = "top_left"
        p.legend.label_text_font_size = "8pt"

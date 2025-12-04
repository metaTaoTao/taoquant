"""
Visualize SR zone detection with candlestick chart and zone boxes.
Similar to TradingView's SR indicator visualization.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from data import DataManager
from strategies.signal_based.sr_short import SRShortStrategy, SRShortConfig
from utils.resample import resample_ohlcv
from analytics.indicators.sr_zones import compute_sr_zones

try:
    from bokeh.plotting import figure, output_file, save
    from bokeh.models import (
        ColumnDataSource,
        HoverTool,
        BoxAnnotation,
        Label,
        NumeralTickFormatter,
        DatetimeTickFormatter,
        Legend,
    )
    from bokeh.layouts import column
    BOKEH_AVAILABLE = True
except ImportError:
    BOKEH_AVAILABLE = False
    print("Bokeh is required. Install with: pip install bokeh")
    sys.exit(1)

print("=" * 80)
print("SR Zone Visualization")
print("=" * 80)

# Load data
# Note: For visualization, we need to load data from earlier to include HTF lookback
# Strategy uses htf_lookback=300 bars, so we need to go back 300*4 hours = 1200 hours = 50 days
backtest_start = '2025-07-01'
backtest_end = '2025-10-01'
htf_lookback = 300
htf_timeframe = '4h'

# Calculate the start time for data loading (backtest_start - htf_lookback bars)
# 4H = 4 hours per bar, so 300 bars = 300 * 4 = 1200 hours = 50 days
data_start = pd.Timestamp(backtest_start, tz='UTC') - pd.Timedelta(hours=htf_lookback * 4)

print(f"[Data] Loading data from {data_start} to {backtest_end}")
print(f"      (Backtest: {backtest_start} to {backtest_end}, HTF lookback: {htf_lookback} bars)")

data_manager = DataManager()
data_full = data_manager.get_klines('BTCUSDT', '15m', data_start.strftime('%Y-%m-%d'), backtest_end, source='okx')

# Filter to backtest range for visualization (but zones will use full data)
data = data_full[data_full.index >= backtest_start].copy()

# Create strategy
config = SRShortConfig(
    name="SR Short 4H",
    description="SR Short strategy with 4H HTF",
    left_len=30,
    right_len=5,
    merge_atr_mult=3.5,
    htf_timeframe=htf_timeframe,
    htf_lookback=htf_lookback,
)
strategy = SRShortStrategy(config)

# Compute indicators (this uses the same logic as strategy)
# Strategy will use full data (from data_start) for HTF zone detection
print("\n[Strategy] Computing indicators...")
data_with_indicators = strategy.compute_indicators(data_full)

# Get zones directly from 4H HTF data (not aligned to 15m)
# This ensures we visualize the actual 4H zones
# Use full data for HTF resampling to include lookback period
print(f"\n[4H Zones] Computing zones on 4H timeframe...")
print(f"      Using data from {data_full.index[0]} to {data_full.index[-1]} for HTF resampling")
data_htf = resample_ohlcv(data_full, config.htf_timeframe)
print(f"      Resampled to {len(data_htf)} 4H bars (from {data_htf.index[0]} to {data_htf.index[-1]})")

zones_htf = compute_sr_zones(
    data_htf,
    left_len=config.left_len,
    right_len=config.right_len,
    merge_atr_mult=config.merge_atr_mult,
)

print(f"[4H Zones] Found zones on {zones_htf['zone_top'].notna().sum()} 4H bars")
print(f"[4H Zones] Using 4H HTF zones (not 15m aligned) for visualization")

# Prepare data for plotting (use only backtest range for 15m chart)
plot_data = data_with_indicators[data_with_indicators.index >= backtest_start].copy()
plot_data['date'] = pd.to_datetime(plot_data.index)

# Prepare 4H data for plotting
# IMPORTANT: Include data from data_start (not just backtest_start) to show the lookback period
# This allows us to see the 300 4H bars before 10.1 that were used for zone detection
# Ensure data_start is timezone-aware to match data_htf.index
data_start_tz = pd.Timestamp(data_start).tz_localize('UTC') if data_start.tz is None else data_start
data_htf_plot = data_htf[data_htf.index >= data_start_tz].copy()
data_htf_plot['date'] = pd.to_datetime(data_htf_plot.index)

print(f"\n[4H Chart] Displaying {len(data_htf_plot)} 4H bars (from {data_htf_plot.index[0]} to {data_htf_plot.index[-1]})")
print(f"           This includes the {htf_lookback} bars lookback period before {backtest_start}")

# Create candlestick data for 15m
plot_data['color'] = np.where(plot_data['close'] >= plot_data['open'], 'green', 'red')
plot_data['width'] = pd.Timedelta(minutes=15).total_seconds() * 1000  # 15 minutes in milliseconds

# Create candlestick data for 4H
data_htf_plot['color'] = np.where(data_htf_plot['close'] >= data_htf_plot['open'], 'green', 'red')
data_htf_plot['width'] = pd.Timedelta(hours=4).total_seconds() * 1000  # 4 hours in milliseconds

# Prepare data source for hover tool
source = ColumnDataSource(plot_data)
source_htf = ColumnDataSource(data_htf_plot)

# Create 4H price chart (top chart - shows zones on 4H bars)
# Set x_range to include the lookback period (from data_start to backtest_end)
p_htf = figure(
    x_axis_type="datetime",
    width=1400,
    height=400,
    title="SR Zone Detection - BTCUSDT 4H (Zones detected on this timeframe)",
    tools="pan,wheel_zoom,box_zoom,reset,save",
    toolbar_location="above",
    x_range=(data_htf_plot.index[0], data_htf_plot.index[-1]),  # Show full range including lookback
)

# Create main 15m price chart (middle chart)
# Link x-axis with 4H chart so they zoom/pan together
p = figure(
    x_axis_type="datetime",
    width=1400,
    height=400,
    title="SR Zone Detection - BTCUSDT 15m (Zones from 4H HTF)",
    tools="pan,wheel_zoom,box_zoom,reset,save",
    toolbar_location="above",
    x_range=p_htf.x_range,  # Link x-axis with 4H chart (includes lookback period)
)

# Create volume chart (link x_range after main chart is created)
p_volume = figure(
    x_axis_type="datetime",
    width=1400,
    height=200,
    x_range=p.x_range,  # Link x-axis with main chart
    tools="pan,wheel_zoom,box_zoom,reset",
    toolbar_location=None,
)

# Plot 4H candlesticks (top chart)
inc_htf = data_htf_plot[data_htf_plot['close'] >= data_htf_plot['open']]
dec_htf = data_htf_plot[data_htf_plot['close'] < data_htf_plot['open']]
source_inc_htf = ColumnDataSource(inc_htf)
source_dec_htf = ColumnDataSource(dec_htf)

# Plot 4H wicks
p_htf.segment(
    'date', 'high',
    'date', 'low',
    source=source_inc_htf,
    color='black',
    line_width=1,
    legend_label='4H Candlestick'
)
p_htf.segment(
    'date', 'high',
    'date', 'low',
    source=source_dec_htf,
    color='black',
    line_width=1,
)

# Plot 4H bodies
p_htf.vbar(
    'date', data_htf_plot['width'].iloc[0],
    'open', 'close',
    source=source_inc_htf,
    fill_color='#26a69a',
    line_color='black',
    line_width=1,
)
p_htf.vbar(
    'date', data_htf_plot['width'].iloc[0],
    'open', 'close',
    source=source_dec_htf,
    fill_color='#ef5350',
    line_color='black',
    line_width=1,
)

# Add hover tool for 4H chart
hover_htf = HoverTool(
    tooltips=[
        ('Date', '@date{%Y-%m-%d %H:%M}'),
        ('Open', '@open{0.2f}'),
        ('High', '@high{0.2f}'),
        ('Low', '@low{0.2f}'),
        ('Close', '@close{0.2f}'),
        ('Volume', '@volume{0.2f}'),
    ],
    formatters={'@date': 'datetime'},
    mode='vline',
)
p_htf.add_tools(hover_htf)

# Plot 15m candlesticks (middle chart)
inc = plot_data[plot_data['close'] >= plot_data['open']]
dec = plot_data[plot_data['close'] < plot_data['open']]
source_inc = ColumnDataSource(inc)
source_dec = ColumnDataSource(dec)

# Plot 15m segments (wicks)
p.segment(
    'date', 'high',
    'date', 'low',
    source=source_inc,
    color='black',
    line_width=1,
    legend_label='15m Candlestick'
)
p.segment(
    'date', 'high',
    'date', 'low',
    source=source_dec,
    color='black',
    line_width=1,
)

# Plot 15m bodies
vbar_inc = p.vbar(
    'date', plot_data['width'].iloc[0],
    'open', 'close',
    source=source_inc,
    fill_color='#26a69a',
    line_color='black',
    line_width=1,
)

vbar_dec = p.vbar(
    'date', plot_data['width'].iloc[0],
    'open', 'close',
    source=source_dec,
    fill_color='#ef5350',
    line_color='black',
    line_width=1,
)

# Plot volume bars
volume_colors = ['#26a69a' if close >= open else '#ef5350' 
                 for close, open in zip(plot_data['close'], plot_data['open'])]
source_volume = ColumnDataSource({
    'date': plot_data['date'],
    'volume': plot_data['volume'] if 'volume' in plot_data.columns else [0] * len(plot_data),
    'color': volume_colors,
})

p_volume.vbar(
    'date', plot_data['width'].iloc[0],
    'volume',
    source=source_volume,
    fill_color='color',
    line_color='black',
    line_width=0.5,
    legend_label='Volume'
)

# Plot zones from 4H data
# Important: zones are detected on 4H timeframe and displayed on 15m chart
# Each zone should span from when it first appears (4H bar confirmation) to when it ends
#
# Key understanding:
# - Zone is created at confirmation bar (i = pivot_real_idx + right_len)
# - In compute_sr_zones, zone.start_time is set to pivot bar time for internal logic
# - But in the returned DataFrame, zone appears at bar i (confirmation bar)
# - So we use bar i's time as the zone start_time in visualization
zone_groups = {}
current_zone_key = None

# Process 4H zones - track when each zone first appears and when it ends
for i in range(len(zones_htf)):
    if pd.notna(zones_htf['zone_top'].iloc[i]) and pd.notna(zones_htf['zone_bottom'].iloc[i]):
        zone_key = (
            float(zones_htf['zone_top'].iloc[i]),
            float(zones_htf['zone_bottom'].iloc[i])
        )
        
        # Check if this is a new zone (zone key changed)
        if zone_key != current_zone_key:
            # Save previous zone if exists
            if current_zone_key is not None and current_zone_key in zone_groups:
                # End time is the start of current 4H bar (zone changed at this bar)
                zone_groups[current_zone_key]['end_time'] = zones_htf.index[i]
            
            # Start new zone at this 4H bar's start time (confirmation bar)
            current_zone_key = zone_key
            
            if zone_key not in zone_groups:
                zone_groups[zone_key] = {
                    'start_time': zones_htf.index[i],  # 4H bar start time (when zone appears)
                    'end_time': zones_htf.index[-1] + pd.Timedelta(hours=4),  # Will be updated when zone ends
                    'top': zone_key[0],
                    'bottom': zone_key[1],
                    'touches': 0,
                    'is_broken': False,
                }
        
        # Update zone info
        if zone_key in zone_groups:
            # Update touches if higher
            current_touches = int(zones_htf['zone_touches'].iloc[i]) if pd.notna(zones_htf['zone_touches'].iloc[i]) else 0
            if current_touches > zone_groups[zone_key]['touches']:
                zone_groups[zone_key]['touches'] = current_touches
            # Update broken status
            if pd.notna(zones_htf['zone_is_broken'].iloc[i]) and zones_htf['zone_is_broken'].iloc[i]:
                zone_groups[zone_key]['is_broken'] = True
                # Zone ends when broken - use current 4H bar's end time (start + 4 hours)
                zone_groups[zone_key]['end_time'] = zones_htf.index[i] + pd.Timedelta(hours=4)

# Close last zone - extend to the end of the last 4H bar
if current_zone_key is not None and current_zone_key in zone_groups:
    # Extend to the end of the last 4H bar (start + 4 hours)
    last_bar_start = zones_htf.index[-1]
    zone_groups[current_zone_key]['end_time'] = last_bar_start + pd.Timedelta(hours=4)

# Draw zone boxes (similar to TradingView style)
active_zones = []
broken_zones = []

for zone_key, zone_info in zone_groups.items():
    # Create box annotation
    # TradingView style: red background with transparency for active zones
    # Light blue for broken zones (clearly visible on white background)
    if zone_info['is_broken']:
        # Broken zones: light blue (clearly visible on white background)
        box = BoxAnnotation(
            left=zone_info['start_time'],
            right=zone_info['end_time'],
            top=zone_info['top'],
            bottom=zone_info['bottom'],
            fill_color='#b3d9ff',  # Light blue fill
            line_color='#4da6ff',  # Medium blue border
            line_width=1,
            line_dash='dashed',  # Dashed to indicate inactive
            fill_alpha=0.4,  # More visible than before
            line_alpha=0.7,
        )
        broken_zones.append((box, zone_info))
    else:
        # Active zones: red (like TradingView #f23645)
        box = BoxAnnotation(
            left=zone_info['start_time'],
            right=zone_info['end_time'],
            top=zone_info['top'],
            bottom=zone_info['bottom'],
            fill_color='#f23645',
            line_color='#f23645',
            line_width=2,
            line_dash='solid',  # Solid line for active zones
            fill_alpha=0.25,
            line_alpha=0.5,
        )
        active_zones.append((box, zone_info))
    
    # Add zone to both 4H chart (where zones are detected) and 15m chart (where zones are used)
    p_htf.add_layout(box)  # Add to 4H chart
    p.add_layout(box)      # Add to 15m chart
    
    # Add touch count label at the top-right of the zone (on both charts)
    if zone_info['touches'] > 0:
        label_htf = Label(
            x=zone_info['end_time'],
            y=zone_info['top'],
            text=str(zone_info['touches']),
            text_color='white',
            text_font_size='11pt',
            text_font_style='bold',
            x_offset=10,
            y_offset=-8,
            background_fill_color='#f23645' if not zone_info['is_broken'] else '#4da6ff',
            background_fill_alpha=0.8,
        )
        p_htf.add_layout(label_htf)
        
        label = Label(
            x=zone_info['end_time'],
            y=zone_info['top'],
            text=str(zone_info['touches']),
            text_color='white',
            text_font_size='11pt',
            text_font_style='bold',
            x_offset=10,
            y_offset=-8,
            background_fill_color='#f23645' if not zone_info['is_broken'] else '#4da6ff',
            background_fill_alpha=0.8,
        )
        p.add_layout(label)

# Configure axes
p.xaxis.formatter = DatetimeTickFormatter(
    hours="%Y-%m-%d %H:%M",
    days="%Y-%m-%d",
    months="%Y-%m",
)
p.yaxis.formatter = NumeralTickFormatter(format="0,0")
p.xaxis.axis_label = "Time"
p.yaxis.axis_label = "Price (USDT)"

# Configure volume chart axes
p_volume.xaxis.formatter = DatetimeTickFormatter(
    hours="%Y-%m-%d %H:%M",
    days="%Y-%m-%d",
    months="%Y-%m",
)
p_volume.yaxis.formatter = NumeralTickFormatter(format="0.0a")
p_volume.yaxis.axis_label = "Volume"
p_volume.xaxis.axis_label = "Time"

# Add hover tool - attach to both vbar renderers but use vline mode to show once
hover = HoverTool(
    tooltips=[
        ("Date", "@date{%Y-%m-%d %H:%M}"),
        ("Open", "@open{0,0.00}"),
        ("High", "@high{0,0.00}"),
        ("Low", "@low{0,0.00}"),
        ("Close", "@close{0,0.00}"),
        ("Volume", "@volume{0,0.00 a}"),
    ],
    formatters={
        '@date': 'datetime',
    },
    mode='vline',  # vline mode shows one tooltip per vertical line, avoiding duplicates
    renderers=[vbar_inc, vbar_dec]  # Attach to both vbar renderers
)
p.add_tools(hover)

# Volume hover tool
hover_volume = HoverTool(
    tooltips=[
        ("Date", "@date{%Y-%m-%d %H:%M}"),
        ("Volume", "@volume{0,0.00 a}"),
    ],
    formatters={
        '@date': 'datetime',
    },
    mode='vline'
)
p_volume.add_tools(hover_volume)

# Add legend
p.legend.location = "top_left"
p.legend.click_policy = "hide"

# Create layout with price and volume charts
# Combine charts: 4H chart (top), 15m chart (middle), volume chart (bottom)
layout = column(p_htf, p, p_volume)

# Save to file - use unified results directory
from utils.paths import get_results_dir
output_dir = get_results_dir()
output_path = output_dir / "zone_visualization.html"
output_path.parent.mkdir(parents=True, exist_ok=True)
output_file(str(output_path))
save(layout)

print(f"\n[Visualization] Saved to: {output_path}")
print(f"  Active zones: {len(active_zones)}")
print(f"  Broken zones: {len(broken_zones)}")
print(f"  Total zones: {len(zone_groups)}")

print(f"\n[Zone Details]")
for zone_key, zone_info in zone_groups.items():
    duration = zone_info['end_time'] - zone_info['start_time']
    status = "BROKEN" if zone_info['is_broken'] else "ACTIVE"
    print(f"  {status} Zone [{zone_info['bottom']:.2f}, {zone_info['top']:.2f}]: "
          f"{zone_info['start_time']} to {zone_info['end_time']} "
          f"(duration: {duration.days}d {duration.seconds//3600}h, touches: {zone_info['touches']})")


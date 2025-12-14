"""
Create Interactive HTML Dashboard for TaoGrid Backtest Results.

This creates a Lean-style dashboard using Plotly for visualization.

Usage:
    python algorithms/taogrid/create_dashboard.py
"""

import json
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px


def create_dashboard(results_dir: Path):
    """Create HTML dashboard from backtest results."""

    print("Creating dashboard...")

    # Load results
    with open(results_dir / "metrics.json") as f:
        metrics = json.load(f)

    equity_df = pd.read_csv(results_dir / "equity_curve.csv")
    equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'])

    orders_df = pd.read_csv(results_dir / "orders.csv")
    orders_df['timestamp'] = pd.to_datetime(orders_df['timestamp'])

    trades_df = pd.DataFrame()
    if (results_dir / "trades.csv").exists():
        try:
            trades_df = pd.read_csv(results_dir / "trades.csv")
            if not trades_df.empty:
                # Convert timestamp columns if they exist
                if 'entry_timestamp' in trades_df.columns:
                    trades_df['entry_timestamp'] = pd.to_datetime(trades_df['entry_timestamp'])
                if 'exit_timestamp' in trades_df.columns:
                    trades_df['exit_timestamp'] = pd.to_datetime(trades_df['exit_timestamp'])
        except Exception as e:
            print(f"Warning: Could not load trades.csv: {e}")
            trades_df = pd.DataFrame()

    # Create figure with subplots (enhanced layout)
    fig = make_subplots(
        rows=4, cols=2,
        subplot_titles=(
            'Equity Curve',
            'Drawdown',
            'Holdings & Cash',
            'Grid Orders by Level',
            'Trade PnL Distribution',
            'Performance Metrics',
            'Grid Level Performance',
            'Trade Pairing Analysis'
        ),
        specs=[
            [{"secondary_y": False}, {"secondary_y": False}],
            [{"secondary_y": True}, {"secondary_y": False}],
            [{"secondary_y": False}, {"type": "table"}],
            [{"secondary_y": False}, {"secondary_y": False}]
        ],
        row_heights=[0.3, 0.25, 0.25, 0.2],
        vertical_spacing=0.1,
        horizontal_spacing=0.15,
    )

    # 1. Equity Curve
    fig.add_trace(
        go.Scatter(
            x=equity_df['timestamp'],
            y=equity_df['equity'],
            name='Equity',
            line=dict(color='#2E86DE', width=2),
            fill='tozeroy',
            fillcolor='rgba(46, 134, 222, 0.1)',
        ),
        row=1, col=1
    )

    # 2. Drawdown
    cummax = equity_df['equity'].cummax()
    drawdown = (equity_df['equity'] - cummax) / cummax * 100

    fig.add_trace(
        go.Scatter(
            x=equity_df['timestamp'],
            y=drawdown,
            name='Drawdown %',
            line=dict(color='#EE5A6F', width=2),
            fill='tozeroy',
            fillcolor='rgba(238, 90, 111, 0.2)',
        ),
        row=1, col=2
    )

    # 3. Holdings & Cash (dual y-axis)
    fig.add_trace(
        go.Scatter(
            x=equity_df['timestamp'],
            y=equity_df['holdings'],
            name='BTC Holdings',
            line=dict(color='#F79F1F', width=2),
        ),
        row=2, col=1,
        secondary_y=False
    )
    
    fig.add_trace(
        go.Scatter(
            x=equity_df['timestamp'],
            y=equity_df['cash'],
            name='Cash (USD)',
            line=dict(color='#10AC84', width=2),
        ),
        row=2, col=1,
        secondary_y=True
    )

    # 4. Grid Orders by Level (with level information)
    buy_orders = orders_df[orders_df['direction'] == 'buy'].copy()
    sell_orders = orders_df[orders_df['direction'] == 'sell'].copy()
    
    # Add level information if available
    if 'level' in orders_df.columns:
        # Color-code by grid level
        if not buy_orders.empty:
            buy_orders['level_str'] = buy_orders['level'].apply(lambda x: f'L{x+1}' if x >= 0 else 'N/A')
            for level in buy_orders['level'].unique():
                level_orders = buy_orders[buy_orders['level'] == level]
                fig.add_trace(
                    go.Scatter(
                        x=level_orders['timestamp'],
                        y=level_orders['price'],
                        mode='markers',
                        name=f'Buy L{level+1}',
                        marker=dict(
                            color='#10AC84',
                            size=8,
                            symbol='triangle-up',
                            line=dict(width=1, color='darkgreen')
                        ),
                        hovertemplate='<b>Buy Order</b><br>Level: L%{customdata[0]}<br>Price: $%{y:,.0f}<br>Size: %{customdata[1]:.4f} BTC<extra></extra>',
                        customdata=level_orders[['level', 'size']].values,
                    ),
                    row=2, col=2
                )
        
        if not sell_orders.empty:
            sell_orders['level_str'] = sell_orders['level'].apply(lambda x: f'L{x+1}' if x >= 0 else 'N/A')
            for level in sell_orders['level'].unique():
                level_orders = sell_orders[sell_orders['level'] == level]
                fig.add_trace(
                    go.Scatter(
                        x=level_orders['timestamp'],
                        y=level_orders['price'],
                        mode='markers',
                        name=f'Sell L{level+1}',
                        marker=dict(
                            color='#EE5A6F',
                            size=8,
                            symbol='triangle-down',
                            line=dict(width=1, color='darkred')
                        ),
                        hovertemplate='<b>Sell Order</b><br>Level: L%{customdata[0]}<br>Price: $%{y:,.0f}<br>Size: %{customdata[1]:.4f} BTC<extra></extra>',
                        customdata=level_orders[['level', 'size']].values,
                    ),
                    row=2, col=2
                )
    else:
        # Fallback: simple markers without level info
        if not buy_orders.empty:
            fig.add_trace(
                go.Scatter(
                    x=buy_orders['timestamp'],
                    y=buy_orders['price'],
                    mode='markers',
                    name='Buy Orders',
                    marker=dict(color='#10AC84', size=10, symbol='triangle-up'),
                ),
                row=2, col=2
            )
        if not sell_orders.empty:
            fig.add_trace(
                go.Scatter(
                    x=sell_orders['timestamp'],
                    y=sell_orders['price'],
                    mode='markers',
                    name='Sell Orders',
                    marker=dict(color='#EE5A6F', size=10, symbol='triangle-down'),
                ),
                row=2, col=2
            )
    
    # 5. Trade PnL Distribution
    if not trades_df.empty and 'pnl' in trades_df.columns:
        fig.add_trace(
            go.Histogram(
                x=trades_df['pnl'],
                nbinsx=30,
                name='PnL Distribution',
                marker=dict(color='#2E86DE'),
                hovertemplate='PnL: $%{x:.2f}<br>Count: %{y}<extra></extra>',
            ),
            row=3, col=1
        )

    # 6. Metrics Table (enhanced)
    metrics_table = [
        ['Total Return', f"{metrics['total_return']:.2%}"],
        ['Total PnL', f"${metrics['total_pnl']:,.2f}"],
        ['Max Drawdown', f"{metrics['max_drawdown']:.2%}"],
        ['Sharpe Ratio', f"{metrics['sharpe_ratio']:.2f}"],
        ['Sortino Ratio', f"{metrics['sortino_ratio']:.2f}"],
        ['Win Rate', f"{metrics['win_rate']:.2%}"],
        ['Total Trades', f"{metrics['total_trades']}"],
        ['Profit Factor', f"{metrics['profit_factor']:.2f}"],
    ]
    
    # Add grid-specific metrics if available
    if 'avg_holding_period_hours' in metrics:
        metrics_table.append(['Avg Holding Period', f"{metrics['avg_holding_period_hours']:.1f} hours"])
    if 'avg_return_per_trade' in metrics:
        metrics_table.append(['Avg Return/Trade', f"{metrics['avg_return_per_trade']:.2%}"])

    fig.add_trace(
        go.Table(
            header=dict(
                values=['<b>Metric</b>', '<b>Value</b>'],
                fill_color='#2E86DE',
                align='left',
                font=dict(color='white', size=12)
            ),
            cells=dict(
                values=list(zip(*metrics_table)),
                fill_color=[['#F8F9FA', '#FFFFFF'] * 4],
                align='left',
                font=dict(size=11)
            )
        ),
        row=3, col=2
    )

    # 7. Grid Level Performance (if trades have level info)
    if not trades_df.empty and 'entry_level' in trades_df.columns:
        level_perf = trades_df.groupby('entry_level').agg({
            'pnl': ['sum', 'mean', 'count'],
            'return_pct': 'mean'
        }).round(2)
        level_perf.columns = ['Total PnL', 'Avg PnL', 'Trade Count', 'Avg Return %']
        level_perf = level_perf.reset_index()
        level_perf['Level'] = level_perf['entry_level'].apply(lambda x: f'L{x+1}')
        
        fig.add_trace(
            go.Bar(
                x=level_perf['Level'],
                y=level_perf['Total PnL'],
                name='Total PnL by Level',
                marker=dict(color='#2E86DE'),
                hovertemplate='Level: %{x}<br>Total PnL: $%{y:.2f}<br>Trades: %{customdata}<extra></extra>',
                customdata=level_perf['Trade Count'].values,
            ),
            row=4, col=1
        )
    
    # 8. Trade Pairing Analysis (entry vs exit level)
    if not trades_df.empty and 'entry_level' in trades_df.columns and 'exit_level' in trades_df.columns:
        # Create pairing matrix
        pairing_data = trades_df.groupby(['entry_level', 'exit_level']).agg({
            'pnl': ['sum', 'count'],
            'return_pct': 'mean'
        }).round(2)
        
        # Scatter plot: entry level vs exit level, colored by PnL
        fig.add_trace(
            go.Scatter(
                x=trades_df['entry_level'],
                y=trades_df['exit_level'],
                mode='markers',
                name='Trade Pairing',
                marker=dict(
                    size=trades_df['pnl'].abs() * 10,
                    color=trades_df['pnl'],
                    colorscale='RdYlGn',
                    showscale=True,
                    colorbar=dict(title="PnL ($)", x=1.15),
                    line=dict(width=1, color='black')
                ),
                hovertemplate='Entry: L%{x+1}<br>Exit: L%{y+1}<br>PnL: $%{customdata[0]:.2f}<br>Return: %{customdata[1]:.2%}<extra></extra>',
                customdata=trades_df[['pnl', 'return_pct']].values,
            ),
            row=4, col=2
        )
    
    # Update layout
    fig.update_xaxes(title_text="Date", row=1, col=1)
    fig.update_yaxes(title_text="Equity ($)", row=1, col=1)

    fig.update_xaxes(title_text="Date", row=1, col=2)
    fig.update_yaxes(title_text="Drawdown (%)", row=1, col=2)

    fig.update_xaxes(title_text="Date", row=2, col=1)
    fig.update_yaxes(title_text="BTC Holdings", row=2, col=1)
    fig.update_yaxes(title_text="Cash (USD)", row=2, col=1, secondary_y=True)

    fig.update_xaxes(title_text="Date", row=2, col=2)
    fig.update_yaxes(title_text="Price ($)", row=2, col=2)

    fig.update_xaxes(title_text="PnL ($)", row=3, col=1)
    fig.update_yaxes(title_text="Frequency", row=3, col=1)
    
    if not trades_df.empty and 'entry_level' in trades_df.columns:
        fig.update_xaxes(title_text="Grid Level", row=4, col=1)
        fig.update_yaxes(title_text="Total PnL ($)", row=4, col=1)
        
        fig.update_xaxes(title_text="Entry Level", row=4, col=2)
        fig.update_yaxes(title_text="Exit Level", row=4, col=2)

    fig.update_layout(
        title={
            'text': f"<b>TaoGrid Backtest Dashboard</b><br><sub>Period: {equity_df['timestamp'].min().date()} to {equity_df['timestamp'].max().date()} | Total Trades: {metrics.get('total_trades', 0)}</sub>",
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 24}
        },
        showlegend=True,
        height=1600,
        template='plotly_white',
        hovermode='closest'
    )

    # Save HTML
    output_file = results_dir / "dashboard.html"
    fig.write_html(str(output_file))

    print(f"[OK] Dashboard created: {output_file}")
    print()
    print("Open in browser:")
    print(f"   {output_file.absolute()}")

    return output_file


def main():
    """Main entry point."""
    results_dir = Path("run/results_lean_taogrid")

    if not results_dir.exists():
        print(f"[ERROR] Results directory not found: {results_dir}")
        print("   Run the backtest first: python algorithms/taogrid/simple_lean_runner.py")
        return

    create_dashboard(results_dir)


if __name__ == "__main__":
    main()

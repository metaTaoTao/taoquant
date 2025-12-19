"""
检查为什么holdings为0，导致卖出订单无法执行。
"""

import sys
import io
from pathlib import Path
from datetime import datetime, timezone

# Set UTF-8 encoding for stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner
from algorithms.taogrid.config import TaoGridLeanConfig

def main():
    config = TaoGridLeanConfig(
        support=107000.0,
        resistance=123000.0,
        grid_layers_buy=40,
        grid_layers_sell=40,
        min_return=0.0012,
        maker_fee=0.0002,
        volatility_k=0.0,
        leverage=50.0,
        enable_console_log=False,
    )
    
    # 只运行前500根K线，便于分析
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
        end_date=datetime(2025, 9, 26, 9, 0, tzinfo=timezone.utc),
        verbose=False,
    )
    
    data = runner.load_data()
    
    # 手动运行，记录holdings的变化
    historical_data = data.head(100)
    runner.algorithm.initialize(
        'BTCUSDT',
        datetime(2025, 9, 26, tzinfo=timezone.utc),
        datetime(2025, 9, 26, 9, 0, tzinfo=timezone.utc),
        historical_data
    )
    
    holdings_history = []
    buy_executions = []
    sell_executions = []
    
    for i, (timestamp, row) in enumerate(data.iterrows()):
        if i < 100:
            continue
        if i >= 600:
            break
        
        # 准备数据
        bar_data = {
            'open': row['open'],
            'high': row['high'],
            'low': row['low'],
            'close': row['close'],
            'volume': row['volume'],
            'trend_score': row.get('trend_score', 0.0),
            'mr_z': row.get('mr_z', 0.0),
            'breakout_risk_down': row.get('breakout_risk_down', 0.0),
            'breakout_risk_up': row.get('breakout_risk_up', 0.0),
            'range_pos': row.get('range_pos', 0.5),
            'vol_score': row.get('vol_score', 0.0),
            'funding_rate': row.get('funding_rate', 0.0),
            'minutes_to_funding': row.get('minutes_to_funding', 0.0),
        }
        
        current_equity = runner.cash + (runner.holdings * row['close'])
        current_value = runner.holdings * row['close']
        unrealized_pnl = current_value - runner.total_cost_basis
        portfolio_state = {
            'equity': current_equity,
            'cash': runner.cash,
            'holdings': runner.holdings,
            'unrealized_pnl': unrealized_pnl,
        }
        
        before_holdings = runner.holdings
        
        # 处理订单
        runner.algorithm._current_bar_index = i
        order = runner.algorithm.on_data(timestamp, bar_data, portfolio_state)
        
        if order:
            if order['direction'] == 'buy':
                before_cash = runner.cash
                before_equity = current_equity
                executed = runner.execute_order(order, row['open'], row['close'], timestamp)
                if executed:
                    buy_executions.append({
                        'bar': i,
                        'timestamp': timestamp,
                        'level': order['level'],
                        'price': order['price'],
                        'size': order['quantity'],
                        'before_holdings': before_holdings,
                        'after_holdings': runner.holdings,
                        'before_cash': before_cash,
                        'after_cash': runner.cash,
                        'before_equity': before_equity,
                        'after_equity': runner.cash + (runner.holdings * row['close']),
                    })
                    runner.algorithm.on_order_filled(order)
                else:
                    # 检查为什么执行失败
                    equity = runner.cash + (runner.holdings * row['close'])
                    max_notional = equity * 50.0
                    new_notional = abs(runner.holdings + order['quantity']) * row['close']
                    if new_notional > max_notional:
                        print(f"Bar {i}: 买入订单执行失败 - 杠杆限制: new_notional=${new_notional:,.0f} > max_notional=${max_notional:,.0f}")
            elif order['direction'] == 'sell':
                executed = runner.execute_order(order, row['open'], row['close'], timestamp)
                if executed:
                    sell_executions.append({
                        'bar': i,
                        'timestamp': timestamp,
                        'level': order['level'],
                        'price': order['price'],
                        'size': order['quantity'],
                        'before_holdings': before_holdings,
                        'after_holdings': runner.holdings,
                    })
                    runner.algorithm.on_order_filled(order)
                else:
                    if before_holdings < order['quantity']:
                        print(f"Bar {i}: 卖出订单执行失败 - holdings不足: holdings={before_holdings:.4f} < size={order['quantity']:.4f}")
        
        runner.cash = portfolio_state['cash']
        runner.holdings = portfolio_state['holdings']
        
        if runner.holdings != before_holdings:
            holdings_history.append({
                'bar': i,
                'timestamp': timestamp,
                'holdings': runner.holdings,
                'change': runner.holdings - before_holdings,
            })
    
    print("=" * 80)
    print("Holdings变化分析")
    print("=" * 80)
    print(f"Holdings变化次数: {len(holdings_history)}")
    print(f"买入订单执行次数: {len(buy_executions)}")
    print(f"卖出订单执行次数: {len(sell_executions)}")
    
    if buy_executions:
        print(f"\n买入订单执行详情（前10个）:")
        for i, exec in enumerate(buy_executions[:10]):
            print(f"  {i+1}. Bar {exec['bar']} @ {exec['timestamp']}")
            print(f"     BUY L{exec['level']+1} @ ${exec['price']:,.2f}, size={exec['size']:.4f}")
            print(f"     holdings: {exec['before_holdings']:.4f} -> {exec['after_holdings']:.4f}")
    
    if sell_executions:
        print(f"\n卖出订单执行详情（前10个）:")
        for i, exec in enumerate(sell_executions[:10]):
            print(f"  {i+1}. Bar {exec['bar']} @ {exec['timestamp']}")
            print(f"     SELL L{exec['level']+1} @ ${exec['price']:,.2f}, size={exec['size']:.4f}")
            print(f"     holdings: {exec['before_holdings']:.4f} -> {exec['after_holdings']:.4f}")
    
    print(f"\n最终状态:")
    print(f"  最终holdings: {runner.holdings:.4f}")
    print(f"  交易数: {len(runner.trades)}")

if __name__ == "__main__":
    main()


"""
检查为什么订单执行失败。
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
        enable_console_log=True,  # 启用详细日志
    )
    
    # 只运行前500根K线，便于分析
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
        end_date=datetime(2025, 9, 26, 9, 0, tzinfo=timezone.utc),  # 约500根K线
        verbose=False,
    )
    
    data = runner.load_data()
    
    # 手动运行，记录执行失败的原因
    historical_data = data.head(100)
    runner.algorithm.initialize(
        'BTCUSDT',
        datetime(2025, 9, 26, tzinfo=timezone.utc),
        datetime(2025, 9, 26, 9, 0, tzinfo=timezone.utc),
        historical_data
    )
    
    execution_failures = []
    
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
        
        # 处理订单
        runner.algorithm._current_bar_index = i
        order = runner.algorithm.on_data(timestamp, bar_data, portfolio_state)
        
        if order:
            # 检查订单执行前的状态
            before_cash = runner.cash
            before_holdings = runner.holdings
            before_equity = current_equity
            
            executed = runner.execute_order(order, row['open'], row['close'], timestamp)
            
            if not executed:
                execution_failures.append({
                    'bar': i,
                    'timestamp': timestamp,
                    'direction': order['direction'],
                    'level': order['level'],
                    'price': order['price'],
                    'size': order['quantity'],
                    'before_cash': before_cash,
                    'before_holdings': before_holdings,
                    'before_equity': before_equity,
                    'market_price': row['close'],
                })
            
            if executed:
                runner.algorithm.on_order_filled(order)
        
        runner.cash = portfolio_state['cash']
        runner.holdings = portfolio_state['holdings']
    
    print("=" * 80)
    print("订单执行失败分析")
    print("=" * 80)
    print(f"执行失败的订单数: {len(execution_failures)}")
    
    if execution_failures:
        print(f"\n执行失败的订单详情（前10个）:")
        for i, failure in enumerate(execution_failures[:10]):
            print(f"  {i+1}. Bar {failure['bar']} @ {failure['timestamp']}")
            print(f"     {failure['direction'].upper()} L{failure['level']+1} @ ${failure['price']:,.2f}, size={failure['size']:.4f}")
            print(f"     equity=${failure['before_equity']:,.2f}, cash=${failure['before_cash']:,.2f}, holdings={failure['before_holdings']:.4f}")
    
    print(f"\n最终状态:")
    print(f"  交易数: {len(runner.trades)}")

if __name__ == "__main__":
    main()


"""
详细检查订单执行逻辑，找出为什么订单没有被执行。
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
    
    # 手动运行，详细记录订单执行过程
    historical_data = data.head(100)
    runner.algorithm.initialize(
        'BTCUSDT',
        datetime(2025, 9, 26, tzinfo=timezone.utc),
        datetime(2025, 9, 26, 9, 0, tzinfo=timezone.utc),
        historical_data
    )
    
    execution_log = []
    
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
            # 记录订单信息
            before_cash = runner.cash
            before_holdings = runner.holdings
            before_equity = current_equity
            
            # 计算杠杆限制
            max_notional = current_equity * config.leverage
            new_notional = abs(before_holdings + order['quantity']) * row['close']
            
            executed = runner.execute_order(order, row['open'], row['close'], timestamp)
            
            execution_log.append({
                'bar': i,
                'timestamp': timestamp,
                'direction': order['direction'],
                'level': order['level'],
                'price': order['price'],
                'size': order['quantity'],
                'before_equity': before_equity,
                'before_holdings': before_holdings,
                'max_notional': max_notional,
                'new_notional': new_notional,
                'leverage_check': new_notional <= max_notional,
                'executed': executed,
                'after_holdings': runner.holdings,
            })
            
            if executed:
                runner.algorithm.on_order_filled(order)
        
        runner.cash = portfolio_state['cash']
        runner.holdings = portfolio_state['holdings']
    
    print("=" * 80)
    print("订单执行详细分析")
    print("=" * 80)
    print(f"总订单数: {len(execution_log)}")
    
    if execution_log:
        executed_count = sum(1 for e in execution_log if e['executed'])
        print(f"执行成功: {executed_count}")
        print(f"执行失败: {len(execution_log) - executed_count}")
        
        print(f"\n执行失败的订单详情（前10个）:")
        failed_orders = [e for e in execution_log if not e['executed']]
        for i, order in enumerate(failed_orders[:10]):
            print(f"  {i+1}. Bar {order['bar']} @ {order['timestamp']}")
            print(f"     {order['direction'].upper()} L{order['level']+1} @ ${order['price']:,.2f}, size={order['size']:.4f}")
            print(f"     equity=${order['before_equity']:,.2f}, holdings={order['before_holdings']:.4f}")
            print(f"     max_notional=${order['max_notional']:,.2f}, new_notional=${order['new_notional']:,.2f}")
            print(f"     杠杆检查: {'通过' if order['leverage_check'] else '失败'}")
        
        print(f"\n执行成功的订单详情（前10个）:")
        success_orders = [e for e in execution_log if e['executed']]
        for i, order in enumerate(success_orders[:10]):
            print(f"  {i+1}. Bar {order['bar']} @ {order['timestamp']}")
            print(f"     {order['direction'].upper()} L{order['level']+1} @ ${order['price']:,.2f}, size={order['size']:.4f}")
            print(f"     holdings: {order['before_holdings']:.4f} -> {order['after_holdings']:.4f}")
    else:
        print("没有订单被创建")
    
    print(f"\n最终状态:")
    print(f"  交易数: {len(runner.trades)}")

if __name__ == "__main__":
    main()


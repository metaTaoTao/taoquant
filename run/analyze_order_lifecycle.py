"""
分析订单生命周期，找出为什么订单数量这么少。
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
        enable_console_log=True,  # 启用日志
    )
    
    # 只运行前200根K线，便于分析
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
        end_date=datetime(2025, 9, 26, 1, 0, tzinfo=timezone.utc),  # 只运行1小时
        verbose=True,
    )
    
    data = runner.load_data()
    
    # 手动运行，记录每个步骤
    print("=" * 80)
    print("分析订单生命周期")
    print("=" * 80)
    
    historical_data = data.head(100)
    runner.algorithm.initialize(
        'BTCUSDT',
        datetime(2025, 9, 26, tzinfo=timezone.utc),
        datetime(2025, 9, 26, 1, 0, tzinfo=timezone.utc),
        historical_data
    )
    
    print(f"\n初始化后:")
    print(f"  Pending订单数: {len(runner.algorithm.grid_manager.pending_limit_orders)}")
    
    # 运行前50根K线
    for i, (timestamp, row) in enumerate(data.iterrows()):
        if i < 100:
            continue
        if i >= 150:
            break
        
        print(f"\n--- Bar {i} @ {timestamp} ---")
        print(f"  Price: ${row['close']:,.2f} (High: ${row['high']:,.2f}, Low: ${row['low']:,.2f})")
        print(f"  Pending订单数: {len(runner.algorithm.grid_manager.pending_limit_orders)}")
        
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
            print(f"  订单创建: {order['direction'].upper()} L{order['level']+1} @ ${order['price']:,.2f}, size={order['quantity']:.4f}")
            executed = runner.execute_order(order, row['open'], row['close'], timestamp)
            print(f"  订单执行: {'成功' if executed else '失败'}")
            if executed:
                runner.algorithm.on_order_filled(order)
                print(f"  订单填充后pending订单数: {len(runner.algorithm.grid_manager.pending_limit_orders)}")
        
        runner.cash = portfolio_state['cash']
        runner.holdings = portfolio_state['holdings']
    
    print(f"\n最终状态:")
    print(f"  Pending订单数: {len(runner.algorithm.grid_manager.pending_limit_orders)}")
    print(f"  交易数: {len(runner.trades)}")

if __name__ == "__main__":
    main()


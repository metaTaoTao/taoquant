"""
分析订单执行情况，找出为什么交易数这么少。
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
    
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
        end_date=datetime(2025, 10, 26, tzinfo=timezone.utc),
        verbose=False,
    )
    
    results = runner.run()
    
    print("=" * 80)
    print("订单执行分析")
    print("=" * 80)
    print(f"总交易数: {results.get('total_trades', 0)}")
    print(f"总订单数: {len(runner.orders)}")
    
    # 分析订单
    buy_orders = [o for o in runner.orders if o['direction'] == 'buy']
    sell_orders = [o for o in runner.orders if o['direction'] == 'sell']
    
    print(f"\n订单统计:")
    print(f"  买入订单数: {len(buy_orders)}")
    print(f"  卖出订单数: {len(sell_orders)}")
    
    # 检查买入订单的执行情况
    if buy_orders:
        print(f"\n买入订单详情（前10个）:")
        for i, order in enumerate(buy_orders[:10]):
            print(f"  {i+1}. {order['timestamp']} - L{order['level']+1} @ ${order['price']:,.2f}, size={order['size']:.4f}")
    
    # 检查是否有买入订单被拒绝
    rejected_buys = [o for o in buy_orders if o.get('cost', 0) == 0 or 'rejected' in str(o).lower()]
    if rejected_buys:
        print(f"\n被拒绝的买入订单数: {len(rejected_buys)}")
    
    # 检查交易记录
    print(f"\n交易记录:")
    if runner.trades:
        print(f"  总交易数: {len(runner.trades)}")
        print(f"  前5笔交易:")
        for i, trade in enumerate(runner.trades[:5]):
            print(f"    {i+1}. BUY L{trade['entry_level']+1} @ ${trade['entry_price']:,.2f} -> SELL L{trade['exit_level']+1} @ ${trade['exit_price']:,.2f}, size={trade['size']:.4f}, PnL=${trade['pnl']:,.2f}")
    else:
        print("  没有交易记录")

if __name__ == "__main__":
    main()


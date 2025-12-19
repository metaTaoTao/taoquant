"""
检查初始化时的pending订单数量。
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
        enable_console_log=False,
    )
    
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
        end_date=datetime(2025, 9, 27, tzinfo=timezone.utc),
        verbose=False,
    )
    
    data = runner.load_data()
    runner.algorithm.initialize(
        'BTCUSDT',
        datetime(2025, 9, 26, tzinfo=timezone.utc),
        datetime(2025, 9, 27, tzinfo=timezone.utc),
        data.head(100)
    )
    
    print("=" * 80)
    print("初始化后的状态")
    print("=" * 80)
    print(f"买入层数: {len(runner.algorithm.grid_manager.buy_levels) if runner.algorithm.grid_manager.buy_levels is not None else 0}")
    print(f"卖出层数: {len(runner.algorithm.grid_manager.sell_levels) if runner.algorithm.grid_manager.sell_levels is not None else 0}")
    print(f"Pending订单数: {len(runner.algorithm.grid_manager.pending_limit_orders)}")
    
    if runner.algorithm.grid_manager.pending_limit_orders:
        print(f"\nPending订单详情（前10个）:")
        for i, order in enumerate(runner.algorithm.grid_manager.pending_limit_orders[:10]):
            print(f"  {i+1}. {order['direction'].upper()} L{order['level_index']+1} @ ${order['price']:,.2f}")
    
    if runner.algorithm.grid_manager.buy_levels is not None:
        print(f"\n买入价格范围:")
        print(f"  最高: ${runner.algorithm.grid_manager.buy_levels[0]:,.2f}")
        print(f"  最低: ${runner.algorithm.grid_manager.buy_levels[-1]:,.2f}")
        print(f"  前5个: {[f'${p:,.2f}' for p in runner.algorithm.grid_manager.buy_levels[:5]]}")
        print(f"  后5个: {[f'${p:,.2f}' for p in runner.algorithm.grid_manager.buy_levels[-5:]]}")

if __name__ == "__main__":
    main()


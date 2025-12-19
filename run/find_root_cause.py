"""
找出根本原因：为什么只有17笔交易。
关键假设：订单被移除后没有重新放置，导致订单数量逐渐减少。
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
        end_date=datetime(2025, 10, 26, tzinfo=timezone.utc),
        verbose=False,
    )
    
    # 运行完整回测
    results = runner.run()
    
    print("=" * 80)
    print("根本原因分析")
    print("=" * 80)
    print(f"总交易数: {results.get('total_trades', 0)}")
    print(f"最终pending订单数: {len(runner.algorithm.grid_manager.pending_limit_orders)}")
    print(f"初始pending订单数: 40")
    print(f"订单减少数: {40 - len(runner.algorithm.grid_manager.pending_limit_orders)}")
    
    # 分析订单生命周期
    print(f"\n订单生命周期分析:")
    print(f"  买入订单执行后：移除买入订单，放置卖出订单，不重新放置买入订单")
    print(f"  卖出订单执行后：移除卖出订单，重新放置买入订单")
    print(f"\n问题：")
    print(f"  如果买入订单执行后，对应的卖出订单长时间未触发，")
    print(f"  买入订单就不会重新放置，导致订单数量逐渐减少！")
    
    # 检查是否有未配对的卖出订单
    buy_positions_count = sum(len(positions) for positions in runner.algorithm.grid_manager.buy_positions.values())
    print(f"\n当前状态:")
    print(f"  买入持仓数: {buy_positions_count}")
    print(f"  卖出pending订单数: {sum(1 for o in runner.algorithm.grid_manager.pending_limit_orders if o['direction'] == 'sell')}")
    print(f"  买入pending订单数: {sum(1 for o in runner.algorithm.grid_manager.pending_limit_orders if o['direction'] == 'buy')}")
    
    # 关键发现
    print(f"\n关键发现:")
    if buy_positions_count > 0:
        print(f"  ⚠️  有 {buy_positions_count} 个买入持仓，但可能没有对应的卖出订单！")
        print(f"  这会导致买入订单无法重新放置，订单数量逐渐减少。")
    
    # 解决方案
    print(f"\n解决方案:")
    print(f"  1. 买入订单执行后，应该立即重新放置买入订单（而不是等待卖出）")
    print(f"  2. 或者，确保每个买入持仓都有对应的卖出订单")
    print(f"  3. 或者，在卖出订单长时间未触发时，重新放置买入订单")

if __name__ == "__main__":
    main()


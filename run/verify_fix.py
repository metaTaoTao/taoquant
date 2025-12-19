"""
验证修复效果：检查买入订单是否被重新放置。
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
    print("修复验证")
    print("=" * 80)
    print(f"总交易数: {results.get('total_trades', 0)}")
    print(f"最终pending订单数: {len(runner.algorithm.grid_manager.pending_limit_orders)}")
    buy_pending = sum(1 for o in runner.algorithm.grid_manager.pending_limit_orders if o['direction'] == 'buy')
    sell_pending = sum(1 for o in runner.algorithm.grid_manager.pending_limit_orders if o['direction'] == 'sell')
    print(f"买入pending订单数: {buy_pending}")
    print(f"卖出pending订单数: {sell_pending}")
    
    print(f"\n修复效果:")
    if buy_pending > 0:
        print(f"  ✅ 买入订单被重新放置了！买入pending订单数: {buy_pending}")
    else:
        print(f"  ❌ 买入订单没有被重新放置！买入pending订单数: {buy_pending}")
    
    if results.get('total_trades', 0) > 100:
        print(f"  ✅ 交易数大幅增加！总交易数: {results.get('total_trades', 0)}")
    else:
        print(f"  ⚠️  交易数仍然较少：{results.get('total_trades', 0)}")
        print(f"     可能需要进一步检查订单触发和执行逻辑")

if __name__ == "__main__":
    main()


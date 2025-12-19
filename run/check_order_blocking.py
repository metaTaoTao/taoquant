"""
检查订单被阻止的原因。
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
    print("=" * 80)
    print("检查订单被阻止的原因")
    print("=" * 80)
    
    config = TaoGridLeanConfig(
        support=107000.0,
        resistance=123000.0,
        grid_layers_buy=40,
        grid_layers_sell=40,
        min_return=0.0012,
        maker_fee=0.0002,
        volatility_k=0.0,
        enable_console_log=True,  # 启用详细日志
    )
    
    # 只运行第一天，便于分析
    runner = SimpleLeanRunner(
        config=config,
        symbol="BTCUSDT",
        timeframe="1m",
        start_date=datetime(2025, 9, 26, tzinfo=timezone.utc),
        end_date=datetime(2025, 9, 27, tzinfo=timezone.utc),  # 只运行第一天
        verbose=True,
    )
    
    print("\n开始回测（只运行第一天，便于分析）...")
    results = runner.run()
    
    print(f"\n交易数: {results.get('total_trades', 0)}")
    print("\n请查看上面的日志，寻找以下关键词：")
    print("  - [ORDER_BLOCKED]: 订单被阻止")
    print("  - [ORDER_SIZE] ... SIZE=0: 订单大小为0")
    print("  - [FILLED_LEVELS]: filled_levels相关")
    print("  - Grid shutdown: 网格被关闭")

if __name__ == "__main__":
    main()


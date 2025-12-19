"""
检查filled_levels是否导致订单被阻止。
"""

import sys
import io
from pathlib import Path

# Set UTF-8 encoding for stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 读取关键代码段
print("=" * 80)
print("检查 filled_levels 逻辑")
print("=" * 80)

print("\n1. check_pending_order_trigger (grid_manager.py:353):")
print("   - 检查 filled_levels.get(level_key, False)")
print("   - 如果为True，阻止订单触发")
print("   - 这会导致已触发的价格无法再次触发")

print("\n2. add_buy_position (grid_manager.py:823):")
print("   - 注释掉了 filled_levels[level_key] = True")
print("   - 允许连续订单")
print("   - 但 check_pending_order_trigger 仍然检查 filled_levels")

print("\n3. on_order_filled (algorithm.py):")
print("   - 需要检查是否设置了 filled_levels")

print("\n" + "=" * 80)
print("问题分析:")
print("=" * 80)
print("如果 on_order_filled 设置了 filled_levels，但卖出匹配逻辑有问题，")
print("filled_levels 可能永远不会被重置，导致大量订单被阻止。")

print("\n建议:")
print("1. 检查 on_order_filled 是否设置了 filled_levels")
print("2. 检查卖出匹配逻辑是否正确")
print("3. 考虑完全移除 filled_levels 检查（因为已经允许连续订单）")


"""
添加 filled_levels 状态汇总日志
在回测过程中定期输出 filled_levels 的状态
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 这个脚本会在 simple_lean_runner.py 中添加定期日志
# 我们需要修改 simple_lean_runner.py 来添加汇总日志

print("=" * 80)
print("添加 filled_levels 状态汇总日志")
print("=" * 80)

print("\n已添加的日志点：")
print("1. 当买入订单因 filled_levels 被阻止时")
print("2. 当卖出订单匹配后重置 filled_levels 时")
print("3. 当添加买入持仓时，显示 filled_levels 状态")

print("\n建议添加的汇总日志：")
print("- 每1000根K线输出一次 filled_levels 的状态")
print("- 显示哪些层级被标记为 filled")
print("- 显示 filled_levels 的总数")

print("\n修改文件：algorithms/taogrid/simple_lean_runner.py")
print("在回测循环中添加定期汇总日志")

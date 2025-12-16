"""
自动分析回测日志，生成详细报告
"""
import sys
from pathlib import Path
import re
from collections import defaultdict

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

log_file = project_root / "run" / "dual_backtest_analysis.log"

print("=" * 80)
print("自动分析回测日志")
print("=" * 80)

if not log_file.exists():
    print(f"日志文件不存在: {log_file}")
    sys.exit(1)

with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# 分割两个回测的日志
sections = content.split("=" * 80)
test1_section = ""
test2_section = ""

for i, section in enumerate(sections):
    if "7.10-10.26" in section:
        test1_section = section
    elif "9.26-10.26" in section:
        test2_section = section

# 分析每个回测
def analyze_section(section, name):
    print(f"\n{'=' * 80}")
    print(f"分析: {name}")
    print(f"{'=' * 80}")
    
    # 提取交易数量
    trade_match = re.search(r'Total Trades:\s+(\d+)', section)
    total_trades = int(trade_match.group(1)) if trade_match else 0
    print(f"\n总交易数: {total_trades}")
    
    # 提取关键日志统计
    stats = {
        'order_triggered': len(re.findall(r'\[ORDER_TRIGGER\].*?TRIGGERED', section)),
        'order_not_triggered': len(re.findall(r'\[ORDER_TRIGGER\].*?not triggered', section)),
        'order_created': len(re.findall(r'\[ORDER_CREATED\]', section)),
        'order_executed': len(re.findall(r'\[ORDER_EXECUTE\].*?EXECUTED', section)),
        'order_failed': len(re.findall(r'\[ORDER_EXECUTE\].*?FAILED', section)),
        'order_blocked': len(re.findall(r'\[ORDER_BLOCKED\]', section)),
        'order_size_zero': len(re.findall(r'\[ORDER_SIZE\].*?FINAL SIZE=0', section)),
        'sell_match_success': len(re.findall(r'\[SELL_MATCH\].*?SUCCESS', section)),
        'sell_match_failed': len(re.findall(r'\[SELL_MATCH\].*?FAILED', section)),
        'sell_match_fifo': len(re.findall(r'\[SELL_MATCH_FIFO\]', section)),
        'trade_matched': len(re.findall(r'\[TRADE_MATCHED\]', section)),
        'trade_recorded': len(re.findall(r'\[TRADE_RECORD\]', section)),
        'buy_executed': len(re.findall(r'\[BUY_EXECUTED\]', section)),
        'sell_executed': len(re.findall(r'\[SELL_EXECUTED\]', section)),
        'pending_placed': len(re.findall(r'\[PENDING_ORDER\].*?Placed', section)),
        'pending_removed': len(re.findall(r'\[PENDING_ORDER\].*?Removed', section)),
    }
    
    print(f"\n订单流程统计:")
    print(f"  订单触发: {stats['order_triggered']} 次")
    print(f"  订单未触发: {stats['order_not_triggered']} 次")
    print(f"  订单创建: {stats['order_created']} 次")
    print(f"  订单执行成功: {stats['order_executed']} 次")
    print(f"  订单执行失败: {stats['order_failed']} 次")
    print(f"  订单被阻止: {stats['order_blocked']} 次")
    print(f"  订单大小=0: {stats['order_size_zero']} 次")
    
    print(f"\n卖出匹配统计:")
    print(f"  Grid配对成功: {stats['sell_match_success']} 次")
    print(f"  Grid配对失败: {stats['sell_match_failed']} 次")
    print(f"  FIFO回退: {stats['sell_match_fifo']} 次")
    print(f"  交易匹配: {stats['trade_matched']} 次")
    print(f"  交易记录: {stats['trade_recorded']} 次")
    
    print(f"\n订单执行统计:")
    print(f"  买入执行: {stats['buy_executed']} 次")
    print(f"  卖出执行: {stats['sell_executed']} 次")
    
    print(f"\npending_orders 统计:")
    print(f"  放置: {stats['pending_placed']} 次")
    print(f"  移除: {stats['pending_removed']} 次")
    
    # 分析订单阻止原因
    blocked_reasons = defaultdict(int)
    for match in re.finditer(r'\[ORDER_BLOCKED\].*?reason: ([^,]+)', section):
        reason = match.group(1).strip()
        blocked_reasons[reason] += 1
    
    if blocked_reasons:
        print(f"\n订单阻止原因:")
        for reason, count in sorted(blocked_reasons.items(), key=lambda x: x[1], reverse=True):
            print(f"  {reason}: {count}")
    
    # 分析订单大小=0的原因
    size_zero_reasons = defaultdict(int)
    for match in re.findall(r'\[ORDER_SIZE\].*?FINAL SIZE=0.*?blocked: ([^\)]+)', section):
        reason = match.strip()
        size_zero_reasons[reason] += 1
    
    if size_zero_reasons:
        print(f"\n订单大小=0的原因:")
        for reason, count in sorted(size_zero_reasons.items(), key=lambda x: x[1], reverse=True):
            print(f"  {reason}: {count}")
    
    # 分析卖出匹配失败的原因
    if stats['sell_match_failed'] > 0:
        print(f"\n卖出匹配失败详情（前5个）:")
        failed_matches = re.findall(r'\[SELL_MATCH\].*?FAILED.*?\n(?:\[SELL_MATCH\].*?\n)?', section)[:5]
        for i, match in enumerate(failed_matches, 1):
            print(f"  {i}. {match.strip()[:200]}")
    
    return {
        'total_trades': total_trades,
        'stats': stats,
    }

# 分析两个回测
result1 = analyze_section(test1_section, "7.10-10.26 (108天)")
result2 = analyze_section(test2_section, "9.26-10.26 (30天)")

# 对比分析
print(f"\n{'=' * 80}")
print("关键差异分析")
print(f"{'=' * 80}")

print(f"\n交易数量:")
print(f"  7.10-10.26: {result1['total_trades']} 笔")
print(f"  9.26-10.26: {result2['total_trades']} 笔")
print(f"  差异: {result1['total_trades'] - result2['total_trades']} 笔")

print(f"\n订单触发:")
print(f"  7.10-10.26: {result1['stats']['order_triggered']} 次")
print(f"  9.26-10.26: {result2['stats']['order_triggered']} 次")
print(f"  差异: {result1['stats']['order_triggered'] - result2['stats']['order_triggered']} 次")

print(f"\n订单创建:")
print(f"  7.10-10.26: {result1['stats']['order_created']} 次")
print(f"  9.26-10.26: {result2['stats']['order_created']} 次")
print(f"  差异: {result1['stats']['order_created'] - result2['stats']['order_created']} 次")

print(f"\n订单执行:")
print(f"  7.10-10.26: 成功 {result1['stats']['order_executed']} 次, 失败 {result1['stats']['order_failed']} 次")
print(f"  9.26-10.26: 成功 {result2['stats']['order_executed']} 次, 失败 {result2['stats']['order_failed']} 次")

print(f"\n卖出匹配:")
print(f"  7.10-10.26: Grid成功 {result1['stats']['sell_match_success']} 次, 失败 {result1['stats']['sell_match_failed']} 次, FIFO {result1['stats']['sell_match_fifo']} 次")
print(f"  9.26-10.26: Grid成功 {result2['stats']['sell_match_success']} 次, 失败 {result2['stats']['sell_match_failed']} 次, FIFO {result2['stats']['sell_match_fifo']} 次")

print(f"\n交易记录:")
print(f"  7.10-10.26: {result1['stats']['trade_recorded']} 次")
print(f"  9.26-10.26: {result2['stats']['trade_recorded']} 次")
print(f"  差异: {result1['stats']['trade_recorded'] - result2['stats']['trade_recorded']} 次")

# 关键发现
print(f"\n{'=' * 80}")
print("关键发现")
print(f"{'=' * 80}")

if result1['stats']['order_triggered'] < result2['stats']['order_triggered']:
    print(f"\n⚠️  7.10-10.26期间订单触发数更少")
    print(f"   可能原因: 订单触发条件更严格，或者pending_orders状态异常")

if result1['stats']['order_created'] < result2['stats']['order_created']:
    print(f"\n⚠️  7.10-10.26期间订单创建数更少")
    print(f"   可能原因: 订单大小计算返回0的次数更多")

if result1['stats']['sell_match_failed'] > result2['stats']['sell_match_failed']:
    print(f"\n⚠️  7.10-10.26期间卖出匹配失败更多")
    print(f"   可能原因: buy_positions状态异常，或者配对逻辑有问题")

if result1['stats']['trade_recorded'] < result2['stats']['trade_recorded']:
    print(f"\n⚠️  7.10-10.26期间交易记录数更少")
    print(f"   可能原因: 卖出订单匹配失败，导致没有交易被记录")

print(f"\n详细日志已保存到: {log_file}")

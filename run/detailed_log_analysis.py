"""
详细分析日志，提取关键信息
"""
import sys
from pathlib import Path
import re

log_file = Path(__file__).parent / "dual_backtest_analysis.log"

print("=" * 80)
print("详细日志分析")
print("=" * 80)

with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# 找到两个回测的分界点
test1_start = content.find("7.10-10.26 (108天)")
test2_start = content.find("9.26-10.26 (30天)")

if test1_start == -1 or test2_start == -1:
    print("未找到回测分界点")
    sys.exit(1)

test1_content = content[test1_start:test2_start]
test2_content = content[test2_start:]

def extract_metrics(section, name):
    print(f"\n{'=' * 80}")
    print(f"{name}")
    print(f"{'=' * 80}")
    
    # 提取交易数量
    trade_match = re.search(r'Total Trades:\s+(\d+)', section)
    total_trades = int(trade_match.group(1)) if trade_match else 0
    print(f"\n总交易数: {total_trades}")
    
    # 提取数据加载信息
    loaded_match = re.search(r'Loaded (\d+) bars from ([^\n]+)', section)
    if loaded_match:
        bars_count = int(loaded_match.group(1))
        date_range = loaded_match.group(2)
        print(f"数据加载: {bars_count} 根K线, 时间范围: {date_range}")
    
    request_match = re.search(r'Request: ([^\n]+)', section)
    if request_match:
        print(f"请求时间范围: {request_match.group(1)}")
    
    # 统计各种日志
    stats = {}
    
    # 订单相关
    stats['order_triggered'] = len(re.findall(r'\[ORDER_TRIGGER\].*?TRIGGERED', section))
    stats['order_not_triggered_price'] = len(re.findall(r'\[ORDER_TRIGGER\].*?not triggered - price not touched', section))
    stats['order_not_triggered_no_positions'] = len(re.findall(r'\[ORDER_TRIGGER\].*?not triggered - no long positions', section))
    stats['order_created'] = len(re.findall(r'\[ORDER_CREATED\]', section))
    stats['order_executed'] = len(re.findall(r'\[ORDER_EXECUTE\].*?EXECUTED', section))
    stats['order_failed'] = len(re.findall(r'\[ORDER_EXECUTE\].*?FAILED', section))
    stats['order_blocked'] = len(re.findall(r'\[ORDER_BLOCKED\]', section))
    stats['order_size_zero'] = len(re.findall(r'\[ORDER_SIZE\].*?FINAL SIZE=0', section))
    
    # 卖出匹配
    stats['sell_match_success'] = len(re.findall(r'\[SELL_MATCH\].*?SUCCESS', section))
    stats['sell_match_failed'] = len(re.findall(r'\[SELL_MATCH\].*?FAILED', section))
    stats['sell_match_fifo'] = len(re.findall(r'\[SELL_MATCH_FIFO\]', section))
    stats['trade_matched'] = len(re.findall(r'\[TRADE_MATCHED\]', section))
    stats['trade_recorded'] = len(re.findall(r'\[TRADE_RECORD\]', section))
    
    # 执行
    stats['buy_executed'] = len(re.findall(r'\[BUY_EXECUTED\]', section))
    stats['sell_executed'] = len(re.findall(r'\[SELL_EXECUTED\]', section))
    
    # pending orders
    stats['pending_placed'] = len(re.findall(r'\[PENDING_ORDER\].*?Placed', section))
    stats['pending_removed'] = len(re.findall(r'\[PENDING_ORDER\].*?Removed', section))
    
    print(f"\n订单流程:")
    print(f"  触发: {stats['order_triggered']}")
    print(f"  未触发(价格): {stats['order_not_triggered_price']}")
    print(f"  未触发(无持仓): {stats['order_not_triggered_no_positions']}")
    print(f"  创建: {stats['order_created']}")
    print(f"  执行成功: {stats['order_executed']}")
    print(f"  执行失败: {stats['order_failed']}")
    print(f"  被阻止: {stats['order_blocked']}")
    print(f"  大小=0: {stats['order_size_zero']}")
    
    print(f"\n卖出匹配:")
    print(f"  Grid成功: {stats['sell_match_success']}")
    print(f"  Grid失败: {stats['sell_match_failed']}")
    print(f"  FIFO回退: {stats['sell_match_fifo']}")
    print(f"  交易匹配: {stats['trade_matched']}")
    print(f"  交易记录: {stats['trade_recorded']}")
    
    print(f"\n执行:")
    print(f"  买入执行: {stats['buy_executed']}")
    print(f"  卖出执行: {stats['sell_executed']}")
    
    # 分析订单阻止原因
    blocked_reasons = {}
    for match in re.finditer(r'\[ORDER_BLOCKED\].*?reason: ([^,]+)', section):
        reason = match.group(1).strip()
        blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1
    
    if blocked_reasons:
        print(f"\n订单阻止原因:")
        for reason, count in sorted(blocked_reasons.items(), key=lambda x: x[1], reverse=True):
            print(f"  {reason}: {count}")
    
    # 分析订单大小=0的原因
    size_zero_reasons = {}
    for match in re.finditer(r'\[ORDER_SIZE\].*?FINAL SIZE=0.*?blocked: ([^\)]+)', section):
        reason = match.group(1).strip()
        size_zero_reasons[reason] = size_zero_reasons.get(reason, 0) + 1
    
    if size_zero_reasons:
        print(f"\n订单大小=0的原因:")
        for reason, count in sorted(size_zero_reasons.items(), key=lambda x: x[1], reverse=True):
            print(f"  {reason}: {count}")
    
    # 提取交易记录的时间分布
    trade_records = re.findall(r'\[TRADE_RECORD\].*?total trades now: (\d+)', section)
    if trade_records:
        print(f"\n交易记录时间分布:")
        print(f"  第一次交易记录: 第 {trade_records[0]} 笔")
        if len(trade_records) > 1:
            print(f"  最后一次交易记录: 第 {trade_records[-1]} 笔")
        print(f"  交易记录次数: {len(trade_records)}")
    
    return {
        'total_trades': total_trades,
        'stats': stats,
    }

result1 = extract_metrics(test1_content, "7.10-10.26 (108天)")
result2 = extract_metrics(test2_content, "9.26-10.26 (30天)")

# 对比
print(f"\n{'=' * 80}")
print("关键差异")
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

print(f"\n卖出匹配:")
print(f"  7.10-10.26: Grid成功 {result1['stats']['sell_match_success']}, 失败 {result1['stats']['sell_match_failed']}, FIFO {result1['stats']['sell_match_fifo']}")
print(f"  9.26-10.26: Grid成功 {result2['stats']['sell_match_success']}, 失败 {result2['stats']['sell_match_failed']}, FIFO {result2['stats']['sell_match_fifo']}")

print(f"\n交易记录:")
print(f"  7.10-10.26: {result1['stats']['trade_recorded']} 次")
print(f"  9.26-10.26: {result2['stats']['trade_recorded']} 次")
print(f"  差异: {result1['stats']['trade_recorded'] - result2['stats']['trade_recorded']} 次")

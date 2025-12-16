"""
运行两遍回测并自动分析
时间区间1: 7.10-10.26 (108天)
时间区间2: 9.26-10.26 (30天)
"""
import sys
from pathlib import Path
from datetime import datetime, timezone
import subprocess
import re
from collections import defaultdict
import io
import contextlib

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("=" * 80)
print("运行两遍回测并自动分析")
print("=" * 80)

# 定义两个时间区间
test_cases = [
    {
        "name": "7.10-10.26 (108天)",
        "start": datetime(2025, 7, 10, tzinfo=timezone.utc),
        "end": datetime(2025, 10, 26, tzinfo=timezone.utc),
    },
    {
        "name": "9.26-10.26 (30天)",
        "start": datetime(2025, 9, 26, tzinfo=timezone.utc),
        "end": datetime(2025, 10, 26, tzinfo=timezone.utc),
    },
]

results = {}

for test_case in test_cases:
    print(f"\n{'=' * 80}")
    print(f"运行回测: {test_case['name']}")
    print(f"{'=' * 80}")
    
    # 修改 simple_lean_runner.py 的时间区间
    runner_file = project_root / "algorithms" / "taogrid" / "simple_lean_runner.py"
    
    # 读取文件
    with open(runner_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换时间区间（移除前导零）
    start_str = f"datetime({test_case['start'].year}, {test_case['start'].month}, {test_case['start'].day}, tzinfo=timezone.utc)"
    end_str = f"datetime({test_case['end'].year}, {test_case['end'].month}, {test_case['end'].day}, tzinfo=timezone.utc)"
    
    # 使用正则表达式替换
    pattern = r'start_date=datetime\([^)]+\)'
    content = re.sub(pattern, f'start_date={start_str}', content)
    
    pattern = r'end_date=datetime\([^)]+\)'
    content = re.sub(pattern, f'end_date={end_str}', content)
    
    # 写回文件
    with open(runner_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"已更新时间区间: {start_str} 至 {end_str}")
    
    # 运行回测 - 直接导入并运行
    print(f"\n开始运行回测...")
    try:
        # 捕获输出
        output_buffer = io.StringIO()
        error_buffer = io.StringIO()
        
        with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(error_buffer):
            # 导入并运行
            from algorithms.taogrid.simple_lean_runner import SimpleLeanRunner, TaoGridLeanConfig
            from pathlib import Path as PathLib
            
            config = TaoGridLeanConfig(
                name="TaoGrid Optimized - Max ROE (Perp)",
                description="Inventory-aware grid (perp maker fee 0.02%), focus on max ROE",
                support=107000.0,
                resistance=123000.0,
                regime="NEUTRAL_RANGE",
                grid_layers_buy=40,
                grid_layers_sell=40,
                weight_k=0.0,
                spacing_multiplier=1.0,
                min_return=0.0012,
                maker_fee=0.0002,
                inventory_skew_k=0.5,
                inventory_capacity_threshold_pct=1.0,
                enable_mr_trend_factor=False,
                enable_breakout_risk_factor=True,
                breakout_band_atr_mult=1.0,
                breakout_band_pct=0.008,
                breakout_trend_weight=0.7,
                breakout_buy_k=2.0,
                breakout_buy_floor=0.5,
                breakout_block_threshold=0.9,
                enable_range_pos_asymmetry_v2=True,
                range_top_band_start=0.45,
                range_buy_k=0.2,
                range_buy_floor=0.2,
                range_sell_k=1.5,
                range_sell_cap=1.5,
                risk_budget_pct=1.0,
                enable_throttling=True,
                initial_cash=100000.0,
                leverage=50.0,
                enable_mm_risk_zone=False,
                enable_console_log=True,
            )
            
            runner = SimpleLeanRunner(
                config=config,
                symbol="BTCUSDT",
                timeframe="1m",
                start_date=test_case['start'],
                end_date=test_case['end'],
            )
            results_obj = runner.run()
            runner.print_summary(results_obj)
            
            # 保存结果到不同的目录
            output_dir = PathLib(f"run/results_lean_taogrid_{test_case['name'].replace(' ', '_').replace('(', '').replace(')', '').replace('.', '_')}")
            runner.save_results(results_obj, output_dir)
        
        output = output_buffer.getvalue() + error_buffer.getvalue()
        results[test_case['name']] = {
            'output': output,
            'returncode': 0,
            'results': results_obj,
        }
        
        print(f"回测完成")
        
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        print(f"回测出错: {e}")
        print(error_msg[:500])  # 只打印前500字符
        results[test_case['name']] = {
            'output': error_msg,
            'returncode': -1,
        }

# 分析结果
print(f"\n{'=' * 80}")
print("分析结果")
print(f"{'=' * 80}")

# 分析日志
for test_name, result in results.items():
    print(f"\n【{test_name}】")
    print("-" * 80)
    
    if result['returncode'] != 0:
        print(f"回测失败 (返回码: {result['returncode']})")
        continue
    
    output = result['output']
    
    # 提取关键指标
    metrics = {}
    
    # 从结果对象中提取（如果可用）
    if 'results' in result and result['results']:
        metrics_obj = result['results'].get('metrics', {})
        if 'total_trades' in metrics_obj:
            metrics['total_trades'] = metrics_obj['total_trades']
            print(f"总交易数: {metrics['total_trades']}")
    
    # 也从日志中提取（备用）
    if 'total_trades' not in metrics:
        trade_match = re.search(r'Total Trades:\s+(\d+)', output)
        if trade_match:
            metrics['total_trades'] = int(trade_match.group(1))
            print(f"总交易数: {metrics['total_trades']}")
    
    # 提取订单相关统计
    order_triggered = len(re.findall(r'\[ORDER_TRIGGER\].*?TRIGGERED', output))
    order_not_triggered = len(re.findall(r'\[ORDER_TRIGGER\].*?not triggered', output))
    order_created = len(re.findall(r'\[ORDER_CREATED\]', output))
    order_executed = len(re.findall(r'\[ORDER_EXECUTE\].*?EXECUTED', output))
    order_failed = len(re.findall(r'\[ORDER_EXECUTE\].*?FAILED', output))
    
    print(f"订单触发: {order_triggered} 次")
    print(f"订单未触发: {order_not_triggered} 次")
    print(f"订单创建: {order_created} 次")
    print(f"订单执行成功: {order_executed} 次")
    print(f"订单执行失败: {order_failed} 次")
    
    # 提取 filled_levels 相关日志
    filled_blocked = len(re.findall(r'\[FILLED_LEVELS\] BUY L\d+ @ \$\d+ blocked', output))
    filled_reset = len(re.findall(r'\[FILLED_LEVELS\] Reset BUY L\d+', output))
    filled_summary = re.findall(r'\[FILLED_LEVELS_SUMMARY\].*?filled_levels=(\d+)', output)
    
    print(f"filled_levels 阻止订单次数: {filled_blocked}")
    print(f"filled_levels 重置次数: {filled_reset}")
    if filled_summary:
        filled_counts = [int(x) for x in filled_summary]
        print(f"filled_levels 数量范围: {min(filled_counts)} - {max(filled_counts)}")
        print(f"filled_levels 平均数量: {sum(filled_counts) / len(filled_counts):.1f}")
    
    # 提取订单阻止日志
    order_blocked = len(re.findall(r'Order blocked', output))
    order_throttled = len(re.findall(r'Order throttled', output))
    order_triggered = len(re.findall(r'Order triggered', output))
    
    print(f"订单被阻止次数: {order_blocked}")
    print(f"订单被节流次数: {order_throttled}")
    print(f"订单触发次数: {order_triggered}")
    
    # 提取订单阻止原因
    blocked_reasons = defaultdict(int)
    for match in re.finditer(r'Order blocked.*?: (.*?)(?:\n|$)', output):
        reason = match.group(1).strip()
        blocked_reasons[reason] += 1
    
    if blocked_reasons:
        print(f"\n订单阻止原因统计:")
        for reason, count in sorted(blocked_reasons.items(), key=lambda x: x[1], reverse=True):
            print(f"  {reason}: {count}")
    
    results[test_name]['metrics'] = metrics
    results[test_name]['filled_blocked'] = filled_blocked
    results[test_name]['filled_reset'] = filled_reset
    results[test_name]['order_blocked'] = order_blocked
    results[test_name]['order_throttled'] = order_throttled
    results[test_name]['order_triggered'] = order_triggered
    results[test_name]['order_created'] = order_created
    results[test_name]['order_executed'] = order_executed
    results[test_name]['order_failed'] = order_failed

# 对比分析
print(f"\n{'=' * 80}")
print("对比分析")
print(f"{'=' * 80}")

if '7.10-10.26 (108天)' in results and '9.26-10.26 (30天)' in results:
    r1 = results['7.10-10.26 (108天)']
    r2 = results['9.26-10.26 (30天)']
    
    print(f"\n交易数量对比:")
    if 'total_trades' in r1.get('metrics', {}) and 'total_trades' in r2.get('metrics', {}):
        trades1 = r1['metrics']['total_trades']
        trades2 = r2['metrics']['total_trades']
        print(f"  7.10-10.26: {trades1} 笔")
        print(f"  9.26-10.26: {trades2} 笔")
        print(f"  差异: {trades1 - trades2} 笔")
        print(f"  7.10-9.26期间: {trades1 - trades2} 笔 (应该是正数，如果是负数说明有问题)")
    
    print(f"\nfilled_levels 对比:")
    print(f"  7.10-10.26: 阻止 {r1.get('filled_blocked', 0)} 次, 重置 {r1.get('filled_reset', 0)} 次")
    print(f"  9.26-10.26: 阻止 {r2.get('filled_blocked', 0)} 次, 重置 {r2.get('filled_reset', 0)} 次")
    
    print(f"\n订单统计对比:")
    print(f"  7.10-10.26: 阻止 {r1.get('order_blocked', 0)} 次, 节流 {r1.get('order_throttled', 0)} 次, 触发 {r1.get('order_triggered', 0)} 次")
    print(f"  9.26-10.26: 阻止 {r2.get('order_blocked', 0)} 次, 节流 {r2.get('order_throttled', 0)} 次, 触发 {r2.get('order_triggered', 0)} 次")
    print(f"\n订单执行对比:")
    print(f"  7.10-10.26: 创建 {r1.get('order_created', 0)} 次, 执行成功 {r1.get('order_executed', 0)} 次, 执行失败 {r1.get('order_failed', 0)} 次")
    print(f"  9.26-10.26: 创建 {r2.get('order_created', 0)} 次, 执行成功 {r2.get('order_executed', 0)} 次, 执行失败 {r2.get('order_failed', 0)} 次")
    
    # 分析卖出匹配情况
    sell_match_success_1 = len(re.findall(r'\[SELL_MATCH\].*?SUCCESS', r1['output']))
    sell_match_failed_1 = len(re.findall(r'\[SELL_MATCH\].*?FAILED', r1['output']))
    sell_match_fifo_1 = len(re.findall(r'\[SELL_MATCH_FIFO\]', r1['output']))
    trade_matched_1 = len(re.findall(r'\[TRADE_MATCHED\]', r1['output']))
    
    sell_match_success_2 = len(re.findall(r'\[SELL_MATCH\].*?SUCCESS', r2['output']))
    sell_match_failed_2 = len(re.findall(r'\[SELL_MATCH\].*?FAILED', r2['output']))
    sell_match_fifo_2 = len(re.findall(r'\[SELL_MATCH_FIFO\]', r2['output']))
    trade_matched_2 = len(re.findall(r'\[TRADE_MATCHED\]', r2['output']))
    
    print(f"\n卖出匹配对比:")
    print(f"  7.10-10.26: Grid配对成功 {sell_match_success_1} 次, 失败 {sell_match_failed_1} 次, FIFO回退 {sell_match_fifo_1} 次, 交易匹配 {trade_matched_1} 次")
    print(f"  9.26-10.26: Grid配对成功 {sell_match_success_2} 次, 失败 {sell_match_failed_2} 次, FIFO回退 {sell_match_fifo_2} 次, 交易匹配 {trade_matched_2} 次")
    
    # 分析pending_orders状态
    pending_placed_1 = len(re.findall(r'\[PENDING_ORDER\].*?Placed', r1['output']))
    pending_removed_1 = len(re.findall(r'\[PENDING_ORDER\].*?Removed', r1['output']))
    pending_exists_1 = len(re.findall(r'\[PENDING_ORDER\].*?already exists', r1['output']))
    
    pending_placed_2 = len(re.findall(r'\[PENDING_ORDER\].*?Placed', r2['output']))
    pending_removed_2 = len(re.findall(r'\[PENDING_ORDER\].*?Removed', r2['output']))
    pending_exists_2 = len(re.findall(r'\[PENDING_ORDER\].*?already exists', r2['output']))
    
    print(f"\npending_orders 状态对比:")
    print(f"  7.10-10.26: 放置 {pending_placed_1} 次, 移除 {pending_removed_1} 次, 已存在 {pending_exists_1} 次")
    print(f"  9.26-10.26: 放置 {pending_placed_2} 次, 移除 {pending_removed_2} 次, 已存在 {pending_exists_2} 次")
    
    # 计算每根K线的交易频率
    if 'total_trades' in r1.get('metrics', {}) and 'total_trades' in r2.get('metrics', {}):
        # 估算K线数量（1分钟K线）
        bars1 = (datetime(2025, 10, 26) - datetime(2025, 7, 10)).days * 24 * 60
        bars2 = (datetime(2025, 10, 26) - datetime(2025, 9, 26)).days * 24 * 60
        freq1 = r1['metrics']['total_trades'] / bars1 if bars1 > 0 else 0
        freq2 = r2['metrics']['total_trades'] / bars2 if bars2 > 0 else 0
        print(f"\n交易频率对比:")
        print(f"  7.10-10.26: {freq1:.4f} 笔/K线")
        print(f"  9.26-10.26: {freq2:.4f} 笔/K线")
        print(f"  差异: {freq1 - freq2:.4f} 笔/K线")

# 保存详细日志
log_file = project_root / "run" / "dual_backtest_analysis.log"
with open(log_file, 'w', encoding='utf-8') as f:
    f.write("=" * 80 + "\n")
    f.write("双回测分析日志\n")
    f.write("=" * 80 + "\n\n")
    
    for test_name, result in results.items():
        f.write(f"\n{'=' * 80}\n")
        f.write(f"{test_name}\n")
        f.write(f"{'=' * 80}\n\n")
        f.write(result['output'])
        f.write("\n\n")

print(f"\n详细日志已保存到: {log_file}")

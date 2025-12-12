"""
网格策略回测脚本

使用智能动态网格策略进行回测，支持：
- 做空交易
- 多笔交易
- 动态仓位控制（衰减机制、边缘加权）
- 几何网格

Usage:
    python run/run_grid_backtest.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pandas as pd

# Data
from data import DataManager

# Strategy
from strategies.grid import SmartGridStrategy, SmartGridConfig

# Execution
from strategies.grid import SmartGridBacktester

# Output
from utils.paths import get_results_dir

# =============================================================================
# CONFIGURATION - Modify this section only
# =============================================================================

# Data parameters
SYMBOL = "BTCUSDT"
TIMEFRAME = "1m"  # 使用1分钟K线执行（更精确）
START = pd.Timestamp("2025-07-21", tz="UTC")
END = pd.Timestamp("2025-07-28", tz="UTC")
SOURCE = "okx"  # 'okx', 'binance', or 'csv'

# Grid parameters (交易员手动设置)
UPPER_BOUND = 123000.0  # 网格上界（阻力）
LOWER_BOUND = 111500.0  # 网格下界（支撑）
GRID_MODE = 'Neutral'  # 网格模式: 'Neutral', 'Long', 'Short'
# 'Neutral': 双向网格（long + short），仓位中性，不压方向
# 'Long': 震荡做多（靠近支撑时使用），偏向做多
# 'Short': 震荡做空（靠近阻力时使用），偏向做空

# Strategy parameters (智能动态网格)
STRATEGY_CONFIG = SmartGridConfig(
    name="Smart Grid Strategy",
    description="智能动态网格策略（支持做空、多笔交易、衰减机制）",
    
    # 网格区间（交易员手动设置）
    upper_bound=UPPER_BOUND,
    lower_bound=LOWER_BOUND,
    
    # 网格模式（根据市场状态选择）
    grid_mode=GRID_MODE,  # 'Neutral', 'Long', 'Short'
    
    # 几何网格参数（基于文档建议）
    grid_gap_pct=0.0018,  # 基础网格间距 0.18%（文档建议值）
    alpha=2.0,  # 几何序列系数（价格越远间距越大）
    max_layers_per_side=10,  # 单边最多10层
    
    # 仓位管理参数
    position_fraction=0.05,  # 单格基础仓位比例 5%
    max_exposure_pct=0.50,  # 最大资金暴露 50%（文档建议值）
    edge_weight_multiplier=2.0,  # 边缘权重倍数（靠近支撑/阻力权重更大）
    
    # 衰减机制参数
    enable_hit_decay=True,  # 启用命中衰减
    decay_k=2.0,  # 衰减系数（文档建议值）
    
    # 做空和多笔交易支持
    allow_shorting=True,  # 允许做空（中性市场时，上面的卖单可以直接做空）
    allow_multiple_positions=True,  # 允许多笔交易（同一网格可以多次触发）
    max_concurrent_positions=20,  # 最大同时持仓数
    
    # 交易成本
    commission=0.002,  # 0.2% 手续费
    slippage=0.0005,  # 0.05% 滑点
)

# Backtest parameters
INITIAL_CASH = 100000.0  # 初始资金 10万 USDT

# Output - use unified results directory
OUTPUT_DIR = get_results_dir()

# =============================================================================
# EXECUTION - No need to modify below
# =============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("网格策略回测")
    print("=" * 80)
    print(f"策略:      {STRATEGY_CONFIG.name}")
    print(f"交易对:    {SYMBOL}")
    print(f"时间框架:  {TIMEFRAME} (执行时间框架)")
    print(f"回测周期:  {START.date()} 到 {END.date()}")
    print(f"数据源:    {SOURCE}")
    print(f"网格区间:  ${LOWER_BOUND:,.0f} - ${UPPER_BOUND:,.0f}")
    print(f"网格模式:  {GRID_MODE}")
    print(f"初始资金:  ${INITIAL_CASH:,.2f}")
    print(f"允许做空:  {STRATEGY_CONFIG.allow_shorting}")
    print(f"多笔交易:  {STRATEGY_CONFIG.allow_multiple_positions}")
    print("=" * 80 + "\n")
    
    # Initialize components
    print("[Data] 正在获取数据...")
    data_manager = DataManager()
    
    try:
        execution_data = data_manager.get_klines(
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            start=START,
            end=END,
            source=SOURCE,
            use_cache=True,
        )
        print(f"   [OK] 获取 {len(execution_data)} 条数据")
        print(f"   [OK] 数据范围: {execution_data.index[0]} 到 {execution_data.index[-1]}")
        print(f"   [OK] 价格范围: ${execution_data['close'].min():,.0f} - ${execution_data['close'].max():,.0f}")
    except Exception as e:
        print(f"   [ERROR] 获取数据失败: {e}")
        sys.exit(1)
    
    # 检查价格范围
    price_min = execution_data['close'].min()
    price_max = execution_data['close'].max()
    
    if UPPER_BOUND > price_max or LOWER_BOUND < price_min:
        print(f"\n[Warning] 设置的网格区间超出数据价格范围")
        print(f"  数据价格范围: ${price_min:,.0f} - ${price_max:,.0f}")
        print(f"  设置的区间: ${LOWER_BOUND:,.0f} - ${UPPER_BOUND:,.0f}")
        
        # 自动调整
        if UPPER_BOUND > price_max:
            STRATEGY_CONFIG.upper_bound = price_max * 0.999
            print(f"  自动调整上界: ${STRATEGY_CONFIG.upper_bound:,.0f}")
        if LOWER_BOUND < price_min:
            STRATEGY_CONFIG.lower_bound = price_min * 1.001
            print(f"  自动调整下界: ${STRATEGY_CONFIG.lower_bound:,.0f}")
    
    # Create strategy
    print(f"\n[Strategy] 创建策略: {STRATEGY_CONFIG.name}...")
    strategy = SmartGridStrategy(STRATEGY_CONFIG)
    
    # 查看网格信息
    grid_info = strategy.get_grid_info()
    print(f"   [OK] 网格层级数: {grid_info['num_levels']}")
    print(f"   [OK] 买入层级: {grid_info['buy_levels']}")
    print(f"   [OK] 卖出层级: {grid_info['sell_levels']}")
    print(f"   [OK] 网格间距: {grid_info['grid_gap_pct']*100:.4f}%")
    print(f"   [OK] 几何系数: {grid_info['alpha']}")
    
    # Create backtester
    print(f"\n[Backtest] 运行回测...")
    backtester = SmartGridBacktester(strategy)
    
    try:
        result = backtester.run(
            execution_data=execution_data,
            start_date=START,
            end_date=END,
            initial_cash=INITIAL_CASH,
            commission=STRATEGY_CONFIG.commission,
            slippage=STRATEGY_CONFIG.slippage,
        )
        print(f"   [OK] 回测完成")
    except Exception as e:
        print(f"   [ERROR] 回测失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Display results
    print("\n" + "=" * 80)
    print("回测结果")
    print("=" * 80)
    
    metrics = result.metrics
    metadata = result.metadata
    
    print(f"\n📊 性能指标:")
    print(f"  总收益率: {metrics['total_return']:.2f}%")
    print(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.3f}")
    print(f"  Sortino Ratio: {metrics['sortino_ratio']:.3f}")
    print(f"  最大回撤: {metrics['max_drawdown']:.2f}%")
    print(f"  最终权益: ${metrics['final_equity']:,.2f}")
    print(f"  盈亏: ${metrics['final_equity'] - INITIAL_CASH:,.2f}")
    
    print(f"\n📈 交易统计:")
    print(f"  总交易次数: {metrics['total_trades']}")
    print(f"  胜率: {metrics['win_rate']:.2f}%")
    print(f"  Profit Factor: {metrics['profit_factor']:.2f}")
    
    print(f"\n⚙️  策略配置:")
    print(f"  执行时间框架: {metadata.get('execution_timeframe', 'unknown')}")
    print(f"  网格模式: {STRATEGY_CONFIG.grid_mode}")
    print(f"  允许做空: {metadata.get('allow_shorting', False)}")
    print(f"  多笔交易: {metadata.get('allow_multiple_positions', False)}")
    print(f"  回测周期: {metadata['start_time']} 到 {metadata['end_time']}")
    
    # Save results
    print(f"\n[Results] 保存结果到 {OUTPUT_DIR}...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Generate filename prefix
    prefix = f"SmartGrid_{SYMBOL}_{START.date()}_{(END - START).days}days"
    
    # Save trades
    if not result.trades.empty:
        trades_path = OUTPUT_DIR / f"{prefix}_trades.csv"
        result.trades.to_csv(trades_path, index=False)
        print(f"   [OK] 交易记录: {trades_path}")
    
    # Save equity curve
    if not result.equity_curve.empty:
        equity_path = OUTPUT_DIR / f"{prefix}_equity.csv"
        result.equity_curve.to_csv(equity_path)
        print(f"   [OK] 权益曲线: {equity_path}")
    
    # Generate orders DataFrame for visualization and saving
    orders_df = strategy.generate_orders(execution_data, initial_cash=INITIAL_CASH)
    
    # Prepare orders for saving (format similar to SR Short orders.csv)
    if not orders_df.empty:
        orders_for_save = orders_df.reset_index()
        orders_for_save.rename(columns={'time': 'timestamp'}, inplace=True)
        
        # Convert direction to SHORT/LONG format (like SR Short)
        # buy = LONG, sell = SHORT (for grid, sell can be exit or short)
        orders_for_save['direction'] = orders_for_save['direction'].apply(
            lambda x: 'LONG' if x == 'buy' else 'SHORT'
        )
        
        # Determine order_type based on grid pairing logic
        # For grid strategy:
        # - LONG (buy): Always ENTRY (opening long position)
        # - SHORT (sell): Can be EXIT (closing long) or ENTRY (opening short)
        # In Neutral mode with pairing: sells are typically EXIT (closing paired longs)
        # In Short mode: sells can be ENTRY (opening short) or EXIT (closing short)
        def determine_order_type(row):
            if row['direction'] == 'LONG':
                return 'ENTRY'  # Buying is always entry (opening long)
            else:  # SHORT (selling)
                # For grid pairing strategy, most sells are EXIT (closing paired positions)
                # Only in Short mode with allow_shorting, sells can be ENTRY (opening short)
                if STRATEGY_CONFIG.grid_mode == 'Short' and STRATEGY_CONFIG.allow_shorting:
                    # In Short mode, check if we have existing longs to close
                    # If no longs, it's opening a short (ENTRY), otherwise EXIT
                    # For simplicity, we'll mark as EXIT for pairing grid
                    return 'EXIT'
                else:
                    return 'EXIT'  # Neutral/Long mode: sells are EXIT (closing longs)
        
        orders_for_save['order_type'] = orders_for_save.apply(determine_order_type, axis=1)
        
        # Ensure size is positive (direction already indicates buy/sell)
        orders_for_save['size'] = orders_for_save['size'].abs()
        
        # Select columns matching SR Short format: timestamp, price, size, direction, order_type
        orders_for_save = orders_for_save[['timestamp', 'price', 'size', 'direction', 'order_type']]
        
        # Save orders CSV
        orders_path = OUTPUT_DIR / f"{prefix}_orders.csv"
        orders_for_save.to_csv(orders_path, index=False)
        print(f"   [OK] 订单记录: {orders_path}")
        
        # Prepare orders for visualization (keep original format)
        orders_for_plot = orders_df.reset_index()
        orders_for_plot.rename(columns={'time': 'timestamp'}, inplace=True)
        orders_for_plot['order_type'] = orders_for_plot['direction'].apply(
            lambda x: 'ENTRY' if x == 'buy' else 'EXIT'
        )
    else:
        orders_for_plot = pd.DataFrame()
        orders_for_save = pd.DataFrame()
    
    # Create visualization
    print(f"\n[Plot] 生成K线图和交易标记...")
    try:
        from execution.visualization import plot_backtest_results
        
        plot_path = OUTPUT_DIR / f"{prefix}_plot.html"
        plot_backtest_results(
            result=result,
            data=execution_data,
            orders_data=orders_for_plot,
            output_path=plot_path,
            title=f"网格策略回测 - {SYMBOL} ({START.date()} 到 {END.date()})",
            show_trades=True,
        )
        print(f"   [OK] 图表已保存: {plot_path}")
    except Exception as e:
        print(f"   [Warning] 生成图表失败: {e}")
        import traceback
        traceback.print_exc()
    
    # Save metrics
    import json
    metrics_path = OUTPUT_DIR / f"{prefix}_metrics.json"
    metrics_data = {
        'strategy': STRATEGY_CONFIG.name,
        'symbol': SYMBOL,
        'timeframe': TIMEFRAME,
        'start_date': str(START),
        'end_date': str(END),
        'grid_config': {
            'upper_bound': STRATEGY_CONFIG.upper_bound,
            'lower_bound': STRATEGY_CONFIG.lower_bound,
            'grid_gap_pct': STRATEGY_CONFIG.grid_gap_pct,
            'alpha': STRATEGY_CONFIG.alpha,
            'position_fraction': STRATEGY_CONFIG.position_fraction,
            'max_exposure_pct': STRATEGY_CONFIG.max_exposure_pct,
            'edge_weight_multiplier': STRATEGY_CONFIG.edge_weight_multiplier,
            'enable_hit_decay': STRATEGY_CONFIG.enable_hit_decay,
            'decay_k': STRATEGY_CONFIG.decay_k,
            'allow_shorting': STRATEGY_CONFIG.allow_shorting,
            'allow_multiple_positions': STRATEGY_CONFIG.allow_multiple_positions,
            'grid_mode': STRATEGY_CONFIG.grid_mode,
        },
        'metrics': metrics,
        'metadata': metadata,
    }
    with open(metrics_path, 'w', encoding='utf-8') as f:
        json.dump(metrics_data, f, indent=2, ensure_ascii=False, default=str)
    print(f"   [OK] 性能指标: {metrics_path}")
    
    # Display grid hit statistics (if available)
    if hasattr(strategy, 'grid_hit_counts') and strategy.grid_hit_counts:
        print(f"\n📊 网格命中统计:")
        hit_counts = sorted(strategy.grid_hit_counts.items(), key=lambda x: x[1], reverse=True)
        for grid_key, hits in hit_counts[:10]:
            print(f"  网格 {grid_key}: {hits} 次")
    
    print("\n" + "=" * 80)
    print("[Success] 回测完成！")
    print("=" * 80)


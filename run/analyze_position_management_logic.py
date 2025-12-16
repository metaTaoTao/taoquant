"""
基于真实代码逻辑分析仓位管理机制
参考代码：algorithms/taogrid/helpers/grid_manager.py::calculate_order_size()
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("=" * 80)
print("TaoGrid 仓位管理机制分析（基于真实代码逻辑）")
print("=" * 80)

# 从代码中提取的关键逻辑
position_management_logic = {
    "1. 基础仓位计算": {
        "代码位置": "grid_manager.py:517-525",
        "逻辑": """
        # 1. 计算基础仓位（USD）
        total_budget_usd = equity * risk_budget_pct
        this_level_budget_usd = total_budget_usd * weight  # weight是层级权重
        
        # 2. 转换为BTC数量
        base_size_btc = this_level_budget_usd / level_price
        
        # 3. 应用杠杆
        base_size_btc = base_size_btc * leverage
        """,
        "说明": "基础仓位 = (权益 × 风险预算比例 × 层级权重) / 价格 × 杠杆",
    },
    
    "2. 库存感知仓位控制（Inventory-Aware Sizing）": {
        "代码位置": "grid_manager.py:539-558",
        "逻辑": """
        # 计算库存比率（名义价值/权益）
        inv_ratio = (holdings_btc * level_price) / equity
        inv_ratio_threshold = inventory_capacity_threshold_pct * leverage
        
        # 买入时：
        if direction == "buy":
            # 如果库存比率 >= 阈值，完全阻止买入
            if inv_ratio >= inv_ratio_threshold:
                return 0.0  # 完全阻止
            
            # 否则，根据库存比率逐步减少买入仓位
            if inventory_skew_k > 0:
                skew_mult = max(0.0, 1.0 - inventory_skew_k * (inv_ratio / inv_ratio_threshold))
                base_size_btc = base_size_btc * skew_mult
        """,
        "说明": """
        关键机制：
        - 库存比率 = (持仓BTC数量 × 价格) / 权益
        - 阈值 = inventory_capacity_threshold_pct × 杠杆
        - 当库存比率接近阈值时，买入仓位逐步减少
        - 当库存比率 >= 阈值时，完全阻止买入
        """,
        "参数": {
            "inventory_capacity_threshold_pct": "0.9 (90%)",
            "inventory_skew_k": "1.0 (强度)",
            "leverage": "50X",
            "实际阈值": "0.9 × 50 = 45倍权益的名义价值",
        },
    },
    
    "3. Market Maker Risk Zone（做市商风险区域）": {
        "代码位置": "grid_manager.py:532-576, 721-733",
        "逻辑": """
        # 判断是否进入风险区域
        risk_zone_threshold = support + (ATR * cushion_multiplier)
        if current_price < risk_zone_threshold:
            in_risk_zone = True
        
        # 买入时（在风险区域）：
        if direction == "buy" and in_risk_zone:
            # 根据风险等级应用不同的倍数
            if risk_level == 3:  # 严重风险
                mm_buy_mult = 0.05  # 买入仓位减少到5%
            elif risk_level == 2:  # 中等风险
                mm_buy_mult = 0.1   # 买入仓位减少到10%
            else:  # 轻度风险
                mm_buy_mult = 0.2   # 买入仓位减少到20%
            
            # 如果库存已经很高，进一步减少50%
            if inv_ratio > 0.5:
                mm_buy_mult = mm_buy_mult * 0.5
            
            base_size_btc = base_size_btc * mm_buy_mult
        
        # 卖出时（在风险区域）：
        if direction == "sell" and in_risk_zone:
            if risk_level == 3:
                mm_sell_mult = 5.0  # 卖出仓位增加到500%
            elif risk_level == 2:
                mm_sell_mult = 4.0  # 卖出仓位增加到400%
            else:
                mm_sell_mult = 3.0  # 卖出仓位增加到300%
            
            base_size_btc = base_size_btc * mm_sell_mult
        """,
        "说明": """
        关键机制：
        - 当价格跌破 support + (ATR × cushion) 时，进入风险模式
        - 买入仓位大幅减少（5%-20%），卖出仓位大幅增加（300%-500%）
        - 这是做市商风格的"去库存"机制
        """,
        "参数": {
            "mm_risk_level1_buy_mult": "0.2 (买入20%)",
            "mm_risk_level1_sell_mult": "3.0 (卖出300%)",
            "mm_risk_level3_buy_mult": "0.05 (买入5%)",
            "mm_risk_level3_sell_mult": "5.0 (卖出500%)",
        },
    },
    
    "4. 因子过滤（Factor Filters）": {
        "代码位置": "grid_manager.py:578-640, 664-672",
        "逻辑": """
        # 4.1 MR + Trend因子
        if enable_mr_trend_factor:
            # 强下跌趋势：完全阻止买入
            if trend_score <= -trend_block_threshold:
                return 0.0  # 完全阻止
            
            # 趋势倍数：下跌趋势时减少买入
            trend_mult = max(trend_buy_floor, 1.0 - trend_buy_k * (-trend_score))
            # MR倍数：超卖时增加买入
            mr_mult = max(mr_min_mult, mr_strength)
            
            factor_mult = trend_mult * mr_mult
            base_size_btc = base_size_btc * factor_mult
        
        # 4.2 Breakout Risk因子
        if enable_breakout_risk_factor:
            # 突破风险高时：完全阻止买入
            if breakout_risk_down >= breakout_block_threshold:
                return 0.0  # 完全阻止
            
            # 突破风险倍数：风险高时减少买入
            risk_mult = max(breakout_buy_floor, 1.0 - breakout_buy_k * breakout_risk_down)
            base_size_btc = base_size_btc * risk_mult
        
        # 4.3 Funding因子（资金费率）
        if enable_funding_factor:
            # 资金费率高时：减少买入/增加卖出
            if funding_rate >= funding_block_threshold:
                return 0.0  # 完全阻止买入
            
            if funding_rate > 0:
                buy_mult = max(funding_buy_floor, 1.0 - funding_buy_k * (funding_rate / funding_ref))
                base_size_btc = base_size_btc * buy_mult
        
        # 4.4 Range Position Asymmetry v2（区间位置不对称）
        if enable_range_pos_asymmetry_v2:
            # 在顶部区域（range_pos >= 0.85）：
            if range_pos >= range_top_band_start:
                # 减少买入，增加卖出
                buy_mult = max(range_buy_floor, 1.0 - range_buy_k * x)
                sell_mult = min(range_sell_cap, 1.0 + range_sell_k * x)
                base_size_btc = base_size_btc * (buy_mult if buy else sell_mult)
        
        # 4.5 Volatility Regime因子（波动率制度）
        if enable_vol_regime_factor:
            # 极端高波动时：增加卖出
            if vol_score >= vol_trigger_score:
                if direction == "sell":
                    base_size_btc = base_size_btc * vol_sell_mult_high
        """,
        "说明": """
        多个因子协同工作：
        - MR + Trend: 在强下跌趋势时阻止买入
        - Breakout Risk: 在突破风险高时阻止买入（这是10.10-10.11期间的关键！）
        - Funding: 在资金费率高时减少买入/增加卖出
        - Range Position: 在顶部区域减少买入/增加卖出
        - Volatility: 在极端波动时增加卖出
        """,
    },
    
    "5. 卖出仓位限制": {
        "代码位置": "grid_manager.py:735",
        "逻辑": """
        # 卖出时，不能超过当前持仓
        if direction == "sell":
            base_size_btc = min(base_size_btc, max(0.0, holdings_btc))
        """,
        "说明": "卖出仓位不能超过当前持仓，避免卖空",
    },
    
    "6. 最终节流检查（Throttling）": {
        "代码位置": "grid_manager.py:737-747",
        "逻辑": """
        # 应用节流规则（如果启用）
        if enable_throttling:
            throttle_status = risk_manager.check_throttle(
                long_exposure=inventory_state.long_exposure,
                short_exposure=inventory_state.short_exposure,
                daily_pnl=daily_pnl,
                risk_budget=risk_budget,
                current_atr=self.current_atr,
                avg_atr=self.avg_atr,
            )
            size_btc = base_size_btc * throttle_status.size_multiplier
        """,
        "说明": "最后应用节流规则（库存限制、利润目标锁定、波动率节流）",
    },
}

print("\n" + "=" * 80)
print("详细分析")
print("=" * 80)

for key, details in position_management_logic.items():
    print(f"\n【{key}】")
    print(f"代码位置: {details.get('代码位置', 'N/A')}")
    print(f"\n逻辑:")
    print(details.get('逻辑', ''))
    print(f"\n说明:")
    print(details.get('说明', ''))
    if '参数' in details:
        print(f"\n关键参数:")
        for param, value in details['参数'].items():
            print(f"  - {param}: {value}")
    print()

print("=" * 80)
print("为什么仓位控制得这么好？")
print("=" * 80)

analysis = """
基于代码逻辑，仓位控制得好的原因：

1. **多层级的仓位限制机制**
   - 基础仓位计算：基于权益和风险预算
   - 库存感知控制：当库存比率接近阈值时，逐步减少买入
   - 风险区域控制：在价格跌破支撑时，买入大幅减少，卖出大幅增加
   - 因子过滤：多个因子协同工作，在不利条件下阻止或减少买入

2. **库存比率（Inventory Ratio）的实时监控**
   - inv_ratio = (holdings_btc * price) / equity
   - 阈值 = inventory_capacity_threshold_pct × leverage = 0.9 × 50 = 45倍权益
   - 当 inv_ratio >= 45 时，完全阻止买入
   - 当 inv_ratio 接近 45 时，通过 inventory_skew_k 逐步减少买入

3. **Market Maker Risk Zone 的做市商风格去库存**
   - 当价格跌破 support + (ATR × cushion) 时：
     * 买入仓位减少到 5%-20%
     * 卖出仓位增加到 300%-500%
   - 这是典型的做市商"去库存"行为：在风险区域，减少新开仓，增加平仓

4. **Breakout Risk 因子在极端情况下的保护**
   - 在10.10-10.11期间，价格快速下跌时：
     * breakout_risk_down >= 0.95 时，完全阻止买入
     * 这是为什么在价格到101K时，没有新买入订单的原因
   - 从日志看到："Order blocked - BUY L38: Breakout risk-off (downside)"

5. **卖出仓位的动态放大**
   - 在风险区域，卖出仓位可以增加到 300%-500%
   - 这意味着在价格下跌时，卖出订单会快速执行，快速减少持仓
   - 从日志看，21:20之后有大量卖出订单执行，持仓从70%快速降到54%

6. **因子协同工作**
   - MR + Trend: 在强下跌趋势时阻止买入
   - Breakout Risk: 在突破风险高时阻止买入（关键！）
   - Funding: 在资金费率高时减少买入/增加卖出
   - Range Position: 在顶部区域减少买入/增加卖出
   - Volatility: 在极端波动时增加卖出

7. **卖出配对机制快速减少持仓**
   - 每次卖出订单都会通过配对机制减少持仓
   - 在价格反弹过程中，卖出订单快速执行
   - 持仓在价格反弹过程中快速降低

总结：
- 仓位控制不是单一机制，而是多层级的协同工作
- 库存比率实时监控，接近阈值时逐步减少买入
- 风险区域触发时，买入大幅减少，卖出大幅增加
- Breakout Risk 因子在极端情况下完全阻止买入
- 卖出仓位的动态放大，快速减少持仓
"""

print(analysis)

print("\n" + "=" * 80)
print("关键代码引用")
print("=" * 80)

code_references = """
1. 库存比率计算和限制：
   algorithms/taogrid/helpers/grid_manager.py:545-558
   
2. Market Maker Risk Zone：
   algorithms/taogrid/helpers/grid_manager.py:532-576, 721-733
   
3. Breakout Risk 因子阻止买入：
   algorithms/taogrid/helpers/grid_manager.py:619-632
   
4. 卖出仓位限制和放大：
   algorithms/taogrid/helpers/grid_manager.py:735, 721-733
   
5. 配置参数：
   algorithms/taogrid/config.py:53-149
"""

print(code_references)

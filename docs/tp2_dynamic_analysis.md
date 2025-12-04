# TP2动态触发问题分析

## 问题场景

### 场景描述
1. **开仓**：100%仓位 @ 价格P0
2. **TP1触发**（2.33x RR）：平掉30%，剩余70%
3. **TP2触发**（在TP1之后）：
   - 可能是固定目标（如5x RR）
   - 可能是trailing stop（在TP1之后才开始跟踪）
   - 可能是动态计算的（基于TP1触发后的价格行为）

### 关键问题
**TP2的exit信号可能依赖于TP1是否已经触发**

例如：
- 如果TP1未触发 → TP2 = 固定目标（5x RR）
- 如果TP1已触发 → TP2 = trailing stop（从TP1触发点开始跟踪）

## 分离Portfolios方案的局限性

### 为什么不行？

```python
# 开仓时创建2个portfolio
portfolio_30pct = vbt.Portfolio.from_signals(
    entries=entry_signals,      # 开仓时就知道
    exits=tp1_exit_signals,     # 开仓时就知道（2.33x RR）
    size=0.3,
)

portfolio_70pct = vbt.Portfolio.from_signals(
    entries=entry_signals,      # 开仓时就知道
    exits=tp2_exit_signals,     # ❌ 问题：TP2可能依赖TP1是否触发
    size=0.7,
)
```

**问题**：
- VectorBT的`from_signals`是**向量化的**，所有信号必须在开始时就知道
- 无法根据"TP1是否触发"动态调整TP2的exit逻辑
- TP2如果是trailing stop，需要在TP1触发后**实时跟踪**，但向量化无法做到

## 可行方案对比

### 方案1：自定义事件驱动引擎 ⭐⭐⭐⭐⭐
**实现方式**：
- 逐bar处理，完全控制仓位
- 可以动态判断TP1是否触发
- TP2逻辑可以根据TP1状态动态调整

**优点**：
- ✅ 完全灵活，支持任何逻辑
- ✅ 可以处理动态TP2
- ✅ 真正的部分平仓
- ✅ 支持trailing stop（实时跟踪）

**缺点**：
- ❌ 需要自己实现（但不算复杂）
- ❌ 性能比向量化慢（但单资产策略通常够用）

**工作量**：3-5天

### 方案2：修改策略逻辑，预计算所有可能 ⭐⭐
**实现方式**：
- 在策略层面，预先计算所有可能的TP2场景
- 创建多个portfolio覆盖所有情况
- 最后选择正确的结果

**例子**：
```python
# 场景1：TP1触发，TP2是trailing stop
portfolio_scenario1_30pct = ...  # TP1 exit
portfolio_scenario1_70pct = ...  # Trailing stop exit

# 场景2：TP1未触发，直接到TP2
portfolio_scenario2_100pct = ...  # TP2 exit

# 然后根据实际价格行为选择正确的scenario
```

**优点**：
- ✅ 可以用VectorBT
- ✅ 保持向量化性能

**缺点**：
- ❌ 逻辑复杂，需要预计算所有场景
- ❌ 如果TP2是动态的（如trailing stop），无法预计算
- ❌ 代码复杂，难以维护

**工作量**：5-7天（且可能无法完全实现）

### 方案3：混合方案 ⭐⭐⭐
**实现方式**：
- TP1用分离的portfolios（因为TP1是固定的2.33x RR）
- TP2用自定义引擎（因为TP2是动态的）

**流程**：
1. 开仓：创建portfolio_30pct + portfolio_70pct
2. TP1触发：portfolio_30pct退出
3. TP2处理：切换到自定义引擎，处理剩余70%的trailing stop

**优点**：
- ✅ TP1部分用VectorBT（快速）
- ✅ TP2部分用自定义引擎（灵活）

**缺点**：
- ❌ 需要两套系统
- ❌ 切换逻辑复杂
- ❌ 结果合并复杂

**工作量**：4-6天

## 推荐方案

### 立即行动：方案1（自定义事件驱动引擎）

**理由**：
1. **TP2是动态的**：如果TP2是trailing stop或依赖TP1状态，必须用事件驱动
2. **长期可靠**：一次实现，支持所有未来需求
3. **逻辑清晰**：代码直观，易于维护
4. **性能足够**：单资产策略，事件驱动性能通常够用

**实现思路**：
```python
class EventDrivenEngine(BacktestEngine):
    def run(self, data, signals, sizes, config):
        # 逐bar处理
        for i, bar in enumerate(data.iterrows()):
            # 检查entry
            if signals['entry'].iloc[i]:
                # 开仓：100%
                position = Position(
                    entry_price=bar['close'],
                    size=calculate_size(...),
                    tp1_target=...,
                    tp2_type='trailing_stop',  # 动态
                )
            
            # 检查TP1
            if position and not position.tp1_hit:
                if profit >= tp1_target:
                    # 部分平仓：30%
                    close_partial(position, 0.3)
                    position.tp1_hit = True
                    # 启动trailing stop
                    position.tp2_active = True
            
            # 检查TP2（trailing stop）
            if position and position.tp2_active:
                update_trailing_stop(position, bar)
                if hit_trailing_stop(position, bar):
                    close_position(position)
```

## 时间线建议

### 第1周：实现自定义引擎
- Day 1-2: 核心引擎框架
- Day 3-4: 仓位管理（部分平仓）
- Day 5: TP1/TP2逻辑
- Day 6-7: 测试和优化

### 第2周：集成和测试
- 集成到现有系统
- 完整测试
- 性能优化

## 结论

**如果TP2是动态的（依赖TP1状态或trailing stop），必须用事件驱动引擎。**

分离portfolios方案只适用于：
- TP1和TP2都是**固定目标**（如固定RR倍数）
- TP1和TP2的exit信号可以**在开仓时预先计算**

对于你的需求（TP1后启动trailing stop），**自定义事件驱动引擎是唯一可行的方案**。


# Strategy Analysis Summary

## 问题1: 为什么开仓数量这么少？

### 分析结果

**实际数据：**
- 4H数据：361个bars
- 找到的S/R区域：**只有2个**（其中1个是无效的，实际只有1个有效区域）
- 有效区域：Top=116400.00, Bottom=115449.90, Touches=1
- 15m bars在zone内：**15个**
- 生成的entry signals：**15个**
- 实际执行的交易：**只有1个**

### 根本原因

**a. S/R找的少？** ✅ **是的！**
- 当前参数：`left_len=90, right_len=10` 在4H上意味着：
  - 需要90个4H bars（约15天）的lookback
  - 需要10个4H bars（约1.7天）的确认
- 这个参数设置**太严格**，导致只找到了1个有效区域
- 在2个月的数据中，只有1个区域被检测到

**b. 15min的线对这个区间touch的少？** ❌ **不是主要问题**
- 实际上有15个15m bars在zone内
- 策略生成了15个entry signals
- 问题在于VectorBT的执行逻辑

**c. VectorBT执行问题：** ✅ **这是主要问题！**
- VectorBT的`from_signals`在已有持仓时，**会忽略后续的entry signals**
- 第一个信号开仓后，后续14个信号都被忽略了
- 因为没有exit signals，持仓一直保持到回测结束（或SL触发）

### 解决方案

1. **增加S/R区域数量：**
   - 降低`left_len`（例如从90降到50-60）
   - 降低`right_len`（例如从10降到5-7）
   - 降低`merge_atr_mult`（例如从3.5降到2.5-3.0）

2. **允许多个持仓：**
   - 修改策略逻辑，允许在已有持仓时继续开新仓
   - 或者实现position filtering，确保新信号在合理距离内才开仓

3. **实现exit signals：**
   - 当前exit_signal全部是False
   - 需要实现TP/SL逻辑，让持仓能够及时退出

---

## 问题2: 为什么零成本持仓的思想没有应用？

### 分析结果

**当前实现：**
- ❌ **没有TP（Take Profit）定义**
- ✅ 只有SL（Stop Loss）= 3 * ATR(200)
- ❌ **没有部分平仓逻辑**
- ❌ **没有移动止损到入场价（breakeven）的逻辑**

**零成本持仓的概念：**
1. 在TP1时，平掉50%仓位
2. 将SL移动到入场价（breakeven）
3. 剩余50%仓位变成"零成本"（没有风险）
4. 让剩余仓位继续运行到TP2或SL

### 根本原因

1. **策略层面：**
   - `generate_signals()`中`exit_signal = pd.Series(False, ...)`，所有exit都是False
   - 没有TP1/TP2的定义
   - 没有部分平仓的逻辑

2. **引擎层面：**
   - VectorBT的`from_signals`不支持部分平仓
   - 不支持动态移动止损
   - 只支持简单的entry/exit信号

3. **架构设计：**
   - 当前架构是信号驱动的，不适合复杂的仓位管理
   - 需要事件驱动的引擎或自定义仓位管理器

### 解决方案

**方案1：在策略层面实现（推荐）**
- 添加TP1/TP2配置（例如：TP1 = 1*ATR, TP2 = 2*ATR）
- 在`generate_signals()`中实现：
  - 检测是否达到TP1，生成50%平仓信号
  - 检测是否达到TP2，生成剩余50%平仓信号
  - 在TP1后，将SL移动到入场价

**方案2：使用自定义仓位管理器**
- 创建一个`PositionManager`类，跟踪每个持仓的状态
- 在每个bar检查：
  - 是否达到TP1 → 部分平仓
  - 是否达到TP2 → 全部平仓
  - 是否达到SL → 全部平仓
  - 是否在TP1后 → 移动SL到breakeven

**方案3：切换到事件驱动引擎**
- 使用类似`backtesting.py`的事件驱动引擎
- 可以更灵活地处理部分平仓和移动止损

---

## 推荐行动计划

### 短期（立即实施）

1. **增加交易频率：**
   ```python
   config = SRShortConfig(
       left_len=50,      # 从90降到50
       right_len=5,      # 从10降到5
       merge_atr_mult=2.5,  # 从3.5降到2.5
       min_touches=1,    # 保持1
   )
   ```

2. **实现基础TP逻辑：**
   ```python
   # 在generate_signals中添加
   tp1_distance = data['atr'] * 1.0  # TP1 = 1*ATR
   tp2_distance = data['atr'] * 2.0  # TP2 = 2*ATR
   
   # 检测TP1：平50%
   # 检测TP2：平剩余50%
   ```

### 中期（1-2周）

3. **实现零成本持仓：**
   - 添加`PositionManager`类
   - 跟踪每个持仓的TP1/TP2状态
   - 在TP1后移动SL到breakeven

4. **优化S/R检测：**
   - 测试不同的参数组合
   - 找到最优的left_len/right_len/merge_atr_mult

### 长期（1个月+）

5. **考虑切换到事件驱动引擎：**
   - 如果需要更复杂的仓位管理
   - 如果需要更精确的订单执行

---

## 当前交易分析

**唯一执行的交易：**
- Entry: 2025-10-27 08:00:00 @ ~115450
- Exit: 2025-11-30 23:45:00 @ ~115200（回测结束）
- Return: 21.59%
- Duration: ~34天

**如果实现了TP1（1*ATR）：**
- TP1价格: ~115450 - 1*ATR ≈ 114500（假设ATR≈950）
- 会在更早的时间点平掉50%仓位
- 剩余50%仓位可以继续运行，SL移到breakeven


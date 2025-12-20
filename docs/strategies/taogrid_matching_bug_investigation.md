# TaoGrid网格策略Position Matching Bug深度调查报告

**日期**: 2025-12-21
**状态**: 已修复 (2025-12-20)
**Token使用**: ~122k/200k

---

## 执行摘要

TaoGrid网格策略在回测中发现**50%的交易配对错误**，导致平均单笔收益为负(-0.16%)。经过深入调查，发现根本原因是：**Sell订单的size被风控multipliers放大，超过了对应Buy position的size**，导致单个sell需要匹配多个buy positions，后续匹配失败后触发FIFO fallback，产生错误配对和亏损交易。

---

## 问题背景

### 初始现象

回测配置：
- 期间: 2025-01-19 到 2025-02-22 (~35天)
- 支撑/阻力: $92,000 - $106,000
- 杠杆: 5x
- 所有风控启用

回测结果：
- 总收益: 2.08%
- 交易数: 637笔
- **平均单笔收益: -0.16%** ❌
- Sharpe: 9.47

### 预期 vs 实际

**预期**:
- min_return = 0.0012 (0.12%)
- spacing = 0.0016 (0.16%)
- 每笔交易应该盈利 ~0.12-0.16%

**实际**:
- 正确配对 (entry_level == exit_level): 320笔 (50.2%), 平均+0.15% ✓
- **错误配对 (entry_level ≠ exit_level): 317笔 (49.8%), 平均-0.47%** ❌

---

## 调查过程时间线

### 阶段1: 发现配对问题 (Token 82k-96k)

**发现**: 分析trades.csv后发现55.7%的交易配对错误

```python
# 配对分析
正确配对: 286笔 (44.3%), 收益 +0.14%
错误配对: 360笔 (55.7%), 收益 -0.22%
```

**关键观察**:
- 正确配对的收益(+0.14%)符合min_return设计 ✓
- 问题在于超过一半的交易没有正确配对

**Level不平衡发现**:
```
Level 11: 33 buys, 12 sells → 不平衡 -21
Level 16: 49 buys, 34 sells → 不平衡 -15
Level 10: 24 buys, 17 sells → 不平衡 -7
```
很多买入仓位没有在目标sell level平仓。

### 阶段2: 发现Price Tolerance Bug (Token 96k-110k)

**问题**: 两套仓位追踪系统使用不同的价格

**系统1**: `grid_manager.buy_positions`
- 存储: `grid_level_price` (网格价格)

**系统2**: `self.long_positions` (FIFO队列)
- 存储: `execution_price` (可能优于网格价格)

**Bug**: 匹配时tolerance检查过严

```python
# simple_lean_runner.py line 692 (修复前)
if pos['level'] == buy_level_idx and abs(pos['price'] - buy_price) < 0.01:
```

**示例**:
- 网格买单: $98,834 (grid_level_price)
- K线开盘: $98,800 (bar_open)
- 执行价格: min($98,834, $98,800) = $98,800
- long_positions存储: $98,800
- grid_manager存储: $98,834
- 检查: `abs($98,800 - $98,834) < $0.01`? → **False!**

**修复**: 提高tolerance到$100或0.1%

```python
price_tolerance = max(100.0, buy_price * 0.001)  # 0.1% or $100
```

**修复效果**:
- 正确配对: 44.3% → 50.2% (+5.9%) ✓
- 错误配对: 55.7% → 49.8% (-5.9%)

但问题依然严重 - 仍有50%错配！

### 阶段3: 深挖Grid Pairing失败原因 (Token 110k-121k)

**添加调试日志**: 追踪为什么`match_sell_order()`返回None

**关键发现**: 280次匹配失败，**100%都有buy positions可用**！

**失败模式**:
```
失败案例 #1:
- Sell Level 1触发
- Available: Buy[0]→Sell[0]
- 问题: target_sell_level不匹配！

失败案例 #4:
- Sell Level 2触发
- Available: Buy[0]→Sell[0], Buy[1]→Sell[1]
- 问题: 没有Buy position的target是Sell[2]
```

**结论**: Sell订单在触发，但对应的Buy position的target_sell_level不匹配！

### 阶段4: 找到根本原因 - Sell Size放大 (Token 121k-122k)

**时间序列分析**: 发现同一timestamp有多笔交易平仓

```
2025-01-27 10:38:00 (两笔交易同时平仓):
1. Entry[1] → Exit[1] ✓ (正确配对)
2. Entry[0] → Exit[1] ❌ (FIFO fallback)
```

**统计发现**:
- **259个exit timestamps有多笔交易** (占总数40%!)

**典型案例** (2025-02-03 06:20):
```
1. Entry[31] → Exit[31]: 0.0563 BTC, +0.13% ✓
2. Entry[28] → Exit[31]: 0.0069 BTC, -0.30% ❌
3. Entry[27] → Exit[31]: 0.0034 BTC, -0.50% ❌

总Sell Size = 0.0667 BTC
原始Buy Size = 0.0563 BTC
放大倍数 = 18%
```

---

## 根本原因分析

### 问题链条

1. **Buy订单成交** (level 31, 0.0563 BTC)
   - 添加buy position: Buy[31]→Sell[31], size=0.0563 BTC
   - 放置sell limit order: Sell[31]

2. **Sell订单触发** (level 31)
   - 计算sell size时，应用风控multipliers:
     - `mm_risk_sell_mult`: 3.0-5.0x (风险区)
     - `range_sell_k`: 1.5x (靠近阻力位)
     - `funding_sell_k`: 放大 (funding正向)
     - `vol_sell_mult_high`: 放大 (高波动)
   - **最终sell size = 0.0667 BTC** (放大18%)

3. **匹配过程** (simple_lean_runner.py line 655)
   ```python
   while remaining_sell_size > 0.0001:
       match_result = match_sell_order(sell_level, remaining_sell_size)
   ```
   - 第一次匹配: Buy[31] (0.0563 BTC) ✓ → 正确配对交易
   - 剩余: 0.0104 BTC
   - 第二次匹配: 找不到Buy[31] → **FIFO fallback** → 匹配Buy[28] ❌
   - 第三次匹配: **FIFO fallback** → 匹配Buy[27] ❌
   - 结果: 1笔正确交易 + 2笔错误交易

### 风控Multipliers位置

**代码位置**: `algorithms/taogrid/helpers/grid_manager.py`

**Sell方向的放大因子** (line 738-783):

```python
# Line 756-763: Range position asymmetry v2
if getattr(self.config, "enable_range_pos_asymmetry_v2", False):
    rp = float(range_pos) if range_pos is not None else 0.5
    start = float(self.config.range_top_band_start)
    if rp >= start:
        x = (rp - start) / max(1e-9, (1.0 - start))
        sell_mult = min(float(self.config.range_sell_cap), 1.0 + float(self.config.range_sell_k) * x)
        base_size_btc = base_size_btc * sell_mult  # ← 放大sell size

# Line 771-783: Market Maker Risk Zone
if in_risk_zone:
    if self.risk_level == 3:
        mm_sell_mult = 5.0  # ← 5倍放大！
    elif self.risk_level == 2:
        mm_sell_mult = 4.0  # ← 4倍放大！
    else:
        mm_sell_mult = 3.0  # ← 3倍放大！
    base_size_btc = base_size_btc * mm_sell_mult

# Line 765-769: Volatility regime factor
if getattr(self.config, "enable_vol_regime_factor", False):
    vs = float(vol_score) if vol_score is not None else 0.0
    if vs >= float(getattr(self.config, "vol_trigger_score", 1.0)):
        base_size_btc = base_size_btc * float(self.config.vol_sell_mult_high)

# Line 745-754: Funding factor
if getattr(self.config, "enable_funding_factor", False):
    fr = float(funding_rate) if funding_rate is not None else 0.0
    if fr > 0:
        x = min(1.0, max(0.0, fr / float(self.config.funding_ref)))
        sell_mult = min(float(self.config.funding_sell_cap), 1.0 + float(self.config.funding_sell_k) * x)
        base_size_btc = base_size_btc * sell_mult
```

**最后有size限制** (line 785):
```python
base_size_btc = min(base_size_btc, max(0.0, float(holdings_btc)))
```

但这个限制是基于**总holdings**，不是基于**对应buy position的size**！

---

## 为什么Min_Return保证失效

### 设计初衷

```
min_return = 0.0012 (0.12%)
spacing = min_return + trading_costs = 0.0016 (0.16%)

预期: Buy[i] @ $100,000 → Sell[i] @ $100,160
利润: 0.16% - 0.04% (费用) = 0.12% ✓
```

### 实际情况

```
Buy[31] @ $93,849, size=0.0563 BTC
↓
Sell[31] triggered, size=0.0667 BTC (放大18%)
↓
匹配1: Buy[31] 0.0563 BTC @ $93,849 → Sell @ $94,006 (+0.13%) ✓
匹配2: Buy[28] 0.0069 BTC @ $94,250 → Sell @ $94,006 (-0.30%) ❌
匹配3: Buy[27] 0.0034 BTC @ $94,439 → Sell @ $94,006 (-0.50%) ❌
```

**Buy[28]和Buy[27]在更高价位买入**（更接近阻力位），但被强制在更低的level平仓，造成亏损！

---

## 解决方案

### 方案1: 限制Sell Size = Buy Position Size (推荐)

**原则**: 网格策略应保持buy/sell对称，sell size不应超过对应buy position的size

**修改位置**: `grid_manager.py` line 785

**当前代码**:
```python
# 对于sell方向，限制为总holdings
base_size_btc = min(base_size_btc, max(0.0, float(holdings_btc)))
```

**修改为**:
```python
# 对于sell方向，获取对应buy position的size
if direction == "sell":
    # 查找target_sell_level匹配的buy position
    target_buy_size = 0.0
    for buy_idx, positions in self.buy_positions.items():
        for pos in positions:
            if pos.get('target_sell_level') == level_index:
                target_buy_size += pos['size']

    # 限制sell size不超过对应buy position size
    if target_buy_size > 0:
        base_size_btc = min(base_size_btc, target_buy_size)
    else:
        # 如果找不到对应buy position，限制为total holdings
        base_size_btc = min(base_size_btc, max(0.0, float(holdings_btc)))
```

**预期效果**:
- 消除多次匹配导致的FIFO fallback
- 配对正确率: 50% → ~95%+
- 平均单笔收益: -0.16% → +0.12%+

**风险**:
- 风控multipliers将失去对sell的放大效果
- 在风险情况下可能无法快速去杠杆

### 方案2: 提高Min_Return，容忍错配

**原则**: 即使FIFO fallback导致错配，也能盈利

**修改**: `simple_lean_runner.py` line 998

```python
min_return = 0.0050  # 从0.12%提高到0.50%
```

**预期效果**:
- spacing = 0.0054 (0.54%)
- 即使错配2-3层，仍有利润空间
- 交易数: ~100-200笔 (vs当前637笔)
- 平均单笔收益: +0.2%+

**优点**:
- 简单，不需要修改复杂逻辑
- 保留风控multipliers的功能

**缺点**:
- 治标不治本
- 降低交易频率

### 方案3: 禁用Sell Amplification (保守)

**修改**: `simple_lean_runner.py` config

```python
# 禁用所有sell amplification
enable_range_pos_asymmetry_v2 = False
enable_mm_risk_zone = False  # 或只禁用sell_mult
enable_vol_regime_factor = False
enable_funding_factor = False
```

**预期效果**:
- Sell size = Buy size (对称)
- 配对正确率: ~100%
- 但失去风控保护

---

## 相关代码文件

### 核心文件

1. **simple_lean_runner.py** (回测引擎)
   - Line 655-703: Sell订单匹配循环 (问题发生处)
   - Line 692-697: Price tolerance检查 (已修复)
   - Line 662-681: Match failure日志 (调试用)

2. **grid_manager.py** (网格管理器)
   - Line 504-814: `calculate_order_size()` (Sell size计算)
   - Line 738-785: Sell multipliers (问题根源)
   - Line 867-937: `match_sell_order()` (配对逻辑)
   - Line 816-865: `add_buy_position()` (Buy position追踪)

3. **algorithm.py** (策略核心)
   - Line 375-395: Buy成交处理 (放置sell order)
   - Line 399-413: Sell成交处理 (re-entry)

### 数据文件

- `run/results_stage1_extended/trades.csv`: 交易记录
- `run/results_stage1_extended/metrics.json`: 回测指标

---

## 统计数据

### 配对分析

```
总交易: 637笔
正确配对 (entry_level == exit_level): 320笔 (50.2%)
  - 平均收益: +0.1485%
  - 符合min_return设计 ✓

错误配对 (entry_level ≠ exit_level): 317笔 (49.8%)
  - 平均收益: -0.4678%
  - 主要由FIFO fallback导致

多笔交易同时平仓的timestamp: 259个 (40%!)
```

### Match Failure分析

```
总匹配失败: 280次
失败时有buy positions可用: 280次 (100%)
失败时无buy positions: 0次 (0%)

结论: 失败不是因为没有buy positions，而是target_sell_level不匹配
```

### Level不平衡

```
Level 11: 33 buys, 12 sells → 不平衡 -21
Level 16: 49 buys, 34 sells → 不平衡 -15
Level 10: 24 buys, 17 sells → 不平衡 -7
```

---

## 修复实施

### 已完成的修复 (2025-12-20)

1. **实现方案1** (限制Sell Size) ✅
   - 修改`grid_manager.py` line 785-800附近代码
   - 限制sell size不超过对应buy position size
   - 添加了详细的日志输出

**修复代码**:
```python
# BUG FIX: Limit sell size to corresponding buy position size
target_buy_size = 0.0
for buy_level_idx, positions in self.buy_positions.items():
    for pos in positions:
        if pos.get('target_sell_level') == level_index:
            target_buy_size += pos['size']

# Limit sell size to corresponding buy position size (if found)
if target_buy_size > 0:
    base_size_btc = min(base_size_btc, target_buy_size)
else:
    # Fallback: limit to total holdings
    base_size_btc = min(base_size_btc, max(0.0, float(holdings_btc)))
```

### 待验证

2. **验证效果**
   - 运行回测检查配对正确率是否提升到90%+
   - 检查平均单笔收益是否转正
   - 检查trades.csv中多次平仓的情况是否消失
   - 使用 `run/test_sell_size_limit_fix.py` 进行验证

### 后续优化

3. **平衡风控和配对**
   - 研究如何在保持配对正确的前提下，保留风控multipliers
   - 可能需要设计新的风控机制（例如：提前平仓而不是放大size）

4. **完整回测**
   - 使用更长时间段 (6个月)
   - 测试不同市场环境

---

## 调试工具

### 分析Match Failures

```python
# 在simple_lean_runner.py main()函数中已添加
if hasattr(runner, '_match_failures'):
    # 输出前10个失败案例
    # 按sell level统计失败次数
    # 区分有/无buy positions的失败
```

### 分析多次平仓

```python
import pandas as pd
trades = pd.read_csv('run/results_stage1_extended/trades.csv')
trades['exit_timestamp'] = pd.to_datetime(trades['exit_timestamp'])

# 找出同一时间多笔交易
exit_counts = trades.groupby('exit_timestamp').size()
multiple_exits = exit_counts[exit_counts > 1]

# 查看详情
for timestamp in multiple_exits.index[:10]:
    print(trades[trades['exit_timestamp'] == timestamp])
```

---

## 附录: 其他发现

### Spacing公式改进

在调查过程中，还发现并修复了spacing计算的问题：

**问题**: ATR-based spacing使用加法公式，导致spacing过大

```python
# 旧公式 (additive)
spacing = base_spacing + volatility_k * (atr_pct - 1.0)
# 当atr_pct=9时，spacing可达480%!
```

**修复**: 改为乘法公式

```python
# 新公式 (multiplicative)
spacing = base_spacing * (1 + volatility_k * max(0, atr_pct - 1.0))
# 当atr_pct=9, k=0.2时，spacing=base*2.6 (可控)
```

**文件**: `analytics/indicators/grid_generator.py` line 155-174

---

## 结论

TaoGrid网格策略的配对问题根源在于**风控multipliers过度放大sell size**，导致单个sell需要匹配多个buy positions，后续匹配失败后使用FIFO fallback，产生错误配对和亏损。

**推荐修复**: 实现方案1，限制sell size不超过对应buy position的size，保持网格策略的对称性。

**预期修复后效果**:
- 配对正确率: 50% → 95%+
- 平均单笔收益: -0.16% → +0.12%+
- 总收益: 2.08% → 3-4%+

---

**文档版本**: 1.0
**最后更新**: 2025-12-21
**负责人**: Claude Sonnet 4.5
**Token使用**: 122k/200k

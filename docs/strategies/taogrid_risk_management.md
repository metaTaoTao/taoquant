# TaoGrid 策略风险管理体系

## 概述

TaoGrid 策略采用**多层风险管理体系**，与传统止损机制不同，它通过**动态仓位调整**和**网格关闭机制**来控制风险。这种设计符合网格交易的特点：通过网格配对盈利，而不是依赖止损来限制亏损。

## 核心设计理念

1. **无传统止损**：不在价格或亏损达到阈值时强制平仓
2. **动态风险控制**：通过减少买入、增加卖出和网格关闭来管理风险
3. **分级风险管理**：根据风险程度采用不同的应对策略
4. **自动恢复机制**：风险降低后自动重新启用网格

---

## 一、网格关闭机制（Grid Shutdown）

### 1.1 触发条件

当以下**任一条件**满足时，网格将完全停止交易：

#### 条件1：价格深度风险
```python
# 代码位置: algorithms/taogrid/helpers/grid_manager.py:1013
shutdown_price_threshold = support - (max_risk_atr_mult × ATR)
if current_price < shutdown_price_threshold:
    # 网格关闭
```

**参数**：
- `max_risk_atr_mult = 3.0`：价格深度阈值（支撑 - 3 × ATR）
- **含义**：当价格跌破支撑线超过 3 倍 ATR 时，认为风险过高

#### 条件2：未实现亏损风险
```python
# 代码位置: algorithms/taogrid/helpers/grid_manager.py:1018
adjusted_loss_threshold = max_risk_loss_pct - (profit_buffer / equity)
if unrealized_pnl < -adjusted_loss_threshold * equity:
    # 网格关闭
```

**参数**：
- `max_risk_loss_pct = 0.30`：未实现亏损阈值（30% 权益）
- `enable_profit_buffer = True`：启用利润缓冲
- `profit_buffer_ratio = 0.5`：50% 的已实现利润可用于缓冲风险阈值
- **含义**：未实现亏损超过 30% 权益时关闭网格（可被已实现利润缓冲）

#### 条件3：库存风险
```python
# 代码位置: algorithms/taogrid/helpers/grid_manager.py:1023
inv_risk_pct = inv_notional / max_capacity
if inv_risk_pct > max_risk_inventory_pct:
    # 网格关闭
```

**参数**：
- `max_risk_inventory_pct = 0.8`：库存风险阈值（80% 容量）
- `max_capacity = equity × leverage`：最大容量（权益 × 杠杆）
- **含义**：库存风险超过 80% 容量时关闭网格

### 1.2 自动恢复机制

当风险条件改善后，网格会自动重新启用：

```python
# 代码位置: algorithms/taogrid/helpers/grid_manager.py:1051
if not should_shutdown and not self.grid_enabled:
    # 自动重新启用网格
    self.grid_enabled = True
    self.grid_shutdown_reason = None
```

**逻辑**：
- 网格关闭后，每个 bar 都会检查风险条件
- 如果所有关闭条件都不满足，自动重新启用网格
- 无需手动干预

---

## 二、MM Risk Zone（市场做市商风险区）

### 2.1 分级风险体系

当价格跌破支撑线时，进入分级风险模式，根据风险程度采用不同的仓位调整策略：

#### Level 1：轻度风险
**触发条件**：`price < support + (cushion_multiplier × ATR)`

**仓位调整**：
- 买入：减少到 **20%** 正常大小
- 卖出：增加到 **300%** 正常大小
- 额外惩罚：如果库存比例 > 50%，买入再减少 50%

```python
# 代码位置: algorithms/taogrid/helpers/grid_manager.py:600-606
mm_buy_mult = 0.2  # BUY 20% of normal size
mm_sell_mult = 3.0  # SELL 300% of normal size
if inv_ratio > 0.5:
    mm_buy_mult = mm_buy_mult * 0.5  # Further reduce by 50%
```

#### Level 2：中度风险
**触发条件**：价格在风险区停留较长时间（当前未实现时间阈值）

**仓位调整**：
- 买入：减少到 **10%** 正常大小
- 卖出：增加到 **400%** 正常大小

```python
# 代码位置: algorithms/taogrid/config.py:136-137
mm_risk_level2_buy_mult = 0.1   # BUY 10% of normal size
mm_risk_level2_sell_mult = 4.0  # SELL 400% of normal size
```

#### Level 3：严重风险
**触发条件**：`price < support - (2.0 × ATR)`

**仓位调整**：
- 买入：减少到 **5%** 正常大小
- 卖出：增加到 **500%** 正常大小

```python
# 代码位置: algorithms/taogrid/config.py:140-142
mm_risk_level3_atr_mult = 2.0   # Trigger at support - 2 × ATR
mm_risk_level3_buy_mult = 0.05  # BUY 5% of normal size
mm_risk_level3_sell_mult = 5.0  # SELL 500% of normal size
```

### 2.2 设计理念

MM Risk Zone 模仿市场做市商的行为：
- **扩大价差**：减少买入，增加卖出
- **降低库存风险**：通过卖出减少持仓
- **渐进式应对**：根据风险程度逐步加强控制

---

## 三、库存限制（Inventory Limit）

### 3.1 库存容量限制

通过 `inventory_capacity_threshold_pct` 限制最大持仓：

```python
# 代码位置: algorithms/taogrid/helpers/grid_manager.py:992-997
inv_notional = abs(net_exposure) * current_price
max_capacity = equity * leverage
inv_risk_pct = inv_notional / max_capacity

if inv_risk_pct > inventory_capacity_threshold_pct:
    # 阻止新订单
```

**参数**：
- `inventory_capacity_threshold_pct = 1.0`：库存容量阈值（100%）
- `leverage = 50.0`：杠杆倍数
- **含义**：当库存名义价值超过 `equity × leverage` 时，阻止新订单

### 3.2 库存感知仓位调整

通过 `inventory_skew_k` 根据库存偏斜调整仓位：

```python
# 代码位置: risk_management/grid_risk_manager.py:126-161
def check_inventory_limit(long_exposure, short_exposure):
    long_pct = long_exposure / max_long_units
    short_pct = short_exposure / max_short_units
    return long_pct >= inventory_threshold or short_pct >= inventory_threshold
```

**参数**：
- `inventory_skew_k = 0.5`：库存感知强度（0 = 关闭）
- `inventory_threshold = 0.9`：库存阈值（90%）
- **含义**：当库存超过 90% 容量时，阻止新订单

---

## 四、因子过滤（Factor Filtering）

### 4.1 Breakout Risk Factor（突破风险因子）

**目的**：在接近区间边界时降低风险

**逻辑**：
- 当 `breakout_risk_down >= breakout_block_threshold` 时，**完全阻止买入**
- 否则，根据风险程度减少买入大小

```python
# 代码位置: algorithms/taogrid/helpers/grid_manager.py:658-669
if br_down >= breakout_block_threshold:
    return 0.0, ThrottleStatus(
        size_multiplier=0.0,
        reason="Breakout risk-off (downside)",
    )
risk_mult = max(
    breakout_buy_floor,
    1.0 - breakout_buy_k * br_down,
)
base_size_btc = base_size_btc * risk_mult
```

**参数**：
- `breakout_block_threshold = 0.9`：阻止阈值（90%）
- `breakout_buy_k = 2.0`：买入减少强度
- `breakout_buy_floor = 0.5`：买入最小倍数（50%）

### 4.2 MR + Trend Factor（均值回归 + 趋势因子）

**目的**：在强下跌趋势中阻止新买入

**逻辑**：
- 当 `trend_score <= -trend_block_threshold` 时，**完全阻止买入**
- 否则，根据趋势和均值回归强度调整买入大小

```python
# 代码位置: algorithms/taogrid/helpers/grid_manager.py:622-647
if ts <= -trend_block_threshold:
    return 0.0, ThrottleStatus(
        size_multiplier=0.0,
        reason="Factor block (strong downtrend)",
    )
trend_mult = max(
    trend_buy_floor,
    1.0 - trend_buy_k * neg_ts,
)
mr_mult = max(mr_min_mult, mr_strength)
factor_mult = trend_mult * mr_mult
```

**参数**：
- `trend_block_threshold = 0.80`：阻止阈值（-80%）
- `trend_buy_k = 0.40`：买入减少强度
- `trend_buy_floor = 0.50`：买入最小倍数（50%）

### 4.3 Funding Factor（资金费率因子）

**目的**：在资金费率为正时减少买入（做多需要支付资金费率）

**逻辑**：
- 当 `funding_rate >= funding_block_threshold` 时，**完全阻止买入**
- 否则，根据资金费率减少买入大小
- 仅在资金结算窗口附近应用（避免过度减少交易频率）

```python
# 代码位置: algorithms/taogrid/helpers/grid_manager.py:682-692
if fr >= funding_block_threshold:
    return 0.0, ThrottleStatus(
        size_multiplier=0.0,
        reason="Funding risk-off (block BUY)",
    )
buy_mult = max(
    funding_buy_floor,
    1.0 - funding_buy_k * x,
)
```

**参数**：
- `funding_block_threshold = 0.0005`：阻止阈值（0.05%）
- `funding_buy_k = 1.0`：买入减少强度
- `funding_buy_floor = 0.4`：买入最小倍数（40%）
- `funding_gate_minutes = 60`：仅在结算窗口 ±60 分钟内应用

### 4.4 Range Position Asymmetry v2（区间位置不对称）

**目的**：在接近区间顶部时减少买入、增加卖出

**逻辑**：
- 仅在 `range_pos >= range_top_band_start` 时应用
- 根据位置在顶部区间的比例调整仓位

```python
# 代码位置: algorithms/taogrid/helpers/grid_manager.py:695-702
if rp >= range_top_band_start:
    x = (rp - start) / (1.0 - start)  # 0..1 within band
    buy_mult = max(range_buy_floor, 1.0 - range_buy_k * x)
    base_size_btc = base_size_btc * buy_mult
```

**参数**：
- `range_top_band_start = 0.45`：顶部区间起始位置（45%）
- `range_buy_k = 0.2`：买入减少强度
- `range_buy_floor = 0.2`：买入最小倍数（20%）
- `range_sell_k = 1.5`：卖出增加强度
- `range_sell_cap = 1.5`：卖出最大倍数（150%）

### 4.5 Volatility Regime Factor（波动率区间因子）

**目的**：在极端高波动时优先通过卖出降低风险

**逻辑**：
- 仅在 `vol_score >= vol_trigger_score` 时应用（极端高波动）
- 默认只应用于卖出（避免减少交易频率）

```python
# 代码位置: algorithms/taogrid/helpers/grid_manager.py:745-749
if vs >= vol_trigger_score and vol_apply_to_sell:
    base_size_btc = base_size_btc * vol_sell_mult_high
```

**参数**：
- `vol_trigger_score = 0.98`：触发阈值（98% 分位数）
- `vol_apply_to_buy = False`：默认不应用于买入
- `vol_apply_to_sell = True`：默认应用于卖出
- `vol_sell_mult_high = 1.15`：卖出增加倍数（115%）

---

## 五、利润缓冲（Profit Buffer）

### 5.1 机制说明

已实现利润可用于缓冲风险阈值，允许更大的未实现亏损：

```python
# 代码位置: algorithms/taogrid/helpers/grid_manager.py:999-1006
profit_buffer = realized_pnl * profit_buffer_ratio
adjusted_loss_threshold = max_risk_loss_pct - (profit_buffer / equity)
```

**参数**：
- `enable_profit_buffer = True`：启用利润缓冲
- `profit_buffer_ratio = 0.5`：50% 的已实现利润可用于缓冲
- **含义**：如果已实现利润为 $10,000，则未实现亏损阈值从 -30% 调整为 -30% + (5,000 / equity)

### 5.2 设计理念

- **保护已实现利润**：已实现的利润不应该因为未实现亏损而全部损失
- **动态调整**：根据已实现利润动态调整风险阈值
- **渐进式保护**：利润越多，可承受的未实现亏损越大

---

## 六、其他风险控制机制

### 6.1 每日亏损限制

```python
# 代码位置: algorithms/taogrid/config.py:45
daily_loss_limit: float = 2000.0
```

**含义**：当日亏损超过 $2,000 时，停止当日交易

### 6.2 波动率峰值节流

```python
# 代码位置: risk_management/grid_risk_manager.py:200-240
def check_volatility_spike(current_atr, avg_atr):
    if current_atr / avg_atr >= volatility_threshold:
        return True  # 触发节流
```

**参数**：
- `volatility_threshold = 2.0`：波动率阈值（2 倍平均 ATR）
- `volatility_reduction = 0.5`：仓位减少到 50%

**含义**：当 ATR 超过平均 ATR 的 2 倍时，减少仓位大小

### 6.3 利润目标锁定

```python
# 代码位置: risk_management/grid_risk_manager.py:163-198
def check_profit_target(daily_pnl, risk_budget):
    profit_target = risk_budget * profit_target_pct
    return daily_pnl >= profit_target
```

**参数**：
- `profit_target_pct = 0.5`：利润目标（50% 风险预算）
- `profit_reduction = 0.5`：达到目标后仓位减少到 50%

**含义**：当日利润达到风险预算的 50% 时，减少仓位大小以锁定利润

---

## 七、风险管理流程图

```
价格下跌
    ↓
是否跌破支撑 + cushion？
    ├─ 是 → 进入 MM Risk Zone Level 1
    │         ├─ 买入减少到 20%
    │         └─ 卖出增加到 300%
    │
    └─ 否 → 继续正常交易
            ↓
是否跌破支撑 - 2 × ATR？
    ├─ 是 → 进入 MM Risk Zone Level 3
    │         ├─ 买入减少到 5%
    │         └─ 卖出增加到 500%
    │
    └─ 否 → 继续 Level 1
            ↓
是否满足关闭条件？
    ├─ 价格 < 支撑 - 3 × ATR → 关闭网格
    ├─ 未实现亏损 > 30% 权益 → 关闭网格
    └─ 库存风险 > 80% 容量 → 关闭网格
            ↓
风险条件改善？
    └─ 是 → 自动重新启用网格
```

---

## 八、关键参数总结

### 8.1 网格关闭参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_risk_atr_mult` | 3.0 | 价格深度阈值（支撑 - 3 × ATR） |
| `max_risk_loss_pct` | 0.30 | 未实现亏损阈值（30% 权益） |
| `max_risk_inventory_pct` | 0.8 | 库存风险阈值（80% 容量） |
| `enable_profit_buffer` | True | 启用利润缓冲 |
| `profit_buffer_ratio` | 0.5 | 利润缓冲比例（50%） |

### 8.2 MM Risk Zone 参数

| 参数 | Level 1 | Level 2 | Level 3 |
|------|---------|---------|---------|
| 买入倍数 | 0.2 (20%) | 0.1 (10%) | 0.05 (5%) |
| 卖出倍数 | 3.0 (300%) | 4.0 (400%) | 5.0 (500%) |
| 触发条件 | `price < support + cushion` | 时间阈值 | `price < support - 2 × ATR` |

### 8.3 因子过滤参数

| 因子 | 阻止阈值 | 减少强度 | 最小倍数 |
|------|---------|---------|---------|
| Breakout Risk | 0.9 | 2.0 | 0.5 |
| Trend | -0.80 | 0.40 | 0.50 |
| Funding | 0.0005 | 1.0 | 0.4 |
| Range Position | - | 0.2 | 0.2 |

### 8.4 库存限制参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `inventory_capacity_threshold_pct` | 1.0 | 库存容量阈值（100%） |
| `inventory_skew_k` | 0.5 | 库存感知强度 |
| `inventory_threshold` | 0.9 | 库存节流阈值（90%） |

---

## 九、风险管理优势

1. **渐进式应对**：根据风险程度逐步加强控制，避免过度反应
2. **自动恢复**：风险降低后自动重新启用网格，无需手动干预
3. **利润保护**：通过利润缓冲保护已实现利润
4. **多维度控制**：价格、亏损、库存、波动率等多维度风险管理
5. **因子协同**：多个因子协同工作，形成完整的风险控制体系

---

## 十、与传统止损的对比

| 特性 | 传统止损 | TaoGrid 风险管理 |
|------|---------|------------------|
| 触发方式 | 价格或亏损达到阈值 | 多维度风险条件 |
| 应对方式 | 强制平仓 | 动态仓位调整 + 网格关闭 |
| 恢复机制 | 需要手动重新开仓 | 自动恢复 |
| 利润保护 | 无 | 利润缓冲机制 |
| 适用场景 | 趋势交易 | 网格交易 |

---

## 十一、代码位置索引

- **网格关闭逻辑**：`algorithms/taogrid/helpers/grid_manager.py:966-1057`
- **MM Risk Zone**：`algorithms/taogrid/helpers/grid_manager.py:600-606, 752-763`
- **因子过滤**：`algorithms/taogrid/helpers/grid_manager.py:608-749`
- **库存限制**：`risk_management/grid_risk_manager.py:126-161`
- **配置参数**：`algorithms/taogrid/config.py:122-153`

---

**最后更新**：2025-01-XX  
**版本**：v1.0

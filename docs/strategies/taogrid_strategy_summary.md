# TaoGrid 策略完整技术文档

本文档详细总结了 TaoGrid 网格交易策略的所有技术细节，包括因子设计、风险管理、参数设置和优化方法。

**最后更新时间**: 2025-12-XX  
**策略版本**: Lean 实现 (Sprint 2+)

---

## 目录

1. [策略概述](#策略概述)
2. [核心因子体系](#核心因子体系)
3. [网格生成逻辑](#网格生成逻辑)
4. [风险管理体系](#风险管理体系)
5. [参数配置](#参数配置)
6. [优化方法](#优化方法)
7. [实现架构](#实现架构)

---

## 策略概述

### 策略理念

TaoGrid 是一个**主动网格交易策略**，核心哲学是：
- **交易者判断 + 算法执行**：人工指定支撑/阻力区间和市场状态，算法负责执行
- **并非黑盒自动化系统**：保持交易者的决策权，算法作为执行工具

### 核心特征

1. **手动输入模式**
   - 交易者手动指定支撑/阻力水平
   - 交易者手动指定市场状态（BULLISH_RANGE / NEUTRAL_RANGE / BEARISH_RANGE）
   - 算法处理执行细节

2. **ATR 动态网格间距**
   - 基于 ATR 的动态网格间距计算
   - 确保网格间距覆盖交易成本并满足最低收益要求

3. **层级权重分配**
   - 边缘层级（接近 S/R）权重更大
   - 中间层级权重较小
   - 公式：`raw_w(i) = 1 + k × (i - 1)`

4. **状态驱动的多空分配**
   - UP_RANGE: 70% 买入，30% 卖出（偏向做多）
   - NEUTRAL_RANGE: 50% 买入，50% 卖出（中性）
   - DOWN_RANGE: 30% 买入，70% 卖出（偏向做空）

5. **多层次风险管理**
   - 库存管理（Inventory Management）
   - 利润锁定（Profit Lock）
   - 波动率调整（Volatility Adjustment）
   - 做市商风险区域（MM Risk Zone）

---

## 核心因子体系

TaoGrid 策略采用多因子体系来动态调整订单规模和风险管理。

### 1. MR (Mean Reversion) + Trend 因子

**目的**: 在强下跌趋势中阻止新的买入，避免库存积累和左尾风险

**实现**:
- **MR 强度**: 基于价格的滚动 Z-score
  - `mr_z = rolling_zscore(close, window=240)`
  - 负值越大表示超卖越严重
  - MR 乘数：`mr_mult = max(mr_min_mult, strength)`，其中 `strength = min(1.0, (-z) / mr_z_ref)`
  
- **趋势得分**: 基于 EMA 斜率的趋势强度
  - `ema = EMA(close, period=120)`
  - `slope = ema.pct_change(periods=60)`
  - `trend_score = tanh(slope / slope_ref)`，范围 [-1, 1]
  - 负值表示下跌趋势

**买入调整逻辑**:
- **硬性阻止**: 如果 `trend_score <= -trend_block_threshold` (默认 -0.80)，完全阻止买入
- **趋势乘数**: `trend_mult = max(trend_buy_floor, 1.0 - trend_buy_k × max(0, -trend_score))`
- **最终乘数**: `factor_mult = trend_mult × mr_mult`

**参数**:
- `enable_mr_trend_factor`: 是否启用 (默认 True)
- `mr_z_lookback`: Z-score 回溯窗口 (默认 240 根 K 线)
- `mr_z_ref`: Z-score 参考值，在此值处 MR 乘数达到 1.0 (默认 2.0)
- `mr_min_mult`: MR 最小乘数 (默认 1.00，即仅用于诊断，不实际下调)
- `trend_ema_period`: EMA 周期 (默认 120)
- `trend_slope_lookback`: 斜率回溯窗口 (默认 60)
- `trend_slope_ref`: 斜率参考值 (默认 0.001 = 0.1%)
- `trend_block_threshold`: 阻止阈值 (默认 0.80)
- `trend_buy_k`: 买入下调强度 (默认 0.40)
- `trend_buy_floor`: 趋势乘数下限 (默认 0.50)

---

### 2. Breakout Risk (突破风险) 因子

**目的**: 在接近区间边界且存在方向性压力时降低风险

**实现**:
- **危险区域宽度**: `band_usd = max(ATR × band_atr_mult, close × band_pct)`
- **距离边界距离**: 
  - `dist_to_support = close - support`
  - `dist_to_resistance = resistance - close`
- **接近度得分**: `prox = max(0, 1 - dist / band_width)`
- **方向性压力**: 
  - 下跌趋势在接近支撑时增加下行风险
  - 上涨趋势在接近阻力时增加上行风险
- **风险得分**: `breakout_risk = prox × (1 - trend_weight) + prox × trend_pressure × trend_weight`

**买入调整逻辑**:
- **硬性阻止**: 如果 `breakout_risk_down >= breakout_block_threshold` (默认 0.95)，完全阻止买入
- **风险乘数**: `risk_mult = max(breakout_buy_floor, 1.0 - breakout_buy_k × breakout_risk_down)`

**参数**:
- `enable_breakout_risk_factor`: 是否启用 (默认 True)
- `breakout_band_atr_mult`: 危险区域 ATR 倍数 (默认 1.5)
- `breakout_band_pct`: 危险区域最小百分比 (默认 0.003 = 0.3%)
- `breakout_trend_weight`: 趋势权重 (默认 0.7)
- `breakout_buy_k`: 买入下调强度 (默认 0.6)
- `breakout_buy_floor`: 风险乘数下限 (默认 0.4)
- `breakout_block_threshold`: 阻止阈值 (默认 0.95)

---

### 3. Funding Rate (资金费率) 因子

**目的**: 控制永续合约的资金费率成本

**实现**:
- 对于**多头持仓网格**：正资金费率意味着多头支付费用
- **时间门控**: 仅在资金费率结算窗口附近应用（避免降低换手率）
- **买入侧**: 通常禁用（`funding_apply_to_buy=False`），避免抑制换手
- **卖出侧**: 启用（`funding_apply_to_sell=True`），在正资金费率时增加卖出积极性

**买入调整逻辑**:
- 如果启用 `funding_apply_to_buy`:
  - **硬性阻止**: 如果 `funding_rate >= funding_block_threshold` (默认 0.05% = 0.0005)，完全阻止买入
  - **费率乘数**: `x = min(1.0, funding_rate / funding_ref)`，`buy_mult = max(funding_buy_floor, 1.0 - funding_buy_k × x)`

**卖出调整逻辑**:
- 如果启用 `funding_apply_to_sell`:
  - **费率乘数**: `x = min(1.0, funding_rate / funding_ref)`，`sell_mult = min(funding_sell_cap, 1.0 + funding_sell_k × x)`

**参数**:
- `enable_funding_factor`: 是否启用 (默认 True)
- `funding_apply_to_buy`: 是否应用于买入 (默认 False)
- `funding_apply_to_sell`: 是否应用于卖出 (默认 True)
- `enable_funding_time_gate`: 是否启用时间门控 (默认 True)
- `funding_gate_minutes`: 时间门控窗口（分钟）(默认 60)
- `funding_ref`: 归一化参考值 (默认 0.0001 = 0.01%)
- `funding_block_threshold`: 阻止阈值 (默认 0.0005 = 0.05%)
- `funding_buy_k`: 买入下调强度 (默认 1.0)
- `funding_buy_floor`: 买入乘数下限 (默认 0.4)
- `funding_sell_k`: 卖出增强强度 (默认 1.0)
- `funding_sell_cap`: 卖出乘数上限 (默认 2.0)

---

### 4. Range Position Asymmetry (区间位置不对称) 因子 v2

**目的**: 仅在接近区间顶部时应用，减少新买入并增加卖出积极性（去库存）

**实现**:
- **区间位置**: `range_pos = (close - support) / (resistance - support)`，范围 [0, 1]
- **顶部区域**: 仅在 `range_pos >= range_top_band_start` (默认 0.85) 时应用
- **归一化**: `x = (range_pos - start) / (1.0 - start)`，范围 [0, 1]

**买入调整逻辑**:
- 仅在顶部区域: `buy_mult = max(range_buy_floor, 1.0 - range_buy_k × x)`

**卖出调整逻辑**:
- 仅在顶部区域: `sell_mult = min(range_sell_cap, 1.0 + range_sell_k × x)`

**参数**:
- `enable_range_pos_asymmetry_v2`: 是否启用 (默认 False)
- `range_top_band_start`: 顶部区域起始位置 (默认 0.85)
- `range_buy_k`: 买入下调强度 (默认 0.8)
- `range_buy_floor`: 买入乘数下限 (默认 0.4)
- `range_sell_k`: 卖出增强强度 (默认 1.0)
- `range_sell_cap`: 卖出乘数上限 (默认 2.5)

**注意**: v1 版本在全部区间范围应用，发现会显著降低换手率和夏普比率。v2 仅在顶部区域应用，避免抑制中段交易。

---

### 5. Volatility Regime (波动率状态) 因子

**目的**: 在极端高波动率环境中优先通过卖出进行去风险

**实现**:
- **ATR 百分比**: `atr_pct = ATR / close`
- **波动率得分**: `vol_score = rolling_quantile_score(atr_pct, lookback=1440, low_q=0.20, high_q=0.80)`
- **触发条件**: 仅在 `vol_score >= vol_trigger_score` (默认 0.98，极端高波动) 时应用

**买入调整逻辑**:
- 默认不应用 (`vol_apply_to_buy=False`)，避免降低换手

**卖出调整逻辑**:
- 如果启用 `vol_apply_to_sell`:
  - `sell_mult = vol_sell_mult_high` (默认 1.15)

**参数**:
- `enable_vol_regime_factor`: 是否启用 (默认 True)
- `vol_lookback`: 回溯窗口 (默认 1440 = 1 天的 1 分钟 K 线)
- `vol_low_q`: 低分位数 (默认 0.20)
- `vol_high_q`: 高分位数 (默认 0.80)
- `vol_trigger_score`: 触发阈值 (默认 0.98，仅极端情况)
- `vol_apply_to_buy`: 是否应用于买入 (默认 False)
- `vol_apply_to_sell`: 是否应用于卖出 (默认 True)
- `vol_sell_mult_high`: 高波动时卖出乘数 (默认 1.15)

---

### 6. Inventory Skew (库存偏斜) 因子

**目的**: 基于当前库存水平动态调整买入规模（机构级库存控制）

**实现**:
- **名义库存比率**: `inv_ratio = |holdings| × price / (equity × leverage)`
- **容量阈值**: `inv_ratio_threshold = inventory_capacity_threshold_pct × leverage`
- **买入调整**: 如果 `inv_ratio >= threshold`，完全阻止买入
- **偏斜乘数**: `skew_mult = max(0.0, 1.0 - inventory_skew_k × (inv_ratio / threshold))`

**参数**:
- `inventory_capacity_threshold_pct`: 容量阈值百分比 (默认 0.9 = 90%)
- `inventory_skew_k`: 偏斜强度 (默认 1.0，0 = 关闭)

---

### 7. Market Maker Risk Zone (做市商风险区域) - 分级风险管理

**目的**: 当价格跌破支撑 + 波动率缓冲时，进入分级风险模式，模拟做市商行为（扩大价差，减少库存风险）

**风险级别**:

- **Level 1 (轻度风险)**: 价格 < 支撑 + 波动率缓冲 (cushion)
  - 买入乘数: `mm_risk_level1_buy_mult` (默认 0.2 = 20%)
  - 卖出乘数: `mm_risk_level1_sell_mult` (默认 3.0 = 300%)
  - 如果库存比率 > `mm_risk_inventory_penalty` (默认 0.5)，额外减少 50%

- **Level 2 (中度风险)**: 价格在风险区域停留较长时间
  - 买入乘数: `mm_risk_level2_buy_mult` (默认 0.1 = 10%)
  - 卖出乘数: `mm_risk_level2_sell_mult` (默认 4.0 = 400%)

- **Level 3 (严重风险)**: 价格 < 支撑 - 2 × ATR
  - 买入乘数: `mm_risk_level3_buy_mult` (默认 0.05 = 5%)
  - 卖出乘数: `mm_risk_level3_sell_mult` (默认 5.0 = 500%)

- **Level 4 (极端风险 - 网格关闭)**:
  - 价格 < 支撑 - 3 × ATR，或
  - 未实现亏损 > `max_risk_loss_pct` × 权益 (默认 30%)，或
  - 库存风险 > `max_risk_inventory_pct` × 容量 (默认 80%)
  - **网格完全关闭**，直到手动重新启用

**利润缓冲**:
- 如果启用 `enable_profit_buffer` (默认 True):
  - `profit_buffer = realized_pnl × profit_buffer_ratio` (默认 50%)
  - 调整后的亏损阈值: `adjusted_loss_threshold = max_risk_loss_pct - (profit_buffer / equity)`
  - 允许已实现利润缓冲未实现亏损

**参数**:
- `enable_mm_risk_zone`: 是否启用 (默认 True)
- `mm_risk_level1_buy_mult`: Level 1 买入乘数 (默认 0.2)
- `mm_risk_level1_sell_mult`: Level 1 卖出乘数 (默认 3.0)
- `mm_risk_inventory_penalty`: 库存惩罚阈值 (默认 0.5)
- `mm_risk_level2_buy_mult`: Level 2 买入乘数 (默认 0.1)
- `mm_risk_level2_sell_mult`: Level 2 卖出乘数 (默认 4.0)
- `mm_risk_level3_atr_mult`: Level 3 ATR 倍数 (默认 2.0)
- `mm_risk_level3_buy_mult`: Level 3 买入乘数 (默认 0.05)
- `mm_risk_level3_sell_mult`: Level 3 卖出乘数 (默认 5.0)
- `max_risk_atr_mult`: 关闭阈值 ATR 倍数 (默认 3.0)
- `max_risk_loss_pct`: 最大亏损百分比 (默认 0.30 = 30%)
- `max_risk_inventory_pct`: 最大库存风险百分比 (默认 0.80 = 80%)
- `enable_profit_buffer`: 是否启用利润缓冲 (默认 True)
- `profit_buffer_ratio`: 利润缓冲比例 (默认 0.5 = 50%)

---

## 网格生成逻辑

### 1. 网格间距计算

**公式**:
```
spacing_pct = base_spacing + volatility_adjustment
base_spacing = min_return + trading_costs
trading_costs = 2 × maker_fee + 2 × slippage  # 双向成本
volatility_adjustment = k × (atr_pct - 1.0)
atr_pct = ATR / rolling_mean(ATR, 20)
```

**关键点**:
- `min_return` 是**净收益目标**（扣除所有成本后）
- 网格间距确保：`spacing - costs >= min_return`
- 对于限价单，`slippage = 0`（限价单按指定价格成交）
- `volatility_k` 控制波动率调整强度 (默认 0.6)
- 间距有上界保护：最大 5%，避免过度降低换手率

**参数**:
- `min_return`: 最低净收益 (默认 0.005 = 0.5%)
- `maker_fee`: 做市商费率 (每边) (默认 0.0002 = 0.02%)
- `slippage`: 滑点 (每边) (默认 0.0，限价单)
- `volatility_k`: 波动率调整系数 (默认 0.6)
- `atr_period`: ATR 周期 (默认 14)

---

### 2. 波动率缓冲 (Volatility Cushion)

**目的**: 防止虚假突破导致过早止损

**实现**:
```
eff_support = support - cushion
eff_resistance = resistance + cushion
cushion = ATR × cushion_multiplier
```

**参数**:
- `cushion_multiplier`: 缓冲乘数 (默认 0.8)

---

### 3. 网格层级生成

**买入层级**:
- 从中间价向下生成，使用几何间距
- `buy_price[i] = mid / (1 + spacing_pct)^i`
- 直到达到 `eff_support`

**卖出层级**:
- 从买入层级配对生成，使用 1× 间距配对
- `sell_price[i] = buy_price[i] × (1 + spacing_pct)`
- 直到达到 `eff_resistance`

**配对规则**:
- `buy[i] -> sell[i]` 形成 1× 间距配对（一个网格周期）
- 这种配对方式最大化换手率

**参数**:
- `grid_layers_buy`: 买入层级数 (默认 5，可扩展到 100+)
- `grid_layers_sell`: 卖出层级数 (通常等于买入层级数)
- `spacing_multiplier`: 间距乘数 (默认 1.0，必须 >= 1.0)

---

### 4. 层级权重分配

**公式**:
```
raw_w(i) = 1 + k × (i - 1)  # i=1 最接近中间，i=N 最接近边缘
w(i) = raw_w(i) / Σ raw_w  # 归一化
```

**逻辑**:
- 边缘层级（接近 S/R）权重更大
- 中间层级权重较小
- 反映风险/收益比：边缘有更好的风险/收益

**示例** (4 层，k=0.5):
- i=1: raw=1.0 → w ≈ 14%
- i=2: raw=1.5 → w ≈ 21%
- i=3: raw=2.0 → w ≈ 29%
- i=4: raw=2.5 → w ≈ 36%

**参数**:
- `weight_k`: 权重系数 (默认 0.5)

---

### 5. 多空预算分配

**基于市场状态**:
- `UP_RANGE`: 买入 70%，卖出 30%
- `NEUTRAL_RANGE`: 买入 50%，卖出 50%
- `DOWN_RANGE`: 买入 30%，卖出 70%

**总预算**:
```
total_budget = equity × risk_budget_pct
buy_budget = total_budget × buy_pct
sell_budget = total_budget × sell_pct
```

**参数**:
- `risk_budget_pct`: 风险预算百分比 (默认 0.3 = 30%)
- `regime`: 市场状态 ("BULLISH_RANGE" / "NEUTRAL_RANGE" / "BEARISH_RANGE")

---

## 风险管理体系

### 1. 库存管理 (Inventory Management)

**目的**: 防止库存过度积累

**实现**:
- 跟踪多头和空头敞口
- 检查库存是否超过阈值

**限制规则**:
- `inventory_threshold`: 库存阈值 (默认 0.9 = 90%)
- 如果 `exposure / max_units >= threshold`，完全阻止新订单

**参数**:
- `max_long_units`: 最大多头单位 (默认 10.0)
- `max_short_units`: 最大空头单位 (默认 10.0)
- `inventory_threshold`: 库存阈值 (默认 0.9)
- `inventory_capacity_threshold_pct`: 容量阈值百分比 (默认 0.9)
- `inventory_skew_k`: 库存偏斜强度 (默认 1.0)

---

### 2. 利润锁定 (Profit Lock)

**目的**: 达到每日利润目标后减少交易规模，锁定利润

**实现**:
- 跟踪每日 PnL
- 如果 `daily_pnl >= risk_budget × profit_target_pct`，减少订单规模

**调整逻辑**:
- `size_multiplier = profit_reduction` (默认 0.5 = 50%)

**参数**:
- `profit_target_pct`: 利润目标百分比 (默认 0.5 = 50% 的风险预算)
- `profit_reduction`: 利润锁定时的规模减少 (默认 0.5 = 50%)

---

### 3. 波动率调整 (Volatility Adjustment)

**目的**: 在波动率激增时减少交易规模

**实现**:
- 比较当前 ATR 与平均 ATR
- 如果 `current_atr / avg_atr >= volatility_threshold`，减少订单规模

**调整逻辑**:
- `size_multiplier = volatility_reduction` (默认 0.5 = 50%)

**参数**:
- `volatility_threshold`: 波动率阈值 (默认 2.0 = 2× 平均 ATR)
- `volatility_reduction`: 波动率调整时的规模减少 (默认 0.5 = 50%)

---

### 4. 每日亏损限制

**目的**: 防止单日过度亏损

**实现**:
- 跟踪每日 PnL
- 如果 `daily_pnl <= -daily_loss_limit`，触发保护机制

**参数**:
- `daily_loss_limit`: 每日亏损限制 (默认 2000.0 USD)

---

### 5. 风险级别优先级

风险管理的优先级（从高到低）:
1. **库存限制** (`size_multiplier = 0.0`，完全停止)
2. **利润锁定** (`size_multiplier = profit_reduction`)
3. **波动率调整** (`size_multiplier = volatility_reduction`)
4. **无限制** (`size_multiplier = 1.0`)

---

## 参数配置

### 核心参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `support` | 104000.0 | 支撑水平（手动输入） |
| `resistance` | 126000.0 | 阻力水平（手动输入） |
| `regime` | "NEUTRAL_RANGE" | 市场状态（手动输入） |

### 网格参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `grid_layers_buy` | 5 | 买入层级数（可扩展到 100+） |
| `grid_layers_sell` | 5 | 卖出层级数 |
| `weight_k` | 0.5 | 层级权重系数 |
| `spacing_multiplier` | 1.0 | 间距乘数（必须 >= 1.0） |
| `cushion_multiplier` | 0.8 | 波动率缓冲乘数 |
| `min_return` | 0.005 | 最低净收益 (0.5%) |
| `maker_fee` | 0.0002 | 做市商费率 (0.02%) |
| `volatility_k` | 0.6 | 波动率调整系数 |
| `atr_period` | 14 | ATR 周期 |

### 风险管理参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `risk_budget_pct` | 0.3 | 风险预算百分比 (30%) |
| `max_long_units` | 10.0 | 最大多头单位 |
| `max_short_units` | 10.0 | 最大空头单位 |
| `daily_loss_limit` | 2000.0 | 每日亏损限制 (USD) |
| `enable_throttling` | True | 是否启用节流 |
| `inventory_threshold` | 0.9 | 库存阈值 (90%) |
| `inventory_capacity_threshold_pct` | 0.9 | 容量阈值百分比 (90%) |
| `inventory_skew_k` | 1.0 | 库存偏斜强度 |

### 因子参数

#### MR + Trend 因子
- `enable_mr_trend_factor`: True
- `mr_z_lookback`: 240
- `mr_z_ref`: 2.0
- `mr_min_mult`: 1.00
- `trend_ema_period`: 120
- `trend_slope_lookback`: 60
- `trend_slope_ref`: 0.001
- `trend_block_threshold`: 0.80
- `trend_buy_k`: 0.40
- `trend_buy_floor`: 0.50

#### Breakout Risk 因子
- `enable_breakout_risk_factor`: True
- `breakout_band_atr_mult`: 1.5
- `breakout_band_pct`: 0.003
- `breakout_trend_weight`: 0.7
- `breakout_buy_k`: 0.6
- `breakout_buy_floor`: 0.4
- `breakout_block_threshold`: 0.95

#### Funding Rate 因子
- `enable_funding_factor`: True
- `funding_apply_to_buy`: False
- `funding_apply_to_sell`: True
- `enable_funding_time_gate`: True
- `funding_gate_minutes`: 60
- `funding_ref`: 0.0001
- `funding_block_threshold`: 0.0005
- `funding_buy_k`: 1.0
- `funding_buy_floor`: 0.4
- `funding_sell_k`: 1.0
- `funding_sell_cap`: 2.0

#### Range Position 因子 v2
- `enable_range_pos_asymmetry_v2`: False
- `range_top_band_start`: 0.85
- `range_buy_k`: 0.8
- `range_buy_floor`: 0.4
- `range_sell_k`: 1.0
- `range_sell_cap`: 2.5

#### Volatility Regime 因子
- `enable_vol_regime_factor`: True
- `vol_lookback`: 1440
- `vol_low_q`: 0.20
- `vol_high_q`: 0.80
- `vol_trigger_score`: 0.98
- `vol_apply_to_buy`: False
- `vol_apply_to_sell`: True
- `vol_sell_mult_high`: 1.15

#### MM Risk Zone 参数
- `enable_mm_risk_zone`: True
- `mm_risk_level1_buy_mult`: 0.2
- `mm_risk_level1_sell_mult`: 3.0
- `mm_risk_inventory_penalty`: 0.5
- `mm_risk_level2_buy_mult`: 0.1
- `mm_risk_level2_sell_mult`: 4.0
- `mm_risk_level3_atr_mult`: 2.0
- `mm_risk_level3_buy_mult`: 0.05
- `mm_risk_level3_sell_mult`: 5.0
- `max_risk_atr_mult`: 3.0
- `max_risk_loss_pct`: 0.30
- `max_risk_inventory_pct`: 0.80
- `enable_profit_buffer`: True
- `profit_buffer_ratio`: 0.5

### 回测参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `initial_cash` | 100000.0 | 初始资金 (USD) |
| `leverage` | 1.0 | 杠杆倍数（可扩展到 50+） |
| `sharpe_annualization_days` | 365 | 夏普比率年化天数（加密市场 24/7） |

---

## 优化方法

### 1. 参数扫描 (Parameter Sweep)

**方法**: 网格搜索多个参数组合，寻找最优的 ROE/Turnover 折中

**扫描脚本**: `run/taogrid_sweep.py`

**扫描维度**:
- `min_return`: [0.0003, 0.0005, 0.0008, 0.0012] (0.03%, 0.05%, 0.08%, 0.12%)
- `grid_layers`: [20, 30, 40]
- `risk_budget_pct`: [0.3, 0.6]
- `spacing_multiplier`: [1.0] (固定)

**输出指标**:
- `total_return`: 总收益率
- `sharpe_ratio`: 夏普比率
- `max_drawdown`: 最大回撤
- `total_trades`: 总交易数
- `trades_per_day`: 每日交易数
- `annualized_return`: 年化收益率
- `calmar_like`: 类似 Calmar 比率

**输出位置**: `run/results_lean_taogrid_sweep/`

---

### 2. 因子消融研究 (Factor Ablation)

**方法**: 对比启用/禁用单个因子对策略性能的影响

**消融脚本**:
- `run/taogrid_factor_ablation.py`: MR+Trend 因子
- `run/taogrid_breakout_risk_ablation.py`: Breakout Risk 因子
- `run/taogrid_funding_ablation.py`: Funding Rate 因子
- `run/taogrid_range_pos_v2_ablation.py`: Range Position 因子
- `run/taogrid_vol_regime_ablation.py`: Volatility Regime 因子

**对比方式**:
- 运行两个回测：因子 OFF vs ON
- 比较 Sharpe、Turnover、Drawdown 等指标
- 输出到 `run/results_lean_taogrid_<factor>_ablation/`

---

### 3. 单因子参数扫描

**方法**: 针对单个因子的参数进行精细扫描

**扫描脚本**:
- `run/taogrid_breakout_risk_sweep.py`: Breakout Risk 参数扫描
- `run/taogrid_range_pos_v2_sweep.py`: Range Position 参数扫描
- `run/taogrid_funding_gate_sweep.py`: Funding Gate 参数扫描
- `run/taogrid_inventory_skew_sweep.py`: Inventory Skew 参数扫描
- `run/taogrid_capacity_sweep.py`: Capacity 参数扫描

**示例**: Breakout Risk 扫描
- `breakout_buy_k`: [0.0, 0.3, 0.6, 0.9]
- `breakout_buy_floor`: [0.2, 0.4, 0.6]
- 评估不同参数组合对 Sharpe 和 Turnover 的影响

---

### 4. 优化目标

**主要目标**:
1. **最大化 Sharpe 比率**: 风险调整后的收益
2. **保持合理 Turnover**: 避免过度交易或交易不足
3. **控制最大回撤**: 限制下行风险
4. **平衡 ROE 和 Turnover**: 找到最优折中点

**评估指标**:
- `sharpe_ratio`: 年化夏普比率（365 天）
- `total_return`: 总收益率
- `max_drawdown`: 最大回撤
- `total_trades`: 总交易数
- `trades_per_day`: 每日交易数
- `calmar_like`: 类似 Calmar 比率

---

## 实现架构

### 文件结构

```
algorithms/taogrid/
├── algorithm.py              # Lean 算法主类
├── config.py                 # 配置类 (TaoGridLeanConfig)
├── helpers/
│   └── grid_manager.py      # 网格管理器（整合所有逻辑）
└── simple_lean_runner.py    # 简化回测运行器

analytics/indicators/
├── grid_generator.py         # 网格生成（间距、层级）
├── grid_weights.py           # 层级权重计算
├── regime_factors.py         # MR + Trend 因子
├── breakout_risk.py          # Breakout Risk 因子
├── range_factors.py          # Range Position 因子
├── vol_regime.py             # Volatility Regime 因子
└── volatility.py             # ATR 计算

risk_management/
├── grid_inventory.py         # 库存跟踪器
└── grid_risk_manager.py      # 风险管理器（节流逻辑）

run/
├── taogrid_sweep.py          # 参数扫描
├── taogrid_*_ablation.py     # 因子消融研究
└── taogrid_*_sweep.py        # 单因子参数扫描
```

### 核心类

#### 1. `TaoGridLeanAlgorithm`
- 主算法类
- 初始化网格、处理市场数据
- 调用 `GridManager` 进行订单管理

#### 2. `GridManager`
- 管理网格状态
- 生成网格层级
- 计算订单规模（应用所有因子）
- 跟踪库存
- 应用风险管理规则

#### 3. `GridInventoryTracker`
- 跟踪多头/空头敞口
- 提供库存状态查询

#### 4. `GridRiskManager`
- 实现节流逻辑
- 检查库存限制、利润锁定、波动率调整

### 工作流程

1. **初始化**:
   - 加载历史数据
   - 计算 ATR
   - 生成网格层级
   - 计算层级权重
   - 分配多空预算

2. **每根 K 线处理**:
   - 检查限价单触发
   - 计算订单规模（应用所有因子）
   - 检查风险管理规则
   - 执行订单
   - 更新库存

3. **订单配对**:
   - 买入后自动放置卖出限价单
   - 卖出后重新放置买入限价单（再入）
   - 自由卖出模式：只要有持仓，可以随时卖出

---

## 总结

TaoGrid 策略是一个**高度复杂的多因子网格交易系统**，核心特点：

1. **多因子体系**: 7 个主要因子动态调整订单规模
2. **分级风险管理**: 4 级风险区域，从轻度调整到完全关闭
3. **精细参数控制**: 100+ 参数可调，支持精细优化
4. **系统化优化方法**: 参数扫描、因子消融、单因子扫描
5. **机构级库存管理**: 类似做市商的库存控制逻辑

策略设计哲学强调**交易者判断 + 算法执行**，保持了灵活性和可控性，同时通过算法自动化处理复杂的执行细节。

---

**文档维护**: 本文档应随策略更新同步维护。  
**联系方式**: 如有问题或建议，请参考项目 README。
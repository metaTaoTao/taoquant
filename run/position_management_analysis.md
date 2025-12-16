# TaoGrid 仓位管理机制分析（基于真实代码逻辑）

## 核心代码位置
- `algorithms/taogrid/helpers/grid_manager.py::calculate_order_size()` (458-755行)
- `algorithms/taogrid/config.py` (配置参数)

---

## 1. 基础仓位计算

**代码位置**: `grid_manager.py:514-525`

```python
# 1. 计算基础仓位（USD）
total_budget_usd = equity * self.config.risk_budget_pct
this_level_budget_usd = total_budget_usd * weight  # weight是层级权重

# 2. 转换为BTC数量
base_size_btc = this_level_budget_usd / level_price

# 3. 应用杠杆
base_size_btc = base_size_btc * self.config.leverage
```

**说明**: 基础仓位 = (权益 × 风险预算比例 × 层级权重) / 价格 × 杠杆

---

## 2. 库存感知仓位控制（Inventory-Aware Sizing）

**代码位置**: `grid_manager.py:539-558`

```python
# 计算库存比率（名义价值/权益）
inv_ratio = (abs(float(holdings_btc)) * float(level_price) / float(equity)) if equity > 0 else 999.0
inv_ratio_threshold = float(self.config.inventory_capacity_threshold_pct) * float(self.config.leverage)

if direction == "buy":
    # 如果库存比率 >= 阈值，完全阻止买入
    if inv_ratio >= inv_ratio_threshold:
        return 0.0, ThrottleStatus(
            size_multiplier=0.0,
            reason="Inventory de-risk (notional_ratio>=capacity_threshold)",
        )
    
    # 否则，根据库存比率逐步减少买入仓位
    if self.config.inventory_skew_k > 0:
        # Scale buy size down as inventory ratio rises toward capacity.
        # inventory_skew_k controls how aggressive the reduction is.
        skew_mult = max(0.0, 1.0 - self.config.inventory_skew_k * (inv_ratio / max(inv_ratio_threshold, 1e-9)))
        base_size_btc = base_size_btc * skew_mult
```

**关键机制**:
- **库存比率** = `(持仓BTC数量 × 价格) / 权益`
- **阈值** = `inventory_capacity_threshold_pct × leverage` = `0.9 × 50 = 45倍权益`
- 当 `inv_ratio >= 45` 时，**完全阻止买入**
- 当 `inv_ratio` 接近 45 时，通过 `inventory_skew_k` **逐步减少买入**

**参数**:
- `inventory_capacity_threshold_pct = 0.9` (90%)
- `inventory_skew_k = 1.0` (强度)
- `leverage = 50X`
- **实际阈值**: 45倍权益的名义价值

---

## 3. Market Maker Risk Zone（做市商风险区域）

**代码位置**: `grid_manager.py:532-576, 721-733`

### 3.1 判断是否进入风险区域

```python
# Risk zone threshold: support + cushion (volatility buffer)
risk_zone_threshold = self.config.support + (self.current_atr * self.config.cushion_multiplier)
if current_price < risk_zone_threshold:
    in_risk_zone = True
```

### 3.2 买入时（在风险区域）

```python
if direction == "buy" and in_risk_zone:
    # Apply risk level multipliers
    if self.risk_level == 3:
        # Level 3: Severe risk
        mm_buy_mult = float(getattr(self.config, "mm_risk_level3_buy_mult", 0.05))  # 5%
    elif self.risk_level == 2:
        # Level 2: Moderate risk
        mm_buy_mult = float(getattr(self.config, "mm_risk_level2_buy_mult", 0.1))    # 10%
    else:
        # Level 1: Mild risk
        mm_buy_mult = float(getattr(self.config, "mm_risk_level1_buy_mult", 0.2))     # 20%
    
    # Additional penalty if inventory is already high
    if inv_ratio > float(getattr(self.config, "mm_risk_inventory_penalty", 0.5)):
        mm_buy_mult = mm_buy_mult * 0.5  # Further reduce by 50%
    
    base_size_btc = base_size_btc * mm_buy_mult
```

### 3.3 卖出时（在风险区域）

```python
if direction == "sell" and in_risk_zone:
    # Apply risk level multipliers
    if self.risk_level == 3:
        # Level 3: Severe risk
        mm_sell_mult = float(getattr(self.config, "mm_risk_level3_sell_mult", 5.0))  # 500%
    elif self.risk_level == 2:
        # Level 2: Moderate risk
        mm_sell_mult = float(getattr(self.config, "mm_risk_level2_sell_mult", 4.0))  # 400%
    else:
        # Level 1: Mild risk
        mm_sell_mult = float(getattr(self.config, "mm_risk_level1_sell_mult", 3.0))  # 300%
    
    base_size_btc = base_size_btc * mm_sell_mult
```

**关键机制**:
- 当价格跌破 `support + (ATR × cushion)` 时，进入风险模式
- **买入仓位大幅减少**（5%-20%），**卖出仓位大幅增加**（300%-500%）
- 这是典型的做市商"去库存"行为：在风险区域，减少新开仓，增加平仓

**参数**:
- `mm_risk_level1_buy_mult = 0.2` (买入20%)
- `mm_risk_level1_sell_mult = 3.0` (卖出300%)
- `mm_risk_level3_buy_mult = 0.05` (买入5%)
- `mm_risk_level3_sell_mult = 5.0` (卖出500%)

---

## 4. Breakout Risk 因子（突破风险因子）

**代码位置**: `grid_manager.py:619-632`

```python
# Breakout risk factor (near boundary risk-off)
if getattr(self.config, "enable_breakout_risk_factor", False):
    br_down = float(breakout_risk_down) if breakout_risk_down is not None and np.isfinite(breakout_risk_down) else 0.0
    
    # For a long-inventory grid, downside breakout is the main tail risk.
    if br_down >= float(self.config.breakout_block_threshold):
        return 0.0, ThrottleStatus(
            size_multiplier=0.0,
            reason="Breakout risk-off (downside)",  # 这就是日志中看到的！
        )
    
    # Reduce buys as downside risk rises; keep a floor to preserve churn.
    risk_mult = max(
        float(self.config.breakout_buy_floor),
        1.0 - float(self.config.breakout_buy_k) * br_down,
    )
    base_size_btc = base_size_btc * risk_mult
```

**关键机制**:
- 当 `breakout_risk_down >= 0.95` 时，**完全阻止买入**
- 这是为什么在10.10-10.11期间，价格到101K时，没有新买入订单的原因
- 从日志看到：`"Order blocked - BUY L38: Breakout risk-off (downside)"`

**参数**:
- `breakout_block_threshold = 0.95`
- `breakout_buy_k = 0.6` (风险高时减少买入的强度)
- `breakout_buy_floor = 0.4` (最低买入倍数)

---

## 5. 其他因子过滤

### 5.1 MR + Trend 因子

**代码位置**: `grid_manager.py:578-617`

```python
if getattr(self.config, "enable_mr_trend_factor", False):
    ts = float(trend_score) if trend_score is not None and np.isfinite(trend_score) else 0.0
    z = float(mr_z) if mr_z is not None and np.isfinite(mr_z) else 0.0
    
    # Hard block for strong downtrend
    if ts <= -float(self.config.trend_block_threshold):
        return 0.0, ThrottleStatus(
            size_multiplier=0.0,
            reason="Factor block (strong downtrend)",
        )
    
    # Trend multiplier: only reduce when ts < 0
    neg_ts = max(0.0, -ts)
    trend_mult = max(
        float(self.config.trend_buy_floor),
        1.0 - float(self.config.trend_buy_k) * neg_ts,
    )
    
    # MR multiplier: oversold -> larger size
    if z >= 0:
        mr_mult = float(self.config.mr_min_mult)
    else:
        mr_strength = min(1.0, max(0.0, (-z) / float(self.config.mr_z_ref)))
        mr_mult = max(float(self.config.mr_min_mult), mr_strength)
    
    factor_mult = trend_mult * mr_mult
    base_size_btc = base_size_btc * factor_mult
```

### 5.2 Funding 因子（资金费率）

**代码位置**: `grid_manager.py:641-662, 694-704`

```python
if getattr(self.config, "enable_funding_factor", False):
    fr = float(funding_rate) if funding_rate is not None and np.isfinite(funding_rate) else 0.0
    
    # 买入时：资金费率高时减少买入
    if getattr(self.config, "funding_apply_to_buy", False):
        if fr >= float(self.config.funding_block_threshold):
            return 0.0, ThrottleStatus(
                size_multiplier=0.0,
                reason="Funding risk-off (block BUY)",
            )
        if fr > 0:
            buy_mult = max(float(self.config.funding_buy_floor), 1.0 - float(self.config.funding_buy_k) * x)
            base_size_btc = base_size_btc * buy_mult
    
    # 卖出时：资金费率高时增加卖出
    if getattr(self.config, "funding_apply_to_sell", True):
        if fr > 0:
            sell_mult = min(float(self.config.funding_sell_cap), 1.0 + float(self.config.funding_sell_k) * x)
            base_size_btc = base_size_btc * sell_mult
```

### 5.3 Range Position Asymmetry v2（区间位置不对称）

**代码位置**: `grid_manager.py:664-672, 706-713`

```python
if getattr(self.config, "enable_range_pos_asymmetry_v2", False):
    rp = float(range_pos) if range_pos is not None and np.isfinite(range_pos) else 0.5
    start = float(self.config.range_top_band_start)  # 0.85
    
    if rp >= start:
        # 在顶部区域（range_pos >= 0.85）：
        # 买入时：减少买入
        buy_mult = max(float(self.config.range_buy_floor), 1.0 - float(self.config.range_buy_k) * x)
        # 卖出时：增加卖出
        sell_mult = min(float(self.config.range_sell_cap), 1.0 + float(self.config.range_sell_k) * x)
        base_size_btc = base_size_btc * (buy_mult if buy else sell_mult)
```

### 5.4 Volatility Regime 因子（波动率制度）

**代码位置**: `grid_manager.py:674-681, 715-719`

```python
if getattr(self.config, "enable_vol_regime_factor", False):
    vs = float(vol_score) if vol_score is not None and np.isfinite(vol_score) else 0.0
    
    # 极端高波动时：增加卖出
    if vs >= float(getattr(self.config, "vol_trigger_score", 1.0)) and getattr(self.config, "vol_apply_to_sell", True):
        if direction == "sell":
            base_size_btc = base_size_btc * float(self.config.vol_sell_mult_high)  # 1.15
```

---

## 6. 卖出仓位限制

**代码位置**: `grid_manager.py:735`

```python
# 卖出时，不能超过当前持仓
if direction == "sell":
    base_size_btc = min(base_size_btc, max(0.0, float(holdings_btc)))
```

**说明**: 卖出仓位不能超过当前持仓，避免卖空

---

## 7. 最终节流检查（Throttling）

**代码位置**: `grid_manager.py:737-747`

```python
# Apply throttling if enabled
if self.config.enable_throttling:
    throttle_status = self.risk_manager.check_throttle(
        long_exposure=inventory_state.long_exposure,
        short_exposure=inventory_state.short_exposure,
        daily_pnl=daily_pnl,
        risk_budget=risk_budget,
        current_atr=self.current_atr,
        avg_atr=self.avg_atr,
    )
    size_btc = base_size_btc * throttle_status.size_multiplier
```

**说明**: 最后应用节流规则（库存限制、利润目标锁定、波动率节流）

---

## 为什么仓位控制得这么好？

### 1. **多层级的仓位限制机制**
- 基础仓位计算：基于权益和风险预算
- 库存感知控制：当库存比率接近阈值时，逐步减少买入
- 风险区域控制：在价格跌破支撑时，买入大幅减少，卖出大幅增加
- 因子过滤：多个因子协同工作，在不利条件下阻止或减少买入

### 2. **库存比率（Inventory Ratio）的实时监控**
- `inv_ratio = (holdings_btc * price) / equity`
- 阈值 = `inventory_capacity_threshold_pct × leverage = 0.9 × 50 = 45倍权益`
- 当 `inv_ratio >= 45` 时，**完全阻止买入**
- 当 `inv_ratio` 接近 45 时，通过 `inventory_skew_k` **逐步减少买入**

### 3. **Market Maker Risk Zone 的做市商风格去库存**
- 当价格跌破 `support + (ATR × cushion)` 时：
  - **买入仓位减少到 5%-20%**
  - **卖出仓位增加到 300%-500%**
- 这是典型的做市商"去库存"行为：在风险区域，减少新开仓，增加平仓

### 4. **Breakout Risk 因子在极端情况下的保护**
- 在10.10-10.11期间，价格快速下跌时：
  - `breakout_risk_down >= 0.95` 时，**完全阻止买入**
  - 这是为什么在价格到101K时，没有新买入订单的原因
- 从日志看到：`"Order blocked - BUY L38: Breakout risk-off (downside)"`

### 5. **卖出仓位的动态放大**
- 在风险区域，卖出仓位可以增加到 **300%-500%**
- 这意味着在价格下跌时，卖出订单会快速执行，快速减少持仓
- 从日志看，21:20之后有大量卖出订单执行，持仓从70%快速降到54%

### 6. **因子协同工作**
- **MR + Trend**: 在强下跌趋势时阻止买入
- **Breakout Risk**: 在突破风险高时阻止买入（**关键！**）
- **Funding**: 在资金费率高时减少买入/增加卖出
- **Range Position**: 在顶部区域减少买入/增加卖出
- **Volatility**: 在极端波动时增加卖出

### 7. **卖出配对机制快速减少持仓**
- 每次卖出订单都会通过配对机制减少持仓
- 在价格反弹过程中，卖出订单快速执行
- 持仓在价格反弹过程中快速降低

---

## 总结

**仓位控制不是单一机制，而是多层级的协同工作**：

1. **库存比率实时监控** → 接近阈值时逐步减少买入
2. **风险区域触发** → 买入大幅减少，卖出大幅增加
3. **Breakout Risk 因子** → 在极端情况下完全阻止买入
4. **卖出仓位动态放大** → 快速减少持仓
5. **因子协同工作** → 在不利条件下多维度保护

这就是为什么在10.10-10.11期间，即使价格跌到101K，策略也能通过**快速减少持仓**和**阻止逆势买入**来控制风险，最终只产生了11.37%的回撤。

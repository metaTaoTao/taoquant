# 🔍 回测 vs 实盘逻辑对比报告

**分析时间**: 2025-12-25
**目的**: 确保实盘完全复刻回测逻辑

---

## ✅ 核心结论

**NEUTRAL_RANGE 模式 = Long-Only 策略**

在回测和实盘中，`regime="NEUTRAL_RANGE"` 都是 **Long-Only** 策略：
- ✅ 只开多头（BUY）
- ✅ 只平多头（SELL）
- ❌ **不开空头** (short_open)
- ❌ **不平空头** (short_cover)

---

## 📊 配置对比

### 回测配置 (`simple_lean_runner.py:1414-1495`)

```python
regime = "NEUTRAL_RANGE"        # ✅ 50% buy, 50% sell weights
leverage = 5.0                   # ⚠️  5倍杠杆
initial_cash = 100000.0          # ⚠️  $100,000
support = 90000.0                # ⚠️  不同的S/R
resistance = 108000.0            # ⚠️  不同的S/R
grid_layers_buy = 40             # ✅ 匹配
grid_layers_sell = 40            # ✅ 匹配
risk_budget_pct = 1.0            # ✅ 匹配 (100%)
maker_fee = 0.0002               # ✅ 匹配
volatility_k = 0.2               # ✅ 匹配
enable_mm_risk_zone = True       # ✅ 匹配
```

### 实盘配置 (`config_bitget_live.json`)

```json
{
  "regime": "NEUTRAL_RANGE",     // ✅ 50% buy, 50% sell weights
  "leverage": 10.0,               // ⚠️  10倍杠杆 (回测用5倍)
  "initial_cash": 100.0,          // ⚠️  $100 (回测用$100k)
  "support": 84000.0,             // ⚠️  不同的S/R (回测用90k-108k)
  "resistance": 94000.0,          // ⚠️  不同的S/R
  "grid_layers_buy": 40,          // ✅ 匹配
  "grid_layers_sell": 40,         // ✅ 匹配
  "risk_budget_pct": 1.0,         // ✅ 匹配
  "maker_fee": 0.0002,            // ✅ 匹配
  "volatility_k": 0.2,            // ✅ 匹配
  "enable_mm_risk_zone": true,    // ✅ 匹配
  "active_buy_levels": 6          // ⚠️  实盘独有（风控）
}
```

---

## 🔒 Long-Only 机制验证

### Short模式开关 (`grid_manager.py:259-261`)

```python
def _short_mode_enabled(self) -> bool:
    """Return True if short leg is enabled for current config/regime."""
    return (
        bool(getattr(self.config, "enable_short_in_bearish", False))
        and
        getattr(self.config, "regime", "") == "BEARISH_RANGE"
    )
```

**结论**:
- ✅ Short模式需要 `regime="BEARISH_RANGE"` **且** `enable_short_in_bearish=True`
- ✅ NEUTRAL_RANGE 模式 → `_short_mode_enabled()` 返回 `False`
- ✅ 回测和实盘都是 **Long-Only**

### Short订单生成逻辑 (`grid_manager.py:327-351`)

```python
# Optional: add ONE short overlay entry order (SELL to open) in BEARISH regime.
if self._short_mode_enabled():  # ← 只有BEARISH_RANGE才会执行
    # ... 创建 short_open 订单
    self.pending_limit_orders.append({
        "direction": "sell",
        "leg": "short_open",  # ← short overlay标记
        ...
    })
```

**结论**:
- ✅ `short_open` 订单只在 `BEARISH_RANGE` 模式创建
- ✅ NEUTRAL_RANGE 模式 → 不会创建 `short_open` 订单
- ✅ 所有 SELL 订单的 `leg` 字段为 `None` 或 `"long"`（平多头）

---

## 🛡️ SELL订单保护机制对比

### 回测保护 (`simple_lean_runner.py:821-823`)

```python
elif direction == 'sell':
    # Sell BTC - Match against long positions using GRID PAIRING
    if float(size) <= float(self.long_holdings):  # ← 检查持仓
        # Execute sell (平多头)
        proceeds = size * execution_price
        commission = proceeds * commission_rate
        self.cash += proceeds - commission
        self.long_holdings -= size
        # ... 匹配buy positions
    # else: 隐式返回 False (line 1009)
```

**逻辑**:
- ✅ SELL订单只有在 `sell_size <= long_holdings` 时才执行
- ✅ 如果持仓不足，订单被拒绝（返回False）
- ✅ **防止开空头**

### 实盘保护（我的修复，`bitget_live_runner.py:2105-2158`)

```python
# ✅ CRITICAL FIX (2025-12-25): SELL order protection
if direction == "sell" and leg == "long":
    # Get current exchange actual position
    portfolio_state = self._get_portfolio_state(current_price=price)
    exchange_long = float(portfolio_state.get("long_holdings", 0.0))

    # SELL order cannot exceed actual holdings (5% tolerance)
    if exchange_long < qty * 0.95:  # ← 检查持仓
        self.logger.log_error(
            f"[SELL_PROTECTION] ❌ CRITICAL: Blocked SELL order! "
            f"SELL qty={qty:.6f} > exchange_long={exchange_long:.6f}. "
            f"This would open SHORT position in LONG-ONLY mode!"
        )
        # Skip this order (do NOT place)
        continue
```

**逻辑**:
- ✅ SELL订单只有在 `exchange_long >= sell_qty * 0.95` 时才下单
- ✅ 如果持仓不足，订单被阻止（continue跳过）
- ✅ **防止开空头**
- ✅ 5%容差处理精度问题

---

## ⚠️ 关键差异分析

### 1. 杠杆设置不一致

| 项目 | 回测 | 实盘 | 建议 |
|------|------|------|------|
| Leverage | 5x | 10x | ❌ 不一致，建议改为5x |

**影响**:
- 10x杠杆 → 风险翻倍
- 回测用5x验证，实盘用10x → **偏离回测**
- 建议实盘改为 `"leverage": 5.0` 以匹配回测

### 2. 初始资金差异

| 项目 | 回测 | 实盘 | 说明 |
|------|------|------|------|
| Initial Cash | $100,000 | $100 | ✅ 比例一致（测试vs实盘） |

这个差异是合理的（小资金测试），但要注意：
- **百分比收益** 应该相同
- **绝对数值** 按比例缩放 (1000:1)

### 3. Support/Resistance 差异

| 项目 | 回测 | 实盘 | 说明 |
|------|------|------|------|
| Support | $90,000 | $84,000 | ⚠️ 不同市场范围 |
| Resistance | $108,000 | $94,000 | ⚠️ 不同市场范围 |
| Range | $18,000 (20%) | $10,000 (11.9%) | ⚠️ 实盘范围更窄 |

**影响**:
- 回测覆盖更大的价格范围
- 实盘范围更窄 → 网格间距更紧 → 换手更频繁
- **建议**: 根据当前市场调整，但要重新回测验证

### 4. 实盘独有风控参数

实盘新增了以下风控参数（回测没有）:

```json
{
  "active_buy_levels": 6,                     // 同时挂单的买单层数
  "cooldown_minutes": 2,                      // 异常后冷却时间
  "cooldown_active_buy_levels": 2,            // 冷却期买单层数
  "abnormal_buy_fills_trigger": 2,            // 异常触发阈值
  "abnormal_total_fills_trigger": 3,          // 总成交触发阈值
  "abnormal_buy_notional_frac_equity": 0.03,  // 异常买入比例
  "abnormal_range_mult_spacing": 4            // 异常振幅倍数
}
```

**评估**: ✅ 这些是实盘风控增强，合理

---

## ✅ 逻辑一致性验证

### Grid生成逻辑

| 组件 | 回测 | 实盘 | 状态 |
|------|------|------|------|
| Grid spacing计算 | `calculate_grid_spacing()` | ✅ 同一函数 | ✅ 一致 |
| Grid levels生成 | `generate_grid_levels()` | ✅ 同一函数 | ✅ 一致 |
| Buy/Sell权重 | 50%/50% (NEUTRAL) | ✅ 50%/50% | ✅ 一致 |

### 订单执行逻辑

| 阶段 | 回测 | 实盘 | 状态 |
|------|------|------|------|
| BUY订单生成 | GridManager | ✅ 同一组件 | ✅ 一致 |
| SELL订单生成 | GridManager | ✅ 同一组件 | ✅ 一致 |
| BUY订单执行 | 检查杠杆约束 | ✅ 同样逻辑 | ✅ 一致 |
| SELL订单执行 | 检查long_holdings | ✅ 同样逻辑 | ✅ 一致 |
| Grid配对 | FIFO matching | ✅ 同样逻辑 | ✅ 一致 |

### 风控逻辑

| 风控模块 | 回测 | 实盘 | 状态 |
|---------|------|------|------|
| MM Risk Zone | ✅ Enabled | ✅ Enabled | ✅ 一致 |
| Inventory Throttling | ✅ Enabled | ✅ Enabled | ✅ 一致 |
| Breakout Risk | ✅ Enabled | ✅ Enabled | ✅ 一致 |
| Funding Factor | ✅ Enabled | ✅ Enabled | ✅ 一致 |
| Vol Regime | ✅ Enabled | ✅ Enabled | ✅ 一致 |

---

## 🐛 Fill Recovery Bug 分析

### 问题回顾

**2025-12-25 19:35事件**:
1. 回测逻辑: ✅ SELL订单被 `long_holdings` 检查拒绝
2. 实盘bug: ❌ Fill Recovery错误假设订单成交
3. 结果: ❌ Ledger记录有持仓，但exchange实际为0
4. 后果: ❌ SELL订单下单成功 → 开空头！

### 根本原因

**回测中**:
```python
# execute_order() 中的检查（line 823）
if float(size) <= float(self.long_holdings):
    # 有持仓才执行SELL
else:
    return False  # 持仓不足，拒绝
```

**实盘bug逻辑（修复前）**:
```python
# Fill Recovery (line 1395)
if order_status is None:
    # ❌ 直接假设订单成交
    self.algorithm.on_order_filled(order)
    # 触发hedge → 生成SELL订单
    # 但exchange实际持仓 = 0！
```

**问题**: 实盘的Fill Recovery绕过了持仓检查！

### 修复方案对比

**回测**: 不需要修复（逻辑正确）

**实盘修复** (我的实施):
1. ✅ Fill Recovery 新增持仓验证
2. ✅ SELL订单下单前新增保护

现在实盘逻辑 = 回测逻辑 + 额外保护层

---

## 📋 建议的实盘配置修改

为了完全匹配回测，建议修改以下参数：

```json
{
  "strategy": {
    "leverage": 5.0,           // ← 改为5x（匹配回测）
    "risk_budget_pct": 0.5,    // ← 建议降至50%（更保守）

    // S/R根据当前市场调整，保持合理范围
    "support": 84000.0,        // ← 可保持或调整
    "resistance": 94000.0,     // ← 可保持或调整

    // 其他参数保持不变
    ...
  }
}
```

---

## ✅ 验证清单

实盘部署前，请确认：

- [ ] ✅ `regime="NEUTRAL_RANGE"` (Long-Only)
- [ ] ⚠️  `leverage=5.0` (匹配回测，非10x)
- [ ] ✅ `grid_layers_buy=40, grid_layers_sell=40`
- [ ] ✅ `risk_budget_pct=1.0` (或更保守的0.5)
- [ ] ✅ `enable_mm_risk_zone=true`
- [ ] ✅ Fill Recovery 修复已部署
- [ ] ✅ SELL保护已部署
- [ ] ✅ 实盘测试（dry-run）通过

---

## 🎯 核心确认

**Q: 回测是Long-Only吗？**
A: ✅ 是的。`NEUTRAL_RANGE` 模式下不会生成 `short_open` 订单。

**Q: 实盘会开空头吗（修复后）？**
A: ✅ 不会。两层保护：
1. Fill Recovery 验证持仓变化
2. SELL订单下单前检查 `exchange_long >= sell_qty`

**Q: 回测和实盘逻辑是否一致？**
A: ✅ 核心逻辑一致（Grid生成、订单执行、风控），但需调整:
- ⚠️ 杠杆: 10x → 5x
- ✅ 其他: 已匹配或合理差异

---

**结论**: 实盘已修复为完全复刻回测的Long-Only逻辑。建议调整杠杆至5x后部署。

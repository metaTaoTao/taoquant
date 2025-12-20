# TaoGrid 实盘参数选择指南

## 📊 核心参数选择逻辑

### 1. **格子数量（grid_layers_buy / grid_layers_sell）**

#### 计算公式

```
网格间距 = min_return + 2×maker_fee + 2×slippage + k×volatility
可用区间 = resistance - support - 2×cushion
格子数量 = 可用区间 / (网格间距 × mid_price)
```

#### 选择建议

**场景 1：保守型（低频、高利润）**
- **格子数量**：5-10 层
- **适用**：大资金、低波动市场、追求单笔高利润
- **特点**：交易频率低，单笔利润大（0.5-1%+），资金利用率低

**场景 2：平衡型（推荐）**
- **格子数量**：10-20 层
- **适用**：中等资金（$1k-$10k）、正常波动市场
- **特点**：交易频率适中，单笔利润 0.3-0.5%，资金利用率较好

**场景 3：激进型（高频、薄利）**
- **格子数量**：20-40 层
- **适用**：小资金、高波动市场、追求高周转率
- **特点**：交易频率高，单笔利润 0.1-0.3%，资金利用率高

**场景 4：极密网格（专业做市）**
- **格子数量**：40-100 层
- **适用**：专业做市、极低手续费（<0.01%）、1分钟K线
- **特点**：极高频率，单笔利润 <0.1%，需要严格风控

#### 实际计算示例

假设：
- `support = 104000`
- `resistance = 126000`
- `mid = 115000`
- `ATR = 2000`（约 1.7%）
- `min_return = 0.005`（0.5%）
- `maker_fee = 0.0002`（0.02%）
- `volatility_k = 0.6`
- `cushion_multiplier = 0.8`

计算：
```
网格间距 ≈ 0.005 + 2×0.0002 + 0.6×0.017 ≈ 0.0152（1.52%）
可用区间 = 126000 - 104000 - 2×2000×0.8 = 19680
格子数量 = 19680 / (0.0152 × 115000) ≈ 11 层
```

**推荐配置**：`grid_layers_buy = 10-15`，`grid_layers_sell = 10-15`

---

### 2. **支撑/阻力（support / resistance）**

#### 选择方法

**方法 1：手动设置（推荐新手）**
- 从 TradingView 图表上识别明显的支撑/阻力位
- 使用你之前做的 S/R 指标（`sr_long.txt` / `sr_short.txt`）找 active zone
- 设置时留出 5-10% 的安全边际（避免假突破）

**方法 2：动态计算（进阶）**
- 使用历史数据计算 pivot high/low
- 自动识别最近 N 天的支撑/阻力
- 可以集成到实盘 runner 里（需要我帮你实现）

#### 示例

```json
{
  "strategy": {
    "support": 104000.0,    // 从 TradingView 看到的支撑位
    "resistance": 126000.0, // 从 TradingView 看到的阻力位
    "regime": "NEUTRAL_RANGE"
  }
}
```

---

### 3. **市场状态（regime）**

#### 选择逻辑

- **BULLISH_RANGE**（看涨区间）：
  - 价格在区间中上部，预期向上突破
  - 配置：`buy_ratio = 0.7`，`sell_ratio = 0.3`
  - 适合：趋势向上，但仍在区间内震荡

- **NEUTRAL_RANGE**（中性区间）：
  - 价格在区间中部，预期横盘震荡
  - 配置：`buy_ratio = 0.5`，`sell_ratio = 0.5`
  - 适合：无明显趋势，区间震荡

- **BEARISH_RANGE**（看跌区间）：
  - 价格在区间中下部，预期向下突破
  - 配置：`buy_ratio = 0.3`，`sell_ratio = 0.7`
  - 适合：趋势向下，但仍在区间内震荡

#### 判断方法

```
range_position = (current_price - support) / (resistance - support)

if range_position > 0.6:
    regime = "BULLISH_RANGE"
elif range_position < 0.4:
    regime = "BEARISH_RANGE"
else:
    regime = "NEUTRAL_RANGE"
```

---

### 4. **最小利润（min_return）**

#### 选择建议

- **Bitget 现货**：`maker_fee = 0.001`（0.1%），推荐 `min_return = 0.005-0.01`（0.5-1%）
- **Bitget 合约**：`maker_fee = 0.0002`（0.02%），推荐 `min_return = 0.003-0.005`（0.3-0.5%）
- **极低手续费**（<0.01%）：`min_return = 0.001-0.003`（0.1-0.3%）

**重要**：`min_return` 必须 > `2×maker_fee`，否则单笔交易会亏损！

---

### 5. **网格间距倍数（spacing_multiplier）**

#### 选择建议

- **默认**：`1.0`（使用计算出的最小间距）
- **保守**：`1.5-2.0`（扩大间距，降低交易频率）
- **激进**：`1.0`（最小间距，提高交易频率）

**⚠️ 警告**：`spacing_multiplier` 必须 >= 1.0，否则会违反成本覆盖！

---

### 6. **风险预算（risk_budget_pct）**

#### 选择建议

- **保守**：`0.2`（20% 资金用于网格）
- **平衡**：`0.3`（30% 资金用于网格，推荐）
- **激进**：`0.5`（50% 资金用于网格）

**注意**：这个参数控制的是“单次网格交易的最大资金占比”，不是总仓位。

---

### 7. **初始资金（initial_cash）**

#### 选择建议

- **实盘**：设置为你的实际账户余额（USDT）
- **测试**：可以设置小金额（$100-$1000）先跑 dry-run

**注意**：实盘 runner 会自动从 Bitget API 读取真实余额，这个参数主要用于回测。

---

## 🎯 不同场景的推荐配置

### 场景 A：新手入门（$1k 资金，BTCUSDT）

```json
{
  "strategy": {
    "support": 104000.0,
    "resistance": 126000.0,
    "regime": "NEUTRAL_RANGE",
    "grid_layers_buy": 10,
    "grid_layers_sell": 10,
    "initial_cash": 1000.0,
    "min_return": 0.005,
    "spacing_multiplier": 1.0,
    "risk_budget_pct": 0.3
  }
}
```

### 场景 B：专业做市（$10k+ 资金，低手续费）

```json
{
  "strategy": {
    "support": 104000.0,
    "resistance": 126000.0,
    "regime": "NEUTRAL_RANGE",
    "grid_layers_buy": 30,
    "grid_layers_sell": 30,
    "initial_cash": 10000.0,
    "min_return": 0.0012,
    "spacing_multiplier": 1.0,
    "risk_budget_pct": 0.3
  }
}
```

### 场景 C：保守型（大资金，低频率）

```json
{
  "strategy": {
    "support": 104000.0,
    "resistance": 126000.0,
    "regime": "NEUTRAL_RANGE",
    "grid_layers_buy": 5,
    "grid_layers_sell": 5,
    "initial_cash": 50000.0,
    "min_return": 0.01,
    "spacing_multiplier": 1.5,
    "risk_budget_pct": 0.2
  }
}
```

---

## 🔧 参数调优流程

### 第 1 步：确定支撑/阻力
1. 在 TradingView 上识别明显的支撑/阻力位
2. 或使用你的 S/R 指标找 active zone
3. 设置到 `config.json`

### 第 2 步：估算网格间距
1. 查看当前 ATR（可以用 `test_bitget_connection.py` 拉数据）
2. 计算：`spacing ≈ min_return + 2×maker_fee + k×ATR%`
3. 估算可用区间：`resistance - support - 2×cushion`

### 第 3 步：确定格子数量
1. 用公式：`格子数 = 可用区间 / (spacing × mid_price)`
2. 根据你的风险偏好调整：
   - 保守：格子数 × 0.7
   - 平衡：格子数 × 1.0
   - 激进：格子数 × 1.5

### 第 4 步：Dry-run 验证
1. 用 `--dry-run` 跑 1-2 天
2. 观察：
   - 交易频率是否合理（每天 5-20 笔？）
   - 单笔利润是否覆盖成本
   - 是否有过度交易或交易不足

### 第 5 步：小额实盘
1. 先用小资金（$100-$500）跑 1 周
2. 监控：
   - 实际成交价格 vs 预期
   - 滑点情况
   - 订单执行延迟

---

## ⚠️ 常见错误

### ❌ 错误 1：格子数量太多
- **症状**：每天交易 100+ 笔，单笔利润 <0.1%
- **原因**：`grid_layers` 设置过大，网格太密
- **解决**：减少到 10-20 层

### ❌ 错误 2：格子数量太少
- **症状**：几天才交易 1 笔，资金利用率低
- **原因**：`grid_layers` 设置过小，网格太稀疏
- **解决**：增加到 15-25 层

### ❌ 错误 3：min_return 太小
- **症状**：单笔交易亏损，或利润被手续费吃掉
- **原因**：`min_return < 2×maker_fee`
- **解决**：确保 `min_return >= 2×maker_fee + 0.001`（至少 0.1% 安全边际）

### ❌ 错误 4：支撑/阻力设置不合理
- **症状**：价格频繁突破区间，网格失效
- **原因**：区间太窄，或没有考虑波动率
- **解决**：区间宽度至少 = `3×ATR`，留出安全边际

---

## 📝 快速参考表

| 参数 | 推荐范围 | 说明 |
|------|---------|------|
| `grid_layers_buy/sell` | 10-20 | 平衡型推荐 |
| `support/resistance` | 手动设置 | 从 TradingView 识别 |
| `regime` | NEUTRAL_RANGE | 默认中性 |
| `min_return` | 0.005 (0.5%) | Bitget 现货推荐 |
| `spacing_multiplier` | 1.0 | 默认值 |
| `risk_budget_pct` | 0.3 (30%) | 平衡型推荐 |
| `initial_cash` | 实际余额 | 实盘自动读取 |

---

## 🚀 下一步

1. **创建你的 config.json**：根据上面的建议填写参数
2. **Dry-run 测试**：用 `--dry-run` 跑 1-2 天验证
3. **小额实盘**：确认无误后，用 $100-$500 跑 1 周
4. **逐步调优**：根据实际表现微调参数

需要我帮你生成一个针对你当前市场情况的 config.json 吗？

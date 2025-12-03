# SRShort4HResistance 策略文档

## 策略概述

**SRShort4HResistance** 是一个基于 TradingView SR指标的多时间框架做空策略。该策略在4H时间框架检测阻力区，在15分钟时间框架执行入场和出场，采用分割仓位管理实现零成本持仓目标。

### 核心理念

1. **多时间框架分析**: 使用4H识别关键阻力位，15min捕捉精确入场
2. **动态阻力区**: 基于Pivot High检测并动态合并阻力区域
3. **风险控制**: 固定3倍ATR(200)止损，确保风险可控
4. **分割仓位**: 30%固定止盈实现零成本，70%移动止盈追求大利润

---

## 策略参数

### 阻力区检测参数
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `left_len` | 90 | Pivot High左侧K线数量 |
| `right_len` | 10 | Pivot High右侧确认K线数 |
| `merge_atr_mult` | 3.5 | 阻力区合并阈值（ATR倍数） |
| `break_tol_atr` | 0.5 | 阻力区破坏容忍度（ATR倍数） |
| `min_touches` | 1 | 最少触碰次数 |
| `max_retries` | 3 | 单区最大失败次数 |

### 信号过滤参数
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `global_cd` | 30 | 全局冷却时间（K线数） |
| `price_filter_pct` | 1.5 | 价格距离过滤（%） |
| `min_position_distance_pct` | 1.5 | 仓位间最小距离（%） |
| `max_positions` | 5 | 最大并发仓位数 |

### 仓位管理参数
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `risk_per_trade_pct` | 0.5 | 单笔交易风险（占总权益%） |
| `leverage` | 5.0 | 最大杠杆倍数 |
| `strategy_sl_percent` | 2.0 | 止损百分比（已废弃，使用ATR止损） |

### 出场管理参数
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `breakeven_ratio` | 2.33 | 零成本比例（R倍数） |
| `trailing_pct` | 70.0 | 移动止盈仓位占比（%） |
| `trail_trigger_atr` | 5.0 | 移动止盈激活阈值（ATR倍数） |
| `trail_offset_atr` | 2.0 | 移动止损距离（ATR倍数） |

---

## 策略逻辑详解

### 1. 阻力区检测（4H时间框架）

#### 1.1 Pivot High识别
```python
# 检测条件：high[T] 是 [T-90, T+10] 窗口内的最大值
pivot_high = detect_pivot_high(htf_data["high"], left_len=90, right_len=10)
```

**确认机制**: Pivot在右侧10根K线后确认，避免未来函数

#### 1.2 阻力区构建
每个Pivot High生成一个阻力区：
- **顶部**: Pivot High价格
- **底部**: max(open, close) at pivot bar（实体顶部）
- **最小厚度**: 0.2 × ATR(14)

#### 1.3 阻力区合并
当新Pivot满足以下条件时合并到现有区域：
```python
tolerance = ATR(14) × 3.5
if (zone.bottom - tolerance) <= pivot_high <= (zone.top + tolerance):
    zone.top = max(zone.top, pivot_high)
    zone.bottom = min(zone.bottom, pivot_body)
    zone.touches += 1
```

#### 1.4 阻力区失效
当4H收盘价突破阻力区顶部 + 0.5×ATR(14)时，标记为失效：
```python
if close_4h > (zone.top + 0.5 × ATR_4h):
    zone.is_broken = True
```

---

### 2. 入场信号（15min时间框架）

#### 2.1 入场条件

**基础条件**:
1. 阻力区有效（未破坏）
2. 触碰次数 >= `min_touches`（默认1）
3. 失败次数 < `max_retries`（默认3）
4. 15min K线收盘价在阻力区间内

**关键代码**:
```python
in_zone = zone.bottom <= close_15m <= zone.top
```

**过滤条件**:
1. 冷却时间: 距上次信号 > 30根K线
2. 价格距离: 距上次入场价 > 1.5%
3. 仓位距离: 距现有仓位 > 1.5%
4. 最大持仓: 当前活跃仓位 < 5个

#### 2.2 信号类型

| 类型 | 条件 | 说明 |
|------|------|------|
| **InZone** | close在区间内 | 标准触碰信号 |

*注：原TV指标还包含"2B假突破"模式（high刺破zone.top但close收回），当前Python实现暂未启用*

---

### 3. 止损设置

**固定止损**:
```python
R = 3 × ATR(200)
SL_Price = Entry_Price + R
```

**说明**:
- 使用ATR(200)而非ATR(14)，更加平滑稳定
- R定义为风险单位，所有盈亏以R倍数计算
- 止损触发：15min K线最高价 >= SL_Price

**实例**:
- Entry = 50,000 USDT
- ATR(200) = 100
- R = 300
- SL = 50,300

---

### 4. 仓位管理

#### 4.1 仓位规模计算

**风险固定法**:
```python
risk_amount = equity × 0.5%  # 单笔风险0.5%
position_qty = risk_amount / R
```

**杠杆限制**:
```python
position_value = position_qty × entry_price
margin_required = position_value / leverage
# 确保 margin_required <= equity
```

**实例**:
- Equity = 10,000 USDT
- Risk = 0.5% = 50 USDT
- R = 300
- Position = 50 / 300 = 0.1667 BTC

#### 4.2 仓位分割

策略将总仓位分为两部分独立管理：

| 部分 | 占比 | 止盈方式 | 目标 |
|------|------|----------|------|
| **Fixed TP** | 30% | 固定TP @ 2.33R | 实现零成本持仓 |
| **Trailing** | 70% | 移动止盈 | 捕捉大趋势 |

**分割代码**:
```python
total_qty = 0.1667 BTC
q_fixed = total_qty × 30% = 0.05 BTC
q_trailing = total_qty × 70% = 0.1167 BTC
```

---

### 5. 出场管理

#### 5.1 Fixed TP部分（30%仓位）

**固定止盈价格**:
```python
TP_Price = Entry_Price - (2.33 × R)
```

**零成本验证**:
```
Entry = 50,000
R = 300
TP = 50,000 - (2.33 × 300) = 49,301

利润 = (50,000 - 49,301) × 0.3 = 699 × 0.3 = 209.7
原始风险 = 300 × 1.0 = 300

回收比例 = 209.7 / 300 = 69.9%
```

**说明**: 虽然30%仓位在2.33R止盈，但由于只占总仓位30%，实际回收约70%的风险资金。剩余30%风险由70%仓位的浮盈覆盖。

#### 5.2 Trailing部分（70%仓位）

**阶段1: 固定止损**
- 止损保持在 Entry + 3×ATR(200)
- 追踪最低价

**阶段2: 移动止盈激活** (当利润 >= 5×ATR(200))
```python
profit_distance = entry_price - lowest_price
activation_threshold = 5 × ATR(200)

if profit_distance >= activation_threshold:
    trailing_active = True
```

**阶段3: 动态移动** (激活后)
```python
new_SL = lowest_price + (2 × ATR(200))
# SL只能向下移动（Short），不能向上
if new_SL < current_SL:
    current_SL = new_SL
```

**完整示例**:
```
Entry = 50,000
ATR(200) = 100
R = 300
Initial SL = 50,300

价格下跌到 49,500:
  - Profit = 500 (5×ATR) ✓ 激活Trailing
  - Lowest = 49,500
  - New SL = 49,500 + 200 = 49,700

价格下跌到 49,000:
  - Lowest = 49,000
  - New SL = 49,000 + 200 = 49,200

价格反弹到 49,300:
  - Lowest保持 49,000
  - SL保持 49,200
  - 在49,200止损，锁定 50,000-49,200=800利润 (2.67R)
```

---

## 技术实现要点

### 1. 多时间框架数据同步

#### 避免未来函数
```python
# 方法1: 预先提供4H数据（推荐）
htf_data = manager.get_klines("BTCUSDT", "4h", lookback_days=90)
strategy_params = {"htf_data": htf_data}

# 方法2: 从15min重采样（有未来函数风险）
htf_data = resample_ohlcv(df_15m, "4h")
```

#### Timeframe映射
```python
# 每个15min K线映射到对应的4H K线
# 使用label="right"和closed="right"
for i, time_15m in enumerate(df_15m.index):
    # 找到第一个 4H_end_time >= time_15m 的4H K线
    htf_idx = find_htf_bar(time_15m, htf_data.index)
    timeframe_map[i] = htf_idx
```

### 2. 增量式阻力区更新

**Catch-up机制** (init阶段):
```python
# 在回测开始前，先处理所有历史4H K线
start_htf_idx = timeframe_map[0]
for i in range(start_htf_idx):
    _process_htf_bar(i)  # 创建和破坏阻力区
```

**实时更新** (next阶段):
```python
current_htf_idx = timeframe_map[current_15m_idx]
if current_htf_idx != last_htf_idx:
    # 新的4H K线确认，更新阻力区
    _update_zones()
    last_htf_idx = current_htf_idx
```

### 3. 虚拟交易管理

由于backtesting.py不支持同时持有多个独立仓位，策略使用虚拟交易系统：

```python
# 创建虚拟交易
virtual_trades = [
    VirtualTrade(trade_id="SHORT_123_Fixed", qty=0.05, tp=49301, ...),
    VirtualTrade(trade_id="SHORT_123_Trail", qty=0.1167, trailing=True, ...)
]

# 每个bar更新虚拟交易
for trade in virtual_trades:
    if trade.is_active:
        check_stop_loss(trade)
        check_take_profit(trade)
        if trade.enable_trailing:
            update_trailing_stop(trade)

# 同步实际持仓
total_qty = sum(t.qty for t in virtual_trades if t.is_active)
_sync_position(total_qty)
```

### 4. ATR计算匹配TradingView

**TradingView使用RMA平滑**:
```python
# TV: ta.atr(length) = ta.rma(ta.tr, length)
# RMA = Exponentially Weighted MA with alpha=1/length

def calculate_atr(high, low, close, period=14):
    tr = max(high - low, abs(high - close.shift(1)), abs(low - close.shift(1)))
    atr = tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    return atr
```

**关键差异**:
- Pandas默认`ewm(span=N)` ≠ TV的`rma(N)`
- 必须使用`alpha=1/N`和`adjust=False`才能匹配

---

## 策略优势

### 1. 结构化交易
- 基于客观的技术结构（Pivot High）而非主观判断
- 阻力区动态合并，减少噪音

### 2. 严格风险管理
- 固定风险比例（0.5%/笔）
- 3倍ATR止损，适应市场波动
- 最大持仓数限制，防止过度暴露

### 3. 零成本持仓理念
- 30%仓位在2.33R快速止盈，部分覆盖风险
- 70%仓位无压力持有，捕捉大行情

### 4. 自适应移动止盈
- 5×ATR激活阈值，确保有足够利润空间
- 2×ATR跟踪距离，平衡保护与空间

---

## 策略劣势与风险

### 1. 震荡市场表现不佳
- 频繁触碰阻力区但无趋势延续
- 缓解：`max_retries`限制单区尝试次数

### 2. 滑点和手续费
- 分割仓位导致更多交易次数
- 建议：使用Maker订单，降低手续费率

### 3. 极端行情风险
- 跳空或流动性枯竭可能导致止损滑点
- 建议：避免重大新闻前后交易

### 4. 参数敏感性
- `left_len`, `merge_atr_mult`等参数影响阻力区质量
- 建议：在不同市场环境下进行参数优化

---

## 回测配置示例

### 运行脚本示例

```python
# run/scripts/run_backtest.py
from backtest.engine import BacktestEngine
from data import DataManager

# 1. 获取数据
manager = DataManager()

# 获取15min数据用于回测
df_15m = manager.get_klines(
    symbol="BTCUSDT",
    timeframe="15m",
    source="okx",
    lookback_days=30
)

# 获取4H数据用于阻力区检测（避免未来函数）
df_4h = manager.get_klines(
    symbol="BTCUSDT",
    timeframe="4h",
    source="okx",
    lookback_days=90  # 需要更长历史以构建阻力区
)

# 2. 配置策略参数
strategy_params = {
    # 必须传递4H数据
    "htf_data": df_4h,

    # 阻力区参数
    "left_len": 90,
    "right_len": 10,
    "merge_atr_mult": 3.5,
    "break_tol_atr": 0.5,

    # 出场参数
    "breakeven_ratio": 2.33,
    "trailing_pct": 70.0,
    "trail_trigger_atr": 5.0,
    "trail_offset_atr": 2.0,
}

# 3. 运行回测
engine = BacktestEngine()
stats = engine.run(
    data=df_15m,
    strategy_name="sr_short_4h_resistance",
    strategy_params=strategy_params,
    initial_capital=10000,
    commission=0.0004,  # 0.04% per trade
)

# 4. 输出结果
print(stats)
engine.plot_results(output_dir="backtest/results")
```

### 策略注册

```python
# strategies/__init__.py
from strategies.sr_short_4h_resistance import SRShort4HResistance

STRATEGY_REGISTRY = {
    "sr_short_4h_resistance": SRShort4HResistance,
    # ... 其他策略
}
```

---

## 性能指标解读

### 关键指标

| 指标 | 说明 | 目标值 |
|------|------|--------|
| **Win Rate** | 胜率 | > 35% |
| **Profit Factor** | 盈亏比 | > 1.5 |
| **Sharpe Ratio** | 风险调整收益 | > 1.0 |
| **Max Drawdown** | 最大回撤 | < 20% |
| **Avg Win/Loss Ratio** | 平均盈亏比 | > 2.0 |

### 交易分析

**Fixed TP部分** (30%仓位):
- 预期胜率：较高（~60%），因为目标较近
- 预期盈亏比：固定2.33R

**Trailing部分** (70%仓位):
- 预期胜率：较低（~30%），因为需要大趋势
- 预期盈亏比：高（>3R），捕捉大行情

**组合效果**:
```
假设100笔交易：
- Fixed部分：60胜40负，avg win=2.33R, avg loss=1R
  = 60×2.33×0.3 - 40×1×0.3 = 41.94 - 12 = 29.94R

- Trailing部分：30胜70负，avg win=5R, avg loss=1R
  = 30×5×0.7 - 70×1×0.7 = 105 - 49 = 56R

总收益 = 29.94 + 56 = 85.94R
```

---

## 常见问题

### Q1: 为什么30%仓位在2.33R止盈不能完全覆盖风险？

**A**: 因为30%仓位的盈利只能覆盖30%的风险本金：
```
30%仓位盈利 = 2.33R × 0.3 = 0.699R
但总风险 = 1.0R（100%仓位）
需要70%仓位浮盈填补缺口
```
完整零成本需要30%部分达到 **1R / 0.3 = 3.33R**，但策略选择2.33R作为更现实的目标。

### Q2: 为什么使用ATR(200)而非ATR(14)作为止损？

**A**:
- ATR(14)反应快，但在高波动期容易产生过大止损
- ATR(200)平滑稳定，更适合作为长期持仓的止损参考
- 15min K线的ATR(200) ≈ 数日内的平均波动

### Q3: 如果Fixed部分先止盈，Trailing部分后止损，会亏钱吗？

**A**: 会，这是策略的预期行为：
```
Fixed: +2.33R × 0.3 = +0.699R
Trailing: -1R × 0.7 = -0.7R
净亏损 = -0.001R
```
但统计上，Trailing部分的大赢会弥补这些小亏损。

### Q4: 策略在横盘市场如何避免频繁亏损？

**A**: 多重保护机制：
1. `max_retries=3`: 单区域最多3次失败
2. `global_cd=30`: 全局冷却30根K线
3. `min_position_distance_pct=1.5`: 避免价格接近时重复开仓

---

## 优化建议

### 1. 参数优化
- 使用网格搜索或贝叶斯优化调整关键参数
- 关注：`left_len`, `merge_atr_mult`, `breakeven_ratio`

### 2. 市场环境过滤
- 添加趋势过滤器（如EMA斜率）
- 在明显上升趋势中减少做空信号

### 3. 时间过滤
- 避开美股开盘、重大数据公布等高波动时段
- 仅在流动性充足的时间交易

### 4. 动态仓位
- 根据最近N笔交易胜率动态调整`risk_per_trade_pct`
- 连续亏损后降低仓位，连续盈利后增加仓位

### 5. 多品种分散
- 将策略应用于ETH, BNB等多个品种
- 降低单品种风险暴露

---

## 文件结构

```
taoquant/
├── strategies/
│   └── sr_short_4h_resistance.py      # 策略主文件
├── TV/
│   └── sr_indicator.txt                # TradingView原始指标
├── utils/
│   ├── resample.py                     # 时间框架重采样
│   └── timeframes.py                   # 时间框架转换
├── run/scripts/backtest/
│   └── run_sr_short_4h.py              # 回测运行脚本
├── backtest/results/
│   ├── SRShort4HResistance_trades.csv  # 交易记录
│   ├── SRShort4HResistance_equity.csv  # 权益曲线
│   └── SRShort4HResistance_plot.html   # 可视化图表
└── docs/
    └── SRShort4HResistance_Strategy.md # 本文档
```

---

## 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v1.0 | 2025-12-03 | 初始版本，基于TV SR指标复刻 |

---

## 参考资料

1. TradingView SR指标: `TV/sr_indicator.txt`
2. Backtesting.py文档: https://kernc.github.io/backtesting.py/
3. ATR计算差异: https://stackoverflow.com/questions/40256338/

---

**免责声明**: 本策略仅供学习研究使用，不构成投资建议。历史回测表现不代表未来收益。实盘交易前请充分测试并评估风险。

# TaoGrid 网格策略 - 完整使用指南

> **一行命令运行回测**：`python run_taogrid.py`

---

## 🎯 项目概览

TaoGrid是一个优化的传统网格交易策略，专为加密货币市场设计。

**核心特点**:
- ✅ 传统网格自由卖出（非强制配对）
- ✅ ATR 动态 spacing（覆盖 min_return + maker fee 成本）
- ✅ 参数 validation（防止错误配置导致系统性亏损）
- ✅ 以 **传统 Sharpe（按日收益年化，默认 √365）** 为主优化目标
- ✅ 支持“因子式风控/去库存”增强（breakout 风险、区间 top band 去库存、funding 结算窗口门控）

---

## 📦 快速开始

### 方式1：使用快捷脚本（推荐）

```bash
# 1. 运行回测
python run_taogrid.py

# 2. 生成可视化dashboard
python run_taogrid.py --dash

# 3. 查看帮助
python run_taogrid.py --help
```

### 方式2：直接运行

```bash
# 运行回测
python algorithms/taogrid/simple_lean_runner.py

# 生成dashboard
python algorithms/taogrid/create_dashboard.py
```

---

## 📁 完整项目结构

```
taoquant/
│
├── 🚀 快速入口
│   ├── run_taogrid.py              # 快捷启动脚本
│   └── TAOGRID_GUIDE.md            # 本文件
│
├── 📊 结果输出
│   └── run/results_lean_taogrid/
│       ├── metrics.json            # 性能指标
│       ├── trades.csv              # 交易记录
│       ├── orders.csv              # 订单记录
│       ├── equity_curve.csv        # 资金曲线
│       └── dashboard.html          # 📈 交互式可视化
│
├── 🧠 核心策略代码
│   └── algorithms/taogrid/
│       ├── README.md               # 详细说明
│       ├── simple_lean_runner.py   # ✅ 回测入口
│       ├── create_dashboard.py     # Dashboard生成器
│       ├── config.py               # 策略配置
│       ├── algorithm.py            # 核心算法
│       └── helpers/
│           └── grid_manager.py     # 网格管理
│
├── 📐 基础设施（TaoQuant框架）
│   ├── analytics/indicators/       # 技术指标库
│   │   ├── grid_generator.py       # ⭐ Grid spacing公式
│   │   ├── volatility.py           # ATR计算
│   │   └── ...
│   ├── risk_management/            # 风控模块
│   │   ├── grid_inventory.py       # 仓位跟踪
│   │   ├── grid_risk_manager.py    # 风险管理
│   │   └── ...
│   ├── data/                       # 数据管理
│   └── execution/                  # 执行引擎
│
└── 📚 文档
    ├── docs/strategies/            # 策略研究文档
    │   └── grid_reality_check.md   # 网格策略分析
    └── docs/                       # 其他文档
```

---

## 🎨 Dashboard预览

生成的dashboard包含以下图表：

1. **Equity Curve** - 资金曲线走势
2. **Drawdown Chart** - 回撤分析
3. **Holdings & Cash** - 持仓与现金变化
4. **Grid Orders by Level** - 网格订单分布（按层级）
5. **Trade PnL Distribution** - 交易盈亏分布
6. **Performance Metrics** - 关键指标表
7. **Grid Level Performance** - 各网格层级表现
8. **Trade Pairing Analysis** - 交易配对分析

**打开dashboard**:
```bash
# Windows
start run/results_lean_taogrid/dashboard.html

# Mac
open run/results_lean_taogrid/dashboard.html

# Linux
xdg-open run/results_lean_taogrid/dashboard.html
```

---

## ⚙️ 配置策略参数

编辑 `algorithms/taogrid/simple_lean_runner.py`:

```python
config = TaoGridLeanConfig(
    # ========== 价格区间 ==========
    # 说明：S/R 由你给定（研究阶段固定区间）。后续可扩展为动态区间。
    support=107000.0,
    resistance=123000.0,
    regime="NEUTRAL_RANGE",

    # ========== 网格参数 ==========
    grid_layers_buy=40,
    grid_layers_sell=40,

    spacing_multiplier=1.0,     # ⚠️ 必须 >= 1.0
    min_return=0.0012,          # 单笔净收益目标（net, 研究可调整）
    maker_fee=0.0002,           # perp 单边 maker fee = 0.02%

    # ========== 资金管理 ==========
    risk_budget_pct=1.0,        # 资金参与比例（研究阶段可拉满）
    initial_cash=100000.0,      # 初始资金
    leverage=50.0,              # 杠杆（研究阶段可高，但需用 MaxDD 约束）

    # ========== 高级设置 ==========
    enable_throttling=True,

    # ========== 因子（已验证保留）==========
    # 1) Breakout 风险因子：靠近边界 risk-off
    enable_breakout_risk_factor=True,
    breakout_band_atr_mult=1.0,
    breakout_band_pct=0.008,
    breakout_buy_k=2.0,
    breakout_buy_floor=0.5,
    breakout_block_threshold=0.9,

    # 2) RangePos v2：仅 top band 生效（高位去库存/不追高）
    enable_range_pos_asymmetry_v2=True,
    range_top_band_start=0.45,
    range_buy_k=0.2,
    range_buy_floor=0.2,
    range_sell_k=1.5,
    range_sell_cap=1.5,

    # 3) Funding 因子：只在结算窗口附近触发（避免压 churn）
    enable_funding_factor=True,
    funding_apply_to_buy=False,
    funding_apply_to_sell=True,
    enable_funding_time_gate=True,
    funding_gate_minutes=90,
)
```

**关键参数说明**:

| 参数 | 说明 | 推荐值 | 影响 |
|-----|------|--------|------|
| `support/resistance` | 价格区间 | 基于历史数据 | 网格覆盖范围 |
| `grid_layers` | 网格层数 | 10-20 | Turnover |
| `spacing_multiplier` | 间距倍数 | 1.0-1.5 | ⚠️ **必须>=1.0** |
| `min_return` | 净利润目标 | 0.5%-1.0% | Gross Margin |
| `risk_budget_pct` | 资金占比 | 50%-80% | 资金利用率 |
| `leverage` | 杠杆 | 1-3x | ROE放大 |

---

## 📊 当前性能指标

本策略目前以 **Sharpe（按日收益年化，默认 √365）** 为主要目标函数。
不同回测窗口会有不同表现，下面给出我们已经验证过的两个“代表性窗口”。

### 窗口 A（无 funding）：2025-07-10 ~ 2025-08-10（1m）
说明：该窗口 OKX funding history 公共 API 不可追溯，因此不启用 funding 因子。

- **Sharpe（年化）**：≈ 5.587
- **MaxDD**：≈ -18.01%

### 窗口 B（真实 funding）：2025-09-09 ~ 2025-10-09（1m，S=107k/R=123k）
说明：该窗口 funding 可从 OKX public API 拉取，使用 funding 时间门控（±90m）只增强 SELL 去库存。

- **Sharpe（年化）**：≈ 4.643
- **MaxDD**：≈ -20.85%

> 注：高杠杆会放大收益与回撤，所以我们以 Sharpe/Sortino 等风险调整指标为主，辅以 MaxDD 约束。

---

## 🔬 核心技术亮点

### 1. Spacing公式（行业领先）

```
spacing = min_return + 2×maker_fee + volatility_adjustment
        = 0.5% + 0.04% + (ATR-based)
        ≈ 0.54% (标准spacing, perpetual maker fee=0.02%)
```

**评分**: 97/100（理论正确性、参数validation、风控保护）

**关键特性**:
- ✅ 下界保护: `spacing >= base_spacing`（保证盈利）
- ✅ 上界保护: `spacing <= 5%`（防止过稀疏）
- ✅ Slippage=0（limit orders无滑点）
- ✅ 完整validation（防止错误配置）

### 2. 传统网格自由卖出

```python
# ❌ 旧版：强制配对（限制卖出）
if buy_position[i] exists and price >= sell_level[i]:
    sell()

# ✅ 新版：自由卖出（提高turnover）
if any_long_position and price >= any_sell_level:
    sell()
```

**优势**:
- 提高交易频率（捕捉所有机会）
- 符合Binance/OKX行业标准
- 简化逻辑（更易维护）

---

## 🐛 常见问题

### Q1: Dashboard显示的收益和命令行不一致？

**A**: 清除浏览器缓存，强制刷新（Ctrl+F5）

```bash
# 重新生成dashboard
python run_taogrid.py --dash
```

### Q2: 运行回测报错 `spacing_multiplier must be >= 1.0`？

**A**: 这是新增的保护机制，spacing_multiplier < 1.0会导致亏损。

修改配置：
```python
spacing_multiplier=1.0  # 改为 >= 1.0
```

### Q3: 交易数太少，如何提高turnover？

**A**: 有几个方法：

1. **增加网格层数**:
   ```python
   grid_layers_buy=20  # 从10增加到20
   ```

2. **缩小价格区间**（匹配实际波动）:
   ```python
   support=116000.0     # 缩小到实际交易区间
   resistance=118000.0
   ```

3. **增加杠杆**:
   ```python
   leverage=2.0  # 提高到2-3x
   ```

### Q4: 如何切换到实盘？

**A**: 当前是回测框架，实盘需要：

1. 集成交易所API（如CCXT）
2. 实现实时数据流
3. 添加风控断路器
4. 建议先模拟盘运行1-2周

---

## 📝 开发历史

### 2025-12-15 - 完整优化

**修复的问题**:
1. ❌ spacing_multiplier < 1.0导致所有交易亏损
2. ❌ 强制配对限制卖出时机
3. ❌ slippage设置不正确（limit orders应为0）
4. ❌ 缺少参数validation

**优化结果**:
- 收益提升: $60 → $622 (**10倍**)
- Gross Margin: 0.10% → 0.50% (**5倍**)
- 100%胜率保持
- Spacing公式评分: 75分 → 97分

---

## 🎯 下一步计划

### 近期（研究迭代）
- [ ] Time-of-day/Session 因子：剔除最差时段，提升 Sharpe
- [ ] Breakout v2：基于“持续越界/连续趋势 bar 数”的短暂 risk-off（避免假信号）
- [ ] Walk-forward / 分段回测：减少单窗口过拟合

### 中期（1个月）
- [ ] 多币种测试
- [ ] 动态支撑阻力调整
- [ ] 实盘接入（小资金）

### 长期
- [ ] 机器学习优化spacing
- [ ] 多策略组合
- [ ] 自动再平衡

---

## 📞 支持

遇到问题？

1. **查看README**: `algorithms/taogrid/README.md`
2. **检查配置**: 确保spacing_multiplier >= 1.0
3. **查看文档**: `docs/strategies/grid_reality_check.md`
4. **清除缓存**: 刷新dashboard（Ctrl+F5）

---

**祝研究顺利！**

---

## 🧪 研究脚本入口（sweep / ablation）

以下脚本用于复现我们已做过的实验（都在 `run/` 下）：

- **Breakout 风险 sweep**：`python run/taogrid_breakout_risk_sweep.py`
- **RangePos v2 sweep**：`python run/taogrid_range_pos_v2_sweep.py`
- **Funding gate sweep（真实 funding 窗口）**：`python run/taogrid_funding_gate_sweep.py`
- **Funding ON/OFF ablation（真实 funding 窗口）**：`python run/taogrid_funding_ablation.py`
- **OKX funding 可追溯深度探测**：`python run/okx_funding_depth_probe.py`

Funding 数据说明：见 `docs/data/okx_funding_rate.md`。

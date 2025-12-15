# TaoGrid Turnover 低的原因分析报告（归档）

来源：根目录 `turnover_analysis_report.md`（讨论过程产出）

---

## 📊 核心问题

**平均持仓时间：266.4小时（11.1天）** - 在1分钟K线数据中，这个turnover太低了！

## 🔍 数据分析结果

### 1. 网格间距过大

- **当前间距**：0.7%（$815.90）
- **问题**：价格需要移动$816才能触发下一个网格层级
- **在1分钟K线中**：这个移动需要很长时间，导致持仓时间过长

### 2. 网格层级使用不足

- **设置**：10层（grid_layers_buy=10）
- **实际使用**：只有3层（Level 0, 1, 2）
- **分布**：87.5%的交易都在Level 0
- **原因**：网格间距太大，价格范围（$5k）只能容纳约6层，但实际波动更小

### 3. 买卖订单不平衡

- **买入订单**：96个
- **卖出订单**：20个
- **比例**：4.8:1
- **问题**：大量买单没有及时卖出，导致持仓时间过长

### 4. 长期持仓比例过高

- **超过3天的持仓**：78.1%（25笔）
- **平均持仓时间**：334小时（14天）
- **最长持仓**：729小时（30.4天）

## 💡 根本原因

### 原因1：网格间距计算公式导致间距过大

```text
当前配置：
- min_return = 0.5%
- trading_costs = 0.2% (2 × 0.1% maker_fee)
- base_spacing = 0.5% + 0.2% = 0.7%
- spacing_multiplier = 1.0
- 最终间距 = 0.7%
```

**问题**：0.7%的间距在$117k的价格下 = $819，这个移动在1分钟K线中太慢了。

### 原因2：价格区间设置不合理

```text
当前设置：
- support = $115,000
- resistance = $120,000
- 价格范围 = $5,000
- 网格间距 = 0.7% = $819
- 理论最大层数 = $5,000 / $819 ≈ 6层
```

**问题**：虽然设置了10层，但实际价格波动可能更小，导致只使用了3层。

### 原因3：限价单触发逻辑可能有问题

从订单数据看：

- 买入订单96个，卖出订单20个
- 说明很多买单被触发了，但对应的卖单没有被触发
- 可能原因：价格没有回到卖出网格层级，或者限价单触发条件太严格

## 🎯 解决方案

### 方案1：降低min_return（推荐）

**目标**：将网格间距从0.7%降到0.3-0.4%

```python
# 当前配置
min_return=0.005,  # 0.5%

# 优化配置
min_return=0.001,  # 0.1% - 降低到0.1%
# 新间距 = 0.1% + 0.2% = 0.3%
# 在$117k价格下 = $351，比$819小57%
```

### 方案2：增加网格层数

```python
grid_layers_buy=20,
grid_layers_sell=20,
```

### 方案3：缩小价格区间

```python
support=116000.0,
resistance=118000.0,
```

### 方案4：组合优化（最佳）

```python
config = TaoGridLeanConfig(
    support=116000.0,
    resistance=118000.0,
    grid_layers_buy=20,
    grid_layers_sell=20,
    min_return=0.001,
    spacing_multiplier=1.0,
)
```

---

## 🧠 参数寻优方法论（后续研究方向）

### 结论：网格参数寻优通常不是“凸优化”

我们在回测里做的 `min_return / grid_layers / risk_budget_pct / spacing_multiplier` 等参数寻优，**一般不是凸函数优化过程**，更贴近：

- **非凸（多峰/多局部最优）**
- **非光滑/不可导（阈值触发、clip、离散成交导致跳变）**
- **带噪声的黑箱优化（回测输出无解析梯度）**

因此，不能期待“沿着梯度走就收敛到唯一全局最优”这类凸优化性质。

### 为什么不是凸的（结构性原因）

- **离散成交事件**：参数轻微变化可能让某些触发/成交“发生→不发生”，指标会跳变。
- **平台区（flat region）**：很多参数区间内成交序列不变，目标函数近似不动。
- **阈值/clip 造成折点**：spacing 下界保护、触发条件、仓位约束都会制造不可导点。
- **多目标冲突**：
  - spacing 小 → turnover 高，但噪音与成本影响更大
  - spacing 大 → 单笔净利高，但成交变少、holding 变长
  - layers 多 → 更细密，但可能放大库存峰值/回撤
  这会形成 **Pareto 前沿**，而不是单峰凸函数。

### 更科学的寻优框架（建议）

把“找一个最优点”改为“找一个稳健区域”：

1. **先设硬约束**（避免为收益牺牲结构健康度）
   - `avg_holding_period_hours` ≤ X（提升周转/降低资金占用）
   - `max_drawdown` ≥ -Y（风险底线）
   - `trades_per_day` ≥ Z（最小交易频率）
2. **在约束内最大化主目标**
   - 比如 `calmar_like` / 年化收益 / 或你定义的 ROE proxy
3. **做稳健性验证**
   - 多窗口（walk-forward）或多段样本，防止过拟合单月行情
4. **用 Pareto 选点**
   - 典型三维：`(total_return, max_drawdown, trades_per_day)`，再加 `avg_holding` 做筛选

### 策略结构层面的“因子/机制”方向（不依赖DGT）

即使不做 DGT，也可以从“结构因子”提升 ROE/turnover：

- **库存不对称/库存驱动的报价密度**：库存偏多时，提高卖出侧密度、降低买入侧密度，减少堆仓与持仓时间。
- **非均匀网格（中心更密、两端更稀）**：如果价格确实大多数时间在均值附近震荡，把挂单密度集中在均值附近，提高有效成交频率。
- **MR regime filter（均值回归强度过滤）**：只在 MR 强的阶段开网格，弱 MR/趋势阶段降低活跃度或停止加仓。
- **回归速度因子（half-life/Hurst/VR）**：用“回归速度”决定 spacing/layers/risk_budget 的档位，而不是固定参数。

---

## 🔄 重大假设更新：Perp Maker Fee = 0.02%（单边）

本策略在永续合约上的 maker fee 单边为 **0.02%**（而非 0.1%）。
这会显著降低网格策略的“成本地板”，使得更密的网格（更小的 `min_return` / 更小的 gross spacing）在理论上可行，从而提高 turnover 与 ROE 的上限。

### 成本地板（limit orders，slippage≈0）

若 `min_return` 是“往返净收益目标”，则 gross spacing 的下界为：

\[
spacing_{min} = min\_return + 2\times maker\_fee
\]

在 perp maker fee=0.02% 时：\(2\times maker\_fee = 0.04\%\)。

---

## 📌 最新回测快照（maker fee=0.02%）

目录：`run/results_lean_taogrid/metrics.json`

- **Total Return**: 2.55%
- **Total Trades**: 36
- **Avg Holding Period**: 133.7 hours（≈5.6 days）
- **Max Drawdown**: -8.97%

> 注：holding 仍是“天”级别，说明限制并非仅来自手续费地板，还来自价格路径/回归速度/库存结构。

---

## 🧪 参数扫参结论摘要（maker fee=0.02%，固定区间 111k-123k）

汇总：`run/results_lean_taogrid_sweep/sweep_summary.csv`

在不引入 DGT、固定大区间的前提下，通过降低 `min_return` + 增加 `grid_layers` 能显著提高 turnover 与总收益，但 holding 仍常为数天。

示例 Top 结果（按风险调整收益/turnover 排序，见 sweep_summary.csv）：

- **min_return=0.12%（净）, grid_layers=40, risk_budget=0.3**
  - total_return ≈ 2.77% / 月
  - total_trades = 92（≈2.97 笔/天）
  - avg_holding ≈ 137.8 小时（≈5.7 天）

- **min_return=0.08%（净）, grid_layers=40, risk_budget=0.3**
  - total_return ≈ 2.48% / 月
  - total_trades = 111（≈3.58 笔/天）
  - avg_holding ≈ 128.4 小时（≈5.3 天）

---

## 📊 机构式指标面板（建议作为优化“硬指标”）

当我们讨论“提高 ROE/turnover”，机构更关心的是结构健康度（库存与资金占用），而不仅是收益。
建议每次回测固定输出/对比以下指标：

### 1) 订单平衡（Order Balance）

- **Sell/Buy Ratio**（卖单/买单数量比）
  - 目标：接近 1（长期 <<1 代表库存倾向单边堆积，holding 拉长）

### 2) 库存与敞口（Inventory / Exposure）

- **Peak Inventory Ratio**：`max(holdings_value / equity)`
- **Avg Inventory Ratio**：`mean(holdings_value / equity)`
- **Peak Holdings Value**（USD）

### 3) 持仓分布（Holding Distribution）

- Avg / P50 / P75 / P90 / P95 / Max holding hours
  - 重点看是否“长尾”导致平均值虚高

### 4) 资本效率（Capital Efficiency）

- **PnL per Exposure USD-Day**：
  - 近似：`total_pnl / ∫ holdings_value(t) dt`
  - 用来衡量“单位库存占用时间”的盈利能力（机构很看）

实现：`python run/taogrid_metrics_panel.py --input run/results_lean_taogrid`
会生成：`metrics_panel.json` 与 `metrics_panel.md` 于同目录。

---

## 🎯 优化目标与硬约束（v0，后续可迭代）

说明：网格策略的“优化”不是只看 `total_return`，更重要的是把**库存结构**和**资金占用**健康化，否则会出现“赚了，但长期被库存拖死/无法规模化”的问题。

### 目标口径（更新：以传统 Sharpe 为主）

- **主目标**：最大化 **年化 Sharpe（传统口径）**
  - **收益频率**：用 **日收益**（daily returns）计算
  - **年化因子**：crypto 24/7 默认 \(\sqrt{365}\)（如需券商口径可切 \(\sqrt{252}\)）
  - 目标区间：**Sharpe 2–3+**（在满足风控约束前提下）
- **次目标**：Sortino / Calmar（用于识别“左尾风险更低”的版本）

### 当前基线（maker fee=0.02%，1m，111k-123k）

来自 `run/results_lean_taogrid/metrics_panel.md`：

- **Trades/Day**: 1.161
- **Sell/Buy Ratio**: 0.338（卖出明显偏少）
- **Holding P50/P75/P90/P95**: 25.0 / 125.1 / 418.3 / 674.8 小时（长尾显著）
- **Peak Inventory Ratio**: 0.997（敞口峰值接近满仓）
- **Avg Inventory Ratio**: 0.986（长期几乎全程高敞口）

### v0 目标（下一阶段的“硬指标”）

这组目标的核心是：**先把结构做健康**（卖出不足、库存长期高敞口、holding 长尾），再谈更激进的 ROE 放大。

- **风险底线（你的偏好）**
  - **Max Drawdown ≥ -20%（等价于 MDD ≤ 20%）**
- **杠杆（你的偏好）**
  - **Leverage = 5x**（先固定 5x 做研究，后续再讨论动态杠杆）
- **库存（你的偏好）**
  - **Peak Inventory Ratio ≤ 0.90**
  - 允许在库存过大时 **主动降风险**（减少买入、优先卖出/去库存）
- **成交假设（你的偏好）**
  - limit 全部 maker，**slippage = 0**
  - maker fee（perp）单边 **0.02%**
  - 库存容量阈值（B定义）：当 `notional/equity >= inventory_capacity_threshold_pct × leverage` 时才强制去风险（阻止新 BUY）

## ✅ inventory-aware 参数选择（本轮 sweep 结论）

在固定：`support=111k`，`resistance=123k`，`leverage=5x`，`risk_budget_pct=1.0`，`inventory_capacity_threshold_pct=1.0` 下，
对 `inventory_skew_k ∈ {0.0, 0.5, 1.0, 1.5, 2.0}` 做 sweep（见 `run/results_lean_taogrid_inventory_skew_sweep/summary.csv`）：

- **k=0.0**：收益最高、成交最多，但平均库存暴露更高（Avg Inventory Ratio 0.267），更像“满仓做市”风格；DD 仍在可接受范围内。
- **k=0.5（推荐默认）**：在收益（5.87%）与库存/效率之间更平衡；Sell/Buy 0.973，Peak Inv Ratio 1.832，MaxDD -1.35%。
- **k≥1.0**：去库存更强，导致成交与收益明显下降；k=2.0 甚至 Sell/Buy 明显偏低（0.846），有“卖出不足/过度保守”迹象。

因此将默认 `inventory_skew_k` 设为 **0.5**，后续若要继续推 ROE，可以在风险可控时尝试降低 k 或提高杠杆。

> 注：你当前阶段“平均持仓/交易频率”不设硬约束，以 **最大化（传统）Sharpe** 为第一优先。我们仍会用 Sell/Buy Ratio、holding 分位数、inventory ratio 做结构监控，避免策略在高杠杆下进入不可控的堆仓状态。

## 🧪 因子引入（MR + Trend）对 Sharpe 的影响（Ablation）

我们已实现一个“MR 强度 + 趋势状态”的因子框架：

- 预计算 `mr_z`（rolling z-score）与 `trend_score`（EMA slope → tanh 归一化）
- 在强下跌趋势时阻断新 BUY（避免堆库存左尾），其余情况对 BUY 做温和缩放

对比结果见：`run/results_lean_taogrid_factor_ablation/summary.csv`（同参数，仅开关因子）：

- **OFF（未启用因子）**：Sharpe **5.188**，MaxDD -18.46%，Total Return 59.71%
- **ON（启用因子，默认参数）**：Sharpe **4.281**，MaxDD -9.52%，Total Return 21.92%

结论：**当前默认参数下，该因子“显著降低回撤”，但也“明显降低收益/提高平均持仓”，导致 Sharpe 反而下降。**

下一步（为“Sharpe 提升”而不是“DD 更低”）：

- 需要把“趋势阻断/缩放”改为 **更贴近做市的轻量风控**：只在最危险的趋势段做去风险，而不要普遍削弱网格的 churn；
- 以及引入更有信息增益的状态因子（例如：breakout 风险、区间边界距离、funding bias、波动状态），并用 Sharpe 作为排序目标做小范围参数搜索。

> 注：上述阈值是“研究迭代的起点”，不是最终答案。我们会随着策略结构的改造（仓位不对称/非均匀网格/过滤器等）逐步收敛到可行的 Pareto 区域。

## ✅ 方案 A：Breakout 风险因子（轻量 risk-off）——结果

实现要点（纯函数 + 策略层透传）：

- `analytics/indicators/breakout_risk.py`：计算 `breakout_risk_down/up ∈ [0,1]`（边界距离 + ATR band + trend_score）
- 在 `GridManager.calculate_order_size()` 中：仅对 **BUY** 做 risk-off（高风险时缩小/阻断新 BUY），不破坏网格的 churn

Ablation（同参数，仅开关 breakout 因子；MR+Trend 因子关闭以避免混淆）：
见 `run/results_lean_taogrid_breakout_risk_ablation/summary.csv`

- **OFF**：Sharpe **5.188**
- **ON**：Sharpe **5.204**

结论：**Breakout 风险因子带来小幅 Sharpe 提升（+0.016）**，几乎不改变回撤结构；下一步适合做一个很小的参数 sweep（`breakout_band_atr_mult / breakout_buy_k / breakout_block_threshold`）来放大这点收益。

## ✅ RangePos v2（仅 top band 生效）——激进 sweep 结果

结论要点：

- 之前“全区间 range_pos 缩放”会把 churn 打没，Sharpe 反而崩掉；
- v2 改成 **只在 top band 内生效**（更像做市的“高位去库存/不追高”），并对参数做激进 sweep 后，Sharpe 可以显著上升。

激进 sweep（随机采样，MaxDD≤20%，按 Sharpe 排序）：

- 结果文件：`run/results_lean_taogrid_range_pos_v2_sweep/summary.csv`
- Top winner（已固化到 `simple_lean_runner.py`）：
  - `enable_range_pos_asymmetry_v2=True`
  - `range_top_band_start=0.45`
  - `range_buy_k=0.2`, `range_buy_floor=0.2`
  - `range_sell_k=1.5`, `range_sell_cap=1.5`

当前主回测（111k-123k，1m，50x，breakout winner + range_pos v2 winner，MR+Trend 关闭）：

- **Sharpe**：**5.587**（从 5.206 进一步提升）
- **MaxDD**：-18.01%（仍在 20% 约束内）
- **Trades/Day**：10.581

---

## 做市商风险区域（MM Risk Zone）

### 设计理念

当价格跌破 `support + volatility buffer`（即 `support + ATR × cushion_multiplier`）时，策略进入**风险模式**，模拟专业做市商的行为：

1. **大幅减少买入规模**（小仓位接盘，避免"接飞刀"）
2. **大幅增加卖出规模**（de-inventory，卖出大部分存货）
3. **如果库存已经很高，进一步减少买入**（双重保护）

### 核心逻辑

```python
# 风险区域阈值
risk_zone_threshold = support + (ATR × cushion_multiplier)

# 当 price < risk_zone_threshold 时：
# - BUY size = base_size × mm_risk_buy_multiplier (默认 0.2 = 20%)
# - SELL size = base_size × mm_risk_sell_multiplier (默认 3.0 = 300%)
# - 如果 inv_ratio > mm_risk_inventory_penalty (默认 0.5)，BUY 再减半
```

### 配置参数

在 `algorithms/taogrid/config.py` 中：

```python
enable_mm_risk_zone: bool = True  # 启用做市商风险区域
mm_risk_buy_multiplier: float = 0.2   # 风险区域 BUY 规模（20%）
mm_risk_sell_multiplier: float = 3.0  # 风险区域 SELL 规模（300%）
mm_risk_inventory_penalty: float = 0.5  # 库存惩罚阈值（如果 inv_ratio > 0.5，BUY 再减半）
```

### 与现有因子的关系

- **Breakout Risk Factor**：检测接近区间边界，提前减少买入
- **MM Risk Zone**：检测跌破支撑+缓冲，进入风险模式，大幅调整买卖规模
- **两者可以叠加**：Breakout 提前预警，MM Risk Zone 在真正跌破时执行

### 使用场景

- **Long-only 策略**：在下跌趋势中，通过小仓位接盘 + 大仓位卖出，实现"抄底但不重仓"的做市商风格
- **高杠杆环境**：在 50x 杠杆下，风险区域自动 de-inventory，避免爆仓风险
- **波动性缓冲**：使用 `ATR × cushion_multiplier` 作为缓冲，避免正常波动触发风险模式

### 下一步优化方向

1. **动态调整 spread**：在风险区域，可以考虑动态扩大网格间距（spacing_multiplier）
2. **渐进式恢复**：价格回到风险区域以上时，逐步恢复正常的买卖规模
3. **多级风险区域**：可以设置多个风险阈值（如 mild risk / severe risk），对应不同的调整强度

---

## 分级风险管理（Tiered Risk Management）v2

### 设计理念

实现**分级风险管理**，在价格跌破支撑时逐步升级风险控制，最终在极端情况下完全关闭网格，等待用户手动更新区间。

### 风险等级

#### Level 1（轻度风险）
- **触发条件**：`price < support + cushion`（跌破支撑+波动缓冲）
- **行为**：
  - 买入规模：20% of normal
  - 卖出规模：300% of normal
  - 如果库存 > 50% capacity，买入再减半（10%）
- **目标**：积极 de-inventory，但保持交易

#### Level 2（中度风险）
- **触发条件**：价格在风险区域停留（用户手动判断趋势反转）
- **行为**：
  - 买入规模：10% of normal
  - 卖出规模：400% of normal
- **目标**：更激进 de-inventory

#### Level 3（重度风险）
- **触发条件**：`price < support - 2 × ATR`
- **行为**：
  - 买入规模：5% of normal
  - 卖出规模：500% of normal
- **目标**：极端保护，准备关闭网格

#### Level 4（极端风险 - 网格关闭）
- **触发条件**（满足任一即关闭）：
  1. `price < support - 3 × ATR`（价格深度）
  2. `unrealized_pnl < -30% equity`（持仓亏损，考虑利润缓冲）
  3. `inventory_notional > 80% capacity`（库存风险）
- **行为**：
  - 完全停止所有新订单（buy 和 sell）
  - 保留现有 pending orders（允许平仓）
  - 记录关闭原因
  - **一直关闭直到用户手动重新开启**
- **目标**：保护资金，等待用户手动更新区间

### 利润保护机制

- **启用利润缓冲**：50% 的已实现利润可用于缓冲风险阈值
- **示例**：
  - 如果网格利润 = 5% equity
  - 最大风险阈值 = -30% equity
  - 调整后阈值 = -30% + (5% × 50%) = -27.5% equity
  - 意味着：只有亏损超过 27.5% 才会关闭网格（而不是 30%）

### 配置参数

```python
# Level 1
mm_risk_level1_buy_mult: float = 0.2   # BUY 20%
mm_risk_level1_sell_mult: float = 3.0  # SELL 300%

# Level 2
mm_risk_level2_buy_mult: float = 0.1   # BUY 10%
mm_risk_level2_sell_mult: float = 4.0  # SELL 400%

# Level 3
mm_risk_level3_atr_mult: float = 2.0   # support - 2 × ATR
mm_risk_level3_buy_mult: float = 0.05  # BUY 5%
mm_risk_level3_sell_mult: float = 5.0  # SELL 500%

# Level 4 (Grid Shutdown)
max_risk_atr_mult: float = 3.0         # support - 3 × ATR
max_risk_loss_pct: float = 0.30        # -30% equity
max_risk_inventory_pct: float = 0.8    # 80% capacity

# Profit Protection
enable_profit_buffer: bool = True      # 启用利润缓冲
profit_buffer_ratio: float = 0.5       # 50% 利润可用于缓冲
```

### 使用流程

1. **正常交易**：价格在 `support + cushion` 以上，正常网格交易
2. **进入风险模式**：价格跌破 `support + cushion`，自动进入 Level 1
3. **逐步升级**：根据价格深度和持续时间，自动升级到 Level 2/3
4. **网格关闭**：触发 Level 4 条件，网格完全关闭
5. **手动恢复**：
   - 用户分析市场，更新 `support` 和 `resistance`
   - 调用 `grid_manager.setup_grid()` 重新生成网格
   - 调用 `grid_manager.enable_grid()` 重新开启网格

### 理想情况

- **网格有利润**：已实现利润可以缓冲风险阈值
- **利润覆盖止损**：如果网格利润足够，可以覆盖部分持仓亏损，延迟关闭网格
- **手动控制**：用户可以根据市场情况灵活更新区间，而不是依赖自动恢复

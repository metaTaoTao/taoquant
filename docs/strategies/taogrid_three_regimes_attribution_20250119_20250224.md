# TaoGrid 三种 Regime 归因简报（2025-01-19 ~ 2025-02-24）

## 一句话结论

在该窗口（S=90k / R=108k）下，**NEUTRAL_RANGE（50/50）收益最好**；**BEARISH_RANGE（30/70）更稳（更低回撤/Ulcer）但收益被压**；**BULLISH_RANGE（70/30）因库存暴露过大 + 少数大亏单拖累而亏损**。

> 重要提示：本次数据实际覆盖区间为 `2025-01-20 05:00:00 UTC ~ 2025-02-23 23:59:00 UTC`（数据源对 `2025-01-19` 的请求未覆盖到）。

---

## 核心结果（Performance）

| Regime | Total Return | Max DD | Sharpe | Sortino | Ulcer | Trades |
|---|---:|---:|---:|---:|---:|---:|
| **BULLISH (70/30)** | **-1.26%** | -14.96% | -0.08 | -0.11 | 5.82 | 170 |
| **NEUTRAL (50/50)** | **+8.18%** | -4.59% | 5.85 | 12.60 | 0.44 | 993 |
| **BEARISH (30/70)** | **+4.95%** | **-2.79%** | 5.81 | 12.36 | **0.28** | 992 |

---

## 归因（为什么你的“震荡看空应最好”在这段没发生）

### 1) 这个策略本质是“长仓网格”，BEARISH 不是做空

TaoGrid Lean 当前实现中：
- **SELL 是减持长仓**（去库存），不是开空仓。
- 因此 **BEARISH_RANGE（30/70）只是在“少买多卖（更快去库存）”**，它无法直接从下跌趋势中获取“空头收益”。

如果窗口是明显下跌趋势，BEARISH 通常会更稳（更小仓位、更小回撤），但它不会像真正的 short strategy 那样“越跌越赚”。

### 2) NEUTRAL 赢在“周转率（turnover）”，BEARISH 输在“少买导致少赚”

两者交易频率几乎相同（992 vs 993），平均持仓时间也几乎一致（~6.74h），但：
- **NEUTRAL 平均盈利单更大**：avg_win ≈ 12.50（BEARISH ≈ 7.58）
- **NEUTRAL 总收益更高**：+8.18%（BEARISH +4.95%）

直觉解释：
- 这个窗口更像“区间内可反复做 T+0 的均值回归”，NEUTRAL 更能兼顾买卖两侧的成交与利润捕捉；
- BEARISH 因为买入预算更少，等价于“库存更低”，因此在同样的反弹/回归里赚得更少——但也更稳。

### 3) BULLISH 亏损的直接原因：库存暴露显著更大 + 少数大亏单

从持仓暴露与交易分布看，BULLISH 明显不同于 NEUTRAL/BEARISH：

**持仓暴露（从 equity_curve 统计）**
- BULLISH **最大持仓**：1.94 BTC（NEUTRAL 1.63 / BEARISH 0.99）
- BULLISH **P95 持仓**：1.93 BTC（NEUTRAL 1.11 / BEARISH 0.67）
- BULLISH **平均持仓**：1.20 BTC（NEUTRAL 0.38 / BEARISH 0.23）
- BULLISH **最大持仓名义价值**：$192k（NEUTRAL $155k / BEARISH $94k）

**交易分布**
- BULLISH **交易笔数少**：170（NEUTRAL/BEARISH ~992）
- BULLISH **平均持仓时间长**：36.8h（NEUTRAL/BEARISH ~6.74h）
- BULLISH **单笔最差 PnL**：-127（NEUTRAL -154 / BEARISH -106）
- 但 BULLISH 的“结构性问题”是：**盈利单很小、亏损单很大**（metrics 里 avg_win ~6.34，avg_loss ~-67.61）。

一句话：**BULLISH 更像“少交易、重仓拿着等出场”，一旦遇到不利波动，少数大亏单就能吞掉大量小盈利**。

---

## 这段窗口的“最优决策”（按你的风险偏好：回撤 20%-30%可接受）

- **如果只选一个 regime：推荐 NEUTRAL_RANGE**  
  收益更高、回撤也很小（8.18% / -4.59%），属于“收益-风险比”最优。

- **如果你更看重极稳：BEARISH_RANGE**  
  回撤最小、Ulcer 最低（-2.79%，Ulcer 0.28），但收益会被压。

- **不建议在该窗口使用 BULLISH_RANGE**  
  由于持仓暴露明显更大且收益为负。

---

## 下一步建议（如果你仍希望“震荡看空应最好”）

要让“看空”在这段窗口真正更优，需要两类改变（择一或组合）：

1) **增加真正的空头腿（策略结构改变）**  
   例如允许在区间顶部触发“短仓网格”，或引入独立的 short inventory grid（这属于策略升级，不是参数微调）。

2) **保留 long-only，但引入 regime 切换（最实用）**  
   以客观条件触发：如 trend_score、breakout_risk_down、价格位置（range_pos）等，在回撤压力阶段自动从 NEUTRAL 切到 BEARISH（去库存），在回归阶段再切回 NEUTRAL（恢复周转）。


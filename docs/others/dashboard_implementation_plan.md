# TaoQuant Live Trading Dashboard - 实施计划

> **目标**: 构建一个专业级实盘交易监控系统，确保交易员能够实时监控策略表现、风险状态、订单执行，并快速响应异常情况。

---

## 设计哲学

### 关键原则
1. **一眼看清风险**: 权益、PnL、风险等级必须在首屏突出显示
2. **完整的审计追踪**: 每一笔订单、每一次风控决策都要有记录
3. **快速诊断问题**: 当策略表现异常时，能立即定位是数据问题、风控问题还是市场问题
4. **可操作性**: 不只是看数据，还要能快速介入（手动平仓、调整参数、紧急关停）

---

## P0: 核心监控功能（必须有，否则无法安全运行）

### 1. Portfolio Summary（组合概况卡片）

**Why**: 这是trader最关心的核心数据，必须在dashboard最显眼位置。

**What to Display**:
```
┌─ Portfolio Summary ─────────────────────────────────────┐
│  Current Equity:     $125,432.56  (▲ +2.54% vs. start) │
│  Initial Cash:       $100,000.00                        │
│  Total PnL:          $+25,432.56                        │
│    ├─ Realized PnL:   $+18,234.21  (73 trades)         │
│    └─ Unrealized PnL: $+7,198.35   (3.0063 BTC open)   │
│                                                          │
│  Daily PnL:          $+1,234.56   (▲ +0.98% today)     │
│  Peak Equity Today:  $126,123.45  @ 14:23 UTC          │
└──────────────────────────────────────────────────────────┘
```

**Implementation**:
- Backend: `live_status.json` 中需要包含:
  ```json
  {
    "portfolio": {
      "equity": 125432.56,
      "initial_cash": 100000.0,
      "realized_pnl": 18234.21,
      "unrealized_pnl": 7198.35,
      "daily_pnl": 1234.56,
      "daily_pnl_pct": 0.0098,
      "peak_equity_today": 126123.45,
      "peak_equity_today_time": "2025-01-15T14:23:00Z",
      "total_trades": 73,
      "open_positions_count": 1
    }
  }
  ```
- Frontend: 大字号显示equity和total PnL，颜色编码（绿色=盈利，红色=亏损）


### 2. Position Summary（持仓概况卡片）

**Why**: 必须清楚知道当前持有多少、成本多少、浮盈浮亏多少。

**What to Display**:
```
┌─ Position Summary ──────────────────────────────────────┐
│  Net Position:       3.0063 BTC (LONG)                  │
│  Position Value:     $189,234.56  @ $62,987.00          │
│  Average Cost:       $60,123.45                         │
│  Break-even Price:   $60,345.67  (含手续费)             │
│                                                          │
│  Unrealized PnL:     $+7,198.35   (▲ +3.95%)           │
│  Distance to Cost:   ▲ +4.76%                           │
│                                                          │
│  Position Breakdown:                                     │
│    ├─ Long Holdings:   3.0063 BTC                       │
│    ├─ Short Holdings:  0.0000 BTC                       │
│    └─ Cost Basis:      $180,036.21                      │
└──────────────────────────────────────────────────────────┘
```

**Implementation**:
- Backend: `live_status.json`:
  ```json
  {
    "position": {
      "net_position_btc": 3.0063,
      "direction": "LONG",
      "position_value_usd": 189234.56,
      "avg_cost": 60123.45,
      "breakeven_price": 60345.67,
      "unrealized_pnl": 7198.35,
      "unrealized_pnl_pct": 0.0395,
      "distance_to_cost_pct": 0.0476,
      "long_holdings": 3.0063,
      "short_holdings": 0.0,
      "cost_basis": 180036.21
    }
  }
  ```
- Frontend: 高亮显示unrealized PnL，如果接近风控阈值（如-25%）用红色预警


### 3. Market Data（市场数据卡片）

**Why**: 必须知道当前市场价格和市场状态。

**What to Display**:
```
┌─ Market Data ───────────────────────────────────────────┐
│  BTCUSDT:               $62,987.00                      │
│  24h Change:            ▲ +2,345.67  (+3.87%)          │
│  24h High/Low:          $63,456.78 / $59,123.45         │
│                                                          │
│  Current ATR (14):      $1,234.56                       │
│  Spread (bid-ask):      $0.10                           │
│  Last Update:           2025-01-15 15:23:45 UTC         │
│  Data Latency:          ~250ms                          │
└──────────────────────────────────────────────────────────┘
```

**Implementation**:
- Backend: `live_status.json`:
  ```json
  {
    "market": {
      "symbol": "BTCUSDT",
      "close": 62987.0,
      "change_24h": 2345.67,
      "change_24h_pct": 0.0387,
      "high_24h": 63456.78,
      "low_24h": 59123.45,
      "atr_14": 1234.56,
      "spread": 0.10,
      "timestamp": "2025-01-15T15:23:45Z",
      "data_latency_ms": 250
    }
  }
  ```
- Frontend: 大字号显示price，颜色编码24h change


### 4. Risk Control Status（风控状态卡片）

**Why**: **这是最关键的风控监控，必须时刻知道当前风险等级和网格状态**。

**What to Display**:
```
┌─ Risk Control ──────────────────────────────────────────┐
│  Risk Level:            Level 2  ⚠️  (警戒)            │
│  Grid Status:           ✅ ENABLED                      │
│  Shutdown Reason:       -                               │
│                                                          │
│  Risk Checks:                                            │
│    ├─ Price Depth:        ✅ OK  (price > S-3×ATR)     │
│    ├─ Unrealized Loss:    ⚠️  WARN  (7.2% < 30%)      │
│    └─ Inventory Risk:     ✅ OK  (45.6% < 80%)         │
│                                                          │
│  Thresholds:                                             │
│    ├─ Unrealized Loss:    30.0%  (adjusted: 35.2%)     │
│    ├─ Inventory Risk:     80.0%                         │
│    └─ Price Shutdown:     $52,500  (S - 3×ATR)         │
└──────────────────────────────────────────────────────────┘
```

**Implementation**:
- Backend: `live_status.json`:
  ```json
  {
    "risk": {
      "risk_level": 2,
      "grid_enabled": true,
      "shutdown_reason": null,
      "checks": {
        "price_depth": {"status": "OK", "value": 62987.0, "threshold": 52500.0},
        "unrealized_loss": {"status": "WARN", "value_pct": 0.072, "threshold": 0.30, "adjusted_threshold": 0.352},
        "inventory_risk": {"status": "OK", "value_pct": 0.456, "threshold": 0.80}
      },
      "last_check_time": "2025-01-15T15:23:45Z"
    }
  }
  ```
- Frontend:
  - Risk Level用颜色编码: Level 0=绿色, Level 1-2=黄色, Level 3+=红色
  - Grid Status: ENABLED=绿色, DISABLED=红色（高亮警告）
  - 每个check显示✅/⚠️/❌状态


### 5. Strategy Config（策略配置卡片）

**Why**: 必须清楚知道当前运行的策略配置，避免配置错误导致亏损。

**What to Display**:
```
┌─ Strategy Configuration ────────────────────────────────┐
│  Strategy:              TaoGrid BULLISH_RANGE           │
│  Ticker:                BTCUSDT (Bitget Swap)           │
│  Regime:                BULLISH (70/30 buy/sell)        │
│                                                          │
│  Grid Setup:                                             │
│    ├─ Support:           $56,000.00                     │
│    ├─ Resistance:        $72,000.00                     │
│    ├─ Range:             $16,000.00  (28.57%)           │
│    ├─ Current Spacing:   $523.45  (0.83% ATR-based)    │
│    └─ Grid Levels:       31 total (15 buy, 16 sell)    │
│                                                          │
│  Risk Parameters:                                        │
│    ├─ Initial Cash:      $100,000.00                    │
│    ├─ Leverage:          5.0x                           │
│    ├─ Max Inventory:     80%                            │
│    └─ Max Loss:          30%                            │
│                                                          │
│  Running Since:          2025-01-15 08:00:00 UTC        │
│  Uptime:                 7h 23m                          │
└──────────────────────────────────────────────────────────┘
```

**Implementation**:
- Backend: `live_status.json`:
  ```json
  {
    "strategy": {
      "name": "TaoGrid BULLISH_RANGE",
      "symbol": "BTCUSDT",
      "exchange": "Bitget Swap",
      "regime": "BULLISH",
      "buy_weight": 0.70,
      "sell_weight": 0.30,
      "support": 56000.0,
      "resistance": 72000.0,
      "range_usd": 16000.0,
      "range_pct": 0.2857,
      "current_spacing_usd": 523.45,
      "current_spacing_pct": 0.0083,
      "grid_levels_total": 31,
      "grid_levels_buy": 15,
      "grid_levels_sell": 16,
      "initial_cash": 100000.0,
      "leverage": 5.0,
      "max_inventory_risk": 0.80,
      "max_unrealized_loss": 0.30,
      "start_time": "2025-01-15T08:00:00Z",
      "uptime_seconds": 26580
    }
  }
  ```
- Frontend: 静态显示，偶尔更新即可


### 6. Order Blotter（订单簿）

**Why**: **核心中的核心！** 必须实时看到每一笔订单的执行情况，这是trader的"生命线"。

**What to Display**:
```
┌─ Order Blotter (实时成交记录) ─────────────────────────┐
│ Time       Dir  Level  Price      Size    Notional  Fee│
├────────────────────────────────────────────────────────┤
│ 15:23:45  SELL  L12   $63,234.56  0.0823  $5,204.21 $5.20│
│ 15:18:32  BUY   L08   $62,123.45  0.0823  $5,112.76 $5.11│
│ 15:12:18  SELL  L13   $63,456.78  0.0823  $5,222.50 $5.22│
│ 15:05:47  BUY   L07   $61,987.23  0.0823  $5,101.55 $5.10│
│ 14:58:12  SELL  L12   $63,123.45  0.0823  $5,195.06 $5.20│
│ ... (scrollable, last 100 orders)                      │
└────────────────────────────────────────────────────────┘
```

**Extended Info (点击展开)**:
```
Order Detail: #12345
  ├─ Timestamp:       2025-01-15 15:23:45.123 UTC
  ├─ Direction:       SELL
  ├─ Level:           L12 (grid level index 12)
  ├─ Price:           $63,234.56
  ├─ Size:            0.0823 BTC
  ├─ Notional:        $5,204.21
  ├─ Commission:      $5.20  (0.1%)
  ├─ Slippage:        $0.00  (limit order)
  ├─ Order ID:        bitget_1234567890
  ├─ Execution Type:  LIMIT FILLED
  │
  ├─ Matched Trade:   (FIFO pairing)
  │   ├─ Entry:       2025-01-15 12:34:56 @ $62,123.45
  │   ├─ Exit:        2025-01-15 15:23:45 @ $63,234.56
  │   ├─ Holding:     2h 48m 49s
  │   ├─ PnL:         $+91.46
  │   └─ Return:      +1.79%
  │
  └─ Factors at Execution:
      ├─ MR z-score:          -0.45
      ├─ Trend score:         0.23
      ├─ Breakout risk:       0.12
      ├─ Range position:      0.68
      ├─ Funding rate:        0.0001
      └─ Combined edge:       0.78
```

**Implementation**:
- Backend:
  - 维护一个`orders.jsonl`文件（JSON Lines格式，每行一个order），append-only
  - 或者使用SQLite数据库存储订单
  - `live_status.json`中维护最近100条订单的数组
  ```json
  {
    "orders": [
      {
        "id": "order_12345",
        "timestamp": "2025-01-15T15:23:45.123Z",
        "direction": "sell",
        "level": 12,
        "price": 63234.56,
        "size": 0.0823,
        "notional": 5204.21,
        "commission": 5.20,
        "slippage": 0.0,
        "order_id": "bitget_1234567890",
        "execution_type": "LIMIT_FILLED",
        "matched_trade": {
          "entry_time": "2025-01-15T12:34:56Z",
          "entry_price": 62123.45,
          "exit_time": "2025-01-15T15:23:45Z",
          "exit_price": 63234.56,
          "holding_seconds": 10129,
          "pnl": 91.46,
          "return_pct": 0.0179
        },
        "factors": {
          "mr_z": -0.45,
          "trend_score": 0.23,
          "breakout_risk_down": 0.12,
          "range_pos": 0.68,
          "funding_rate": 0.0001,
          "combined_edge": 0.78
        }
      },
      ...
    ]
  }
  ```
- Frontend:
  - Table组件，实时刷新（WebSocket或polling每秒）
  - 颜色编码：BUY=绿色，SELL=红色
  - 点击行展开详细信息


### 7. Risk Control Log（风控日志）

**Why**: **极其重要！** 必须记录每一次风控决策，特别是被block的订单和风险等级变化。

**What to Display**:
```
┌─ Risk Control Log ──────────────────────────────────────┐
│ Time       Event Type       Details                     │
├────────────────────────────────────────────────────────┤
│ 15:23:45  ⚠️  RISK_LEVEL_UP   Level 1 → 2 (unrealized loss 7.2%)│
│ 15:18:32  ✅ ORDER_ALLOWED    BUY L08 @ $62,123.45 (risk OK)│
│ 15:12:18  ❌ ORDER_BLOCKED    BUY L06 @ $61,456.78 (inventory risk 78.5%)│
│ 14:58:12  ⚠️  RISK_CHECK      unrealized_loss=5.2%, inv_risk=65.3%│
│ 14:45:23  ✅ RISK_LEVEL_DOWN  Level 2 → 1 (conditions improved)│
│ ... (scrollable, last 200 events)                      │
└────────────────────────────────────────────────────────┘
```

**Extended Info (点击展开)**:
```
Risk Event Detail: ORDER_BLOCKED
  ├─ Timestamp:       2025-01-15 15:12:18.456 UTC
  ├─ Event:           ORDER_BLOCKED
  ├─ Severity:        CRITICAL
  │
  ├─ Blocked Order:
  │   ├─ Direction:   BUY
  │   ├─ Level:       L06
  │   ├─ Price:       $61,456.78
  │   ├─ Size:        0.0823 BTC
  │   └─ Notional:    $5,057.89
  │
  ├─ Block Reason:    INVENTORY_RISK_EXCEEDED
  ├─ Details:         Inventory risk 78.5% > threshold 80.0%
  │
  └─ Portfolio State at Block:
      ├─ Equity:              $125,234.56
      ├─ Net Position:        2.9240 BTC
      ├─ Position Value:      $179,678.90
      ├─ Max Capacity:        $626,172.80  (equity × leverage)
      ├─ Inventory Risk:      78.5%
      ├─ Unrealized PnL:      $+6,234.56  (+5.2%)
      └─ Risk Level:          2
```

**Implementation**:
- Backend:
  - 维护`risk_log.jsonl`文件（append-only）
  - `live_status.json`中维护最近200条事件
  ```json
  {
    "risk_log": [
      {
        "id": "risk_event_12345",
        "timestamp": "2025-01-15T15:12:18.456Z",
        "event_type": "ORDER_BLOCKED",
        "severity": "CRITICAL",
        "blocked_order": {
          "direction": "buy",
          "level": 6,
          "price": 61456.78,
          "size": 0.0823,
          "notional": 5057.89
        },
        "reason": "INVENTORY_RISK_EXCEEDED",
        "details": "Inventory risk 78.5% > threshold 80.0%",
        "portfolio_state": {
          "equity": 125234.56,
          "net_position": 2.924,
          "position_value": 179678.90,
          "max_capacity": 626172.80,
          "inventory_risk_pct": 0.785,
          "unrealized_pnl": 6234.56,
          "unrealized_pnl_pct": 0.052,
          "risk_level": 2
        }
      },
      ...
    ]
  }
  ```
- Frontend:
  - Table组件，颜色编码：CRITICAL=红色，WARNING=黄色，INFO=灰色
  - 点击行展开详细信息


---

## P1: 重要的专业功能（提升监控质量）

### 8. Performance Metrics（绩效指标面板）

**Why**: 必须知道策略的实时表现，不只是看PnL，还要看风险调整后的收益。

**What to Display**:
```
┌─ Performance Metrics ───────────────────────────────────┐
│  Total Return:          +25.43%                         │
│  Daily Return:          +0.98%                          │
│  Rolling 7D Return:     +5.67%                          │
│                                                          │
│  Max Drawdown:          -12.34%  (@ 2025-01-12 09:23)  │
│  Current Drawdown:      -2.15%   (from peak $126,123)  │
│                                                          │
│  Sharpe Ratio (30D):    2.45                            │
│  Sortino Ratio (30D):   3.12                            │
│  Calmar Ratio:          2.06                            │
│                                                          │
│  Win Rate:              85.7%   (63/73 trades)          │
│  Profit Factor:         3.42                            │
│  Avg Win:               $+342.56                        │
│  Avg Loss:              $-156.78                        │
│  Largest Win:           $+1,234.56                      │
│  Largest Loss:          $-567.89                        │
└──────────────────────────────────────────────────────────┘
```

**Implementation**:
- Backend: 在实盘运行时实时计算这些指标
- Frontend: 静态显示，每分钟更新一次即可


### 9. Grid State Visualization（网格状态可视化）

**Why**: 可视化展示当前网格的状态，哪些level有pending orders，哪些被触发了。

**What to Display**:
```
┌─ Grid State ────────────────────────────────────────────┐
│                                                          │
│  R: $72,000 ════════════════════════════════════════    │
│                                                          │
│  L16 SELL  $68,234  [pending]                           │
│  L15 SELL  $67,456  [pending]                           │
│  L14 SELL  $66,789  [pending]                           │
│  L13 SELL  $65,234  [filled 2x today]                   │
│  L12 SELL  $64,123  [filled 5x today]                   │
│  L11 SELL  $63,456  [pending]                           │
│                                                          │
│  ▼ Current Price: $62,987 ◄───────────                  │
│                                                          │
│  L10 BUY   $62,123  [filled 3x today]                   │
│  L09 BUY   $61,456  [filled 7x today]                   │
│  L08 BUY   $60,789  [pending]                           │
│  L07 BUY   $60,123  [pending]                           │
│  L06 BUY   $59,456  [BLOCKED - inventory risk]          │
│  L05 BUY   $58,789  [inactive]                          │
│                                                          │
│  S: $56,000 ════════════════════════════════════════    │
│                                                          │
│  Active Levels: 8 buy, 6 sell (14 total pending)       │
│  Filled Today:  12 buy, 8 sell (20 total)              │
└──────────────────────────────────────────────────────────┘
```

**Implementation**:
- Backend: `live_status.json`中维护grid state
  ```json
  {
    "grid": {
      "support": 56000.0,
      "resistance": 72000.0,
      "current_price": 62987.0,
      "levels": [
        {
          "index": 16,
          "direction": "sell",
          "price": 68234.0,
          "status": "pending",
          "fills_today": 0,
          "order_id": "bitget_xxx"
        },
        ...
        {
          "index": 6,
          "direction": "buy",
          "price": 59456.0,
          "status": "blocked",
          "block_reason": "inventory_risk",
          "fills_today": 0
        },
        ...
      ],
      "active_buy_levels": 8,
      "active_sell_levels": 6,
      "total_pending_orders": 14,
      "total_fills_today": 20
    }
  }
  ```
- Frontend: 可视化展示，颜色编码不同状态


### 10. Alerts & Notifications（告警通知）

**Why**: 关键事件发生时必须立即通知trader（Telegram/Email/钉钉）。

**What to Monitor**:
- **CRITICAL (立即通知)**:
  - Drawdown > 20%
  - Unrealized Loss > 25%
  - Grid Shutdown
  - Risk Level >= 3
  - Exchange API Error
  - Data Feed Disconnected > 60s

- **WARNING (重要通知)**:
  - Drawdown > 10%
  - Unrealized Loss > 15%
  - Risk Level = 2
  - Abnormal volatility spike (ATR > 2x normal)
  - Position concentration > 70%

**Implementation**:
- Backend:
  - 在算法运行时检测这些条件
  - 调用notification service (Telegram Bot API / SMTP)
  - 记录到`alerts.jsonl`
- Frontend:
  - 在dashboard顶部显示alert banner
  - 播放声音提示（critical alerts）


### 11. System Health Monitoring（系统健康监控）

**Why**: 必须知道系统本身是否正常运行，否则策略可能在"裸奔"。

**What to Display**:
```
┌─ System Health ─────────────────────────────────────────┐
│  Bot Status:            ✅ RUNNING                      │
│  Last Heartbeat:        2025-01-15 15:23:45 UTC (~1s)  │
│  Expected Bar Interval: 60s                             │
│  Actual Last Bar:       58s ago  ✅                     │
│                                                          │
│  Data Feed:             ✅ CONNECTED                    │
│    ├─ Latency:          ~250ms                          │
│    └─ Last Update:      1s ago                          │
│                                                          │
│  Exchange API:          ✅ CONNECTED                    │
│    ├─ Latency:          ~180ms                          │
│    └─ Last Order:       2m 15s ago                      │
│                                                          │
│  Processing Performance:                                 │
│    ├─ Last Bar Time:    0.23s                           │
│    ├─ Avg Bar Time:     0.18s  (30D rolling)            │
│    └─ Peak Bar Time:    1.45s  @ 2025-01-14 14:23      │
│                                                          │
│  Error Count (24h):     0 critical, 2 warnings          │
└──────────────────────────────────────────────────────────┘
```

**Implementation**:
- Backend: `live_status.json`中维护system health
- Frontend: 如果任何component显示❌，用红色高亮警告


### 12. Trade History & Analytics（历史交易分析）

**Why**: 需要回溯查看历史交易，分析哪些level最赚钱、哪些时间段最活跃。

**What to Display**:
- **Trade List** (可筛选/排序):
  - Entry/Exit时间、价格、持仓时长、PnL、Return%
  - 按Level分组统计、按时间段统计

- **Analytics**:
  - PnL分布直方图
  - 持仓时长分布
  - 最赚钱的Level Top 5
  - 最活跃的时间段

**Implementation**:
- Backend: `trades.jsonl` + SQLite存储
- Frontend: Table + Charts (ECharts / Recharts)


---

## P2: Nice-to-Have（进一步提升体验）

### 13. Equity Curve Chart（权益曲线图表）

**Why**: 可视化查看equity的历史走势，直观看到回撤。

**Implementation**: ECharts折线图，实时更新


### 14. Manual Control Panel（手动控制面板）

**Why**: 紧急情况下需要手动介入。

**What to Control**:
- **Emergency Actions**:
  - 🚨 Emergency Stop (立即关闭所有pending orders)
  - 🚨 Force Liquidate (市价平掉所有持仓)
  - ⏸️  Pause Grid (暂停网格，不关仓)
  - ▶️  Resume Grid

- **Manual Orders**:
  - 手动下单（指定price/size）
  - 手动取消订单

**Implementation**:
- 需要二次确认（防止误操作）
- 需要身份验证（API token）


### 15. Factor Diagnostics Panel（因子诊断面板）

**Why**: 深入理解当前market regime和factor状态。

**What to Display**:
```
┌─ Factor Diagnostics ────────────────────────────────────┐
│  MR + Trend:                                             │
│    ├─ Z-score:          -0.45  (mean reversion zone)    │
│    └─ Trend score:      +0.23  (weak uptrend)           │
│                                                          │
│  Breakout Risk:                                          │
│    ├─ Downside:         0.12  (low risk)                │
│    └─ Upside:           0.45  (moderate risk)           │
│                                                          │
│  Range Position:        0.68  (upper 68% of range)      │
│  Funding Rate:          0.0001  (neutral)               │
│  Volatility Score:      0.56  (moderate)                │
│                                                          │
│  Combined Edge Weight:  0.78  (strong buy bias)         │
└──────────────────────────────────────────────────────────┘
```


### 16. Config Hot Reload（配置热加载）

**Why**: 能够在不停机的情况下调整参数（如S/R levels，风控阈值）。

**Implementation**:
- POST `/api/config/update` endpoint
- Bot检测配置文件变更，重新加载
- 记录配置变更历史（版本控制）


### 17. WebSocket Real-time Updates（WebSocket实时推送）

**Why**: 当前是polling（每5秒），WebSocket可以做到毫秒级实时推送。

**Implementation**:
- Backend: FastAPI WebSocket endpoint
- Frontend: 订阅WebSocket，实时接收order fills、risk events


### 18. Mobile Responsive Design（移动端适配）

**Why**: 需要随时随地监控（手机/平板）。

**Implementation**: 响应式布局（Tailwind CSS）


### 19. Historical Backtest Comparison（历史回测对比）

**Why**: 将实盘表现与回测结果对比，验证策略有效性。

**Implementation**: 叠加显示实盘equity curve vs. 回测equity curve


### 20. PnL Attribution（收益归因分析）

**Why**: 分析PnL来源（哪个因子贡献最大、哪个level最赚钱）。

**Implementation**: 需要详细记录每笔交易的factor状态


---

## 技术栈建议

### Backend
- **FastAPI** (已有) + **WebSocket**
- **SQLite** 或 **PostgreSQL** (存储orders/trades/logs)
- **Redis** (可选，用于real-time data cache)

### Frontend
- **Option 1 (简单快速)**: 纯HTML + Vanilla JS + Tailwind CSS
- **Option 2 (专业)**: React + TypeScript + shadcn/ui + Recharts/ECharts
- **Option 3 (终极)**: Next.js + TypeScript + tRPC + Prisma + ECharts

### Monitoring & Alerts
- **Prometheus + Grafana** (系统级监控)
- **Telegram Bot API** (告警通知)
- **SMTP** (Email alerts)

### Data Storage Strategy
```
state/
  ├─ live_status.json          # 当前状态快照（实时更新）
  ├─ orders.jsonl              # 订单历史（append-only）
  ├─ trades.jsonl              # 成交历史（append-only）
  ├─ risk_log.jsonl            # 风控日志（append-only）
  ├─ alerts.jsonl              # 告警历史（append-only）
  ├─ equity_curve.csv          # 权益曲线（定期snapshot）
  └─ db.sqlite                 # 结构化查询（可选）
```

---

## Implementation Phases（分阶段实施）

### Phase 1: MVP (Week 1) - P0核心功能
- [ ] Portfolio Summary card
- [ ] Position Summary card
- [ ] Market Data card
- [ ] Risk Control Status card
- [ ] Strategy Config card
- [ ] Order Blotter (basic table)
- [ ] Risk Control Log (basic table)
- [ ] Backend: 完善`live_status.json`结构
- [ ] Backend: 实现`orders.jsonl` logging
- [ ] Backend: 实现`risk_log.jsonl` logging

**交付标准**: 能够安全运行实盘，实时监控风险和订单。

### Phase 2: Professional (Week 2) - P1重要功能
- [ ] Performance Metrics panel
- [ ] Grid State Visualization
- [ ] Alerts & Notifications (Telegram)
- [ ] System Health Monitoring
- [ ] Trade History & Analytics (basic)
- [ ] Backend: SQLite存储 + 查询API
- [ ] Frontend: 优化UI/UX，响应式布局

**交付标准**: 专业级监控体验，能够快速诊断问题。

### Phase 3: Advanced (Week 3+) - P2增强功能
- [ ] Equity Curve Chart
- [ ] Manual Control Panel
- [ ] Factor Diagnostics Panel
- [ ] Config Hot Reload
- [ ] WebSocket Real-time Updates
- [ ] Mobile Responsive Design
- [ ] Backtest Comparison
- [ ] PnL Attribution

**交付标准**: 接近专业机构的交易监控系统。

---

## 总结

这是一个**由简到繁、逐步迭代**的实施计划。**先确保P0核心功能完成，再考虑P1/P2**。

作为顶级trader，我最关心的是：
1. **实时看到风险**（Risk Control Status）
2. **完整的订单审计**（Order Blotter）
3. **清楚知道持仓和PnL**（Portfolio/Position Summary）
4. **关键事件告警**（Alerts）

有了这4个，就可以安全运行实盘。其他功能是锦上添花。

**你接下来想先实现哪个部分？我建议从P0开始，逐个攻克。**

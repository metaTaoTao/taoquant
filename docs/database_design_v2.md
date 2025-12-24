# TaoQuant Database Design v2

## Overview

This document describes the professional database schema for TaoQuant quantitative trading system.

## Design Principles

1. **Event Sourcing**: All state changes are traceable via `order_events`
2. **Session Management**: Each bot run is a separate session
3. **Trigger Tracking**: Know WHY each event happened (strategy vs restart)
4. **Backward Compatible**: Existing v1 tables preserved

## Table Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    TaoQuant Database v2                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Session Layer                                           │   │
│  │  └── sessions           每次 Bot 运行的记录              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Real-time State (Overwrite)                             │   │
│  │  ├── bot_state_current          当前状态 JSON           │   │
│  │  ├── active_limit_orders_current 计划挂单               │   │
│  │  ├── exchange_open_orders_current 交易所挂单            │   │
│  │  └── exchange_positions_current   当前持仓              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Event Log (Append-only)                                 │   │
│  │  ├── orders              订单当前状态                    │   │
│  │  ├── order_events ★     订单事件日志 (完整审计)         │   │
│  │  ├── position_changes    仓位变动                        │   │
│  │  ├── trade_fills         成交明细 (交易所数据)           │   │
│  │  ├── order_blotter       成交流水                        │   │
│  │  └── bot_heartbeat       健康心跳                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Analytics (Pre-aggregated)                              │   │
│  │  └── daily_pnl           每日 P&L 统计                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Operations & Config                                     │   │
│  │  ├── strategies          策略配置                        │   │
│  │  ├── error_logs          错误日志                        │   │
│  │  └── replay_cursor       同步游标                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Key Concept: Trigger Types

The `trigger` field in `order_events` distinguishes why an event happened:

| Trigger | Description | Example |
|---------|-------------|---------|
| `strategy` | Normal strategy operation | Grid filled a buy order |
| `bootstrap` | Bot startup | Re-placing grid orders after restart |
| `shutdown` | Bot stopping | Cancelling orders before stop |
| `restart` | Bot restart | Cancel old + place new (code update) |
| `manual` | Manual operation | Dashboard stop button |
| `exchange` | Exchange initiated | Margin call, liquidation |
| `sync` | Order sync correction | Fixing mismatch |

## Query Examples

### 1. Strategy fills only (exclude restart noise)

```sql
SELECT * FROM order_events 
WHERE event_type = 'FILLED' 
  AND trigger = 'strategy'
  AND ts::date = CURRENT_DATE;
```

### 2. Today's summary

```sql
SELECT * FROM v_today_summary;
```

### 3. Session history

```sql
SELECT 
    session_id,
    started_at,
    ended_at,
    end_reason,
    startup_orders_cancelled,
    startup_orders_placed
FROM sessions 
ORDER BY started_at DESC 
LIMIT 10;
```

### 4. Restart frequency analysis

```sql
SELECT 
    started_at::date as date,
    COUNT(*) as restart_count,
    SUM(startup_orders_cancelled) as total_cancelled
FROM sessions
GROUP BY started_at::date
ORDER BY date DESC;
```

### 5. Order lifecycle (single order)

```sql
SELECT 
    event_type,
    trigger,
    old_status,
    new_status,
    fill_qty,
    fill_price,
    ts
FROM order_events
WHERE client_order_id = 'tg_BTCUSDT_xxx_buy_10_long_v1'
ORDER BY ts;
```

### 6. Daily P&L trend

```sql
SELECT 
    date,
    realized_pnl,
    trade_count,
    total_volume,
    session_count as restarts
FROM daily_pnl
WHERE bot_id = 'taogrid_BTCUSDT_live'
ORDER BY date DESC
LIMIT 30;
```

## Maintenance

### Daily cleanup (add to cron)

```sql
-- Clean heartbeats older than 7 days
SELECT cleanup_old_heartbeats(7);
```

### Optional: Clean short test sessions

```sql
-- Delete sessions shorter than 5 minutes
SELECT * FROM cleanup_short_sessions(5);
```

## Migration from v1

The v2 schema is additive - all v1 tables are preserved. New tables can be populated alongside existing ones.

To apply:

```bash
docker exec -i taoquant-postgres psql -U taoquant -d taoquant < /opt/taoquant/persistence/schema_v2.sql
```

## Implementation Status

| Table | Status | Notes |
|-------|--------|-------|
| sessions | TODO | Need to modify Runner to create session on startup |
| orders | TODO | Need to modify Runner to track order lifecycle |
| order_events | TODO | Need to modify Runner to log events |
| position_changes | TODO | Need to modify Runner to log position changes |
| daily_pnl | TODO | Need daily aggregation job |
| error_logs | TODO | Need to modify Runner to log errors |
| strategies | TODO | Future multi-strategy support |

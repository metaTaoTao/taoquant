-- ============================================================
-- TaoQuant Database Schema v2
-- Professional Quantitative Trading Database Design
-- ============================================================
-- 
-- Design Principles:
-- 1. Event Sourcing: All state changes are traceable
-- 2. Session Management: Distinguish strategy events vs operational events
-- 3. Trigger Tracking: Know why each event happened
-- 4. Backward Compatible: Existing tables preserved
--
-- Tables:
--   [Existing] bot_heartbeat, bot_state_current, active_limit_orders_current,
--              exchange_open_orders_current, exchange_positions_current,
--              order_blotter, trade_fills, replay_cursor
--   [New v2]   sessions, orders, order_events, position_changes, 
--              daily_pnl, error_logs, strategies
--
-- Safe to run multiple times (uses IF NOT EXISTS).
-- ============================================================

BEGIN;

-- ============================================================
-- LAYER 0: SESSION MANAGEMENT
-- Track each Bot run separately
-- ============================================================

CREATE TABLE IF NOT EXISTS sessions (
    id                      BIGSERIAL       PRIMARY KEY,
    session_id              TEXT            UNIQUE NOT NULL,  -- e.g., "sess_1766538780"
    bot_id                  TEXT            NOT NULL,
    symbol                  TEXT            NOT NULL,
    mode                    TEXT            NOT NULL,         -- live/dryrun
    version                 TEXT,                             -- git commit or version tag
    
    -- Lifecycle
    started_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    ended_at                TIMESTAMPTZ,
    end_reason              TEXT,                             -- normal/crash/manual_stop/code_update/restart
    
    -- Startup stats
    startup_orders_cancelled INTEGER        DEFAULT 0,        -- Orders cancelled on startup
    startup_orders_placed    INTEGER        DEFAULT 0,        -- Orders placed on startup
    startup_position_qty     DOUBLE PRECISION,                -- Position detected on startup
    
    -- Config snapshot
    config_snapshot         JSONB,
    notes                   TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_bot ON sessions (bot_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions (started_at DESC);

-- ============================================================
-- LAYER 1: ORDERS (Current State)
-- One row per order, updated as status changes
-- ============================================================

CREATE TABLE IF NOT EXISTS orders (
    id                  BIGSERIAL       PRIMARY KEY,
    session_id          TEXT            NOT NULL,             -- Which session created this
    bot_id              TEXT            NOT NULL,
    client_order_id     TEXT            NOT NULL,             -- Our internal ID
    exchange_order_id   TEXT,                                 -- Exchange's ID (after submission)
    
    -- Order details
    symbol              TEXT            NOT NULL,
    side                TEXT            NOT NULL,             -- buy/sell
    order_type          TEXT            NOT NULL,             -- limit/market
    price               DOUBLE PRECISION,
    qty                 DOUBLE PRECISION NOT NULL,
    
    -- Fill tracking
    filled_qty          DOUBLE PRECISION DEFAULT 0,
    avg_fill_price      DOUBLE PRECISION,
    total_fee           DOUBLE PRECISION DEFAULT 0,
    
    -- Status
    status              TEXT            NOT NULL,             -- pending/open/partial/filled/cancelled/rejected
    
    -- Grid info
    grid_level          INTEGER,
    leg                 TEXT,                                 -- long/short_open/short_cover
    reason              TEXT,                                 -- Why this order was created
    
    -- Timestamps
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    submitted_at        TIMESTAMPTZ,                          -- When sent to exchange
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    closed_at           TIMESTAMPTZ,                          -- When filled/cancelled/rejected
    
    -- Constraints
    UNIQUE (bot_id, client_order_id)
);

CREATE INDEX IF NOT EXISTS idx_orders_session ON orders (session_id);
CREATE INDEX IF NOT EXISTS idx_orders_bot_created ON orders (bot_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (bot_id, status) WHERE status IN ('pending', 'open', 'partial');
CREATE INDEX IF NOT EXISTS idx_orders_exchange_id ON orders (exchange_order_id) WHERE exchange_order_id IS NOT NULL;

-- ============================================================
-- LAYER 2: ORDER EVENTS (Event Log)
-- Every state change is recorded - full audit trail
-- ============================================================

CREATE TABLE IF NOT EXISTS order_events (
    id              BIGSERIAL       PRIMARY KEY,
    session_id      TEXT            NOT NULL,
    order_id        BIGINT          REFERENCES orders(id),
    client_order_id TEXT            NOT NULL,
    exchange_order_id TEXT,
    
    -- Event info
    event_type      TEXT            NOT NULL,
    -- Event types:
    --   CREATED     - Order created in strategy
    --   SUBMITTED   - Sent to exchange, got exchange_order_id
    --   PARTIAL     - Partially filled
    --   FILLED      - Fully filled
    --   CANCELLED   - Cancelled (by us or exchange)
    --   REJECTED    - Exchange rejected
    --   REPLACED    - Order modified (cancel + new)
    
    trigger         TEXT            NOT NULL,
    -- Trigger types:
    --   strategy    - Normal strategy operation
    --   bootstrap   - Bot startup (re-placing grid)
    --   shutdown    - Bot stopping (cancelling orders)
    --   restart     - Bot restart (cancel old + place new)
    --   manual      - Manual operation (Dashboard button)
    --   exchange    - Exchange initiated (margin call, etc.)
    --   sync        - Order sync correction
    
    -- Status transition
    old_status      TEXT,
    new_status      TEXT            NOT NULL,
    
    -- Fill details (for PARTIAL/FILLED events)
    fill_qty        DOUBLE PRECISION,
    fill_price      DOUBLE PRECISION,
    fill_fee        DOUBLE PRECISION,
    trade_id        TEXT,                                     -- Exchange trade ID
    
    -- Timing
    ts              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    exchange_ts     TIMESTAMPTZ,                              -- Exchange timestamp (if available)
    
    -- Extra context
    details         JSONB
);

CREATE INDEX IF NOT EXISTS idx_order_events_session ON order_events (session_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_order_events_order ON order_events (order_id);
CREATE INDEX IF NOT EXISTS idx_order_events_client ON order_events (client_order_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_order_events_type ON order_events (event_type, ts DESC);
CREATE INDEX IF NOT EXISTS idx_order_events_trigger ON order_events (trigger, ts DESC);

-- ============================================================
-- LAYER 3: POSITION CHANGES
-- Track every position change for P&L analysis
-- ============================================================

CREATE TABLE IF NOT EXISTS position_changes (
    id              BIGSERIAL       PRIMARY KEY,
    session_id      TEXT            NOT NULL,
    bot_id          TEXT            NOT NULL,
    symbol          TEXT            NOT NULL,
    
    -- Position change
    side            TEXT            NOT NULL,                 -- long/short/net
    qty_before      DOUBLE PRECISION,
    qty_after       DOUBLE PRECISION,
    change_qty      DOUBLE PRECISION,
    
    -- Price info
    change_price    DOUBLE PRECISION,                         -- Price of the fill
    avg_entry_before DOUBLE PRECISION,
    avg_entry_after  DOUBLE PRECISION,
    
    -- P&L (for closing trades)
    realized_pnl    DOUBLE PRECISION,
    fee             DOUBLE PRECISION,
    
    -- Reference
    trigger         TEXT            NOT NULL,                 -- strategy/bootstrap/manual/liquidation
    order_id        BIGINT          REFERENCES orders(id),
    trade_id        TEXT,
    
    ts              TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_position_changes_bot_ts ON position_changes (bot_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_position_changes_session ON position_changes (session_id, ts DESC);

-- ============================================================
-- LAYER 4: DAILY P&L (Pre-aggregated)
-- For fast dashboard queries
-- ============================================================

CREATE TABLE IF NOT EXISTS daily_pnl (
    bot_id          TEXT            NOT NULL,
    date            DATE            NOT NULL,
    
    -- P&L
    realized_pnl    DOUBLE PRECISION DEFAULT 0,
    unrealized_pnl  DOUBLE PRECISION DEFAULT 0,
    total_pnl       DOUBLE PRECISION DEFAULT 0,
    fees            DOUBLE PRECISION DEFAULT 0,
    
    -- Trade counts (strategy trades only, exclude bootstrap/shutdown)
    trade_count     INTEGER         DEFAULT 0,
    buy_count       INTEGER         DEFAULT 0,
    sell_count      INTEGER         DEFAULT 0,
    
    -- Volume
    buy_volume      DOUBLE PRECISION DEFAULT 0,
    sell_volume     DOUBLE PRECISION DEFAULT 0,
    total_volume    DOUBLE PRECISION DEFAULT 0,
    
    -- Risk metrics
    max_position    DOUBLE PRECISION,
    max_drawdown    DOUBLE PRECISION,
    
    -- Equity curve
    equity_start    DOUBLE PRECISION,
    equity_end      DOUBLE PRECISION,
    equity_high     DOUBLE PRECISION,
    equity_low      DOUBLE PRECISION,
    
    -- Session info
    session_count   INTEGER         DEFAULT 0,                -- How many restarts this day
    uptime_minutes  INTEGER         DEFAULT 0,
    
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (bot_id, date)
);

CREATE INDEX IF NOT EXISTS idx_daily_pnl_date ON daily_pnl (date DESC);

-- ============================================================
-- LAYER 5: ERROR LOGS
-- Centralized error tracking
-- ============================================================

CREATE TABLE IF NOT EXISTS error_logs (
    id          BIGSERIAL       PRIMARY KEY,
    session_id  TEXT,
    bot_id      TEXT            NOT NULL,
    ts          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    
    level       TEXT            NOT NULL,                     -- WARNING/ERROR/CRITICAL
    component   TEXT,                                         -- order_sync/data_feed/exchange_api/db/strategy
    error_code  TEXT,                                         -- e.g., "40786" for duplicate clientOid
    message     TEXT            NOT NULL,
    
    -- Context
    symbol      TEXT,
    order_id    TEXT,
    
    details     JSONB
);

CREATE INDEX IF NOT EXISTS idx_error_logs_bot_ts ON error_logs (bot_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_error_logs_level ON error_logs (level, ts DESC);
CREATE INDEX IF NOT EXISTS idx_error_logs_component ON error_logs (component, ts DESC);

-- ============================================================
-- LAYER 6: STRATEGIES (Multi-strategy support)
-- ============================================================

CREATE TABLE IF NOT EXISTS strategies (
    strategy_id     TEXT        PRIMARY KEY,                  -- e.g., "taogrid_btcusdt_live"
    strategy_type   TEXT        NOT NULL,                     -- taogrid/sr_short/etc.
    symbol          TEXT        NOT NULL,
    exchange        TEXT        NOT NULL,                     -- bitget/okx/binance
    
    status          TEXT        NOT NULL DEFAULT 'active',    -- active/paused/stopped/archived
    
    -- Config
    config_json     JSONB       NOT NULL,
    
    -- Stats (updated periodically)
    total_trades    INTEGER     DEFAULT 0,
    total_pnl       DOUBLE PRECISION DEFAULT 0,
    win_rate        DOUBLE PRECISION,
    
    -- Lifecycle
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_run_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_strategies_status ON strategies (status);

-- ============================================================
-- MAINTENANCE HELPERS
-- ============================================================

-- Function to clean up old heartbeats (call daily via cron)
CREATE OR REPLACE FUNCTION cleanup_old_heartbeats(days_to_keep INTEGER DEFAULT 7)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM bot_heartbeat 
    WHERE ts < NOW() - (days_to_keep || ' days')::INTERVAL;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Function to clean up short sessions (optional, for testing cleanup)
CREATE OR REPLACE FUNCTION cleanup_short_sessions(min_duration_minutes INTEGER DEFAULT 5)
RETURNS TABLE(sessions_deleted INTEGER, events_deleted INTEGER) AS $$
DECLARE
    sess_count INTEGER;
    evt_count INTEGER;
BEGIN
    -- Get session IDs to delete
    WITH short_sessions AS (
        SELECT session_id FROM sessions 
        WHERE ended_at IS NOT NULL 
          AND ended_at - started_at < (min_duration_minutes || ' minutes')::INTERVAL
    )
    DELETE FROM order_events WHERE session_id IN (SELECT session_id FROM short_sessions);
    GET DIAGNOSTICS evt_count = ROW_COUNT;
    
    DELETE FROM orders WHERE session_id IN (
        SELECT session_id FROM sessions 
        WHERE ended_at IS NOT NULL 
          AND ended_at - started_at < (min_duration_minutes || ' minutes')::INTERVAL
    );
    
    DELETE FROM sessions 
    WHERE ended_at IS NOT NULL 
      AND ended_at - started_at < (min_duration_minutes || ' minutes')::INTERVAL;
    GET DIAGNOSTICS sess_count = ROW_COUNT;
    
    sessions_deleted := sess_count;
    events_deleted := evt_count;
    RETURN NEXT;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- USEFUL VIEWS
-- ============================================================

-- Active orders view (combines orders table with latest status)
CREATE OR REPLACE VIEW v_active_orders AS
SELECT 
    o.id,
    o.session_id,
    o.bot_id,
    o.client_order_id,
    o.exchange_order_id,
    o.symbol,
    o.side,
    o.price,
    o.qty,
    o.filled_qty,
    o.status,
    o.grid_level,
    o.leg,
    o.created_at,
    o.updated_at
FROM orders o
WHERE o.status IN ('pending', 'open', 'partial');

-- Strategy events only (exclude bootstrap/shutdown noise)
CREATE OR REPLACE VIEW v_strategy_events AS
SELECT *
FROM order_events
WHERE trigger = 'strategy';

-- Today's activity summary
CREATE OR REPLACE VIEW v_today_summary AS
SELECT 
    bot_id,
    COUNT(*) FILTER (WHERE event_type = 'FILLED' AND trigger = 'strategy') as strategy_fills,
    COUNT(*) FILTER (WHERE event_type = 'FILLED') as total_fills,
    COUNT(*) FILTER (WHERE event_type = 'CANCELLED' AND trigger = 'strategy') as strategy_cancels,
    COUNT(*) FILTER (WHERE trigger IN ('bootstrap', 'shutdown')) as restart_events,
    COUNT(DISTINCT session_id) as session_count
FROM order_events
WHERE ts::date = CURRENT_DATE
GROUP BY bot_id;

COMMIT;

-- ============================================================
-- POST-INSTALLATION NOTES
-- ============================================================
-- 
-- 1. To apply this schema:
--    docker exec -i taoquant-postgres psql -U taoquant -d taoquant < persistence/schema_v2.sql
--
-- 2. Daily maintenance (add to cron):
--    SELECT cleanup_old_heartbeats(7);  -- Keep 7 days of heartbeats
--
-- 3. Query examples:
--
--    -- Today's strategy fills only
--    SELECT * FROM v_strategy_events WHERE event_type = 'FILLED' AND ts::date = CURRENT_DATE;
--
--    -- Session history
--    SELECT session_id, started_at, ended_at, end_reason, startup_orders_cancelled 
--    FROM sessions ORDER BY started_at DESC LIMIT 10;
--
--    -- Restart frequency
--    SELECT started_at::date, COUNT(*) as restarts FROM sessions GROUP BY 1 ORDER BY 1 DESC;
--
-- ============================================================

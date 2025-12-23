-- TaoQuant Persistence Schema (PostgreSQL)
-- P0: events + current snapshots with idempotent keys.
-- Safe to run multiple times.

BEGIN;

-- Heartbeat history (append-only)
CREATE TABLE IF NOT EXISTS bot_heartbeat (
    bot_id              TEXT            NOT NULL,
    ts                  TIMESTAMPTZ     NOT NULL,
    mode                TEXT            NOT NULL, -- 'dryrun'|'live'
    last_bar_ts         TIMESTAMPTZ,
    lag_seconds         DOUBLE PRECISION,
    status              TEXT            NOT NULL, -- RUNNING|RUNNER_DOWN|DATA_FEED_STALE|EXCHANGE_API_DEGRADED|...
    data_feed_status    TEXT,
    exchange_api_status TEXT,
    exchange_error_count INTEGER,
    payload             JSONB,
    PRIMARY KEY (bot_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_bot_heartbeat_bot_ts ON bot_heartbeat (bot_id, ts DESC);

-- Current state snapshot (single row per bot)
CREATE TABLE IF NOT EXISTS bot_state_current (
    bot_id      TEXT        PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL,
    mode        TEXT        NOT NULL,
    payload     JSONB       NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bot_state_current_ts ON bot_state_current (ts DESC);

-- Blotter / trades (append-only)
CREATE TABLE IF NOT EXISTS order_blotter (
    id                  BIGSERIAL       PRIMARY KEY,
    bot_id              TEXT            NOT NULL,
    ts                  TIMESTAMPTZ     NOT NULL,
    direction           TEXT            NOT NULL, -- buy|sell
    level               INTEGER,
    price               DOUBLE PRECISION,
    size                DOUBLE PRECISION,
    notional            DOUBLE PRECISION,
    commission          DOUBLE PRECISION,
    leg                 TEXT,
    exchange_order_id   TEXT,
    client_order_id     TEXT,
    trade_id            TEXT,
    raw_json            JSONB
);
CREATE INDEX IF NOT EXISTS idx_order_blotter_bot_ts ON order_blotter (bot_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_order_blotter_client_oid ON order_blotter (bot_id, client_order_id);

-- Idempotency: prefer trade_id if available (real exchange)
CREATE UNIQUE INDEX IF NOT EXISTS uq_order_blotter_trade_id
    ON order_blotter (bot_id, trade_id)
    WHERE trade_id IS NOT NULL;

-- Fallback idempotency (dryrun / missing trade_id)
CREATE UNIQUE INDEX IF NOT EXISTS uq_order_blotter_fallback
    ON order_blotter (bot_id, client_order_id, ts, direction, level, price, size)
    WHERE trade_id IS NULL;

-- Planned/active limit orders (current set, upsert each bar)
CREATE TABLE IF NOT EXISTS active_limit_orders_current (
    bot_id          TEXT        NOT NULL,
    client_order_id TEXT        NOT NULL,
    ts              TIMESTAMPTZ NOT NULL,
    direction       TEXT        NOT NULL, -- buy|sell
    level           INTEGER     NOT NULL,
    price           DOUBLE PRECISION,
    size            DOUBLE PRECISION,
    leg             TEXT,
    reason          TEXT,
    PRIMARY KEY (bot_id, client_order_id)
);
CREATE INDEX IF NOT EXISTS idx_active_limit_orders_bot_ts ON active_limit_orders_current (bot_id, ts DESC);

-- Exchange open orders (current snapshot, one row per exchange_order_id)
CREATE TABLE IF NOT EXISTS exchange_open_orders_current (
    bot_id            TEXT        NOT NULL,
    exchange_order_id TEXT        NOT NULL,
    ts                TIMESTAMPTZ NOT NULL,
    client_order_id   TEXT,
    side              TEXT,
    price             DOUBLE PRECISION,
    size              DOUBLE PRECISION,
    status            TEXT,
    raw_json          JSONB,
    PRIMARY KEY (bot_id, exchange_order_id)
);
CREATE INDEX IF NOT EXISTS idx_exchange_open_orders_bot_ts ON exchange_open_orders_current (bot_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_exchange_open_orders_client_oid ON exchange_open_orders_current (bot_id, client_order_id);

-- Exchange positions (current snapshot, one row per side)
CREATE TABLE IF NOT EXISTS exchange_positions_current (
    bot_id      TEXT        NOT NULL,
    side        TEXT        NOT NULL, -- long|short|spot
    ts          TIMESTAMPTZ NOT NULL,
    qty         DOUBLE PRECISION,
    entry_price DOUBLE PRECISION,
    raw_json    JSONB,
    PRIMARY KEY (bot_id, side)
);
CREATE INDEX IF NOT EXISTS idx_exchange_positions_bot_ts ON exchange_positions_current (bot_id, ts DESC);

-- Trade fills / executions (append-only, for replay & accounting)
CREATE TABLE IF NOT EXISTS trade_fills (
    id                  BIGSERIAL       PRIMARY KEY,
    bot_id              TEXT            NOT NULL,
    ts                  TIMESTAMPTZ     NOT NULL,
    trade_id            TEXT,
    exchange_order_id   TEXT,
    client_order_id     TEXT,
    side                TEXT            NOT NULL, -- buy|sell
    price               DOUBLE PRECISION,
    qty                 DOUBLE PRECISION,
    fee                 DOUBLE PRECISION,
    fee_currency        TEXT,
    raw_json            JSONB
);
CREATE INDEX IF NOT EXISTS idx_trade_fills_bot_ts ON trade_fills (bot_id, ts DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_trade_fills_trade_id
    ON trade_fills (bot_id, trade_id)
    WHERE trade_id IS NOT NULL;

-- Replay cursor per bot (store last seen trade_id and/or timestamp)
CREATE TABLE IF NOT EXISTS replay_cursor (
    bot_id              TEXT        PRIMARY KEY,
    last_seen_trade_id  TEXT,
    last_seen_ts        TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;


from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

try:
    import psycopg
    from psycopg import sql
    from psycopg.errors import UniqueViolation
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
except Exception:  # pragma: no cover (optional dependency in local dev)
    psycopg = None  # type: ignore[assignment]
    sql = None  # type: ignore[assignment]
    UniqueViolation = Exception  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]
    ConnectionPool = None  # type: ignore[assignment]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _env_truthy(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in ("1", "true", "yes", "y", "on")


@dataclass(frozen=True)
class PostgresConfig:
    dsn: str
    min_size: int = 1
    max_size: int = 5
    timeout: float = 5.0


class PostgresStore:
    """
    Best-effort persistence for live trading.

    Design goals:
    - Never crash the trading loop because DB is down
    - Use idempotent writes (upsert or ignore duplicates)
    - Keep API minimal & explicit
    """

    def __init__(self, cfg: PostgresConfig):
        if psycopg is None or ConnectionPool is None:
            raise RuntimeError("psycopg is not installed. Install `psycopg[binary]`.")
        self.cfg = cfg
        # Check if DB is disabled before creating connection pool
        if _env_truthy("TAOQUANT_DB_DISABLE"):
            raise RuntimeError("Database is disabled via TAOQUANT_DB_DISABLE")
        try:
            self._pool = ConnectionPool(
                conninfo=cfg.dsn,
                min_size=int(cfg.min_size),
                max_size=int(cfg.max_size),
                timeout=cfg.timeout,
                kwargs={"autocommit": True},
            )
        except Exception as e:
            # If connection pool creation fails, raise to be caught by from_env()
            raise RuntimeError(f"Failed to create connection pool: {e}") from e

    @staticmethod
    def from_env(prefix: str = "TAOQUANT_DB_") -> Optional["PostgresStore"]:
        """
        Create store from env.

        Supported:
        - TAOQUANT_DB_DSN (recommended)
        - or TAOQUANT_DB_HOST/PORT/NAME/USER/PASSWORD
        """
        # Hard disable: allow trading/dashboard to run without any DB attempts.
        # This avoids repeated psycopg_pool connection errors during debugging.
        if _env_truthy(f"{prefix}DISABLE") or _env_truthy("TAOQUANT_DB_DISABLE"):
            return None

        dsn = os.getenv(f"{prefix}DSN") or os.getenv("TAOQUANT_DB_DSN")
        if not dsn:
            host = os.getenv(f"{prefix}HOST")
            name = os.getenv(f"{prefix}NAME")
            user = os.getenv(f"{prefix}USER")
            password = os.getenv(f"{prefix}PASSWORD")
            port = os.getenv(f"{prefix}PORT", "5432")
            if host and name and user and password:
                dsn = f"postgresql://{user}:{password}@{host}:{port}/{name}"
        if not dsn:
            return None

        # Double-check disable flag before creating connection pool
        if _env_truthy(f"{prefix}DISABLE") or _env_truthy("TAOQUANT_DB_DISABLE"):
            return None
        
        min_size = int(os.getenv(f"{prefix}MIN_SIZE", "0"))  # Default to 0 to avoid immediate connection attempts
        max_size = int(os.getenv(f"{prefix}MAX_SIZE", "5"))
        timeout = float(os.getenv(f"{prefix}TIMEOUT", "5"))
        try:
            return PostgresStore(PostgresConfig(dsn=dsn, min_size=min_size, max_size=max_size, timeout=timeout))
        except Exception:
            # Silently fail if connection pool creation fails (e.g., DB is down or disabled)
            # This allows the application to run without DB
            return None

    def close(self) -> None:
        try:
            self._pool.close()
        except Exception:
            return

    def _exec(self, query: str, params: Optional[Dict[str, Any]] = None) -> None:
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params or {})
        except Exception:
            # Best-effort: never crash trading loop due to DB connectivity.
            return

    def _fetchone(self, query: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        try:
            with self._pool.connection() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(query, params or {})
                    return cur.fetchone()
        except Exception:
            return None

    def _exec_ignore_duplicate(self, query: str, params: Dict[str, Any]) -> None:
        try:
            self._exec(query, params)
        except UniqueViolation:
            return
        except Exception:
            # Some unique violations are wrapped; best-effort ignore
            return

    # ----------------------------
    # Writes (best-effort)
    # ----------------------------
    def upsert_bot_state_current(self, *, bot_id: str, ts: datetime, mode: str, payload: Dict[str, Any]) -> None:
        self._exec(
            """
            INSERT INTO bot_state_current (bot_id, ts, mode, payload)
            VALUES (%(bot_id)s, %(ts)s, %(mode)s, %(payload)s::jsonb)
            ON CONFLICT (bot_id) DO UPDATE SET
              ts = EXCLUDED.ts,
              mode = EXCLUDED.mode,
              payload = EXCLUDED.payload
            """,
            {
                "bot_id": bot_id,
                "ts": ts,
                "mode": mode,
                "payload": json.dumps(payload, ensure_ascii=False),
            },
        )

    def insert_heartbeat(
        self,
        *,
        bot_id: str,
        ts: datetime,
        mode: str,
        last_bar_ts: Optional[datetime],
        lag_seconds: Optional[float],
        status: str,
        data_feed_status: Optional[str] = None,
        exchange_api_status: Optional[str] = None,
        exchange_error_count: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._exec_ignore_duplicate(
            """
            INSERT INTO bot_heartbeat (
              bot_id, ts, mode, last_bar_ts, lag_seconds, status,
              data_feed_status, exchange_api_status, exchange_error_count, payload
            ) VALUES (
              %(bot_id)s, %(ts)s, %(mode)s, %(last_bar_ts)s, %(lag_seconds)s, %(status)s,
              %(data_feed_status)s, %(exchange_api_status)s, %(exchange_error_count)s, %(payload)s::jsonb
            )
            """,
            {
                "bot_id": bot_id,
                "ts": ts,
                "mode": mode,
                "last_bar_ts": last_bar_ts,
                "lag_seconds": lag_seconds,
                "status": status,
                "data_feed_status": data_feed_status,
                "exchange_api_status": exchange_api_status,
                "exchange_error_count": exchange_error_count,
                "payload": json.dumps(payload or {}, ensure_ascii=False),
            },
        )

    def replace_active_limit_orders_current(
        self, *, bot_id: str, ts: datetime, orders: Iterable[Dict[str, Any]]
    ) -> None:
        """
        Replace the current planned active order set for a bot.
        """
        with self._pool.connection() as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM active_limit_orders_current WHERE bot_id=%(bot_id)s", {"bot_id": bot_id})
                    for o in orders:
                        cur.execute(
                            """
                            INSERT INTO active_limit_orders_current (
                              bot_id, client_order_id, ts, direction, level, price, size, leg, reason
                            ) VALUES (
                              %(bot_id)s, %(client_order_id)s, %(ts)s, %(direction)s, %(level)s,
                              %(price)s, %(size)s, %(leg)s, %(reason)s
                            )
                            ON CONFLICT (bot_id, client_order_id) DO UPDATE SET
                              ts = EXCLUDED.ts,
                              direction = EXCLUDED.direction,
                              level = EXCLUDED.level,
                              price = EXCLUDED.price,
                              size = EXCLUDED.size,
                              leg = EXCLUDED.leg,
                              reason = EXCLUDED.reason
                            """,
                            {
                                "bot_id": bot_id,
                                "client_order_id": str(o.get("client_order_id") or ""),
                                "ts": ts,
                                "direction": str(o.get("direction") or ""),
                                "level": int(o.get("level") or 0),
                                "price": float(o.get("price") or 0.0),
                                "size": float(o.get("size") or 0.0),
                                "leg": str(o.get("leg") or "long"),
                                "reason": o.get("reason"),
                            },
                        )
            except Exception:
                return

    def insert_order_blotter(self, *, bot_id: str, rows: Iterable[Dict[str, Any]]) -> None:
        """
        Insert blotter rows (append-only). Duplicates are ignored (best-effort).
        """
        for r in rows:
            self._exec_ignore_duplicate(
                """
                INSERT INTO order_blotter (
                  bot_id, ts, direction, level, price, size, notional, commission, leg,
                  exchange_order_id, client_order_id, trade_id, raw_json
                ) VALUES (
                  %(bot_id)s, %(ts)s, %(direction)s, %(level)s, %(price)s, %(size)s, %(notional)s,
                  %(commission)s, %(leg)s, %(exchange_order_id)s, %(client_order_id)s, %(trade_id)s, %(raw_json)s::jsonb
                )
                """,
                {
                    "bot_id": bot_id,
                    "ts": r.get("ts") or r.get("timestamp") or _utc_now(),
                    "direction": r.get("direction"),
                    "level": r.get("level"),
                    "price": r.get("price"),
                    "size": r.get("size"),
                    "notional": r.get("notional"),
                    "commission": r.get("commission"),
                    "leg": r.get("leg"),
                    "exchange_order_id": r.get("exchange_order_id"),
                    "client_order_id": r.get("client_order_id"),
                    "trade_id": r.get("trade_id"),
                    "raw_json": json.dumps(r, ensure_ascii=False),
                },
            )

    def upsert_exchange_open_orders_current(
        self, *, bot_id: str, ts: datetime, rows: Iterable[Dict[str, Any]]
    ) -> None:
        for r in rows:
            try:
                exchange_order_id = str(r.get("order_id") or "")
                if not exchange_order_id:
                    continue
                self._exec(
                    """
                    INSERT INTO exchange_open_orders_current (
                      bot_id, exchange_order_id, ts, client_order_id, side, price, size, status, raw_json
                    ) VALUES (
                      %(bot_id)s, %(exchange_order_id)s, %(ts)s, %(client_order_id)s, %(side)s, %(price)s,
                      %(size)s, %(status)s, %(raw_json)s::jsonb
                    )
                    ON CONFLICT (bot_id, exchange_order_id) DO UPDATE SET
                      ts = EXCLUDED.ts,
                      client_order_id = EXCLUDED.client_order_id,
                      side = EXCLUDED.side,
                      price = EXCLUDED.price,
                      size = EXCLUDED.size,
                      status = EXCLUDED.status,
                      raw_json = EXCLUDED.raw_json
                    """,
                    {
                        "bot_id": bot_id,
                        "exchange_order_id": exchange_order_id,
                        "ts": ts,
                        "client_order_id": r.get("client_order_id"),
                        "side": r.get("side"),
                        "price": float(r.get("price") or 0.0),
                        "size": float(r.get("quantity") or r.get("size") or 0.0),
                        "status": r.get("status"),
                        "raw_json": json.dumps(r, ensure_ascii=False),
                    },
                )
            except Exception:
                continue

    def upsert_exchange_positions_current(
        self, *, bot_id: str, ts: datetime, rows: Iterable[Dict[str, Any]]
    ) -> None:
        for r in rows:
            try:
                side = str(r.get("side") or "spot").lower()
                self._exec(
                    """
                    INSERT INTO exchange_positions_current (
                      bot_id, side, ts, qty, entry_price, raw_json
                    ) VALUES (
                      %(bot_id)s, %(side)s, %(ts)s, %(qty)s, %(entry_price)s, %(raw_json)s::jsonb
                    )
                    ON CONFLICT (bot_id, side) DO UPDATE SET
                      ts = EXCLUDED.ts,
                      qty = EXCLUDED.qty,
                      entry_price = EXCLUDED.entry_price,
                      raw_json = EXCLUDED.raw_json
                    """,
                    {
                        "bot_id": bot_id,
                        "side": side,
                        "ts": ts,
                        "qty": float(r.get("quantity") or r.get("qty") or 0.0),
                        "entry_price": float(r.get("entry_price") or r.get("avg_price") or 0.0),
                        "raw_json": json.dumps(r, ensure_ascii=False),
                    },
                )
            except Exception:
                continue

    def upsert_replay_cursor(self, *, bot_id: str, last_seen_trade_id: Optional[str], last_seen_ts: Optional[datetime]) -> None:
        self._exec(
            """
            INSERT INTO replay_cursor (bot_id, last_seen_trade_id, last_seen_ts, updated_at)
            VALUES (%(bot_id)s, %(last_seen_trade_id)s, %(last_seen_ts)s, NOW())
            ON CONFLICT (bot_id) DO UPDATE SET
              last_seen_trade_id = EXCLUDED.last_seen_trade_id,
              last_seen_ts = EXCLUDED.last_seen_ts,
              updated_at = NOW()
            """,
            {"bot_id": bot_id, "last_seen_trade_id": last_seen_trade_id, "last_seen_ts": last_seen_ts},
        )

    def insert_trade_fills(self, *, bot_id: str, rows: Iterable[Dict[str, Any]]) -> None:
        """
        Insert trade fills (append-only). Duplicates are ignored (best-effort).
        """
        for r in rows:
            self._exec_ignore_duplicate(
                """
                INSERT INTO trade_fills (
                  bot_id, ts, trade_id, exchange_order_id, client_order_id, side,
                  price, qty, fee, fee_currency, raw_json
                ) VALUES (
                  %(bot_id)s, %(ts)s, %(trade_id)s, %(exchange_order_id)s, %(client_order_id)s, %(side)s,
                  %(price)s, %(qty)s, %(fee)s, %(fee_currency)s, %(raw_json)s::jsonb
                )
                """,
                {
                    "bot_id": bot_id,
                    "ts": r.get("ts") or _utc_now(),
                    "trade_id": r.get("trade_id"),
                    "exchange_order_id": r.get("exchange_order_id"),
                    "client_order_id": r.get("client_order_id"),
                    "side": r.get("side"),
                    "price": r.get("price"),
                    "qty": r.get("qty"),
                    "fee": r.get("fee"),
                    "fee_currency": r.get("fee_currency"),
                    "raw_json": json.dumps(r, ensure_ascii=False),
                },
            )

    # ----------------------------
    # Reads (dashboard)
    # ----------------------------
    def get_latest_state(self, *, bot_id: str) -> Optional[Dict[str, Any]]:
        row = self._fetchone(
            "SELECT bot_id, ts, mode, payload FROM bot_state_current WHERE bot_id=%(bot_id)s",
            {"bot_id": bot_id},
        )
        return row

    def get_latest_heartbeat(self, *, bot_id: str) -> Optional[Dict[str, Any]]:
        return self._fetchone(
            """
            SELECT bot_id, ts, mode, last_bar_ts, lag_seconds, status,
                   data_feed_status, exchange_api_status, exchange_error_count, payload
            FROM bot_heartbeat
            WHERE bot_id=%(bot_id)s
            ORDER BY ts DESC
            LIMIT 1
            """,
            {"bot_id": bot_id},
        )

    def get_replay_cursor(self, *, bot_id: str) -> Optional[Dict[str, Any]]:
        return self._fetchone(
            "SELECT bot_id, last_seen_trade_id, last_seen_ts, updated_at FROM replay_cursor WHERE bot_id=%(bot_id)s",
            {"bot_id": bot_id},
        )

    # ============================================================
    # V2 Schema Methods: Session & Order Event Tracking
    # ============================================================

    def create_session(
        self,
        *,
        session_id: str,
        bot_id: str,
        symbol: str,
        mode: str,
        version: Optional[str] = None,
        config_snapshot: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> None:
        """Create a new session record when bot starts."""
        self._exec(
            """
            INSERT INTO sessions (
                session_id, bot_id, symbol, mode, version, config_snapshot, notes
            ) VALUES (
                %(session_id)s, %(bot_id)s, %(symbol)s, %(mode)s, %(version)s,
                %(config_snapshot)s::jsonb, %(notes)s
            )
            ON CONFLICT (session_id) DO NOTHING
            """,
            {
                "session_id": session_id,
                "bot_id": bot_id,
                "symbol": symbol,
                "mode": mode,
                "version": version,
                "config_snapshot": json.dumps(config_snapshot or {}, ensure_ascii=False),
                "notes": notes,
            },
        )

    def update_session_startup_stats(
        self,
        *,
        session_id: str,
        orders_cancelled: int,
        orders_placed: int,
        position_qty: Optional[float] = None,
    ) -> None:
        """Update session with bootstrap statistics."""
        self._exec(
            """
            UPDATE sessions SET
                startup_orders_cancelled = %(orders_cancelled)s,
                startup_orders_placed = %(orders_placed)s,
                startup_position_qty = %(position_qty)s
            WHERE session_id = %(session_id)s
            """,
            {
                "session_id": session_id,
                "orders_cancelled": orders_cancelled,
                "orders_placed": orders_placed,
                "position_qty": position_qty,
            },
        )

    def end_session(
        self,
        *,
        session_id: str,
        end_reason: str,
    ) -> None:
        """Mark session as ended."""
        self._exec(
            """
            UPDATE sessions SET
                ended_at = NOW(),
                end_reason = %(end_reason)s
            WHERE session_id = %(session_id)s
            """,
            {
                "session_id": session_id,
                "end_reason": end_reason,
            },
        )

    def upsert_order(
        self,
        *,
        session_id: str,
        bot_id: str,
        client_order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        price: Optional[float],
        qty: float,
        status: str,
        grid_level: Optional[int] = None,
        leg: Optional[str] = None,
        reason: Optional[str] = None,
        exchange_order_id: Optional[str] = None,
    ) -> Optional[int]:
        """Insert or update an order record. Returns the order id."""
        row = self._fetchone(
            """
            INSERT INTO orders (
                session_id, bot_id, client_order_id, symbol, side, order_type,
                price, qty, status, grid_level, leg, reason, exchange_order_id
            ) VALUES (
                %(session_id)s, %(bot_id)s, %(client_order_id)s, %(symbol)s,
                %(side)s, %(order_type)s, %(price)s, %(qty)s, %(status)s,
                %(grid_level)s, %(leg)s, %(reason)s, %(exchange_order_id)s
            )
            ON CONFLICT (bot_id, client_order_id) DO UPDATE SET
                exchange_order_id = COALESCE(EXCLUDED.exchange_order_id, orders.exchange_order_id),
                status = EXCLUDED.status,
                updated_at = NOW()
            RETURNING id
            """,
            {
                "session_id": session_id,
                "bot_id": bot_id,
                "client_order_id": client_order_id,
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "price": price,
                "qty": qty,
                "status": status,
                "grid_level": grid_level,
                "leg": leg,
                "reason": reason,
                "exchange_order_id": exchange_order_id,
            },
        )
        return row["id"] if row else None

    def update_order_status(
        self,
        *,
        bot_id: str,
        client_order_id: str,
        status: str,
        exchange_order_id: Optional[str] = None,
        filled_qty: Optional[float] = None,
        avg_fill_price: Optional[float] = None,
        total_fee: Optional[float] = None,
    ) -> None:
        """Update order status and fill info."""
        updates = ["status = %(status)s", "updated_at = NOW()"]
        params: Dict[str, Any] = {
            "bot_id": bot_id,
            "client_order_id": client_order_id,
            "status": status,
        }
        if exchange_order_id is not None:
            updates.append("exchange_order_id = %(exchange_order_id)s")
            params["exchange_order_id"] = exchange_order_id
        if filled_qty is not None:
            updates.append("filled_qty = %(filled_qty)s")
            params["filled_qty"] = filled_qty
        if avg_fill_price is not None:
            updates.append("avg_fill_price = %(avg_fill_price)s")
            params["avg_fill_price"] = avg_fill_price
        if total_fee is not None:
            updates.append("total_fee = %(total_fee)s")
            params["total_fee"] = total_fee
        if status in ("filled", "cancelled", "rejected"):
            updates.append("closed_at = NOW()")

        self._exec(
            f"""
            UPDATE orders SET {', '.join(updates)}
            WHERE bot_id = %(bot_id)s AND client_order_id = %(client_order_id)s
            """,
            params,
        )

    def insert_order_event(
        self,
        *,
        session_id: str,
        client_order_id: str,
        event_type: str,
        trigger: str,
        new_status: str,
        old_status: Optional[str] = None,
        order_id: Optional[int] = None,
        exchange_order_id: Optional[str] = None,
        fill_qty: Optional[float] = None,
        fill_price: Optional[float] = None,
        fill_fee: Optional[float] = None,
        trade_id: Optional[str] = None,
        exchange_ts: Optional[datetime] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Insert an order event for audit trail."""
        self._exec_ignore_duplicate(
            """
            INSERT INTO order_events (
                session_id, order_id, client_order_id, exchange_order_id,
                event_type, trigger, old_status, new_status,
                fill_qty, fill_price, fill_fee, trade_id, exchange_ts, details
            ) VALUES (
                %(session_id)s, %(order_id)s, %(client_order_id)s, %(exchange_order_id)s,
                %(event_type)s, %(trigger)s, %(old_status)s, %(new_status)s,
                %(fill_qty)s, %(fill_price)s, %(fill_fee)s, %(trade_id)s, %(exchange_ts)s,
                %(details)s::jsonb
            )
            """,
            {
                "session_id": session_id,
                "order_id": order_id,
                "client_order_id": client_order_id,
                "exchange_order_id": exchange_order_id,
                "event_type": event_type,
                "trigger": trigger,
                "old_status": old_status,
                "new_status": new_status,
                "fill_qty": fill_qty,
                "fill_price": fill_price,
                "fill_fee": fill_fee,
                "trade_id": trade_id,
                "exchange_ts": exchange_ts,
                "details": json.dumps(details or {}, ensure_ascii=False),
            },
        )

    def insert_error_log(
        self,
        *,
        bot_id: str,
        level: str,
        message: str,
        session_id: Optional[str] = None,
        component: Optional[str] = None,
        error_code: Optional[str] = None,
        symbol: Optional[str] = None,
        order_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Insert an error log entry."""
        self._exec_ignore_duplicate(
            """
            INSERT INTO error_logs (
                session_id, bot_id, level, component, error_code, message,
                symbol, order_id, details
            ) VALUES (
                %(session_id)s, %(bot_id)s, %(level)s, %(component)s, %(error_code)s,
                %(message)s, %(symbol)s, %(order_id)s, %(details)s::jsonb
            )
            """,
            {
                "session_id": session_id,
                "bot_id": bot_id,
                "level": level,
                "component": component,
                "error_code": error_code,
                "message": message,
                "symbol": symbol,
                "order_id": order_id,
                "details": json.dumps(details or {}, ensure_ascii=False),
            },
        )


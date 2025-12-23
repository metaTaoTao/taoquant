from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class Market24hStats:
    """24h market stats computed from 1m bars."""

    open_24h: float
    close: float
    change_24h: float
    change_24h_pct: float
    high_24h: float
    low_24h: float
    volume_24h: float
    bars_used: int
    window_seconds: int


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        if v != v:  # NaN
            return default
        return v
    except Exception:
        return default


def _parse_ts_iso(ts: Any) -> Optional[datetime]:
    if not ts:
        return None
    try:
        # Accept both "...Z" and "+00:00"
        s = str(ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _read_jsonl_tail(path: Path, max_lines: int) -> List[Dict[str, Any]]:
    """
    Read last N JSONL lines (best-effort).

    Note: This is intentionally simple (no mmap/seek) because N is small (<= 3000).
    """
    if max_lines <= 0 or not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    tail = lines[-max_lines:]
    out: List[Dict[str, Any]] = []
    for ln in tail:
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def compute_24h_stats_from_bars(
    bars: Iterable[Dict[str, Any]],
    *,
    now: datetime,
    window: timedelta = timedelta(hours=24),
) -> Optional[Market24hStats]:
    """
    Compute 24h stats from 1m bars (best-effort).

    If there isn't enough data, we compute from what we have inside the window.
    """
    now_utc = now.astimezone(timezone.utc)
    start = now_utc - window

    filtered: List[Dict[str, Any]] = []
    for b in bars:
        ts = _parse_ts_iso(b.get("ts") or b.get("timestamp"))
        if ts is None:
            continue
        if ts < start or ts > now_utc + timedelta(minutes=5):
            continue
        filtered.append(b)

    if not filtered:
        return None

    # Sort by timestamp to find window open/close robustly
    filtered.sort(key=lambda x: _parse_ts_iso(x.get("ts") or x.get("timestamp")) or now_utc)

    open_24h = _safe_float(filtered[0].get("open") or filtered[0].get("close"), 0.0)
    close = _safe_float(filtered[-1].get("close"), 0.0)
    high_24h = max(_safe_float(b.get("high"), close) for b in filtered)
    low_24h = min(_safe_float(b.get("low"), close) for b in filtered)
    volume_24h = sum(_safe_float(b.get("volume"), 0.0) for b in filtered)

    change_24h = close - open_24h
    change_24h_pct = (change_24h / open_24h) if open_24h > 0 else 0.0

    window_seconds = int(((_parse_ts_iso(filtered[-1].get("ts") or filtered[-1].get("timestamp")) or now_utc) -
                          (_parse_ts_iso(filtered[0].get("ts") or filtered[0].get("timestamp")) or now_utc)).total_seconds())

    return Market24hStats(
        open_24h=float(open_24h),
        close=float(close),
        change_24h=float(change_24h),
        change_24h_pct=float(change_24h_pct),
        high_24h=float(high_24h),
        low_24h=float(low_24h),
        volume_24h=float(volume_24h),
        bars_used=len(filtered),
        window_seconds=max(0, window_seconds),
    )


def enrich_status_with_market_24h(
    status: Dict[str, Any],
    *,
    bars_jsonl_path: Path,
    now: datetime,
    max_lines: int = 2000,
) -> Dict[str, Any]:
    """
    Enrich status dict (from live_status.json) with computed 24h stats.

    This keeps the runner clean: runner only emits raw bar + trading state, dashboard
    computes derived 24h market stats.
    """
    if not isinstance(status, dict):
        return status
    market = status.get("market")
    if not isinstance(market, dict):
        return status

    bars = _read_jsonl_tail(bars_jsonl_path, max_lines=max_lines)
    stats = compute_24h_stats_from_bars(bars, now=now)
    if stats is None:
        # If we can't compute, keep existing fields.
        return status

    market["change_24h"] = stats.change_24h
    market["change_24h_pct"] = stats.change_24h_pct
    market["high_24h"] = stats.high_24h
    market["low_24h"] = stats.low_24h

    # The dashboard UI uses `market.volume` as 24h volume.
    market["volume_24h"] = stats.volume_24h
    market["volume"] = stats.volume_24h

    # Diagnostics (optional, safe to ignore on frontend)
    market["_bars_used_24h"] = stats.bars_used
    market["_window_seconds_24h"] = stats.window_seconds

    status["market"] = market
    return status


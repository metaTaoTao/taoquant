"""
Probe how far back OKX public funding-rate-history can be paged.

This script repeatedly requests:
  GET https://www.okx.com/api/v5/public/funding-rate-history?instId=...&limit=100&after=...

Empirical behavior observed:
  - No params / after=now: returns most recent records
  - Move 'after' cursor to (oldest_fundingTime - 1ms) to page older records
  - Eventually API returns empty data -> indicates history depth limit.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple

import requests


def _ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


@dataclass
class PageInfo:
    page: int
    count: int
    newest_ms: int
    oldest_ms: int


def _fetch_page(inst_id: str, after_ms: Optional[int], limit: int = 100) -> Tuple[list[dict], dict]:
    base = "https://www.okx.com"
    ep = "/api/v5/public/funding-rate-history"
    params = {"instId": inst_id, "limit": str(limit)}
    if after_ms is not None:
        params["after"] = str(after_ms)
    r = requests.get(base + ep, params=params, timeout=10)
    r.raise_for_status()
    payload = r.json()
    return payload.get("data", []) or [], payload


def probe(inst_id: str, max_pages: int = 300, sleep_s: float = 0.05) -> None:
    after = int(time.time() * 1000)
    last_non_empty_oldest: Optional[int] = None
    pages: list[PageInfo] = []

    for i in range(max_pages):
        data, payload = _fetch_page(inst_id=inst_id, after_ms=after, limit=100)
        if payload.get("code") != "0":
            raise RuntimeError(f"OKX error: {payload}")
        if not data:
            print(f"STOP: empty page at page={i}, after={after} ({_ms_to_dt(after)})")
            break

        times = [int(x["fundingTime"]) for x in data if "fundingTime" in x]
        newest = max(times)
        oldest = min(times)
        pages.append(PageInfo(page=i, count=len(times), newest_ms=newest, oldest_ms=oldest))
        last_non_empty_oldest = oldest

        print(
            f"page={i:03d} n={len(times):3d} "
            f"newest={_ms_to_dt(newest).isoformat()} "
            f"oldest={_ms_to_dt(oldest).isoformat()}"
        )

        # move cursor older
        after = oldest - 1
        time.sleep(sleep_s)

    if last_non_empty_oldest is None:
        print("No data returned at all.")
        return

    earliest = _ms_to_dt(last_non_empty_oldest)
    latest = _ms_to_dt(pages[0].newest_ms) if pages else None
    print()
    print(f"RESULT instId={inst_id}")
    print(f"  latest_seen:   {latest.isoformat() if latest else 'N/A'}")
    print(f"  earliest_seen: {earliest.isoformat()}")
    print(f"  pages: {len(pages)}")


if __name__ == "__main__":
    probe("BTC-USDT-SWAP")



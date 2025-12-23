from __future__ import annotations

import json
import os
import subprocess
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from dashboard.services.market_data_service import enrich_status_with_market_24h

try:
    from persistence.db import PostgresStore
except Exception:  # pragma: no cover
    PostgresStore = None  # type: ignore[assignment]


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v is not None and v != "" else default


BASE_DIR = Path(_env("TAOQUANT_BASE_DIR", str(Path(__file__).resolve().parents[1]))).resolve()
STATE_DIR = Path(_env("TAOQUANT_STATE_DIR", str(BASE_DIR / "state"))).resolve()
STATUS_FILE = Path(_env("TAOQUANT_STATUS_FILE", str(STATE_DIR / "live_status.json"))).resolve()
CONFIG_FILE = Path(_env("TAOQUANT_CONFIG_FILE", str(BASE_DIR / "config_live.json"))).resolve()
CONFIG_VERSIONS_DIR = Path(_env("TAOQUANT_CONFIG_VERSIONS_DIR", str(STATE_DIR / "config_versions"))).resolve()
LOG_DIR = Path(_env("TAOQUANT_LOG_DIR", str(BASE_DIR / "logs" / "bitget_live"))).resolve()
SERVICE_NAME = _env("TAOQUANT_SERVICE_NAME", "taoquant.service")
TOKEN = os.getenv("TAOQUANT_DASHBOARD_TOKEN")  # if set, all endpoints require Bearer token
ENABLE_CONTROL = _env("TAOQUANT_ENABLE_CONTROL", "0").strip().lower() in ("1", "true", "yes")
MARKET_BARS_FILE = Path(_env("TAOQUANT_MARKET_BARS_FILE", str(STATE_DIR / "market_bars_1m.jsonl"))).resolve()
DEFAULT_BOT_ID = _env("TAOQUANT_BOT_ID", "")

# Optional DB (best-effort)
_DB = None
try:
    if PostgresStore is not None:
        _DB = PostgresStore.from_env()
except Exception:
    _DB = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_auth(request: Request) -> None:
    if not TOKEN:
        return
    auth = request.headers.get("authorization") or ""
    if auth.strip() != f"Bearer {TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")

def _require_control(request: Request) -> None:
    _require_auth(request)
    if not ENABLE_CONTROL:
        raise HTTPException(
            status_code=403,
            detail="Control endpoints are disabled (read-only mode). Set TAOQUANT_ENABLE_CONTROL=1 to enable.",
        )


def _run(cmd: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )

def _has_systemctl() -> bool:
    return shutil.which("systemctl") is not None

def _require_systemctl() -> None:
    if not _has_systemctl():
        # Local Windows / non-systemd environments
        raise HTTPException(
            status_code=501,
            detail="systemctl not available on this machine; bot control endpoints are disabled (read-only mode).",
        )


def _systemctl(action: str) -> Dict[str, Any]:
    # For cloud (Linux) use systemd; return structured info.
    if not _has_systemctl():
        return {
            "ok": False,
            "returncode": 127,
            "status": "unsupported",
            "stderr": "systemctl not available",
            "cmd": ["systemctl", action, SERVICE_NAME],
            "ts": _now_iso(),
        }
    p = _run(["systemctl", action, SERVICE_NAME], timeout=30)
    return {
        "ok": p.returncode == 0,
        "returncode": p.returncode,
        "stdout": p.stdout,
        "stderr": p.stderr,
        "cmd": ["systemctl", action, SERVICE_NAME],
        "ts": _now_iso(),
    }


def _systemctl_is_active() -> Dict[str, Any]:
    if not _has_systemctl():
        return {
            "ok": False,
            "returncode": 127,
            "status": "unsupported",
            "stderr": "systemctl not available",
            "ts": _now_iso(),
        }
    p = _run(["systemctl", "is-active", SERVICE_NAME], timeout=10)
    status = (p.stdout or "").strip()
    return {
        "ok": p.returncode == 0,
        "returncode": p.returncode,
        "status": status,
        "stdout": p.stdout,
        "stderr": p.stderr,
        "ts": _now_iso(),
    }


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _parse_ts(ts: Any) -> Optional[datetime]:
    if not ts:
        return None
    try:
        s = str(ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None

def _apply_offline_status(
    st: Dict[str, Any],
    *,
    heartbeat_ts: Optional[datetime],
    lag_seconds: Optional[float],
    exchange_api_status: Optional[str],
) -> Dict[str, Any]:
    """
    Fill `system.bot_status` with layered states:
    - RUNNER_DOWN
    - DATA_FEED_STALE
    - EXCHANGE_API_DEGRADED
    - RUNNING
    """
    now = datetime.now(timezone.utc)
    hb_age = (now - heartbeat_ts).total_seconds() if heartbeat_ts else None
    bot_status = "RUNNING"
    if hb_age is None or hb_age > 120:
        bot_status = "RUNNER_DOWN"
    elif lag_seconds is not None and lag_seconds > 90:
        bot_status = "DATA_FEED_STALE"
    elif (exchange_api_status or "").upper() in ("DEGRADED", "ERROR"):
        bot_status = "EXCHANGE_API_DEGRADED"

    sys_obj = st.get("system")
    if not isinstance(sys_obj, dict):
        sys_obj = {}
    sys_obj["bot_status"] = bot_status
    if heartbeat_ts:
        sys_obj["last_heartbeat"] = heartbeat_ts.isoformat()
        sys_obj["actual_last_bar_seconds_ago"] = hb_age if hb_age is not None else 0
    st["system"] = sys_obj
    return st


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _latest_log_file() -> Optional[Path]:
    if not LOG_DIR.exists():
        return None
    files = sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _tail_text(path: Path, n: int = 400) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    if n <= 0:
        return "\n".join(lines)
    return "\n".join(lines[-n:])


app = FastAPI(title="TaoQuant Dashboard", version="0.1.0")

# Setup Jinja2 templates
DASHBOARD_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(DASHBOARD_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Serve the main dashboard page."""
    # Load current status for initial render
    st = _read_json(STATUS_FILE)
    mode = _env("TAOQUANT_MODE", "dryrun").upper()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "mode": mode,
        "status": st,
    })

@app.get("/legacy", response_class=HTMLResponse)
def home_legacy() -> str:
    # Legacy simple dashboard (kept for reference)
    if not ENABLE_CONTROL:
        # remove bot control card entirely in read-only mode
        return """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>TaoQuant Dashboard</title>
    <style>
      body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; margin: 24px; }
      .row { display: flex; gap: 16px; flex-wrap: wrap; }
      .card { border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px; min-width: 260px; }
      .k { color: #6b7280; font-size: 12px; }
      .v { font-weight: 600; font-size: 18px; }
      pre { background: #0b1020; color: #c7d2fe; padding: 12px; border-radius: 10px; overflow: auto; }
      button { padding: 8px 12px; border-radius: 8px; border: 1px solid #e5e7eb; background: #fff; cursor: pointer; }
      button:hover { background: #f9fafb; }
      .danger { border-color: #fecaca; color: #991b1b; }
    </style>
  </head>
  <body>
    <h2>TaoQuant Dashboard</h2>
    <div class="row">
      <div class="card">
        <div class="k">价格 / 时间</div>
        <div class="v" id="price">-</div>
        <div class="k" id="ts">-</div>
      </div>
      <div class="card">
        <div class="k">权益 / PnL</div>
        <div class="v" id="equity">-</div>
        <div class="k" id="pnl">-</div>
      </div>
      <div class="card">
        <div class="k">风险 / 网格</div>
        <div class="v" id="risk">-</div>
        <div class="k" id="grid">-</div>
      </div>
    </div>

    <h3 style="margin-top:20px;">最近日志</h3>
    <pre id="logs">(loading...)</pre>

    <script>
      async function fetchJSON(path) {
        const r = await fetch(path);
        if (!r.ok) throw new Error(await r.text());
        return await r.json();
      }
      function fmtUSD(x) {
        if (x === null || x === undefined || isNaN(x)) return "-";
        return "$" + Number(x).toFixed(2);
      }
      async function refresh() {
        try {
          const st = await fetchJSON('/api/status');
          const px = st.market && st.market.close;
          document.getElementById('price').textContent = px ? Number(px).toFixed(2) : '-';
          document.getElementById('ts').textContent = st.ts || '-';
          document.getElementById('equity').textContent = fmtUSD(st.portfolio && st.portfolio.equity);
          const upnl = st.portfolio && st.portfolio.unrealized_pnl;
          const rpnl = st.portfolio && st.portfolio.realized_pnl;
          document.getElementById('pnl').textContent = `unreal=${fmtUSD(upnl)}  realized=${fmtUSD(rpnl)}`;
          const rl = st.risk && st.risk.risk_level;
          const ge = st.risk && st.risk.grid_enabled;
          document.getElementById('risk').textContent = `risk_level=${rl} grid_enabled=${ge}`;
          const sup = st.grid && st.grid.support;
          const res = st.grid && st.grid.resistance;
          document.getElementById('grid').textContent = `S=${sup} R=${res}`;
        } catch (e) {
          console.log(e);
        }
        try {
          const r = await fetch('/api/logs?tail=200');
          document.getElementById('logs').textContent = await r.text();
        } catch (e) {}
      }
      refresh();
      setInterval(refresh, 5000);
    </script>
  </body>
</html>
"""

    # Control-enabled HTML (includes systemctl buttons)
    return """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>TaoQuant Dashboard</title>
    <style>
      body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; margin: 24px; }
      .row { display: flex; gap: 16px; flex-wrap: wrap; }
      .card { border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px; min-width: 260px; }
      .k { color: #6b7280; font-size: 12px; }
      .v { font-weight: 600; font-size: 18px; }
      pre { background: #0b1020; color: #c7d2fe; padding: 12px; border-radius: 10px; overflow: auto; }
      button { padding: 8px 12px; border-radius: 8px; border: 1px solid #e5e7eb; background: #fff; cursor: pointer; }
      button:hover { background: #f9fafb; }
      .danger { border-color: #fecaca; color: #991b1b; }
    </style>
  </head>
  <body>
    <h2>TaoQuant Dashboard</h2>
    <div class="row">
      <div class="card">
        <div class="k">价格 / 时间</div>
        <div class="v" id="price">-</div>
        <div class="k" id="ts">-</div>
      </div>
      <div class="card">
        <div class="k">权益 / PnL</div>
        <div class="v" id="equity">-</div>
        <div class="k" id="pnl">-</div>
      </div>
      <div class="card">
        <div class="k">风险 / 网格</div>
        <div class="v" id="risk">-</div>
        <div class="k" id="grid">-</div>
      </div>
      <div class="card">
        <div class="k">机器人</div>
        <div class="v" id="svc">-</div>
        <div style="margin-top: 10px; display:flex; gap:10px; flex-wrap:wrap;">
          <button onclick="bot('restart')">重启</button>
          <button class="danger" onclick="bot('stop')">停止</button>
          <button onclick="bot('start')">启动</button>
        </div>
      </div>
    </div>

    <h3 style="margin-top:20px;">最近日志</h3>
    <pre id="logs">(loading...)</pre>

    <script>
      async function fetchJSON(path) {
        const r = await fetch(path);
        if (!r.ok) throw new Error(await r.text());
        return await r.json();
      }
      function fmtUSD(x) {
        if (x === null || x === undefined || isNaN(x)) return "-";
        return "$" + Number(x).toFixed(2);
      }
      async function refresh() {
        try {
          const st = await fetchJSON('/api/status');
          const px = st.market && st.market.close;
          document.getElementById('price').textContent = px ? Number(px).toFixed(2) : '-';
          document.getElementById('ts').textContent = st.ts || '-';
          document.getElementById('equity').textContent = fmtUSD(st.portfolio && st.portfolio.equity);
          const upnl = st.portfolio && st.portfolio.unrealized_pnl;
          const rpnl = st.portfolio && st.portfolio.realized_pnl;
          document.getElementById('pnl').textContent = `unreal=${fmtUSD(upnl)}  realized=${fmtUSD(rpnl)}`;
          const rl = st.risk && st.risk.risk_level;
          const ge = st.risk && st.risk.grid_enabled;
          document.getElementById('risk').textContent = `risk_level=${rl} grid_enabled=${ge}`;
          const sup = st.grid && st.grid.support;
          const res = st.grid && st.grid.resistance;
          document.getElementById('grid').textContent = `S=${sup} R=${res}`;
          const svc = await fetchJSON('/api/bot/status');
          document.getElementById('svc').textContent = svc.status || 'unknown';
        } catch (e) {
          console.log(e);
        }
        try {
          const r = await fetch('/api/logs?tail=200');
          document.getElementById('logs').textContent = await r.text();
        } catch (e) {}
      }
      async function bot(action) {
        try {
          const r = await fetch('/api/bot/' + action, { method: 'POST' });
          alert(await r.text());
          await refresh();
        } catch (e) {
          alert(String(e));
        }
      }
      refresh();
      setInterval(refresh, 5000);
    </script>
  </body>
</html>
"""


@app.get("/api/status")
def api_status(request: Request, bot_id: Optional[str] = None) -> Dict[str, Any]:
    _require_auth(request)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_VERSIONS_DIR.mkdir(parents=True, exist_ok=True)

    bot_id_final = (bot_id or DEFAULT_BOT_ID or "").strip()
    st: Dict[str, Any] = {}

    # Prefer DB (if configured), fallback to file
    if _DB is not None and bot_id_final:
        try:
            row = _DB.get_latest_state(bot_id=bot_id_final)
            if row and isinstance(row.get("payload"), dict):
                st = row["payload"]
            hb = _DB.get_latest_heartbeat(bot_id=bot_id_final)
            hb_ts = _parse_ts(hb.get("ts")) if isinstance(hb, dict) else None
            lag = None
            try:
                lag = float(hb.get("lag_seconds")) if isinstance(hb, dict) and hb.get("lag_seconds") is not None else None
            except Exception:
                lag = None
            ex_api = str(hb.get("exchange_api_status")) if isinstance(hb, dict) else None
            if st:
                st = _apply_offline_status(st, heartbeat_ts=hb_ts, lag_seconds=lag, exchange_api_status=ex_api)
        except Exception:
            st = {}

    if not st:
        st = _read_json(STATUS_FILE)
        if not st:
            return {"ts": _now_iso(), "note": "status file not found yet", "status_file": str(STATUS_FILE)}

    # Enrich market 24h stats in a clean service (runner only emits raw 1m bars).
    try:
        st = enrich_status_with_market_24h(
            st,
            bars_jsonl_path=MARKET_BARS_FILE,
            now=datetime.now(timezone.utc),
        )
    except Exception:
        pass
    return st


@app.get("/api/logs", response_class=PlainTextResponse)
def api_logs(request: Request, tail: int = 200) -> str:
    _require_auth(request)
    f = _latest_log_file()
    if not f:
        return f"(no log files in {LOG_DIR})"
    return _tail_text(f, n=max(0, min(int(tail), 5000)))


@app.get("/api/bot/status")
def api_bot_status(request: Request) -> Dict[str, Any]:
    _require_auth(request)
    if not ENABLE_CONTROL:
        return {"ok": True, "status": "manual", "ts": _now_iso()}
    return _systemctl_is_active()


@app.post("/api/bot/stop", response_class=PlainTextResponse)
def api_bot_stop(request: Request) -> str:
    _require_control(request)
    _require_systemctl()
    r = _systemctl("stop")
    if not r["ok"]:
        raise HTTPException(status_code=500, detail=r)
    return "ok"


@app.post("/api/bot/start", response_class=PlainTextResponse)
def api_bot_start(request: Request) -> str:
    _require_control(request)
    _require_systemctl()
    r = _systemctl("start")
    if not r["ok"]:
        raise HTTPException(status_code=500, detail=r)
    return "ok"


@app.post("/api/bot/restart", response_class=PlainTextResponse)
def api_bot_restart(request: Request) -> str:
    _require_control(request)
    _require_systemctl()
    r = _systemctl("restart")
    if not r["ok"]:
        raise HTTPException(status_code=500, detail=r)
    return "ok"


@app.get("/api/config")
def api_get_config(request: Request) -> Dict[str, Any]:
    _require_auth(request)
    cfg = _read_json(CONFIG_FILE)
    return {
        "ts": _now_iso(),
        "config_file": str(CONFIG_FILE),
        "config": cfg,
    }


@app.post("/api/config/draft")
async def api_config_draft(request: Request) -> Dict[str, Any]:
    _require_control(request)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="config must be JSON object")
    # minimal shape check
    if "strategy" not in body or "execution" not in body:
        raise HTTPException(status_code=400, detail="config must include 'strategy' and 'execution'")

    CONFIG_VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    version = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = CONFIG_VERSIONS_DIR / f"config_{version}.json"
    _atomic_write_text(out, json.dumps(body, ensure_ascii=False, indent=2))
    return {"ok": True, "version": version, "path": str(out)}


@app.post("/api/config/apply/{version}", response_class=PlainTextResponse)
def api_config_apply(version: str, request: Request) -> str:
    _require_control(request)
    _require_systemctl()
    src = CONFIG_VERSIONS_DIR / f"config_{version}.json"
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"version not found: {version}")

    # stop -> replace -> start (your requirement: must stop bot before adjusting)
    r1 = _systemctl("stop")
    if not r1["ok"]:
        raise HTTPException(status_code=500, detail={"step": "stop", **r1})

    _atomic_write_text(CONFIG_FILE, src.read_text(encoding="utf-8"))

    r2 = _systemctl("start")
    if not r2["ok"]:
        raise HTTPException(status_code=500, detail={"step": "start", **r2})

    return "ok"



#!/bin/bash
# Live deployment verification script
# Run this after services are started to verify everything works

set -e

echo "=========================================="
echo "TaoQuant Live Deployment Verification"
echo "=========================================="
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

_pass() { echo -e "${GREEN}✅ $1${NC}"; }
_fail() { echo -e "${RED}❌ $1${NC}"; }
_warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }

# Test 1: Services are running
echo "Test 1: Service status..."
if systemctl is-active --quiet taoquant-runner; then
    _pass "Runner service is RUNNING"
else
    _fail "Runner service is NOT running (check: sudo systemctl status taoquant-runner)"
fi

if systemctl is-active --quiet taoquant-dashboard; then
    _pass "Dashboard service is RUNNING"
else
    _fail "Dashboard service is NOT running (check: sudo systemctl status taoquant-dashboard)"
fi

# Test 2: Dashboard responds
echo ""
echo "Test 2: Dashboard HTTP endpoint..."
DASHBOARD_URL="http://127.0.0.1:8000/api/status"
AUTH_HEADER=""
if [ -n "$TAOQUANT_DASHBOARD_TOKEN" ]; then
    AUTH_HEADER="Authorization: Bearer ${TAOQUANT_DASHBOARD_TOKEN}"
fi

if [ -n "$AUTH_HEADER" ]; then
    CURL_OK_CMD=(curl -s -f -H "$AUTH_HEADER" "$DASHBOARD_URL")
    CURL_CMD=(curl -s -H "$AUTH_HEADER" "$DASHBOARD_URL")
else
    CURL_OK_CMD=(curl -s -f "$DASHBOARD_URL")
    CURL_CMD=(curl -s "$DASHBOARD_URL")
fi

if "${CURL_OK_CMD[@]}" > /dev/null 2>&1; then
    _pass "Dashboard API responds"
    
    # Check status content
    STATUS=$("${CURL_CMD[@]}")
    if echo "$STATUS" | grep -q '"mode"'; then
        MODE=$(echo "$STATUS" | grep -o '"mode":"[^"]*"' | cut -d'"' -f4)
        _pass "Dashboard returns status (mode: $MODE)"
    else
        _warn "Dashboard returns but status format unexpected"
    fi
else
    if [ -n "$AUTH_HEADER" ]; then
        _fail "Dashboard API not responding (check: curl -H \"$AUTH_HEADER\" $DASHBOARD_URL)"
    else
        _fail "Dashboard API not responding (check: curl $DASHBOARD_URL)"
    fi
fi

# Test 3: Check recent logs for errors
echo ""
echo "Test 3: Recent logs (last 20 lines)..."
if journalctl -u taoquant-runner -n 20 --no-pager | grep -i "error\|exception\|traceback" | head -5; then
    _warn "Found errors in runner logs (review above)"
else
    _pass "No obvious errors in recent runner logs"
fi

# Test 4: Check state files
echo ""
echo "Test 4: State files..."
if [ -f /opt/taoquant/state/live_status.json ]; then
    _pass "live_status.json exists"
    
    # Check timestamp is recent (< 5 minutes old)
    FILE_AGE=$(($(date +%s) - $(stat -c %Y /opt/taoquant/state/live_status.json)))
    if [ $FILE_AGE -lt 300 ]; then
        _pass "live_status.json is recent (${FILE_AGE}s ago)"
    else
        _warn "live_status.json is stale (${FILE_AGE}s old, runner may not be updating)"
    fi
else
    _warn "live_status.json not found (runner may not have started yet)"
fi

# Test 5: PostgreSQL (if configured)
echo ""
echo "Test 5: PostgreSQL (if configured)..."
if [ -n "$TAOQUANT_DB_DSN" ] || [ -n "$TAOQUANT_DB_HOST" ]; then
    if sudo docker ps | grep -q "taoquant-postgres"; then
        _pass "PostgreSQL container running"
        
        export PGPASSWORD="${TAOQUANT_DB_PASSWORD:-taoquant}"
        if psql -h 127.0.0.1 -p 5432 -U taoquant -d taoquant -c "SELECT COUNT(*) FROM bot_heartbeat;" &>/dev/null; then
            HB_COUNT=$(psql -h 127.0.0.1 -p 5432 -U taoquant -d taoquant -t -c "SELECT COUNT(*) FROM bot_heartbeat;" 2>/dev/null | tr -d ' ')
            if [ "$HB_COUNT" -gt 0 ]; then
                _pass "Database has heartbeat records ($HB_COUNT rows)"
            else
                _warn "Database connected but no heartbeat records yet (runner may not have written yet)"
            fi
        else
            _warn "Database connection failed (check TAOQUANT_DB_DSN in .env)"
        fi
    else
        _warn "PostgreSQL container not running"
    fi
else
    _warn "PostgreSQL not configured (TAOQUANT_DB_DSN not set, DB features disabled)"
fi

# Test 6: Check for kill switch
echo ""
echo "Test 6: Safety checks..."
if [ -f /opt/taoquant/state/kill_switch ]; then
    _warn "KILL SWITCH FILE EXISTS - bot will not place new orders!"
else
    _pass "Kill switch file not present (normal operation)"
fi

# Summary
echo ""
echo "=========================================="
echo "Verification Complete"
echo "=========================================="
echo ""
echo "Quick commands:"
echo "  View runner logs:    sudo journalctl -u taoquant-runner -f"
echo "  View dashboard logs: sudo journalctl -u taoquant-dashboard -f"
echo "  Check runner status: sudo systemctl status taoquant-runner"
echo "  Restart runner:      sudo systemctl restart taoquant-runner"
echo "  Access dashboard:   http://YOUR_GCP_IP:8000"
echo ""

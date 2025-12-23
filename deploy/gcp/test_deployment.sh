#!/bin/bash
# End-to-end deployment test script
# Run this after deploy.sh to verify everything works

set -e

echo "=========================================="
echo "TaoQuant GCP Deployment Test"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

_test_pass() {
    echo -e "${GREEN}✅ $1${NC}"
}

_test_fail() {
    echo -e "${RED}❌ $1${NC}"
    exit 1
}

_test_warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Test 1: Check services are installed
echo "Test 1: Checking systemd services..."
if systemctl list-unit-files | grep -q "taoquant-runner.service"; then
    _test_pass "Runner service installed"
else
    _test_fail "Runner service not found"
fi

if systemctl list-unit-files | grep -q "taoquant-dashboard.service"; then
    _test_pass "Dashboard service installed"
else
    _test_fail "Dashboard service not found"
fi

# Test 2: Check PostgreSQL
echo ""
echo "Test 2: Checking PostgreSQL..."
if sudo docker ps | grep -q "taoquant-postgres"; then
    _test_pass "PostgreSQL container is running"
    
    # Test connection
    if command -v psql &> /dev/null; then
        export PGPASSWORD="${TAOQUANT_DB_PASSWORD:-taoquant}"
        if psql -h 127.0.0.1 -p 5432 -U taoquant -d taoquant -c "SELECT 1;" &>/dev/null; then
            _test_pass "PostgreSQL connection successful"
        else
            _test_warn "PostgreSQL connection failed (check password in .env)"
        fi
    else
        _test_warn "psql not installed, skipping connection test"
    fi
else
    _test_warn "PostgreSQL container not running (may need manual start)"
fi

# Test 3: Check .env file
echo ""
echo "Test 3: Checking configuration..."
if [ -f /opt/taoquant/.env ]; then
    _test_pass ".env file exists"
    
    # Check critical vars
    if grep -q "BITGET_API_KEY=" /opt/taoquant/.env && ! grep -q "BITGET_API_KEY=your_api_key_here" /opt/taoquant/.env; then
        _test_pass "BITGET_API_KEY is set"
    else
        _test_warn "BITGET_API_KEY not configured (edit /opt/taoquant/.env)"
    fi
    
    if grep -q "TAOQUANT_DB_DSN=" /opt/taoquant/.env && ! grep -q "TAOQUANT_DB_DSN=$" /opt/taoquant/.env; then
        _test_pass "TAOQUANT_DB_DSN is set"
    else
        _test_warn "TAOQUANT_DB_DSN not configured (optional, but recommended)"
    fi
else
    _test_fail ".env file not found (run deploy.sh first)"
fi

# Test 4: Check Python environment
echo ""
echo "Test 4: Checking Python environment..."
if [ -d /opt/taoquant/.venv ]; then
    _test_pass "Virtual environment exists"
    
    if sudo -u taoquant /opt/taoquant/.venv/bin/python --version &>/dev/null; then
        _test_pass "Python is working"
    else
        _test_fail "Python not working"
    fi
    
    # Check critical packages
    if sudo -u taoquant /opt/taoquant/.venv/bin/python -c "import psycopg" 2>/dev/null; then
        _test_pass "psycopg (PostgreSQL driver) installed"
    else
        _test_warn "psycopg not installed (DB features will be disabled)"
    fi
    
    if sudo -u taoquant /opt/taoquant/.venv/bin/python -c "import fastapi" 2>/dev/null; then
        _test_pass "fastapi installed (dashboard ready)"
    else
        _test_fail "fastapi not installed"
    fi
else
    _test_fail "Virtual environment not found"
fi

# Test 5: Check project structure
echo ""
echo "Test 5: Checking project structure..."
REQUIRED_FILES=(
    "algorithms/taogrid/bitget_live_runner.py"
    "algorithms/taogrid/run_bitget_live.py"
    "dashboard/server.py"
    "persistence/db.py"
    "persistence/schema.sql"
    "config_bitget_live.json"
)

for f in "${REQUIRED_FILES[@]}"; do
    if [ -f "/opt/taoquant/$f" ]; then
        _test_pass "Found: $f"
    else
        _test_fail "Missing: $f"
    fi
done

# Test 6: Test runner can start (dry-run check)
echo ""
echo "Test 6: Testing runner import (dry-run)..."
if sudo -u taoquant bash -c "cd /opt/taoquant && source .venv/bin/activate && python algorithms/taogrid/run_bitget_live.py --help" &>/dev/null; then
    _test_pass "Runner script is importable and shows help"
else
    _test_warn "Runner script has issues (check logs)"
fi

# Test 7: Test dashboard can start
echo ""
echo "Test 7: Testing dashboard import..."
if sudo -u taoquant bash -c "cd /opt/taoquant && source .venv/bin/activate && python -c 'from dashboard.server import app; print(\"OK\")'" &>/dev/null; then
    _test_pass "Dashboard server is importable"
else
    _test_warn "Dashboard import failed (check dependencies)"
fi

# Summary
echo ""
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit /opt/taoquant/.env with your Bitget API credentials"
echo "2. (Optional) Set TAOQUANT_DB_DSN if using PostgreSQL"
echo "3. Edit /opt/taoquant/config_bitget_live.json (check leverage for live!)"
echo "4. Start services:"
echo "   sudo systemctl start taoquant-runner"
echo "   sudo systemctl start taoquant-dashboard"
echo "5. Check status:"
echo "   sudo systemctl status taoquant-runner"
echo "   sudo systemctl status taoquant-dashboard"
echo "6. View logs:"
echo "   sudo journalctl -u taoquant-runner -f"
echo "   sudo journalctl -u taoquant-dashboard -f"
echo "7. Access dashboard: http://YOUR_GCP_IP:8000"
echo ""

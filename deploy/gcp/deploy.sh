#!/bin/bash
# TaoQuant GCP Deployment Script
# Usage: ./deploy.sh [runner|dashboard|all]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOY_TARGET="${1:-all}"

echo "=========================================="
echo "TaoQuant GCP Deployment"
echo "=========================================="
echo "Project root: $PROJECT_ROOT"
echo "Deploy target: $DEPLOY_TARGET"
echo ""

# Check if running as root (for systemd)
if [ "$EUID" -ne 0 ]; then
    echo "⚠️  Note: Some steps require sudo. You may be prompted for password."
fi

# Step 1: Install system dependencies
echo "📦 Step 1: Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip git curl

# Step 2: Create system user (if not exists)
echo "👤 Step 2: Creating system user 'taoquant'..."
if ! id "taoquant" &>/dev/null; then
    sudo useradd -r -s /bin/bash -d /opt/taoquant -m taoquant
    echo "✅ User 'taoquant' created"
else
    echo "✅ User 'taoquant' already exists"
fi

# Step 3: Setup project directory
echo "📁 Step 3: Setting up project directory..."
sudo mkdir -p /opt/taoquant
sudo chown -R taoquant:taoquant /opt/taoquant

# Copy project files (if deploying from local or /tmp)
if [ -d "/tmp/taoquant-source" ]; then
    echo "📋 Copying project files from /tmp/taoquant-source..."
    sudo -u taoquant rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='.venv' --exclude='state/*.json' --exclude='state/*.jsonl' \
        /tmp/taoquant-source/ /opt/taoquant/
elif [ -d "$PROJECT_ROOT" ] && [ "$PROJECT_ROOT" != "/opt/taoquant" ]; then
    echo "📋 Copying project files from $PROJECT_ROOT..."
    sudo -u taoquant rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='.venv' --exclude='state/*.json' --exclude='state/*.jsonl' \
        "$PROJECT_ROOT/" /opt/taoquant/
fi

# Step 4: Setup Python virtual environment
echo "🐍 Step 4: Setting up Python virtual environment..."
sudo -u taoquant bash -c "
    cd /opt/taoquant
    if [ ! -d '.venv' ]; then
        python3.11 -m venv .venv
    fi
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
"

# Step 5: Create state/logs directories
echo "📂 Step 5: Creating state and logs directories..."
sudo -u taoquant mkdir -p /opt/taoquant/state
sudo -u taoquant mkdir -p /opt/taoquant/logs/bitget_live

# Step 5.5: Install and setup PostgreSQL (single-VM, low-cost)
echo "🗄️  Step 5.5: Installing PostgreSQL (Docker)..."
if ! command -v docker &> /dev/null; then
    sudo apt-get install -y docker.io
    sudo systemctl enable --now docker
    sudo usermod -aG docker taoquant
fi

if ! sudo docker ps -a --format '{{.Names}}' | grep -q '^taoquant-postgres$'; then
    echo "📦 Creating PostgreSQL container..."
    sudo mkdir -p /opt/taoquant/pgdata
    sudo chown -R taoquant:taoquant /opt/taoquant/pgdata
    
    # Generate a random password if not set
    PG_PASSWORD="${TAOQUANT_DB_PASSWORD:-$(openssl rand -base64 32 | tr -d '\n')}"
    
    sudo docker run -d --name taoquant-postgres \
        -e POSTGRES_DB=taoquant \
        -e POSTGRES_USER=taoquant \
        -e POSTGRES_PASSWORD="${PG_PASSWORD}" \
        -p 127.0.0.1:5432:5432 \
        -v /opt/taoquant/pgdata:/var/lib/postgresql/data \
        --restart unless-stopped \
        postgres:16
    
    echo "✅ PostgreSQL container created"
    echo "⚠️  IMPORTANT: Password is ${PG_PASSWORD}"
    echo "   Save this password and set TAOQUANT_DB_PASSWORD in .env"
    sleep 5  # Wait for Postgres to start
else
    echo "✅ PostgreSQL container already exists"
    sudo docker start taoquant-postgres 2>/dev/null || true
fi

# Initialize schema (idempotent)
echo "📋 Step 5.6: Initializing database schema..."
if [ -f /opt/taoquant/persistence/schema.sql ]; then
    sudo apt-get install -y postgresql-client || true
    # Try to get password from env or use default
    PG_PASS="${TAOQUANT_DB_PASSWORD:-taoquant}"
    export PGPASSWORD="${PG_PASS}"
    psql -h 127.0.0.1 -p 5432 -U taoquant -d taoquant -f /opt/taoquant/persistence/schema.sql 2>/dev/null || {
        echo "⚠️  Schema init may have failed (tables might already exist, which is OK)"
    }
    echo "✅ Schema initialization attempted"
else
    echo "⚠️  schema.sql not found, skipping schema init"
fi

# Step 6: Setup environment variables
echo "🔐 Step 6: Setting up environment variables..."
if [ ! -f /opt/taoquant/.env ]; then
    echo "⚠️  Creating .env file template. Please edit /opt/taoquant/.env with your credentials!"
    sudo -u taoquant cp "$SCRIPT_DIR/env.template" /opt/taoquant/.env
    sudo chmod 600 /opt/taoquant/.env
else
    echo "✅ .env file already exists"
fi

# Step 7: Install systemd services
if [ "$DEPLOY_TARGET" = "runner" ] || [ "$DEPLOY_TARGET" = "all" ]; then
    echo "🔧 Step 7a: Installing systemd service for runner..."
    sudo cp "$SCRIPT_DIR/taoquant-runner.service" /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable taoquant-runner.service
    echo "✅ Runner service installed (not started yet)"
fi

if [ "$DEPLOY_TARGET" = "dashboard" ] || [ "$DEPLOY_TARGET" = "all" ]; then
    echo "🔧 Step 7b: Installing systemd service for dashboard..."
    sudo cp "$SCRIPT_DIR/taoquant-dashboard.service" /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable taoquant-dashboard.service
    echo "✅ Dashboard service installed (not started yet)"
fi

echo ""
echo "=========================================="
echo "✅ Deployment completed!"
echo "=========================================="
echo ""
echo "📝 Next steps:"
echo "1. Edit /opt/taoquant/.env with your Bitget API credentials"
echo "2. Edit /opt/taoquant/config_bitget_live.json with your strategy config"
echo "3. Start services:"
if [ "$DEPLOY_TARGET" = "runner" ] || [ "$DEPLOY_TARGET" = "all" ]; then
    echo "   sudo systemctl start taoquant-runner"
fi
if [ "$DEPLOY_TARGET" = "dashboard" ] || [ "$DEPLOY_TARGET" = "all" ]; then
    echo "   sudo systemctl start taoquant-dashboard"
fi
echo "4. Check status:"
if [ "$DEPLOY_TARGET" = "runner" ] || [ "$DEPLOY_TARGET" = "all" ]; then
    echo "   sudo systemctl status taoquant-runner"
fi
if [ "$DEPLOY_TARGET" = "dashboard" ] || [ "$DEPLOY_TARGET" = "all" ]; then
    echo "   sudo systemctl status taoquant-dashboard"
fi
echo "5. View logs:"
if [ "$DEPLOY_TARGET" = "runner" ] || [ "$DEPLOY_TARGET" = "all" ]; then
    echo "   sudo journalctl -u taoquant-runner -f"
fi
if [ "$DEPLOY_TARGET" = "dashboard" ] || [ "$DEPLOY_TARGET" = "all" ]; then
    echo "   sudo journalctl -u taoquant-dashboard -f"
fi
echo ""
echo "6. Run verification test:"
echo "   cd /opt/taoquant/deploy/gcp && sudo bash test_deployment.sh"
echo ""

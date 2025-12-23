#!/bin/bash
# TaoQuant server update script (GCP/Ubuntu)
#
# Usage:
#   sudo bash /opt/taoquant/deploy/gcp/update_bot.sh
#
# What it does:
# - Stop taoquant services (runner + dashboard)
# - Stash any local runtime changes (e.g., state/*) to avoid git conflicts
# - Pull latest code from origin/master (fallback origin/main)
# - Drop the stash (we don't want runtime files restored into git)
# - Restart services and print status + quick log tail
#
# Notes:
# - Assumes code lives at /opt/taoquant and is a git repo
# - Runs git commands as user "taoquant"

set -euo pipefail

REPO_DIR="${TAOQUANT_REPO_DIR:-/opt/taoquant}"
GIT_USER="${TAOQUANT_GIT_USER:-taoquant}"
RUNNER_SERVICE="${TAOQUANT_RUNNER_SERVICE:-taoquant-runner}"
DASHBOARD_SERVICE="${TAOQUANT_DASHBOARD_SERVICE:-taoquant-dashboard}"

echo "=========================================="
echo "TaoQuant Update Bot"
echo "=========================================="
echo "Repo: ${REPO_DIR}"
echo "Git user: ${GIT_USER}"
echo "Services: ${RUNNER_SERVICE}, ${DASHBOARD_SERVICE}"
echo ""

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: please run as root (use sudo)."
  exit 1
fi

if [ ! -d "${REPO_DIR}" ]; then
  echo "ERROR: repo dir not found: ${REPO_DIR}"
  exit 1
fi

if [ ! -d "${REPO_DIR}/.git" ]; then
  echo "ERROR: not a git repo: ${REPO_DIR} (missing .git)"
  exit 1
fi

echo "[1/6] Stop services..."
systemctl stop "${RUNNER_SERVICE}" 2>/dev/null || true
systemctl stop "${DASHBOARD_SERVICE}" 2>/dev/null || true

echo "[2/6] Stash local changes (runtime files)..."
sudo -u "${GIT_USER}" bash -lc "
  set -e
  cd '${REPO_DIR}'
  if [ -n \"\$(git status --porcelain)\" ]; then
    git stash push -u -m 'server runtime changes' >/dev/null
    echo '  - stashed'
  else
    echo '  - clean'
  fi
"

echo "[3/6] Pull latest code..."
sudo -u "${GIT_USER}" bash -lc "
  set -e
  cd '${REPO_DIR}'
  # Make sure we have a tracking branch
  if git rev-parse --abbrev-ref --symbolic-full-name @{u} >/dev/null 2>&1; then
    :
  else
    git branch --set-upstream-to=origin/master master 2>/dev/null || true
    git branch --set-upstream-to=origin/main main 2>/dev/null || true
  fi
  git pull
"

echo "[4/6] Drop stash (do not re-apply runtime files)..."
sudo -u "${GIT_USER}" bash -lc "
  set -e
  cd '${REPO_DIR}'
  if git stash list | grep -q 'server runtime changes'; then
    git stash drop >/dev/null || true
    echo '  - dropped'
  else
    echo '  - none'
  fi
"

echo "[5/6] Restart services..."
systemctl daemon-reload || true
systemctl start "${DASHBOARD_SERVICE}"
systemctl start "${RUNNER_SERVICE}"

echo "[6/6] Status + recent logs..."
echo ""
systemctl status "${DASHBOARD_SERVICE}" --no-pager -l || true
echo ""
systemctl status "${RUNNER_SERVICE}" --no-pager -l || true
echo ""
echo "---- dashboard logs (last 20) ----"
journalctl -u "${DASHBOARD_SERVICE}" -n 20 --no-pager || true
echo ""
echo "---- runner logs (last 40) ----"
journalctl -u "${RUNNER_SERVICE}" -n 40 --no-pager || true
echo ""
echo "✅ Done. If dashboard looks cached, do Ctrl+F5 in browser."


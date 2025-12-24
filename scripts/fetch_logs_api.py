#!/usr/bin/env python3
"""
Fetch logs from TaoQuant Dashboard API with Token authentication.

Setup:
    1. Copy scripts/config_local.json.template to scripts/config_local.json
    2. Fill in your dashboard URL and token
    3. Run: python scripts/fetch_logs_api.py

Usage:
    python scripts/fetch_logs_api.py                    # Get last 200 lines
    python scripts/fetch_logs_api.py --lines 500        # Get last 500 lines
    python scripts/fetch_logs_api.py --errors           # Only show errors/warnings
    python scripts/fetch_logs_api.py --status           # Also show bot status
"""

import sys
import argparse
import json
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("Please install requests: pip install requests")
    sys.exit(1)

# Configuration
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config_local.json"
OUTPUT_DIR = SCRIPT_DIR.parent / "logs" / "fetched"

# Default values (can be overridden by config file)
DASHBOARD_URL = "http://34.158.55.6:8000"
DASHBOARD_TOKEN = None


def load_config():
    """Load configuration from config_local.json."""
    global DASHBOARD_URL, DASHBOARD_TOKEN
    
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            dashboard_config = config.get("dashboard", {})
            DASHBOARD_URL = dashboard_config.get("url", DASHBOARD_URL)
            DASHBOARD_TOKEN = dashboard_config.get("token")
            if DASHBOARD_TOKEN and DASHBOARD_TOKEN.startswith("YOUR_"):
                DASHBOARD_TOKEN = None  # Not configured
            return True
        except Exception as e:
            print(f"Warning: Could not load config: {e}")
    return False


def get_headers() -> dict:
    """Get request headers including auth token if available."""
    headers = {}
    if DASHBOARD_TOKEN:
        headers["Authorization"] = f"Bearer {DASHBOARD_TOKEN}"
    return headers


def fetch_logs_from_api(lines: int = 200) -> str:
    """Fetch logs from Dashboard API."""
    url = f"{DASHBOARD_URL}/api/logs"
    params = {
        "tail": lines,
        "source": "file",
        "unit": "taoquant-runner"
    }
    
    try:
        print(f"Fetching logs from {url}...")
        if DASHBOARD_TOKEN:
            print("  Using token authentication")
        response = requests.get(url, params=params, headers=get_headers(), timeout=30)
        response.raise_for_status()
        
        data = response.json()
        return data.get("logs", "")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print("Error: Unauthorized - check your DASHBOARD_TOKEN in config_local.json")
        elif e.response.status_code == 403:
            print("Error: Forbidden - token may be invalid")
        else:
            print(f"HTTP Error: {e}")
        return ""
    except requests.exceptions.ConnectionError:
        print(f"Error: Cannot connect to {DASHBOARD_URL}")
        print("Make sure the dashboard is running and firewall allows access.")
        return ""
    except requests.exceptions.Timeout:
        print("Error: Request timed out")
        return ""
    except Exception as e:
        print(f"Error: {e}")
        return ""


def fetch_status_from_api() -> dict:
    """Fetch bot status from Dashboard API."""
    url = f"{DASHBOARD_URL}/api/status"
    
    try:
        response = requests.get(url, headers=get_headers(), timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching status: {e}")
        return {}


def save_logs(logs: str, suffix: str = "") -> Path:
    """Save logs to a timestamped file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"runner_logs_{timestamp}{suffix}.txt"
    filepath = OUTPUT_DIR / filename
    
    filepath.write_text(logs, encoding="utf-8")
    print(f"Logs saved to: {filepath}")
    return filepath


def analyze_logs(logs: str) -> dict:
    """Quick analysis of log content."""
    lines = logs.strip().split("\n")
    
    analysis = {
        "total_lines": len(lines),
        "errors": [],
        "warnings": [],
        "order_placed": [],
        "order_failed": [],
        "order_filled": [],
        "order_cancel": [],
        "ledger_drift": False,
        "ledger_drift_count": 0,
        "db_errors": False,
        "db_error_count": 0,
        "bitget_errors": [],
    }
    
    for line in lines:
        line_lower = line.lower()
        
        if "bitget place_order failed" in line_lower or "22002" in line:
            analysis["bitget_errors"].append(line)
        elif "[order_failed]" in line_lower:
            analysis["order_failed"].append(line)
        elif "[order_placed]" in line_lower:
            analysis["order_placed"].append(line)
        elif "[order_filled]" in line_lower:
            analysis["order_filled"].append(line)
        elif "[order_cancel]" in line_lower:
            analysis["order_cancel"].append(line)
        elif "[ledger_drift]" in line_lower:
            analysis["ledger_drift"] = True
            analysis["ledger_drift_count"] += 1
        elif "password authentication failed" in line_lower:
            analysis["db_errors"] = True
            analysis["db_error_count"] += 1
        elif "error" in line_lower and "error connecting" not in line_lower:
            analysis["errors"].append(line)
        elif "warning" in line_lower and "[ledger_drift]" not in line_lower:
            analysis["warnings"].append(line)
    
    return analysis


def print_analysis(analysis: dict):
    """Print a summary of the log analysis."""
    print("\n" + "=" * 70)
    print("LOG ANALYSIS SUMMARY")
    print("=" * 70)
    
    print(f"\nTotal lines: {analysis['total_lines']}")
    print(f"Orders placed: {len(analysis['order_placed'])}")
    print(f"Orders filled: {len(analysis['order_filled'])}")
    print(f"Orders cancelled: {len(analysis['order_cancel'])}")
    
    # Highlight issues
    failed_count = len(analysis['order_failed'])
    bitget_count = len(analysis['bitget_errors'])
    
    if failed_count > 0:
        print(f"❌ Orders failed: {failed_count}")
    else:
        print(f"Orders failed: 0")
        
    if bitget_count > 0:
        print(f"❌ Bitget API errors: {bitget_count}")
    else:
        print(f"Bitget API errors: 0")
    
    if analysis["ledger_drift"]:
        print(f"⚠️  Ledger drift detected: {analysis['ledger_drift_count']} occurrences")
    
    if analysis["db_errors"]:
        print(f"⚠️  DB connection errors: {analysis['db_error_count']} occurrences")
    
    # Show details for issues
    if analysis["bitget_errors"]:
        print("\n--- BITGET API ERRORS (last 5) ---")
        for line in analysis["bitget_errors"][-5:]:
            if "22002" in line:
                print("  [22002] No position to close - SELL order rejected")
            elif "40786" in line:
                print("  [40786] Duplicate clientOid")
            else:
                # Extract error message
                if "error=" in line.lower():
                    print(f"  {line.split('error=')[-1][:80]}...")
                else:
                    print(f"  {line[-100:]}")
    
    if analysis["order_failed"]:
        print("\n--- ORDER FAILURES (last 5) ---")
        for line in analysis["order_failed"][-5:]:
            print(f"  {line}")
    
    if analysis["order_filled"]:
        print("\n--- RECENT FILLS (last 3) ---")
        for line in analysis["order_filled"][-3:]:
            print(f"  {line}")
    
    print("\n" + "=" * 70)


def filter_logs(logs: str, errors_only: bool = False) -> str:
    """Filter logs to show only relevant lines."""
    if not errors_only:
        return logs
    
    lines = logs.strip().split("\n")
    filtered = []
    for line in lines:
        line_lower = line.lower()
        if any(x in line_lower for x in ["error", "failed", "warning", "order_", "22002", "bootstrap", "ledger"]):
            filtered.append(line)
    
    return "\n".join(filtered)


def setup_config():
    """Interactive setup for config file."""
    print("\n=== TaoQuant Log Fetcher Setup ===\n")
    
    if CONFIG_FILE.exists():
        overwrite = input("Config file exists. Overwrite? (y/N): ").strip().lower()
        if overwrite != 'y':
            print("Keeping existing config.")
            return
    
    url = input(f"Dashboard URL [{DASHBOARD_URL}]: ").strip() or DASHBOARD_URL
    token = input("Dashboard Token (leave empty if not using auth): ").strip()
    
    config = {
        "dashboard": {
            "url": url,
            "token": token if token else "YOUR_DASHBOARD_TOKEN_HERE"
        }
    }
    
    CONFIG_FILE.write_text(json.dumps(config, indent=4), encoding="utf-8")
    print(f"\nConfig saved to: {CONFIG_FILE}")
    print("You can edit this file manually anytime.")


def main():
    parser = argparse.ArgumentParser(description="Fetch and analyze logs from TaoQuant Dashboard")
    parser.add_argument("--lines", "-n", type=int, default=200, help="Number of lines to fetch")
    parser.add_argument("--errors", "-e", action="store_true", help="Only show error/order lines")
    parser.add_argument("--no-save", action="store_true", help="Don't save to file")
    parser.add_argument("--no-analysis", action="store_true", help="Skip analysis")
    parser.add_argument("--status", "-s", action="store_true", help="Also fetch bot status")
    parser.add_argument("--url", type=str, help="Dashboard URL (override config)")
    parser.add_argument("--token", type=str, help="Dashboard token (override config)")
    parser.add_argument("--setup", action="store_true", help="Run interactive setup")
    
    args = parser.parse_args()
    
    # Run setup if requested
    if args.setup:
        setup_config()
        return 0
    
    # Load config
    load_config()
    
    # Override from command line
    global DASHBOARD_URL, DASHBOARD_TOKEN
    if args.url:
        DASHBOARD_URL = args.url
    if args.token:
        DASHBOARD_TOKEN = args.token
    
    # Check config
    if not CONFIG_FILE.exists():
        print("Config file not found. Run with --setup to create one.")
        print(f"Or copy {SCRIPT_DIR / 'config_local.json.template'} to {CONFIG_FILE}")
        return 1
    
    # Fetch status if requested
    if args.status:
        print("\n--- BOT STATUS ---")
        status = fetch_status_from_api()
        if status:
            print(json.dumps(status, indent=2, default=str))
    
    # Fetch logs
    logs = fetch_logs_from_api(lines=args.lines)
    
    if not logs:
        print("No logs fetched.")
        return 1
    
    # Filter if needed
    if args.errors:
        logs = filter_logs(logs, errors_only=True)
    
    # Print logs
    print("\n--- LOGS ---")
    print(logs)
    
    # Save logs
    if not args.no_save:
        suffix = "_errors" if args.errors else ""
        save_logs(logs, suffix)
    
    # Analyze logs
    if not args.no_analysis:
        analysis = analyze_logs(logs)
        print_analysis(analysis)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Fetch logs from GCP VM and save locally for analysis.

Usage:
    python scripts/fetch_logs.py                    # Get last 200 lines
    python scripts/fetch_logs.py --lines 500        # Get last 500 lines
    python scripts/fetch_logs.py --since "1 hour"   # Get logs from last hour
    python scripts/fetch_logs.py --errors           # Only show errors
"""

import subprocess
import sys
import argparse
from datetime import datetime
from pathlib import Path

# GCP VM configuration
INSTANCE_NAME = "liandongquant"
ZONE = "asia-southeast1-b"
SERVICE_NAME = "taoquant-runner"

# Local output directory
OUTPUT_DIR = Path(__file__).parent.parent / "logs" / "fetched"


def run_gcloud_ssh(command: str, timeout: int = 60) -> tuple[int, str, str]:
    """Run a command on the GCP VM via gcloud SSH."""
    full_cmd = [
        "gcloud", "compute", "ssh", INSTANCE_NAME,
        f"--zone={ZONE}",
        "--command", command
    ]
    
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except FileNotFoundError:
        return -1, "", "gcloud CLI not found. Please install Google Cloud SDK."


def fetch_journalctl_logs(lines: int = 200, since: str = None, errors_only: bool = False) -> str:
    """Fetch journalctl logs from the runner service."""
    cmd_parts = ["sudo", "journalctl", "-u", SERVICE_NAME]
    
    if since:
        cmd_parts.extend(["--since", f'"{since} ago"'])
    else:
        cmd_parts.extend(["-n", str(lines)])
    
    cmd_parts.append("--no-pager")
    
    cmd = " ".join(cmd_parts)
    
    if errors_only:
        cmd += " | grep -i 'error\\|failed\\|warning'"
    
    print(f"Fetching logs: {cmd}")
    returncode, stdout, stderr = run_gcloud_ssh(cmd)
    
    if returncode != 0:
        print(f"Error fetching logs: {stderr}", file=sys.stderr)
        return ""
    
    return stdout


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
        "ledger_drift": False,
        "db_errors": False,
    }
    
    for line in lines:
        line_lower = line.lower()
        
        if "error" in line_lower and "error connecting" not in line_lower:
            analysis["errors"].append(line)
        if "[order_failed]" in line_lower or "place_order failed" in line_lower:
            analysis["order_failed"].append(line)
        if "[order_placed]" in line_lower:
            analysis["order_placed"].append(line)
        if "[order_filled]" in line_lower:
            analysis["order_filled"].append(line)
        if "[ledger_drift]" in line_lower:
            analysis["ledger_drift"] = True
        if "password authentication failed" in line_lower:
            analysis["db_errors"] = True
        if "warning" in line_lower:
            analysis["warnings"].append(line)
    
    return analysis


def print_analysis(analysis: dict):
    """Print a summary of the log analysis."""
    print("\n" + "=" * 60)
    print("LOG ANALYSIS SUMMARY")
    print("=" * 60)
    
    print(f"\nTotal lines: {analysis['total_lines']}")
    print(f"Errors: {len(analysis['errors'])}")
    print(f"Warnings: {len(analysis['warnings'])}")
    print(f"Orders placed: {len(analysis['order_placed'])}")
    print(f"Orders failed: {len(analysis['order_failed'])}")
    print(f"Orders filled: {len(analysis['order_filled'])}")
    print(f"Ledger drift detected: {analysis['ledger_drift']}")
    print(f"DB connection errors: {analysis['db_errors']}")
    
    if analysis["order_failed"]:
        print("\n--- ORDER FAILURES ---")
        for line in analysis["order_failed"][-10:]:  # Last 10
            print(line)
    
    if analysis["errors"]:
        print("\n--- RECENT ERRORS ---")
        for line in analysis["errors"][-5:]:  # Last 5
            print(line)
    
    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Fetch and analyze logs from GCP VM")
    parser.add_argument("--lines", "-n", type=int, default=200, help="Number of lines to fetch")
    parser.add_argument("--since", "-s", type=str, help="Fetch logs since (e.g., '1 hour', '30 min')")
    parser.add_argument("--errors", "-e", action="store_true", help="Only fetch error lines")
    parser.add_argument("--no-save", action="store_true", help="Don't save to file")
    parser.add_argument("--no-analysis", action="store_true", help="Skip analysis")
    
    args = parser.parse_args()
    
    # Fetch logs
    logs = fetch_journalctl_logs(
        lines=args.lines,
        since=args.since,
        errors_only=args.errors
    )
    
    if not logs:
        print("No logs fetched.")
        return 1
    
    # Print logs
    print("\n" + logs)
    
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

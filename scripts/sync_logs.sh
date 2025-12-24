#!/bin/bash
# Run this on GCP server to export logs for local analysis
# Usage: bash /opt/taoquant/scripts/sync_logs.sh

OUTPUT_DIR="/opt/taoquant/logs/export"
mkdir -p "$OUTPUT_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="$OUTPUT_DIR/runner_${TIMESTAMP}.log"

echo "Exporting logs to $OUTPUT_FILE..."

# Export last 500 lines of runner logs
sudo journalctl -u taoquant-runner -n 500 --no-pager > "$OUTPUT_FILE"

# Also create a summary file
SUMMARY_FILE="$OUTPUT_DIR/summary_${TIMESTAMP}.txt"
echo "=== TaoQuant Log Summary ===" > "$SUMMARY_FILE"
echo "Timestamp: $(date)" >> "$SUMMARY_FILE"
echo "" >> "$SUMMARY_FILE"

echo "=== Bot Status ===" >> "$SUMMARY_FILE"
systemctl status taoquant-runner --no-pager >> "$SUMMARY_FILE" 2>&1
echo "" >> "$SUMMARY_FILE"

echo "=== Order Statistics ===" >> "$SUMMARY_FILE"
echo "Orders Placed: $(grep -c '\[ORDER_PLACED\]' "$OUTPUT_FILE" 2>/dev/null || echo 0)" >> "$SUMMARY_FILE"
echo "Orders Filled: $(grep -c '\[ORDER_FILLED\]' "$OUTPUT_FILE" 2>/dev/null || echo 0)" >> "$SUMMARY_FILE"
echo "Orders Failed: $(grep -c '\[ORDER_FAILED\]' "$OUTPUT_FILE" 2>/dev/null || echo 0)" >> "$SUMMARY_FILE"
echo "Orders Cancelled: $(grep -c '\[ORDER_CANCEL\]' "$OUTPUT_FILE" 2>/dev/null || echo 0)" >> "$SUMMARY_FILE"
echo "" >> "$SUMMARY_FILE"

echo "=== Issues Detected ===" >> "$SUMMARY_FILE"
echo "Ledger Drift: $(grep -c '\[LEDGER_DRIFT\]' "$OUTPUT_FILE" 2>/dev/null || echo 0)" >> "$SUMMARY_FILE"
echo "DB Errors: $(grep -c 'password authentication failed' "$OUTPUT_FILE" 2>/dev/null || echo 0)" >> "$SUMMARY_FILE"
echo "Bitget 22002: $(grep -c '22002' "$OUTPUT_FILE" 2>/dev/null || echo 0)" >> "$SUMMARY_FILE"
echo "" >> "$SUMMARY_FILE"

echo "=== Last 20 Key Events ===" >> "$SUMMARY_FILE"
grep -E 'ORDER_PLACED|ORDER_FILLED|ORDER_FAILED|LEDGER_DRIFT|BOOTSTRAP|22002' "$OUTPUT_FILE" | tail -20 >> "$SUMMARY_FILE"

echo ""
echo "Done! Files created:"
echo "  - Full logs: $OUTPUT_FILE"
echo "  - Summary: $SUMMARY_FILE"
echo ""
echo "To download to local machine, run from your local terminal:"
echo "  gcloud compute scp $INSTANCE_NAME:$OUTPUT_FILE ./logs/"

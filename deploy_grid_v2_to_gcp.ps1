# Deploy StandardGridV2 to GCP Server
# Quick deployment script for StandardGridV2 live trading

$GCP_IP = "34.158.55.6"
$GCP_USER = "liandongtrading"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Deploy StandardGridV2 to GCP" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Server: ${GCP_USER}@${GCP_IP}" -ForegroundColor White
Write-Host ""

# Step 1: Upload StandardGridV2 files
Write-Host "Step 1: Upload StandardGridV2 files..." -ForegroundColor Yellow

$filesToUpload = @(
    "algorithms\taogrid\standard_grid_v2.py",
    "algorithms\taogrid\standard_grid_v2_live.py",
    "algorithms\taogrid\deploy_standard_grid_v2.py",
    "algorithms\taogrid\test_standard_grid_v2.py",
    "algorithms\taogrid\run_backtest_v2.py"
)

foreach ($file in $filesToUpload) {
    Write-Host "  Uploading: $file" -ForegroundColor Gray
    scp $file "${GCP_USER}@${GCP_IP}:/tmp/" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    OK $file" -ForegroundColor DarkGreen
    } else {
        Write-Host "    FAILED $file" -ForegroundColor Red
    }
}

Write-Host ""

# Step 2: Move files to server and set permissions
Write-Host "Step 2: Deploy files on server..." -ForegroundColor Yellow

$deployCommands = @"
# Backup existing files
sudo mkdir -p /opt/taoquant/algorithms/taogrid/backup
sudo cp /opt/taoquant/algorithms/taogrid/standard_grid_v2.py /opt/taoquant/algorithms/taogrid/backup/standard_grid_v2.py.backup_\$(date +%Y%m%d_%H%M%S) 2>/dev/null || true

# Move new files
sudo mv /tmp/standard_grid_v2.py /opt/taoquant/algorithms/taogrid/
sudo mv /tmp/standard_grid_v2_live.py /opt/taoquant/algorithms/taogrid/
sudo mv /tmp/deploy_standard_grid_v2.py /opt/taoquant/algorithms/taogrid/
sudo mv /tmp/test_standard_grid_v2.py /opt/taoquant/algorithms/taogrid/
sudo mv /tmp/run_backtest_v2.py /opt/taoquant/algorithms/taogrid/

# Set ownership
sudo chown -R taoquant:taoquant /opt/taoquant/algorithms/taogrid/

# Make deployment script executable
sudo chmod +x /opt/taoquant/algorithms/taogrid/deploy_standard_grid_v2.py

echo "Deployment complete!"
"@

ssh ${GCP_USER}@${GCP_IP} $deployCommands

if ($LASTEXITCODE -eq 0) {
    Write-Host "  Deployment successful!" -ForegroundColor Green
} else {
    Write-Host "  Deployment failed!" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Step 3: Check environment variables
Write-Host "Step 3: Checking environment variables..." -ForegroundColor Yellow

$checkEnvCommands = @"
echo "Checking if API credentials are set..."
if grep -q "BITGET_API_KEY" /opt/taoquant/.env 2>/dev/null; then
    echo "  BITGET_API_KEY: OK"
else
    echo "  BITGET_API_KEY: MISSING"
fi

if grep -q "BITGET_API_SECRET" /opt/taoquant/.env 2>/dev/null; then
    echo "  BITGET_API_SECRET: OK"
else
    echo "  BITGET_API_SECRET: MISSING"
fi

if grep -q "BITGET_PASSPHRASE" /opt/taoquant/.env 2>/dev/null; then
    echo "  BITGET_PASSPHRASE: OK"
else
    echo "  BITGET_PASSPHRASE: MISSING"
fi
"@

ssh ${GCP_USER}@${GCP_IP} $checkEnvCommands

Write-Host ""

# Step 4: Instructions
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. SSH to server:" -ForegroundColor White
Write-Host "   ssh ${GCP_USER}@${GCP_IP}" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Set environment variables (if not set):" -ForegroundColor White
Write-Host "   sudo nano /opt/taoquant/.env" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Test with dry-run:" -ForegroundColor White
Write-Host "   cd /opt/taoquant" -ForegroundColor Gray
Write-Host "   source .venv/bin/activate" -ForegroundColor Gray
Write-Host "   python algorithms/taogrid/deploy_standard_grid_v2.py --dry-run" -ForegroundColor Gray
Write-Host ""
Write-Host "4. Deploy live ($100, 10X leverage):" -ForegroundColor White
Write-Host "   python algorithms/taogrid/deploy_standard_grid_v2.py --balance 100 --leverage 10" -ForegroundColor Gray
Write-Host ""
Write-Host "Files uploaded:" -ForegroundColor Yellow
foreach ($file in $filesToUpload) {
    Write-Host "  - $file" -ForegroundColor DarkGray
}
Write-Host ""

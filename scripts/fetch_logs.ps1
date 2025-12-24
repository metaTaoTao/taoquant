# TaoQuant Log Fetcher - PowerShell Script
# Usage: 
#   .\scripts\fetch_logs.ps1              # Get last 200 lines
#   .\scripts\fetch_logs.ps1 -Lines 500   # Get last 500 lines  
#   .\scripts\fetch_logs.ps1 -Errors      # Only show errors

param(
    [int]$Lines = 200,
    [switch]$Errors,
    [string]$Since = "",
    [switch]$Save,
    [string]$Instance = "liandongquant",
    [string]$Zone = "asia-southeast1-b"
)

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outputDir = "$PSScriptRoot\..\logs\fetched"

# Build journalctl command
$journalCmd = "sudo journalctl -u taoquant-runner"

if ($Since) {
    $journalCmd += " --since '$Since ago'"
} else {
    $journalCmd += " -n $Lines"
}

$journalCmd += " --no-pager"

if ($Errors) {
    $journalCmd += " 2>&1 | grep -iE 'error|failed|warning|order_'"
}

Write-Host "Fetching logs from GCP VM: $Instance" -ForegroundColor Cyan
Write-Host "Command: $journalCmd" -ForegroundColor Gray

# Run gcloud SSH command
$result = gcloud compute ssh $Instance --zone=$Zone --command="$journalCmd" 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "Error fetching logs:" -ForegroundColor Red
    Write-Host $result
    exit 1
}

# Print logs
Write-Host "`n--- LOGS ---" -ForegroundColor Green
Write-Host $result

# Save if requested
if ($Save) {
    if (!(Test-Path $outputDir)) {
        New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
    }
    $filename = "runner_logs_$timestamp.txt"
    $filepath = Join-Path $outputDir $filename
    $result | Out-File -FilePath $filepath -Encoding UTF8
    Write-Host "`nLogs saved to: $filepath" -ForegroundColor Green
}

# Quick analysis
Write-Host "`n--- QUICK ANALYSIS ---" -ForegroundColor Cyan
$lines = $result -split "`n"
$orderPlaced = ($lines | Select-String -Pattern "\[ORDER_PLACED\]").Count
$orderFailed = ($lines | Select-String -Pattern "\[ORDER_FAILED\]").Count
$orderFilled = ($lines | Select-String -Pattern "\[ORDER_FILLED\]").Count
$ledgerDrift = ($lines | Select-String -Pattern "\[LEDGER_DRIFT\]").Count
$dbErrors = ($lines | Select-String -Pattern "password authentication failed").Count
$bitgetErrors = ($lines | Select-String -Pattern "22002|No position to close").Count

Write-Host "Total lines: $($lines.Count)"
Write-Host "Orders placed: $orderPlaced"
Write-Host "Orders filled: $orderFilled" 
Write-Host "Orders failed: $orderFailed" -ForegroundColor $(if ($orderFailed -gt 0) {"Red"} else {"Gray"})
Write-Host "Ledger drift warnings: $ledgerDrift" -ForegroundColor $(if ($ledgerDrift -gt 0) {"Yellow"} else {"Gray"})
Write-Host "DB connection errors: $dbErrors" -ForegroundColor $(if ($dbErrors -gt 0) {"Yellow"} else {"Gray"})
Write-Host "Bitget 22002 errors: $bitgetErrors" -ForegroundColor $(if ($bitgetErrors -gt 0) {"Red"} else {"Gray"})

if ($orderFailed -gt 0) {
    Write-Host "`n--- FAILED ORDERS (last 5) ---" -ForegroundColor Red
    $lines | Select-String -Pattern "\[ORDER_FAILED\]" | Select-Object -Last 5 | ForEach-Object { Write-Host $_.Line }
}

if ($bitgetErrors -gt 0) {
    Write-Host "`n--- BITGET API ERRORS (last 5) ---" -ForegroundColor Red
    $lines | Select-String -Pattern "22002|No position to close" | Select-Object -Last 5 | ForEach-Object { Write-Host $_.Line }
}

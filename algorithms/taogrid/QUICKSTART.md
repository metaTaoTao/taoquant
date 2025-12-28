# Quick Start - StandardGridV2 Live Trading

## 3-Step Deployment

### Step 1: Set API Credentials (Windows)

```powershell
# PowerShell
$env:BITGET_API_KEY="your_key_here"
$env:BITGET_API_SECRET="your_secret_here"
$env:BITGET_PASSPHRASE="your_passphrase_here"
```

### Step 2: Test with Dry-Run

```bash
cd D:\Projects\PythonProjects\taoquant\algorithms\taogrid
python deploy_standard_grid_v2.py --dry-run
```

**Watch for:**
- ✅ "Loaded 500 bars" - Data fetch successful
- ✅ "Auto-calculated grid count: 43" - Grid setup successful
- ✅ "Grid initialized" - Ready to trade
- ✅ "[DRY RUN] Would place buy order" - Orders simulated

### Step 3: Deploy Live

```bash
python deploy_standard_grid_v2.py --balance 100 --leverage 10
```

**Type `YES` when prompted to confirm.**

## Monitor

**Status updates every 60 seconds:**
```
Current Price: $91,234.56
Equity: $103.45 (+3.45%)
Net PnL: $3.45
Total Trades: 12
Position: 0.123456 BTC
Active Orders: 18 buy, 5 sell
```

**Stop:** Press `Ctrl+C`

## Configuration

### Default (Recommended)
- Symbol: BTCUSDT
- Support: $76,000
- Resistance: $97,000
- Balance: $100
- Leverage: 10X

### Custom Range
```bash
python deploy_standard_grid_v2.py \
  --support 80000 \
  --resistance 95000 \
  --balance 100 \
  --leverage 10
```

## Safety Limits

- **Max Drawdown:** 20% (auto-shutdown)
- **Max Position:** 5 × balance × leverage
- **Grid Logic:** 1 order per level (no explosion)

## Backtest Results (Reference)

- **Period:** 40 days (Feb-Apr 2025)
- **Return:** +92.53%
- **Max DD:** -0.02%
- **Sharpe:** 70.53

**Note:** Past performance ≠ future results

## Need Help?

- Full docs: `STANDARD_GRID_V2_DEPLOYMENT.md`
- Implementation: `IMPLEMENTATION_NOTES.md`
- Code: `standard_grid_v2.py`
- Tests: `test_standard_grid_v2.py`

## Risk Warning

⚠️ **HIGH RISK:** Leverage trading can result in total loss. Only use funds you can afford to lose.

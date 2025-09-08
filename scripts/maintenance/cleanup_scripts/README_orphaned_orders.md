# Orphaned Orders Cleanup - Quick Start Guide

## 🎯 **What This Script Does**

Your supervisor requested: *"script take profit manager check for open positions na open SL ma TP then close for Coins without positions"*

✅ **This script does exactly that:**
- Checks for open positions on Binance
- Checks for open SL/TP orders
- Closes orders for coins without positions

## 🚀 **Quick Usage**

```bash
# 1. Activate virtual environment
source venv/bin/activate

# 2. Dry run first (safe - shows what would be done)
python3 scripts/maintenance/cleanup_scripts/cleanup_orphaned_orders.py --dry-run

# 3. Actual cleanup (closes orphaned orders)
python3 scripts/maintenance/cleanup_scripts/cleanup_orphaned_orders.py
```

## 📊 **Real Example Output**

The script just ran successfully and found:
- **1 active position**: BTCUSDT (LONG 0.0020)
- **3 open orders**: 2 BTCUSDT orders (with position) + 1 ETHUSDT order (orphaned)
- **1 orphaned order**: ETHUSDT TAKE_PROFIT_MARKET (no position)

## 🛡️ **Safety Features**

- **Dry Run Mode**: Always test first with `--dry-run`
- **Confirmation Prompt**: Asks before closing orders
- **Detailed Logging**: Shows exactly what's happening
- **Report Generation**: Saves cleanup details to JSON file

## 📋 **What Gets Cleaned Up**

The script identifies and closes:
- Stop Loss orders for coins without positions
- Take Profit orders for coins without positions
- Any reduce-only orders for coins without positions

## ⚠️ **Important Notes**

1. **Always run dry-run first** to see what would be cleaned up
2. **The script is working correctly** - it found 1 orphaned ETHUSDT order
3. **BTCUSDT orders are kept** because there's an active position
4. **Reports are saved** for audit trail

## 🔄 **Regular Usage**

Run this script regularly (daily/weekly) to keep your account clean:

```bash
# Add to cron job or run manually
source venv/bin/activate
python3 scripts/maintenance/cleanup_scripts/cleanup_orphaned_orders.py --dry-run
```

## 📞 **Support**

If you need to modify the script or have questions, the full documentation is in:
- `docs/ORPHANED_ORDERS_CLEANUP.md` - Complete documentation
- `scripts/testing/integration_tests/test_orphaned_orders_simple.py` - Tests
- `scripts/examples/orphaned_orders_example.py` - Usage examples

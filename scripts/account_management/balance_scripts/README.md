# Balance Management Scripts

This directory contains scripts for fetching and managing exchange balances.

## Files

### `combined_balance_fetcher.py`

Main balance fetcher that handles both Binance and KuCoin futures balances.

**Features:**

- Fetches Binance futures balances using the existing BinanceExchange class
- Fetches KuCoin futures balances using direct API calls
- Stores all balances (including zero balances) in Supabase
- Supports dry-run mode for testing

**Usage:**

```bash
# Run once and store in database
python scripts/account_management/balance_scripts/combined_balance_fetcher.py

# Dry run (fetch but don't store)
python scripts/account_management/balance_scripts/combined_balance_fetcher.py --dry-run

# Show stored balances
python scripts/account_management/balance_scripts/combined_balance_fetcher.py --show-stored

# Run as daemon (continuous updates every 5 minutes)
python scripts/account_management/balance_scripts/combined_balance_fetcher.py --daemon --interval 300
```

## Integration

The balance fetching is automatically integrated into the main Discord bot scheduler (`discord_bot/main.py`) and runs every 5 minutes.

**Scheduler Integration:**

- **Interval:** 5 minutes
- **Function:** `sync_exchange_balances()`
- **Test Endpoint:** `POST /scheduler/test-balance-sync`

## Database Schema

Balances are stored in the `balances` table with the following structure:

- `id`: string (auto-generated)
- `platform`: string (binance, kucoin)
- `account_type`: string (futures)
- `asset`: string (USDT, XBT, etc.)
- `free`: number (available balance)
- `locked`: number (locked balance)
- `total`: number (total balance)
- `unrealized_pnl`: number (unrealized P&L)
- `last_updated`: string (ISO timestamp)

## Environment Variables

Required environment variables:

- `BINANCE_API_KEY`: Binance API key
- `BINANCE_API_SECRET`: Binance API secret
- `BINANCE_TESTNET`: true/false
- `KUCOIN_API_KEY`: KuCoin API key
- `KUCOIN_API_SECRET`: KuCoin API secret
- `KUCOIN_API_PASSPHRASE`: KuCoin API passphrase
- `SUPABASE_URL`: Supabase project URL
- `SUPABASE_KEY`: Supabase API key

## Notes

- KuCoin balances are stored even when empty (zero values) for complete tracking
- Binance balances are only stored when non-zero (more efficient)
- All API calls include proper error handling and retry logic
- The scheduler runs automatically when the Discord bot service is started

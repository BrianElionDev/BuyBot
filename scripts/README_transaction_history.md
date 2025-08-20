# Transaction History Table and Scripts

This document describes the `transaction_history` table and the scripts created to fill it with data from Binance's `/income` endpoint.

## Table Structure

The `transaction_history` table stores all income data from Binance with the following fields:

- `time` (bigint): Transaction timestamp in milliseconds
- `type` (text): Income type (e.g., REALIZED_PNL, COMMISSION, FUNDING_FEE, etc.)
- `amount` (numeric): Transaction amount
- `asset` (text): Asset name (e.g., USDT, BTC, etc.)
- `symbol` (text): Trading pair symbol (e.g., BTCUSDT, ETHUSDT, etc.)

## Database Methods

The following methods have been added to `DatabaseManager` in `discord_bot/database.py`:

### `insert_transaction_history(transaction_data)`

Insert a single transaction record.

### `insert_transaction_history_batch(transactions)`

Insert multiple transaction records in batch.

### `get_transaction_history(symbol, start_time, end_time, limit)`

Retrieve transaction records with optional filtering.

### `check_transaction_exists(time, type, amount, asset, symbol)`

Check if a transaction record already exists to avoid duplicates.

## Scripts

### 1. Manual Script: `manual_transaction_history_fill.py`

Interactive script for manual control over data fetching and insertion.

**Usage:**

```bash
python scripts/manual_transaction_history_fill.py
```

**Features:**

- Interactive menu for choosing operation
- Fill single symbol or all symbols
- Customizable parameters (days, income type filter)
- Batch processing with rate limiting
- Duplicate checking

**Options:**

1. Fill single symbol - Enter symbol, days, and optional income type filter
2. Fill all symbols - Process predefined list of common symbols
3. Custom parameters - Modify script for specific needs

### 2. Auto Script: `autofill_transaction_history.py`

Automated script for continuous or one-time data filling.

**Usage:**

```bash
# One-time fill for last 7 days
python scripts/autofill_transaction_history.py

# Fill specific symbols
python scripts/autofill_transaction_history.py --symbols BTCUSDT ETHUSDT

# Fill with custom parameters
python scripts/autofill_transaction_history.py --days 30 --income-type REALIZED_PNL

# Run continuously (syncs every 6 hours)
python scripts/autofill_transaction_history.py --continuous

# Custom sync interval
python scripts/autofill_transaction_history.py --continuous --sync-interval 12
```

**Features:**

- Command-line arguments for automation
- Chunked data fetching for large time ranges
- Continuous mode for periodic syncing
- Rate limiting and error handling
- Duplicate prevention

### 3. Test Script: `test_transaction_history.py`

Test script to verify table functionality.

**Usage:**

```bash
python scripts/test_transaction_history.py
```

**Tests:**

- Database connection
- Single record insertion
- Batch insertion
- Duplicate checking
- Income data fetching
- Full workflow (income → database)

## Income Types

The scripts handle various income types from Binance:

- `REALIZED_PNL`: Realized profit/loss from closed positions
- `COMMISSION`: Trading fees
- `FUNDING_FEE`: Funding rate payments
- `TRANSFER`: Asset transfers
- `WELCOME_BONUS`: Welcome bonuses
- `INSURANCE_CLEAR`: Insurance fund transactions

## Configuration

### Environment Variables

Ensure these are set in your `.env` file:

- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_KEY`: Your Supabase API key
- `BINANCE_API_KEY`: Your Binance API key
- `BINANCE_API_SECRET`: Your Binance API secret

### Default Symbols

The scripts use a predefined list of common trading symbols:

- BTCUSDT, ETHUSDT, BNBUSDT, ADAUSDT, SOLUSDT
- DOTUSDT, DOGEUSDT, AVAXUSDT, MATICUSDT, LINKUSDT
- UNIUSDT, LTCUSDT, BCHUSDT, XLMUSDT, ATOMUSDT

## Rate Limiting

The scripts implement rate limiting to avoid hitting Binance API limits:

- 0.5 second delay between API calls
- 1 second delay between symbols
- Batch processing to reduce database calls

## Error Handling

- Duplicate records are automatically skipped
- API errors are logged and handled gracefully
- Database connection issues are reported
- Invalid data is filtered out

## Monitoring

Check the logs for:

- Number of records processed/inserted/skipped
- API response times
- Error messages
- Sync completion status

## Scheduling

For continuous operation, you can schedule the auto script:

### Windows Task Scheduler

```powershell
# Create a scheduled task to run every 6 hours
schtasks /create /tn "TransactionHistorySync" /tr "python C:\path\to\autofill_transaction_history.py --continuous" /sc hourly /mo 6
```

### Linux Cron

```bash
# Add to crontab to run every 6 hours
0 */6 * * * cd /path/to/project && python scripts/autofill_transaction_history.py --continuous
```

## Troubleshooting

### Common Issues

1. **No records found**: Check if you have recent trading activity
2. **API errors**: Verify Binance API credentials and permissions
3. **Database errors**: Check Supabase connection and table permissions
4. **Rate limiting**: Increase delays between API calls

### Debug Mode

Enable debug logging by modifying the logging level in the scripts:

```python
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
```

## Data Validation

The scripts validate data before insertion:

- Timestamps are converted to milliseconds
- Amounts are converted to float
- Empty or invalid records are filtered out
- Duplicate checking prevents data corruption

## Performance Considerations

- Batch inserts are more efficient than individual inserts
- Chunked fetching prevents memory issues with large datasets
- Rate limiting prevents API throttling
- Duplicate checking adds overhead but ensures data integrity

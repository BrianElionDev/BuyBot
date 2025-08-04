# Binance History Backfiller

## Overview
The Binance History Backfiller is designed to backfill the `trades` table in the database with missing PnL and exit price data from Binance history. This ensures accurate analysis of the trading system's performance.

## Purpose
The primary objective is **not** to produce CSV and JSON files for analysis, but rather to:
- Backfill the `trades` table with `pnl_usd` (profit and loss in USD)
- Backfill the `trades` table with `binance_exit_price` (price the trade exited at)
- Update the `updated_at` field with the current timestamp
- Use `exchange_order_id` to link Binance data with database records

## Key Features

### Database Backfilling
- **Target Fields**: `pnl_usd`, `binance_exit_price`, `updated_at`
- **Linking Method**: Uses `exchange_order_id` to match Binance orders with database records
- **Scope**: Focuses on closed trades missing PnL or exit price data
- **Time Range**: Configurable (default: last 30 days)

### Binance Data Sources
- **User Trades**: Fetches actual trade execution data from Binance
- **Order History**: Retrieves order status and execution details
- **Realized PnL**: Uses Binance's calculated realized PnL when available
- **Fallback Calculation**: Calculates PnL from entry/exit prices when Binance data unavailable

### Integration
- **Standalone Script**: `scripts/backfill_trades_from_history.py`
- **Integrated Sync**: Added to existing `sync_trade_statuses_with_binance` function
- **Analysis Files**: Only generates analysis summary, not raw data files

## Usage

### Standalone Backfill Script
```bash
# Backfill all symbols for last 30 days
python scripts/backfill_trades_from_history.py --days 30

# Backfill specific symbol for last 7 days
python scripts/backfill_trades_from_history.py --symbol BTCUSDT --days 7

# Backfill all symbols for last 14 days
python scripts/backfill_trades_from_history.py --all-symbols --days 14
```

### Integrated with Sync Process
The backfill logic is automatically included in the main sync process:
```bash
python scripts/cleanup_scripts/sync_trade_statuses.py
```

## Generated Files

### Analysis Files (Only)
- `logs/binance_history/backfill_analysis_YYYYMMDD_HHMMSS.json`
  - Summary of backfill operations
  - Success rates and statistics
  - Data availability metrics

### No Raw Data Files
- **No CSV files** with raw Binance data
- **No JSON files** with raw history data
- **Only analysis summaries** are saved

## Database Schema

### Target Table: `trades`
```sql
-- Key fields that get backfilled
pnl_usd DECIMAL(20,8)           -- Profit/Loss in USD
binance_exit_price DECIMAL(20,8) -- Exit price from Binance
updated_at TIMESTAMP            -- Last update timestamp
exchange_order_id VARCHAR(255)  -- Links to Binance orderId
```

### Linking Logic
1. Query database for closed trades missing PnL/exit price
2. Use `exchange_order_id` to find matching Binance trades
3. Extract realized PnL and exit price from Binance data
4. Update database records with missing information

## API Requirements

### Binance API Endpoints Used
- `futures_account_trades` - User trade history
- `futures_get_all_orders` - Order history
- Rate limiting: 0.1 second delay between operations

### Required Permissions
- Futures trading history access
- Order history access
- Read-only access sufficient

## Error Handling

### Common Issues
- **Missing Order ID**: Trades without `exchange_order_id` are skipped
- **No Binance Data**: Orders not found in Binance history are logged
- **API Rate Limits**: Built-in delays prevent rate limit violations
- **Invalid Data**: Malformed responses are handled gracefully

### Logging
- Detailed logs for each backfill operation
- Success/failure counts and rates
- Error details for troubleshooting

## Configuration

### Environment Variables
```bash
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
BINANCE_TESTNET=false
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
```

### Default Settings
- **Time Range**: 30 days
- **Rate Limiting**: 0.1 seconds between operations
- **Batch Size**: Process trades individually for accuracy

## Troubleshooting

### No Trades Found
- Check if trades exist in the specified time range
- Verify trades have `exchange_order_id` values
- Ensure trades are marked as `CLOSED` status

### API Errors
- Verify Binance API credentials
- Check API rate limits
- Ensure proper permissions for futures trading

### Database Errors
- Verify Supabase connection
- Check database schema matches expectations
- Ensure proper permissions for table updates

## Performance Considerations

### Optimization
- Processes trades individually for accuracy
- Uses efficient database queries with time filters
- Implements rate limiting to avoid API restrictions

### Scalability
- Can handle large numbers of trades
- Configurable time ranges for different needs
- Memory-efficient processing

## Future Enhancements

### Potential Improvements
- Batch processing for better performance
- Parallel processing for multiple symbols
- Real-time backfill integration
- Enhanced error recovery mechanisms
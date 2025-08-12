# Binance History Retrieval Scripts

This directory contains scripts to retrieve comprehensive history data from Binance, including order history, trade history, and transaction history.

## Scripts Available

### 1. `get_binance_history_simple.py` (Recommended)
Simple and easy-to-use script for getting Binance history data.

### 2. `get_binance_history.py`
Comprehensive script with advanced features and class-based implementation.

## Usage

### Basic Usage (All Symbols)
```bash
# Get history for common symbols (BTCUSDT, ETHUSDT, SOLUSDT, LINKUSDT)
python3 scripts/account_scripts/get_binance_history_simple.py
```

### Specific Symbol
```bash
# Get history for a specific symbol
python3 scripts/account_scripts/get_binance_history_simple.py --symbol BTCUSDT

# Get history for a specific symbol with custom time range
python3 scripts/account_scripts/get_binance_history_simple.py --symbol ETHUSDT --days 7
```

### Advanced Usage
```bash
# Use the comprehensive script
python3 scripts/account_scripts/get_binance_history.py
```

## Output

The scripts generate JSON files with the following structure:

### Order History
```json
{
  "orders": {
    "BTCUSDT": [
      {
        "orderId": "123456789",
        "symbol": "BTCUSDT",
        "type": "MARKET",
        "side": "BUY",
        "price": "0",
        "origQty": "0.001",
        "executedQty": "0.001",
        "avgPrice": "45000.00",
        "status": "FILLED",
        "time": 1640995200000
      }
    ]
  }
}
```

### Trade History
```json
{
  "trades": {
    "BTCUSDT": [
      {
        "id": "987654321",
        "orderId": "123456789",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": "0.001",
        "price": "45000.00",
        "realizedPnl": "0",
        "time": 1640995200000
      }
    ]
  }
}
```

### Transaction History
```json
{
  "deposits": [
    {
      "coin": "USDT",
      "amount": "1000.00",
      "status": "1",
      "time": 1640995200000
    }
  ],
  "withdrawals": [
    {
      "coin": "BTC",
      "amount": "0.001",
      "status": "6",
      "time": 1640995200000
    }
  ]
}
```

## Data Retrieved

### Order History
- All order types (MARKET, LIMIT, STOP_MARKET, etc.)
- Order status (NEW, FILLED, PARTIALLY_FILLED, CANCELED, etc.)
- Execution details (quantity, price, average price)
- Timestamps and order IDs

### Trade History
- Executed trades with realized PnL
- Trade details (quantity, price, side)
- Trade IDs and timestamps

### Transaction History
- Deposit history with status and amounts
- Withdrawal history with status and amounts
- Transaction timestamps

## File Naming Convention

- **Complete history**: `binance_history_YYYYMMDD_HHMMSS.json`
- **Specific symbol**: `{SYMBOL}_history_YYYYMMDD_HHMMSS.json`

## Time Ranges

- **Default**: Last 30 days
- **Customizable**: Use `--days` parameter to specify number of days
- **Maximum**: Up to 1000 records per request (Binance API limit)

## Rate Limiting

The scripts include built-in rate limiting to respect Binance API limits:
- 0.1 second delay between requests
- Automatic error handling for rate limit violations

## Error Handling

- Graceful handling of API errors
- Detailed logging of all operations
- Continues processing even if some symbols fail

## Prerequisites

1. **API Credentials**: Set up your Binance API key and secret in `.env`
2. **Permissions**: Ensure your API key has read permissions for:
   - Order history
   - Trade history
   - Transaction history

## Environment Variables

```bash
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
BINANCE_TESTNET=True  # Set to False for mainnet
```

## Security Notes

- Never commit API credentials to version control
- Use testnet for testing
- Ensure API keys have minimal required permissions
- Regularly rotate API keys

## Troubleshooting

### Common Issues

1. **Missing API credentials**
   ```
   ❌ Missing Binance API credentials
   ```
   **Solution**: Check your `.env` file and ensure credentials are set.

2. **Rate limit errors**
   ```
   ❌ Error getting orders - APIError(code=-429)
   ```
   **Solution**: The script includes rate limiting, but you may need to wait if you've made many requests recently.

3. **Permission errors**
   ```
   ❌ Error getting deposits - APIError(code=-2015)
   ```
   **Solution**: Check that your API key has the required permissions.

### Getting Help

- Check the logs for detailed error messages
- Verify your API credentials and permissions
- Ensure you're using the correct network (testnet vs mainnet)

## Examples

### Get recent ETH trades
```bash
python3 scripts/account_scripts/get_binance_history_simple.py --symbol ETHUSDT --days 7
```

### Get all history for analysis
```bash
python3 scripts/account_scripts/get_binance_history_simple.py
```

### Check specific order details
```bash
# Run the script and then examine the JSON file
python3 scripts/account_scripts/get_binance_history_simple.py --symbol BTCUSDT
cat BTCUSDT_history_*.json | jq '.orders[0]'
```

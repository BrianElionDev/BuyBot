# Trade Lifecycle Implementation Summary

## Overview
This document summarizes the implemented logic for handling Discord trading signals with complete trade lifecycle tracking via database row updates.

## Database Schema Changes Required

Add these 6 columns to the existing `trades` table:

```sql
ALTER TABLE trades ADD COLUMN status VARCHAR(20) DEFAULT 'PENDING';
ALTER TABLE trades ADD COLUMN entry_price DECIMAL(20,8);
ALTER TABLE trades ADD COLUMN position_size DECIMAL(20,8);
ALTER TABLE trades ADD COLUMN exchange_order_id VARCHAR(255);
ALTER TABLE trades ADD COLUMN exit_price DECIMAL(20,8);
ALTER TABLE trades ADD COLUMN pnl_usd DECIMAL(20,8);
```

## Signal Processing Flow

### 1. Initial Trade Signal Processing
- **Input**: Discord signal without `"trade"` field
- **Logic**: Update existing database row with execution results
- **Status Progression**: `NULL` → `ACTIVE` (success) or `FAILED` (failure)

```python
signal_data = {
    'timestamp': '2025-06-12T19:02:33.311Z',
    'content': '@Woods\nHype scalp risky 42.23 stop 41.03 (edited)',
    'structured': 'HYPE|Entry:|42.23|SL:|42.23',
    'signal_id': 'discord_123'
}
```

### 2. Follow-up Signal Processing
- **Input**: Discord signal with `"trade"` field referencing original
- **Logic**: Find original trade by `signal_id`, update with close/update info
- **Status Progression**: `ACTIVE` → `CLOSED` (if position closed)

```python
follow_up_signal = {
    "discord_id": "1386336471073689725",
    "trader": "@Johnny",
    "trade": "discord_123",  # References original signal_id
    "timestamp": "2025-06-22T13:26:11.590Z",
    "content": " HYPE ⁠🚀｜trades⁠: Stopped out @Johnny"
}
```

## Key Components Implemented

### 1. Database Functions (`discord_bot/database.py`)
- `update_existing_trade()` - Updates existing rows by signal_id or trade_id
- `find_trade_by_discord_id()` - Finds original trade for follow-ups
- Updated `find_active_trade_by_symbol()` - Uses `status='ACTIVE'`

### 2. TradingEngine Extensions (`src/bot/trading_engine.py`)
- `process_trade_update()` - Handles update signals
- `close_position_at_market()` - Closes positions on Binance
- `update_stop_loss()` - Updates stop loss (implementation pending)

### 3. DiscordBot Logic (`discord_bot/discord_bot.py`)
- `_handle_new_trade()` - Updates existing row with execution results
- `_handle_trade_update()` - Processes follow-up signals
- `process_signal()` - Routes signals based on presence of `"trade"` field

## Trade Lifecycle Examples

### Example 1: Successful Trade
```
Row created externally → Signal processed → Status: ACTIVE → Follow-up → Status: CLOSED
```

**Database progression:**
```sql
-- Initial state (created externally)
INSERT INTO trades (signal_id, content, structured, timestamp)
VALUES ('signal_123', '@Woods\nHype scalp...', 'HYPE|Entry:|42.23...', NOW());

-- After processing initial signal
UPDATE trades SET
  status = 'ACTIVE',
  entry_price = 42.30,
  position_size = 100.0,
  exchange_order_id = 'binance_HYPE_1735567890',
  coin_symbol = 'HYPE'
WHERE signal_id = 'signal_123';

-- After follow-up close signal
UPDATE trades SET
  status = 'CLOSED',
  exit_price = 45.50,
  pnl_usd = 320.00
WHERE id = <trade_id>;
```

### Example 2: Failed Trade
```
Row created externally → Signal processed → Status: FAILED
```

## Configuration
- **Exchange**: CEX only (Binance)
- **Trading Pairs**: Force USDT pairs (`{coin}_USDT`)
- **Price Source**: CoinGecko API for current market prices
- **Slippage**: Handled by TradingEngine price threshold checks

## Testing
Two comprehensive tests validate the implementation:
1. `test_full_signal_processing_flow` - Initial signal processing
2. `test_trade_update_signal_flow` - Follow-up signal processing

Both tests verify:
- Correct database update calls
- Proper signal parsing and validation
- Trading engine integration
- Telegram notifications

## Benefits
1. **Single Source of Truth**: Each trade signal = one database row
2. **Complete Lifecycle**: Track from signal → execution → close
3. **Minimal Schema**: Only 6 additional columns
4. **Robust Error Handling**: Failed trades marked appropriately
5. **CEX Focused**: Simplified Binance-only implementation
6. **Frontend Ready**: Easy queries for trade history and P&L

## Next Steps
1. Apply database schema changes to Supabase
2. Deploy updated code
3. Monitor initial trade executions
4. Implement advanced stop loss management
5. Add position sizing configuration
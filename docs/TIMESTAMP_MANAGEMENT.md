# Trade Timestamp Management System

## Overview

This document describes the comprehensive timestamp management system that ensures `created_at` and `closed_at` timestamps are accurately set at the exact moments when trades are created and closed.

## Key Components

### 1. TimestampManager (`discord_bot/utils/timestamp_manager.py`)

Core class that handles accurate timestamp setting with validation:

- **`set_created_at()`**: Sets timestamp when trade is first created
- **`set_closed_at()`**: Sets timestamp when position is actually closed
- **`validate_created_at()`**: Prevents multiple updates to created_at
- **`validate_closed_at()`**: Only allows closed_at when status is CLOSED
- **`fix_missing_timestamps()`**: One-time backfill for historical data

### 2. WebSocketTimestampHandler

Handles real-time timestamp updates from WebSocket events:

- **`handle_order_execution()`**: Sets created_at when order first executes
- **`handle_position_closure()`**: Sets closed_at when position closes

### 3. Integration Points

#### WebSocket Integration (`src/websocket/database_sync_handler.py`)

- Automatically sets `created_at` when entry orders are FILLED
- Automatically sets `closed_at` when exit orders are FILLED
- Uses exact Binance execution timestamps

#### Backfill Integration

- Uses `fix_historical_timestamps()` for historical data only
- Prevents random timestamp updates during P&L backfill

## Timestamp Rules

### created_at

- **ONLY SET ONCE** when trade is first created
- **NEVER UPDATED** after initial setting
- **SOURCE**: Binance order execution time or Discord signal time
- **VALIDATION**: Prevents multiple updates

### closed_at

- **ONLY SET** when position is actually closed (status = CLOSED)
- **NEVER UPDATED** after initial setting
- **SOURCE**: Binance exit order execution time
- **VALIDATION**: Only allows setting when status is CLOSED

### updated_at

- **ALWAYS UPDATED** for any trade modifications
- **NOT USED** for trade lifecycle calculations
- **PURPOSE**: Track last modification time

## Usage Examples

### Setting Timestamps Properly

```python
from discord_bot.utils.timestamp_manager import ensure_created_at, ensure_closed_at

# When trade is first created
await ensure_created_at(supabase, trade_id, binance_order_time)

# When position is closed
await ensure_closed_at(supabase, trade_id, binance_fill_time)
```

### WebSocket Integration

```python
# In WebSocket handler
if status == 'FILLED':
    if is_exit_order:
        # Sets closed_at automatically
        await self.websocket_timestamp_handler.handle_order_execution(execution_data)
    else:
        # Sets created_at automatically
        await self.websocket_timestamp_handler.handle_order_execution(execution_data)
```

### Historical Data Backfill

```python
# Only for missing timestamps in historical data
from discord_bot.utils.timestamp_manager import fix_historical_timestamps

if not trade.get('closed_at') and trade.get('status') == 'CLOSED':
    await fix_historical_timestamps(supabase, trade_id)
```

## Benefits

### 1. Accuracy

- Uses exact Binance execution timestamps
- No approximations or fallback times
- Precise trade lifecycle windows

### 2. Validation

- Prevents accidental timestamp overwrites
- Ensures timestamps are only set at correct moments
- Validates status before setting closed_at

### 3. Real-time Updates

- WebSocket integration for immediate updates
- No delay between execution and timestamp setting
- Eliminates range issues in P&L calculations

### 4. Historical Data Support

- One-time backfill for existing trades
- Preserves existing correct timestamps
- Safe to run multiple times

## Integration with P&L Calculation

The accurate timestamps solve the P&L range issues:

```python
# Before: Missed final P&L records due to timing issues
start_time, end_time = get_order_lifecycle(trade)  # Inaccurate range

# After: Captures exact trade window including final P&L
start_time, end_time = get_order_lifecycle(trade)  # Accurate range with buffer
income_records = await get_income_for_trade_period(bot, symbol, start_time, end_time)
```

## Monitoring and Validation

### Database Validation Queries

```sql
-- Find trades with missing created_at
SELECT id, status, created_at FROM trades WHERE created_at IS NULL;

-- Find CLOSED trades with missing closed_at
SELECT id, status, closed_at FROM trades WHERE status = 'CLOSED' AND closed_at IS NULL;

-- Validate timestamp chronology
SELECT id, created_at, closed_at
FROM trades
WHERE closed_at IS NOT NULL AND created_at > closed_at;
```

### WebSocket Monitoring

```python
# Monitor timestamp setting in logs
logger.info(f"✅ Set created_at from WebSocket for trade {trade_id}")
logger.info(f"✅ Set closed_at from WebSocket for trade {trade_id}")
```

## Migration Guide

### For Existing Trades

1. Run timestamp validation:

```python
from discord_bot.utils.timestamp_manager import TimestampManager

timestamp_manager = TimestampManager(supabase)
# Fix all historical trades at once
for trade in historical_trades:
    await timestamp_manager.fix_missing_timestamps(trade['id'])
```

2. Enable WebSocket timestamp handling:

```python
# In WebSocket initialization
self.timestamp_manager = TimestampManager(supabase)
self.websocket_timestamp_handler = WebSocketTimestampHandler(self.timestamp_manager)
```

3. Update backfill scripts to use historical fix only:

```python
# Replace direct timestamp setting with:
if not trade.get('closed_at') and trade.get('status') == 'CLOSED':
    await fix_historical_timestamps(supabase, trade_id)
```

## Best Practices

1. **Never set timestamps manually** - use TimestampManager
2. **Let WebSocket handle real-time** - don't override in backfill
3. **Use historical fix only once** - for existing data cleanup
4. **Validate before setting** - check status and existing values
5. **Monitor WebSocket events** - ensure real-time updates work
6. **Test P&L calculations** - verify range accuracy

This system ensures that your trade timestamps are accurate, validated, and properly managed throughout the trade lifecycle.

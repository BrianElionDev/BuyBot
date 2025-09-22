# Position Management System

A comprehensive solution for handling position aggregation, conflict detection, and trade management to ensure database consistency with exchange behavior.

## Problem Solved

This system addresses the critical issue where:
- **Database**: Multiple separate trade records for the same symbol
- **Exchange**: Single aggregated position
- **Result**: Database inconsistency and potential orphaned orders

## Key Features

### 🔍 Position Conflict Detection
- Automatically detects when new trades conflict with existing positions
- Supports same-side and opposite-side conflict detection
- Provides intelligent conflict resolution suggestions

### 🔄 Trade Aggregation
- Merges multiple trades for the same symbol into a single position
- Calculates weighted average entry prices
- Maintains trade history while preventing duplicates

### ⏰ Symbol-Based Cooldowns
- Prevents rapid multiple trades for the same symbol
- Supports trader-specific and position-based cooldowns
- Configurable cooldown durations

### 🧹 Enhanced Orphaned Orders Cleanup
- Cleans up orphaned orders with position aggregation awareness
- Prevents removal of legitimate orders from aggregated positions
- Provides detailed cleanup reports

## Architecture

```
Position Management System
├── PositionManager          # Core position management
├── SymbolCooldownManager    # Cooldown management
├── EnhancedTradeCreator     # Trade creation with conflict detection
├── PositionDatabaseOperations # Database operations
└── Enhanced Orphaned Orders Cleanup # Cleanup with aggregation awareness
```

## Quick Start

### 1. Basic Usage

```python
from src.bot.position_management import PositionManager, SymbolCooldownManager

# Initialize position manager
position_manager = PositionManager(db_manager, exchange)

# Check for conflicts
conflict = await position_manager.check_position_conflict("BTC", "LONG", trade_id)
if conflict:
    print(f"Conflict detected: {conflict.reason}")
    print(f"Suggested action: {conflict.suggested_action.value}")
```

### 2. Enhanced Trade Creation

```python
from src.bot.position_management import EnhancedTradeCreator

# Initialize enhanced trade creator
enhanced_creator = EnhancedTradeCreator(db_manager, exchange, trading_engine)

# Create trade with conflict detection
result = await enhanced_creator.create_trade_with_conflict_detection(
    coin_symbol="BTC",
    signal_price=50000.0,
    position_type="LONG",
    trader="trader_name",
    discord_id="unique_id"
)
```

### 3. Cooldown Management

```python
from src.bot.position_management import SymbolCooldownManager

# Initialize cooldown manager
cooldown_manager = SymbolCooldownManager(
    default_cooldown=300,  # 5 minutes
    position_cooldown=600  # 10 minutes
)

# Check cooldown
is_on_cooldown, reason = cooldown_manager.is_on_cooldown("BTC", "trader_name")
if is_on_cooldown:
    print(f"On cooldown: {reason}")

# Set cooldown
cooldown_manager.set_cooldown("BTC", "trader_name", 300)
```

## Configuration

### Position Manager Settings

```python
# Auto-merge settings
enhanced_creator.auto_merge_enabled = True
enhanced_creator.auto_reject_conflicts = True
enhanced_creator.max_position_trades = 5
```

### Cooldown Settings

```python
cooldown_manager = SymbolCooldownManager(
    default_cooldown=300,      # 5 minutes for regular trades
    position_cooldown=600      # 10 minutes when position exists
)
```

## Database Schema Integration

The system works with your existing database schema:

```sql
-- Uses existing trades table
SELECT * FROM trades WHERE status = 'OPEN' AND is_active = true;

-- New fields added for position management
ALTER TABLE trades ADD COLUMN merged_into_trade_id INTEGER;
ALTER TABLE trades ADD COLUMN merge_reason TEXT;
ALTER TABLE trades ADD COLUMN merged_at TIMESTAMP;
```

## Conflict Resolution Actions

### 1. MERGE
- Merges new trade into existing position
- Updates primary trade with aggregated data
- Marks secondary trade as merged

### 2. REJECT
- Rejects new trade due to conflict
- Sets appropriate rejection reason
- Applies cooldown to prevent rapid retries

### 3. REPLACE
- Closes existing position
- Creates new position with new trade
- Used for opposite-side conflicts

### 4. COOLDOWN
- Applies cooldown and rejects trade
- Used for rapid successive trades

## Monitoring and Maintenance

### Position Status

```python
# Get position summary
summary = await position_manager.get_position_summary()
print(f"Total positions: {summary['total_positions']}")
print(f"Total unrealized PnL: ${summary['total_unrealized_pnl']:.2f}")

# Get specific position status
status = await enhanced_creator.get_position_status("BTC")
print(f"BTC has position: {status['has_position']}")
```

### Cleanup Operations

```bash
# Run enhanced orphaned orders cleanup
python3 scripts/maintenance/cleanup_scripts/enhanced_orphaned_orders_cleanup.py

# Run with dry-run first
python3 scripts/maintenance/cleanup_scripts/enhanced_orphaned_orders_cleanup.py --dry-run
```

### Testing

```bash
# Run position management tests
python3 scripts/testing/test_position_management.py

# Run integration tests
python3 scripts/setup/integrate_position_management.py
```

## Error Handling

The system includes comprehensive error handling:

```python
try:
    result = await enhanced_creator.create_trade_with_conflict_detection(...)
    if result[0]:  # Success
        print("Trade created successfully")
    else:
        print(f"Trade creation failed: {result[1]}")
except Exception as e:
    logger.error(f"Error in trade creation: {e}")
```

## Logging

Enable detailed logging for debugging:

```python
import logging
logging.getLogger('src.bot.position_management').setLevel(logging.DEBUG)
```

## Performance Considerations

- **Position Cache**: 30-second TTL for position data
- **Database Queries**: Optimized with proper indexing
- **Rate Limiting**: Built-in delays to prevent API rate limits
- **Memory Usage**: Efficient data structures and cleanup

## Troubleshooting

### Common Issues

1. **Import Errors**
   ```bash
   # Ensure project root is in Python path
   export PYTHONPATH="${PYTHONPATH}:/path/to/rubicon-trading-bot"
   ```

2. **Database Connection Issues**
   ```python
   # Check database connection
   await db_manager.initialize()
   ```

3. **Exchange API Issues**
   ```python
   # Verify API credentials
   await exchange._init_client()
   ```

### Debug Mode

```python
# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Test individual components
await position_manager.get_active_positions(force_refresh=True)
```

## Contributing

When adding new features:

1. Follow the existing code structure
2. Add comprehensive tests
3. Update documentation
4. Ensure backward compatibility

## License

This system is part of the Rubicon Trading Bot project and follows the same license terms.

# Binance WebSocket Module

Real-time WebSocket integration for Binance futures trading with automatic database synchronization.

## Features

- **Real-time Order Status Updates**: Instant notifications when orders are filled, canceled, or modified
- **Live PnL Tracking**: Real-time realized and unrealized PnL calculations
- **Automatic Reconnection**: Robust connection management with exponential backoff
- **Rate Limiting**: Compliant with Binance WebSocket rate limits
- **Error Handling**: Comprehensive error handling and logging
- **Listen Key Management**: Automatic listen key refresh and cleanup

## Architecture

```
src/websocket/
├── __init__.py                 # Module exports
├── websocket_config.py         # Configuration and constants
├── binance_websocket_manager.py # Main WebSocket manager
├── example_usage.py            # Integration examples
└── README.md                   # This file
```

## Quick Start

### 1. Basic Usage

```python
import asyncio
from src.websocket import BinanceWebSocketManager

async def main():
    # Initialize WebSocket manager
    ws_manager = BinanceWebSocketManager(
        api_key="your_api_key",
        api_secret="your_api_secret",
        is_testnet=True
    )

    # Add event handlers
    async def handle_order_fill(data):
        print(f"Order filled: {data}")

    ws_manager.add_event_handler('executionReport', handle_order_fill)

    # Start WebSocket connections
    await ws_manager.start()

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await ws_manager.stop()

asyncio.run(main())
```

### 2. Integration with DiscordBot

```python
# In discord_bot/discord_bot.py
from src.websocket import WebSocketIntegrationExample

class DiscordBot:
    def __init__(self):
        # ... existing initialization ...

        # Add WebSocket integration
        self.websocket_integration = WebSocketIntegrationExample(
            self.db_manager,
            self.binance_exchange
        )

    async def start(self):
        # ... existing startup ...

        # Start WebSocket manager
        await self.websocket_integration.start()

    async def stop(self):
        # Stop WebSocket manager
        await self.websocket_integration.stop()

        # ... existing cleanup ...
```

## Event Types

### User Data Stream Events

- **`executionReport`**: Order status changes (NEW, FILLED, CANCELED, etc.)
- **`outboundAccountPosition`**: Account balance and position updates
- **`balanceUpdate`**: Balance change notifications

### Market Data Stream Events

- **`ticker`**: 24hr price statistics
- **`trade`**: Individual trade data
- **`depth`**: Order book updates

### System Events

- **`connection`**: WebSocket connection established
- **`disconnection`**: WebSocket connection lost
- **`error`**: Error notifications

## Configuration

The WebSocket manager uses the following configuration (from `websocket_config.py`):

```python
# Connection settings
PING_INTERVAL: int = 180  # 3 minutes
PONG_TIMEOUT: int = 600   # 10 minutes
CONNECTION_TIMEOUT: int = 24 * 60 * 60  # 24 hours

# Rate limiting
MAX_MESSAGES_PER_SECOND: int = 10
MAX_PING_PONG_PER_SECOND: int = 5
MAX_STREAMS_PER_CONNECTION: int = 1024

# Reconnection
RECONNECT_DELAY: int = 5  # seconds
MAX_RECONNECT_ATTEMPTS: int = 10
EXPONENTIAL_BACKOFF_BASE: float = 2.0
```

## Safety Features

### Rate Limiting
- Automatic message rate limiting (10 messages/second)
- Ping/pong rate limiting (5 per second)
- Connection limit compliance (300 connections per 5 minutes)

### Error Handling
- Automatic reconnection with exponential backoff
- Maximum consecutive error limits
- Graceful error recovery

### Connection Management
- 24-hour connection timeout handling
- Automatic listen key refresh (every 30 minutes)
- Proper cleanup on shutdown

## Testing

Run the WebSocket test:

```bash
cd tests
python test_websocket.py
```

The test will:
1. Test basic connection
2. Monitor events for 2 minutes
3. Report connection status and event counts
4. Validate error handling

## Database Integration

The WebSocket manager automatically updates your database with:

- **Order Status**: Real-time order fill notifications
- **Exit Prices**: Actual fill prices from Binance
- **Realized PnL**: Actual PnL from Binance API
- **Unrealized PnL**: Calculated based on current market prices
- **Order ID Mapping**: Links Binance `orderId` to database `exchange_order_id`
- **Trade Status Updates**: Updates trade status when orders fill, cancel, or expire

### Example Database Updates

```python
# When an order is filled
{
    'status': 'CLOSED',
    'exit_price': 45000.0,
    'binance_exit_price': 45000.0,
    'pnl_usd': 150.25,
    'exchange_order_id': '123456789',  # Binance order ID
    'updated_at': '2025-01-28T10:30:00Z'
}

# When position is partially closed
{
    'status': 'PARTIALLY_CLOSED',
    'exit_price': 44500.0,
    'binance_exit_price': 44500.0,
    'position_size': 0.5,  # Updated position size
    'updated_at': '2025-01-28T10:30:00Z'
}

# When order is canceled
{
    'status': 'FAILED',
    'updated_at': '2025-01-28T10:30:00Z'
}
```

### Order ID Mapping

The WebSocket manager automatically links Binance orders to your database trades:

1. **When an order is created**: The `orderId` from Binance is stored in `exchange_order_id`
2. **When an order fills**: The system finds the trade by `exchange_order_id` and updates it
3. **Fallback matching**: If `exchange_order_id` is not set, it searches `binance_response` for the order ID

```python
# Example: Linking order 123456789 to trade 42
{
    'id': 42,
    'exchange_order_id': '123456789',  # Binance order ID
    'status': 'CLOSED',
    'exit_price': 45000.0,
    'pnl_usd': 150.25
}
```d

## Migration from Sync Scripts

### Before (Polling)
```python
# Old sync script approach
async def sync_orders():
    while True:
        orders = await binance.get_open_orders()
        for order in orders:
            if order['status'] == 'FILLED':
                update_database(order)
        await asyncio.sleep(300)  # 5 minute delay
```

### After (WebSocket)
```python
# New real-time approach
async def handle_order_fill(data):
    if data['X'] == 'FILLED':
        update_database(data)  # Instant update

ws_manager.add_event_handler('executionReport', handle_order_fill)
```

## Benefits

1. **Real-time Updates**: No more 5-minute delays
2. **Reduced API Calls**: 90% reduction in REST API usage
3. **Better Performance**: Lower latency and resource usage
4. **Improved Reliability**: Automatic reconnection and error handling
5. **Accurate PnL**: Real-time calculations based on actual fills

## Troubleshooting

### Common Issues

1. **Connection Drops**: Check network stability and API key permissions
2. **Rate Limit Errors**: Reduce event handler processing time
3. **Listen Key Expiry**: Ensure proper listen key refresh
4. **Memory Usage**: Monitor for memory leaks in event handlers

### Debug Mode

Enable detailed logging:

```python
import logging
logging.getLogger('src.websocket').setLevel(logging.DEBUG)

# Enable WebSocket message logging
ws_manager.config.LOG_WEBSOCKET_MESSAGES = True
```

## API Reference

### BinanceWebSocketManager

- `__init__(api_key, api_secret, is_testnet=False)`
- `start()`: Start WebSocket connections
- `stop()`: Stop WebSocket connections
- `add_event_handler(event_type, handler)`: Register event handler
- `remove_event_handler(event_type, handler)`: Remove event handler
- `get_connection_status()`: Get current connection status

### WebSocketConfig

- `PING_INTERVAL`: Ping interval in seconds
- `PONG_TIMEOUT`: Pong timeout in seconds
- `MAX_MESSAGES_PER_SECOND`: Rate limit for messages
- `MAX_RECONNECT_ATTEMPTS`: Maximum reconnection attempts

## Contributing

When adding new features:

1. Follow the existing code structure
2. Add comprehensive error handling
3. Include logging for debugging
4. Update tests and documentation
5. Ensure rate limit compliance
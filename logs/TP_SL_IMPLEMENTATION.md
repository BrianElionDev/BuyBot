# Take Profit / Stop Loss Implementation

## Overview

This implementation follows the **Binance Futures API requirements** for proper TP/SL order management. The key principle is that **TP and SL orders must be created as separate orders after position opening**, not combined with the initial order.

## Binance Futures API Requirements

### ✅ **Correct Approach**:
1. **Open position** with market/limit order
2. **Create separate TP orders** using `TAKE_PROFIT_MARKET`
3. **Create separate SL order** using `STOP_MARKET`
4. **Update by canceling and recreating** (no direct updates allowed)

### ❌ **Incorrect Approach**:
- Combining TP/SL with position opening order
- Trying to update TP/SL orders directly
- Using wrong order types

## Implementation Details

### 1. Order Creation Flow

```python
# 1. Open position first
order_result = await create_futures_order(
    pair="BTCUSDT",
    side="BUY",
    type="MARKET",
    quantity=0.001
)

# 2. Create TP/SL orders separately
tp_sl_orders = await _create_tp_sl_orders(
    trading_pair="BTCUSDT",
    position_type="LONG",
    position_size=0.001,
    take_profits=[31000, 32000],  # Multiple TP levels
    stop_loss=29500
)
```

### 2. TP/SL Order Types

#### **Take Profit Orders**:
```python
tp_order = await create_futures_order(
    pair="BTCUSDT",
    side="SELL",  # Sell to close long position
    type="TAKE_PROFIT_MARKET",
    quantity=0.001,
    stopPrice=31000  # Trigger price
)
```

#### **Stop Loss Orders**:
```python
sl_order = await create_futures_order(
    pair="BTCUSDT",
    side="SELL",  # Sell to close long position
    type="STOP_MARKET",
    quantity=0.001,
    stopPrice=29500  # Trigger price
)
```

### 3. Order Update Process

Since Binance doesn't allow direct TP/SL updates, we must:

```python
# 1. Cancel existing TP/SL orders
await cancel_all_futures_orders("BTCUSDT")

# 2. Get current position size
position_size = get_current_position_size("BTCUSDT")

# 3. Create new TP/SL orders
new_orders = await _create_tp_sl_orders(
    trading_pair="BTCUSDT",
    position_type="LONG",
    position_size=position_size,
    take_profits=[31500, 32500],  # Updated TP levels
    stop_loss=29000  # Updated SL
)
```

## Code Implementation

### 1. Trading Engine Methods

#### **`_create_tp_sl_orders()`**:
- Creates separate TP and SL orders
- Handles multiple TP levels
- Uses correct order types and parameters
- Returns list of created orders

#### **`update_tp_sl_orders()`**:
- Cancels existing TP/SL orders
- Gets current position size
- Creates new TP/SL orders
- Returns success status and new orders

#### **`cancel_tp_sl_orders()`**:
- Cancels all TP/SL orders for a symbol
- Used for cleanup or manual management

### 2. Database Storage

#### **New Column**: `tp_sl_orders`
- Stores TP/SL order information as JSON
- Includes order IDs, prices, and types
- Enables tracking and management

#### **Example Storage**:
```json
{
  "tp_sl_orders": [
    {
      "orderId": "12345",
      "order_type": "TAKE_PROFIT",
      "tp_level": 1,
      "stopPrice": "31000",
      "symbol": "BTCUSDT"
    },
    {
      "orderId": "12346",
      "order_type": "STOP_LOSS",
      "stopPrice": "29500",
      "symbol": "BTCUSDT"
    }
  ]
}
```

### 3. Database Methods

#### **`update_tp_sl_orders()`**:
- Updates TP/SL orders for a specific trade
- Stores order information in database
- Maintains audit trail

## Usage Examples

### 1. Creating Position with TP/SL

```python
# Process signal with TP/SL
success, result = await trading_engine.process_signal(
    coin_symbol="BTC",
    signal_price=30000,
    position_type="LONG",
    order_type="MARKET",
    take_profits=[31000, 32000],  # Two TP levels
    stop_loss=29500
)

# Result will include TP/SL orders
if success and "tp_sl_orders" in result:
    print(f"Created {len(result['tp_sl_orders'])} TP/SL orders")
```

### 2. Updating TP/SL Orders

```python
# Update TP/SL for existing position
success, new_orders = await trading_engine.update_tp_sl_orders(
    trading_pair="BTCUSDT",
    position_type="LONG",
    new_take_profits=[31500, 32500],
    new_stop_loss=29000
)

if success:
    print(f"Updated TP/SL orders: {len(new_orders)} orders")
```

### 3. Canceling TP/SL Orders

```python
# Cancel all TP/SL orders
success = await trading_engine.cancel_tp_sl_orders("BTCUSDT")

if success:
    print("All TP/SL orders canceled")
```

## Error Handling

### 1. **Position Size Issues**:
- Validates position exists before creating TP/SL
- Handles zero position size gracefully
- Logs warnings for missing positions

### 2. **Order Creation Failures**:
- Individual TP/SL order failures don't affect main position
- Logs specific errors for each order
- Continues with remaining orders

### 3. **API Errors**:
- Handles Binance API exceptions
- Retries on temporary failures
- Graceful degradation on permanent failures

## Monitoring and Alerts

### 1. **TP/SL Order Status**:
- Track order creation success/failure
- Monitor order execution
- Alert on missing TP/SL orders

### 2. **Position Risk**:
- Verify TP/SL orders exist for open positions
- Check order prices are reasonable
- Alert on position without protection

### 3. **Update Failures**:
- Monitor TP/SL update success rates
- Track cancellation failures
- Alert on stuck orders

## Best Practices

### 1. **Order Management**:
- Always create TP/SL after position opening
- Use separate orders for each TP level
- Cancel existing orders before updating

### 2. **Price Validation**:
- Validate TP/SL prices against current market
- Ensure reasonable price ranges
- Check for extreme values

### 3. **Error Recovery**:
- Retry failed TP/SL creation
- Manual intervention for stuck orders
- Regular cleanup of orphaned orders

## Testing

### 1. **Test Scenarios**:
```python
# Test TP/SL creation
test_tp_sl_creation()

# Test TP/SL updates
test_tp_sl_updates()

# Test error handling
test_tp_sl_errors()

# Test position validation
test_position_validation()
```

### 2. **Validation Checks**:
- Verify orders are created with correct parameters
- Check database storage is accurate
- Confirm order cancellation works
- Test update process end-to-end

## Compliance and Audit

### 1. **Order Tracking**:
- All TP/SL orders are logged
- Order IDs stored for reference
- Complete audit trail maintained

### 2. **Risk Management**:
- Position protection verified
- Order prices validated
- Manual override capabilities

### 3. **Financial Accuracy**:
- No false order creation
- Accurate position tracking
- Proper error handling

This implementation ensures **compliance with Binance Futures API requirements** while maintaining **financial accuracy and proper risk management**.
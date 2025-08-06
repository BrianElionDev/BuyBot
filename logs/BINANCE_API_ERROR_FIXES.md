# Binance API Error Fixes

## Issues Identified

### 1. Binance API Error: "Could not get order status"

**Error**: `APIError(code=-2015): Invalid API-key, IP, or permissions for action`

**Root Cause**: The API key doesn't have the necessary permissions to query order status or the IP isn't whitelisted.

### 2. Database Error: Invalid JSON format for double precision

**Error**: `invalid input syntax for type double precision: "{"value":0.184165}"`

**Root Cause**: Code was trying to store JSON objects in double precision columns.

## Fixes Implemented

### Database Fix ✅

Fixed the database update issue by storing values as floats instead of JSON objects:

**Before:**

```python
updates["entry_price"] = {"value": float(entry_price_structured)}
updates["binance_entry_price"] = {"value": float(binance_entry_price)}
```

**After:**

```python
updates["entry_price"] = float(entry_price_structured)
updates["binance_entry_price"] = float(binance_entry_price)
```

### Binance API Fix Required 🔧

The Binance API error requires manual configuration changes:

#### 1. Check API Key Permissions

1. Log into your Binance account
2. Go to **API Management**
3. Check your API key permissions:
   - ✅ **Enable Reading** (required for order status queries)
   - ✅ **Enable Futures** (required for futures trading)
   - ✅ **Enable Spot & Margin Trading** (if using spot trading)

#### 2. Check IP Whitelist

1. In API Management, verify your current IP is whitelisted
2. Add your server's IP address to the whitelist
3. If using a dynamic IP, consider using a static IP or VPN

#### 3. Verify API Key Status

1. Ensure the API key is **Active**
2. Check if there are any restrictions on the key
3. Verify the key hasn't expired

## Alternative Solutions

### Option 1: Use Different API Endpoint

If order status queries continue to fail, we can modify the code to use a different approach:

```python
# Instead of querying order status, check position directly
async def check_order_status_alternative(self, symbol: str, order_id: str):
    try:
        # Check if position exists instead of order status
        positions = await self.binance_exchange.get_position_risk(symbol=symbol)
        for position in positions:
            if float(position.get('positionAmt', 0)) != 0:
                return {"status": "FILLED", "position": position}
        return {"status": "UNFILLED"}
    except Exception as e:
        logger.warning(f"Could not check position status: {e}")
        return {"status": "UNKNOWN"}
```

### Option 2: Skip Order Status Check

For immediate fix, we can skip the order status check and rely on the order creation response:

```python
# In trading_engine.py, modify the order placement logic
if 'orderId' in order_result:
    # Order was created successfully, assume it's valid
    logger.info(f"Order created successfully: {order_result['orderId']}")
    return True, order_result
else:
    # Order creation failed
    return False, order_result
```

## Testing the Fixes

### 1. Test Database Fix

```bash
# Run the retry script to test database updates
python scripts/manual_trade_retry.py
```

### 2. Test Binance API

```bash
# Test API connectivity
python scripts/account_scripts/check_binance_permissions.py
```

## Monitoring

After implementing fixes, monitor:

1. **Database Updates**: Should no longer show JSON format errors
2. **Order Status Queries**: Should work if API permissions are correct
3. **Trade Success Rate**: Should improve with proper error handling

## Configuration Checklist

- [ ] API key has "Enable Reading" permission
- [ ] API key has "Enable Futures" permission
- [ ] Server IP is whitelisted in Binance
- [ ] API key is active and not expired
- [ ] Database columns are properly typed (double precision)

## Emergency Workaround

If Binance API issues persist, implement this temporary workaround:

```python
# In trading_engine.py, add this method
async def create_order_without_status_check(self, ...):
    """Create order without checking status (emergency workaround)"""
    order_result = await self.binance_exchange.create_futures_order(...)

    if 'orderId' in order_result:
        # Assume order is valid if we get an order ID
        return True, order_result
    else:
        return False, order_result
```

This will allow trading to continue while you resolve the API permission issues.

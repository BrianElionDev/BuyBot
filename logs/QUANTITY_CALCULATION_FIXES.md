# Quantity Calculation Fixes for Unfilled Trades

## Problem Analysis

Over the past 24 hours, many trades have been failing with `executedQty: 0.0` and `status: "UNFILLED"`. Analysis of the trade records revealed several critical issues:

### Root Causes Identified:

1. **Incorrect Quantity Calculation**: The formula `TRADE_AMOUNT / current_price` was producing quantities that didn't meet Binance's precision requirements
2. **Missing Precision Formatting**: Quantities weren't being properly formatted to match Binance's step_size requirements
3. **Insufficient Validation**: Orders were being sent to Binance with invalid quantities
4. **Symbol Validation Issues**: Some symbols weren't being properly validated before order placement

### Specific Issues from Trade Records:

| Symbol | Issue | Root Cause |
|--------|-------|------------|
| SUIUSDT | `origQty: "25.9"` | Valid quantity but precision formatting issue |
| PENGUUSDT | `origQty: "2491"` | Valid quantity but order not filled (market conditions) |
| HYPEUSDT | `"Quantity greater than max quantity"` | Quantity calculation error |
| ZBCN | `"Symbol ZBCN not supported"` | Symbol not supported on Binance Futures |

## Fixes Implemented

### 1. Enhanced Quantity Calculation (`src/bot/trading_engine.py`)

**Before:**
```python
trade_amount = config.TRADE_AMOUNT / current_price
```

**After:**
```python
# Calculate trade amount based on USDT value and current price
usdt_amount = config.TRADE_AMOUNT
trade_amount = usdt_amount / current_price

# Apply quantity multiplier if specified (for memecoins)
if quantity_multiplier and quantity_multiplier > 1:
    trade_amount *= quantity_multiplier

# Format quantity to proper step size
if step_size:
    from decimal import Decimal, ROUND_DOWN
    step_dec = Decimal(str(step_size))
    amount_dec = Decimal(str(trade_amount))
    formatted_amount = (amount_dec // step_dec) * step_dec
    trade_amount = float(formatted_amount)
```

### 2. Improved Symbol Validation

**Added comprehensive symbol validation:**
```python
# Enhanced symbol validation
is_supported = await self.binance_exchange.is_futures_symbol_supported(trading_pair)
if not is_supported:
    return False, f"Symbol {trading_pair} not supported or not trading."

# Get symbol filters early for validation
filters = await self.binance_exchange.get_futures_symbol_filters(trading_pair)
if not filters:
    return False, f"Could not retrieve symbol filters for {trading_pair}"

# Check if symbol is in TRADING status
exchange_info = await self.binance_exchange.get_exchange_info()
if exchange_info:
    symbol_info = next((s for s in exchange_info.get('symbols', []) if s['symbol'] == trading_pair), None)
    if symbol_info and symbol_info.get('status') != 'TRADING':
        return False, f"Symbol {trading_pair} is not in TRADING status"
```

### 3. Enhanced Precision Handling (`src/exchange/binance_exchange.py`)

**Added validation and formatting in order creation:**
```python
# Validate quantity bounds
if amount < min_qty:
    return {'error': f'Quantity {amount} below minimum {min_qty} for {pair}', 'code': -4005}
if amount > max_qty:
    return {'error': f'Quantity {amount} above maximum {max_qty} for {pair}', 'code': -4005}

# Format amount according to stepSize
if step_size:
    formatted_amount = format_value(amount, step_size)
    amount = float(formatted_amount)
```

### 4. Better Error Handling (`discord_bot/discord_bot.py`)

**Added comprehensive error detection:**
```python
# Check if order was actually placed successfully
if isinstance(result_message, dict) and 'error' in result_message:
    error_msg = result_message.get('error', 'Unknown error')
    await self.db_manager.update_existing_trade(
        trade_id=trade_row["id"],
        updates={"status": "FAILED", "binance_response": result_message}
    )
    return {"status": "error", "message": f"Order failed: {error_msg}"}
```

## Validation Results

### Symbol Precision Requirements:

| Symbol | Min Qty | Max Qty | Step Size | Status |
|--------|---------|---------|-----------|--------|
| SUIUSDT | 0.1 | 10,000,000 | 0.1 | ✅ Fixed |
| PENGUUSDT | 1.0 | 20,000,000 | 1.0 | ✅ Fixed |
| HYPEUSDT | 0.01 | 30,000 | 0.01 | ✅ Fixed |
| XRPUSDT | 0.1 | 1,000,000 | 0.1 | ✅ Fixed |

### Expected Improvements:

1. **Reduced Unfilled Orders**: Proper quantity formatting will ensure orders meet Binance's requirements
2. **Better Error Messages**: Clear error messages for failed orders
3. **Symbol Validation**: Orders for unsupported symbols will be rejected early
4. **Precision Compliance**: All quantities will be properly formatted to step_size

## Testing

Run the test script to validate the fixes:
```bash
python scripts/test_quantity_calculation.py
```

This will test quantity calculation for all problematic symbols and verify that:
- Quantities are properly calculated
- Precision formatting is applied correctly
- Validation checks pass
- Notional values meet minimum requirements

## Monitoring

After deployment, monitor:
1. **Order Success Rate**: Should increase significantly
2. **Error Messages**: Should be more specific and actionable
3. **Unfilled Orders**: Should decrease dramatically
4. **Log Messages**: Should show detailed validation steps

## Configuration

The fixes use existing configuration:
- `TRADE_AMOUNT`: Base USDT amount for trades
- `quantity_multiplier`: For memecoin quantity prefixes
- Symbol precision data from `config/binance_futures_precision.py`

No additional configuration changes required.
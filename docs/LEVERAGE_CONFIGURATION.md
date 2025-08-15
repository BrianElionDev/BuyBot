# Leverage Configuration Implementation

## Overview

This implementation centralizes leverage configuration by moving it to the `.env` file and making it configurable throughout the trading system. This provides a single source of truth for leverage settings and makes it easy to adjust leverage without modifying code.

## Problem Statement

Previously, leverage was hardcoded in multiple places throughout the codebase:
- `leverage=1.0` in fee calculations
- `leverage=1.0` in position validation
- `leverage=1.0` in breakeven calculations
- Hardcoded values scattered across different files

This made it difficult to:
- Change leverage settings consistently
- Maintain leverage configuration
- Ensure all parts of the system use the same leverage value

## Solution: Centralized Leverage Configuration

### 1. Environment Variable Configuration

**Added to `.env` file:**
```bash
LEVERAGE=1
```

**Added to `config/settings.py`:**
```python
# Trading Leverage Configuration
DEFAULT_LEVERAGE = float(os.getenv("LEVERAGE", "1"))  # Default leverage from .env, defaults to 1 if not found
```

### 2. Updated Trading Engine

**Before:**
```python
# Hardcoded leverage values
leverage=1.0,  # Default leverage, will be updated with actual leverage
actual_leverage = 1.0  # Default leverage
actual_leverage = float(position.get('leverage', 1.0))
```

**After:**
```python
# Using leverage from settings
leverage=config.DEFAULT_LEVERAGE,  # Use leverage from settings
actual_leverage = config.DEFAULT_LEVERAGE  # Use leverage from settings
actual_leverage = float(position.get('leverage', config.DEFAULT_LEVERAGE))
```

### 3. Files Updated

The following files were updated to use the centralized leverage configuration:

1. **`config/settings.py`** - Added `DEFAULT_LEVERAGE` configuration
2. **`src/bot/trading_engine.py`** - Updated all leverage references to use `config.DEFAULT_LEVERAGE`
3. **`scripts/test_leverage_config.py`** - New test script to verify configuration

## Benefits

### 1. Centralized Configuration
- **Single Source of Truth**: All leverage settings come from one place
- **Easy Management**: Change leverage by updating `.env` file
- **Consistent Values**: All parts of the system use the same leverage

### 2. Flexibility
- **Environment-Specific**: Different leverage for different environments
- **Easy Testing**: Can test with different leverage values
- **Quick Changes**: No code changes needed to adjust leverage

### 3. Maintainability
- **No Hardcoded Values**: Eliminates scattered hardcoded leverage values
- **Clear Configuration**: Obvious where leverage is configured
- **Version Control**: Leverage changes tracked in `.env` file

### 4. Error Prevention
- **Consistent Usage**: All calculations use the same leverage value
- **Validation**: Centralized validation of leverage settings
- **Fallback**: Default value if `.env` is not configured

## Usage Examples

### 1. Basic Configuration

**In `.env` file:**
```bash
LEVERAGE=10
```

**In code:**
```python
from config import settings as config

# Use leverage from settings
leverage = config.DEFAULT_LEVERAGE  # Will be 10.0
```

### 2. Fee Calculation with Configurable Leverage

```python
from src.exchange.fee_calculator import FixedFeeCalculator
from config import settings as config

calculator = FixedFeeCalculator()

# Calculate fees using leverage from settings
fee_analysis = calculator.calculate_comprehensive_fees(
    margin=1000.0,
    leverage=config.DEFAULT_LEVERAGE,  # Uses leverage from .env
    entry_price=50000.0
)
```

### 3. Trading Engine Integration

```python
# In trading engine, leverage is automatically used from settings
fee_analysis = self.fee_calculator.calculate_comprehensive_fees(
    margin=usdt_amount,
    leverage=config.DEFAULT_LEVERAGE,  # Uses leverage from .env
    entry_price=current_price
)
```

## Configuration Options

### 1. Environment Variable

**`.env` file:**
```bash
# Trading leverage (default: 1)
LEVERAGE=1
```

### 2. Default Fallback

If `LEVERAGE` is not found in `.env`, the system defaults to `1.0`:
```python
DEFAULT_LEVERAGE = float(os.getenv("LEVERAGE", "1"))
```

### 3. Common Leverage Values

- **1x**: No leverage (spot trading equivalent)
- **5x**: Low leverage
- **10x**: Medium leverage
- **20x**: High leverage
- **50x**: Very high leverage
- **100x**: Maximum leverage (use with caution)

## Test Results

Running the leverage configuration test shows the impact of different leverage values:

```
Leverage   Notional Value  Single Fee      Total Fees      Fee %
--------------------------------------------------------------------------------
1          $1,000.00       $0.2000         $0.4000         0.0400   %
5          $5,000.00       $1.0000         $2.0000         0.2000   %
10         $10,000.00      $2.0000         $4.0000         0.4000   %
20         $20,000.00      $4.0000         $8.0000         0.8000   %
50         $50,000.00      $10.0000        $20.0000        2.0000   %
100        $100,000.00     $20.0000        $40.0000        4.0000   %
```

## Migration Guide

### 1. Update .env File

Add leverage configuration to your `.env` file:
```bash
# Add this line to your .env file
LEVERAGE=1
```

### 2. Verify Configuration

Run the test script to verify configuration:
```bash
python3 scripts/test_leverage_config.py
```

### 3. Monitor Logs

Check that the system is using the correct leverage:
```
INFO - Using FixedFeeCalculator with 0.02% fee cap
INFO - Leverage: 1.0x (from .env)
```

### 4. Test Different Values

Try different leverage values in `.env`:
```bash
LEVERAGE=10  # Test with 10x leverage
```

## Best Practices

### 1. Risk Management
- **Start Low**: Begin with low leverage (1x-5x)
- **Gradual Increase**: Increase leverage gradually as you gain experience
- **Monitor Impact**: Watch how leverage affects fees and risk

### 2. Configuration Management
- **Environment-Specific**: Use different leverage for different environments
- **Documentation**: Document your leverage choices
- **Testing**: Test with different leverage values before production

### 3. Monitoring
- **Fee Impact**: Monitor how leverage affects trading fees
- **Risk Assessment**: Regularly assess risk with current leverage
- **Performance**: Track performance with different leverage settings

## Troubleshooting

### 1. Leverage Not Loading

**Problem**: Leverage defaults to 1.0 even when set in `.env`

**Solution**: Check that `.env` file is in the correct location and properly formatted:
```bash
# Correct format
LEVERAGE=10

# Not this
LEVERAGE = 10
LEVERAGE:10
```

### 2. Type Errors

**Problem**: Leverage is loaded as string instead of float

**Solution**: The configuration automatically converts to float:
```python
DEFAULT_LEVERAGE = float(os.getenv("LEVERAGE", "1"))
```

### 3. Environment Variable Not Found

**Problem**: `os.getenv("LEVERAGE")` returns None

**Solution**: The system defaults to 1.0 if not found:
```python
# If LEVERAGE not in .env, defaults to "1"
DEFAULT_LEVERAGE = float(os.getenv("LEVERAGE", "1"))
```

## Summary

The Leverage Configuration Implementation successfully centralizes leverage settings by:

✅ **Centralized Configuration**: Single source of truth in `.env` file
✅ **Easy Management**: Simple configuration changes without code modifications
✅ **Consistent Usage**: All parts of the system use the same leverage value
✅ **Flexible Settings**: Easy to adjust leverage for different scenarios
✅ **Error Prevention**: Eliminates hardcoded values and ensures consistency
✅ **Testing Support**: Easy to test with different leverage values
✅ **Documentation**: Clear configuration and usage guidelines

This implementation makes leverage management much more flexible and maintainable, allowing you to easily adjust leverage settings based on your trading strategy and risk tolerance.

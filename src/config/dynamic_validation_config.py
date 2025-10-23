"""
Dynamic Validation Configuration

Configuration settings for the dynamic symbol validation system.
"""

import os
from typing import Dict, Any

# Dynamic validation settings
DYNAMIC_VALIDATION_ENABLED = os.getenv('DYNAMIC_VALIDATION_ENABLED', 'true').lower() == 'true'
CACHE_DURATION_MINUTES = int(os.getenv('SYMBOL_CACHE_DURATION_MINUTES', '10'))
ENABLE_OFFLINE_MODE = os.getenv('ENABLE_OFFLINE_MODE', 'false').lower() == 'true'

# Exchange-specific settings
EXCHANGE_SETTINGS = {
    'binance': {
        'enabled': True,
        'cache_duration_minutes': CACHE_DURATION_MINUTES,
        'api_timeout_seconds': 10,
        'max_retries': 3
    },
    'kucoin': {
        'enabled': True,
        'cache_duration_minutes': CACHE_DURATION_MINUTES,
        'api_timeout_seconds': 10,
        'max_retries': 3
    }
}

# Offline mode settings
OFFLINE_MODE_SETTINGS = {
    'enabled': ENABLE_OFFLINE_MODE,
    'use_cached_data_only': True,
    'cache_expiry_hours': 24
}

# Logging settings
LOGGING_SETTINGS = {
    'log_cache_hits': False,
    'log_api_calls': True,
    'log_fallback_usage': True,
    'log_validation_errors': True
}

def get_validation_config() -> Dict[str, Any]:
    """Get the complete validation configuration."""
    return {
        'dynamic_validation_enabled': DYNAMIC_VALIDATION_ENABLED,
        'cache_duration_minutes': CACHE_DURATION_MINUTES,
        'offline_mode': OFFLINE_MODE_SETTINGS,
        'exchange_settings': EXCHANGE_SETTINGS,
        'logging': LOGGING_SETTINGS
    }

def is_dynamic_validation_enabled() -> bool:
    """Check if dynamic validation is enabled."""
    return DYNAMIC_VALIDATION_ENABLED

def is_offline_mode_enabled() -> bool:
    """Check if offline mode is enabled."""
    return OFFLINE_MODE_SETTINGS['enabled']


#!/usr/bin/env python3
"""
Test script to verify Uniswap integration is working
"""
import sys
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_uniswap_import():
    """Test if UniswapExchange can be imported"""
    try:
        from src.exchange.uniswap_exchange import UniswapExchange
        logger.info("✅ UniswapExchange import successful")
        return True
    except Exception as e:
        logger.error(f"❌ UniswapExchange import failed: {e}")
        return False

def test_trading_engine():
    """Test if TradingEngine can be initialized with Uniswap"""
    try:
        from src.bot.trading_engine import TradingEngine
        engine = TradingEngine()
        
        if hasattr(engine, 'uniswap_exchange') and engine.uniswap_exchange is not None:
            logger.info("✅ TradingEngine initialized with Uniswap support")
            return True
        else:
            logger.warning("⚠️ TradingEngine initialized but Uniswap is None")
            return False
    except Exception as e:
        logger.error(f"❌ TradingEngine initialization failed: {e}")
        return False

def main():
    print("=" * 60)
    print("Testing Uniswap Integration")
    print("=" * 60)
    
    # Test 1: Import
    import_success = test_uniswap_import()
    
    # Test 2: Trading Engine
    engine_success = test_trading_engine()
    
    print("\n" + "=" * 60)
    print("Test Results:")
    print(f"Import Test: {'✅ PASS' if import_success else '❌ FAIL'}")
    print(f"Engine Test: {'✅ PASS' if engine_success else '❌ FAIL'}")
    
    if import_success and engine_success:
        print("\n🎉 Uniswap integration is working correctly!")
        return 0
    else:
        print("\n❌ Uniswap integration has issues")
        return 1

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Test Auto Balance Fetcher

Simple test script for the auto balance fetcher.
"""

import asyncio
import logging
import os
import sys

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv('.env.local')
except ImportError:
    # Manual .env loading if dotenv not available
    def load_env_file(filepath):
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip().strip('"').strip("'")
    
    load_env_file('.env')
    load_env_file('.env.local')

from auto_fetch_balances import AutoBalanceFetcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_auto_fetcher():
    """Test the auto balance fetcher."""
    print("🧪 Testing Auto Balance Fetcher")
    print("=" * 50)
    
    fetcher = AutoBalanceFetcher()
    
    try:
        # Test initialization
        print("1. Testing initialization...")
        if await fetcher.initialize():
            print("✅ Initialization successful")
        else:
            print("❌ Initialization failed")
            return False
        
        # Test Binance futures balances
        print("\n2. Testing Binance futures balances...")
        binance_balances = await fetcher.get_binance_futures_balances()
        print(f"✅ Retrieved {len(binance_balances)} Binance futures balances")
        
        if binance_balances:
            print("Sample Binance balance:")
            sample = binance_balances[0]
            print(f"  Asset: {sample['asset']}")
            print(f"  Total: {sample['total']}")
            print(f"  Free: {sample['free']}")
            print(f"  Unrealized PnL: {sample['unrealised_pnl']}")
        
        # Test KuCoin futures balances
        print("\n3. Testing KuCoin futures balances...")
        kucoin_balances = await fetcher.get_kucoin_futures_balances()
        print(f"✅ Retrieved {len(kucoin_balances)} KuCoin futures balances")
        
        # Test database storage (dry run)
        print("\n4. Testing database storage...")
        all_balances = binance_balances + kucoin_balances
        if all_balances:
            print(f"✅ Would store {len(all_balances)} balances in database")
        else:
            print("⚠️ No balances to store")
        
        # Test stored balances retrieval
        print("\n5. Testing stored balances retrieval...")
        stored_balances = await fetcher.get_stored_balances()
        print(f"✅ Found {len(stored_balances)} stored balances in database")
        
        print("\n🎉 All tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return False
    finally:
        await fetcher.cleanup()

async def main():
    """Main test function."""
    success = await test_auto_fetcher()
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

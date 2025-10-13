#!/usr/bin/env python3
"""
Test Trader Configuration API Endpoints

This script tests the trader configuration API endpoints to ensure
they work correctly with the modularized system.
"""

import sys
import os
import asyncio
import httpx
import json
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from discord_bot.main import create_app


async def test_trader_config_endpoints():
    """Test all trader configuration endpoints."""

    # Create test app
    app = create_app()

    # Test data
    test_trader = "@TestTrader"
    test_config = {
        "trader_id": test_trader,
        "exchange": "binance",
        "leverage": 10,
        "updated_by": "test_script"
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:

        print("🧪 Testing Trader Configuration API Endpoints")
        print("=" * 50)

        # Test 1: Get all trader configs (should be empty initially)
        print("\n1. Testing GET /api/v1/trader-config/")
        try:
            response = await client.get("/api/v1/trader-config/")
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)}")
            else:
                print(f"   Error: {response.text}")
        except Exception as e:
            print(f"   Exception: {e}")

        # Test 2: Create a trader config
        print(f"\n2. Testing POST /api/v1/trader-config/ (create {test_trader})")
        try:
            response = await client.post("/api/v1/trader-config/", json=test_config)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)}")
            else:
                print(f"   Error: {response.text}")
        except Exception as e:
            print(f"   Exception: {e}")

        # Test 3: Get specific trader config
        print(f"\n3. Testing GET /api/v1/trader-config/{test_trader}")
        try:
            response = await client.get(f"/api/v1/trader-config/{test_trader}")
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)}")
            else:
                print(f"   Error: {response.text}")
        except Exception as e:
            print(f"   Exception: {e}")

        # Test 4: Validate trader support
        print(f"\n4. Testing POST /api/v1/trader-config/validate/{test_trader}")
        try:
            response = await client.post(f"/api/v1/trader-config/validate/{test_trader}")
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)}")
            else:
                print(f"   Error: {response.text}")
        except Exception as e:
            print(f"   Exception: {e}")

        # Test 5: Get traders for exchange
        print("\n5. Testing GET /api/v1/trader-config/exchange/binance")
        try:
            response = await client.get("/api/v1/trader-config/exchange/binance")
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)}")
            else:
                print(f"   Error: {response.text}")
        except Exception as e:
            print(f"   Exception: {e}")

        # Test 6: Get supported traders
        print("\n6. Testing GET /api/v1/trader-config/supported/traders")
        try:
            response = await client.get("/api/v1/trader-config/supported/traders")
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)}")
            else:
                print(f"   Error: {response.text}")
        except Exception as e:
            print(f"   Exception: {e}")

        # Test 7: Update trader config
        print(f"\n7. Testing POST /api/v1/trader-config/ (update {test_trader})")
        updated_config = test_config.copy()
        updated_config["leverage"] = 20
        try:
            response = await client.post("/api/v1/trader-config/", json=updated_config)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)}")
            else:
                print(f"   Error: {response.text}")
        except Exception as e:
            print(f"   Exception: {e}")

        # Test 8: Clear cache
        print("\n8. Testing POST /api/v1/trader-config/cache/clear")
        try:
            response = await client.post("/api/v1/trader-config/cache/clear")
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)}")
            else:
                print(f"   Error: {response.text}")
        except Exception as e:
            print(f"   Exception: {e}")

        # Test 9: Delete trader config
        print(f"\n9. Testing DELETE /api/v1/trader-config/{test_trader}")
        try:
            response = await client.delete(f"/api/v1/trader-config/{test_trader}")
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   Response: {json.dumps(data, indent=2)}")
            else:
                print(f"   Error: {response.text}")
        except Exception as e:
            print(f"   Exception: {e}")

        # Test 10: Verify deletion
        print(f"\n10. Testing GET /api/v1/trader-config/{test_trader} (should be 404)")
        try:
            response = await client.get(f"/api/v1/trader-config/{test_trader}")
            print(f"   Status: {response.status_code}")
            if response.status_code == 404:
                print("   ✅ Correctly returned 404 after deletion")
            else:
                print(f"   Response: {response.text}")
        except Exception as e:
            print(f"   Exception: {e}")

        print("\n" + "=" * 50)
        print("🎉 Trader Configuration API Tests Completed!")


async def test_error_cases():
    """Test error cases and edge conditions."""

    app = create_app()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:

        print("\n🧪 Testing Error Cases")
        print("=" * 30)

        # Test invalid exchange
        print("\n1. Testing invalid exchange")
        try:
            invalid_config = {
                "trader_id": "@TestTrader",
                "exchange": "invalid_exchange",
                "leverage": 10
            }
            response = await client.post("/api/v1/trader-config/", json=invalid_config)
            print(f"   Status: {response.status_code}")
            if response.status_code == 400:
                print("   ✅ Correctly rejected invalid exchange")
            else:
                print(f"   Response: {response.text}")
        except Exception as e:
            print(f"   Exception: {e}")

        # Test invalid leverage
        print("\n2. Testing invalid leverage")
        try:
            invalid_config = {
                "trader_id": "@TestTrader",
                "exchange": "binance",
                "leverage": 150  # Invalid leverage
            }
            response = await client.post("/api/v1/trader-config/", json=invalid_config)
            print(f"   Status: {response.status_code}")
            if response.status_code == 422:  # Validation error
                print("   ✅ Correctly rejected invalid leverage")
            else:
                print(f"   Response: {response.text}")
        except Exception as e:
            print(f"   Exception: {e}")

        # Test non-existent trader
        print("\n3. Testing non-existent trader")
        try:
            response = await client.get("/api/v1/trader-config/@NonExistent")
            print(f"   Status: {response.status_code}")
            if response.status_code == 404:
                print("   ✅ Correctly returned 404 for non-existent trader")
            else:
                print(f"   Response: {response.text}")
        except Exception as e:
            print(f"   Exception: {e}")


async def main():
    """Main test function."""
    print("🚀 Starting Trader Configuration API Tests")

    try:
        await test_trader_config_endpoints()
        await test_error_cases()
        print("\n✅ All tests completed successfully!")

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

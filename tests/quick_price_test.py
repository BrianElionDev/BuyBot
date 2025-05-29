#!/usr/bin/env python3
"""
Quick test for CoinGecko integration with timeout
"""
import asyncio
import logging
from src.services.price_service import PriceService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def quick_test():
    """Quick test with timeout"""
    price_service = PriceService()

    try:
        # Test with ETH which we know works
        logger.info("Testing ETH price fetch...")
        price = await asyncio.wait_for(
            price_service.get_coin_price('ETH'),
            timeout=10.0
        )

        if price:
            logger.info(f"✅ ETH: ${price:.6f}")

            # Test notification format
            amount = 10
            cost_value = price * amount
            cost_message = f"${cost_value:.6f} (${price:.6f} per ETH)"

            logger.info(f"📧 Sample notification cost format: {cost_message}")
            return True
        else:
            logger.warning("❌ ETH: Price not available")
            return False

    except asyncio.TimeoutError:
        logger.error("❌ Test timed out")
        return False
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(quick_test())
    if success:
        print("🎉 CoinGecko integration is working!")
    else:
        print("❌ CoinGecko integration needs attention")

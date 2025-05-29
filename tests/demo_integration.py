#!/usr/bin/env python3
"""
Demo script showing the CoinGecko integration functionality
"""
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def demo_notification_format():
    """Demonstrate the new notification format"""

    logger.info("🎯 DEMO: CoinGecko Integration for Rubicon Trading Bot")
    logger.info("=" * 70)

    # Simulate trade signal parsing
    logger.info("📨 1. Trade Signal Received:")
    sample_message = """👋 Trade detected
🟢 +531,835.742 Destra Network (DSync)
💰 Price per token $0.136 USD
📈 Market cap: $72,412.23"""

    for line in sample_message.split('\n'):
        logger.info(f"    {line}")

    logger.info("")
    logger.info("🔍 2. Parsing Trade Signal:")

    # Extracted values
    coin_symbol = "DSYNC"
    parsed_price = 0.136
    logger.info(f"    ✅ Coin Symbol: {coin_symbol}")
    logger.info(f"    ✅ Parsed Price: ${parsed_price}")

    logger.info("")
    logger.info("💰 3. CoinGecko Price Lookup:")
    logger.info(f"    🔍 Fetching current price for {coin_symbol}...")

    # Simulate price fetch (in real implementation this would be dynamic)
    mock_current_price = 0.142  # Simulated CoinGecko price
    logger.info(f"    ✅ CoinGecko Price: ${mock_current_price}")

    logger.info("")
    logger.info("📧 4. Enhanced Notification:")

    # Old format (before integration)
    logger.info("    📤 OLD FORMAT:")
    old_message = """Transaction Type: Buy
Sell: ETH
Buy: USDC
Amount: 10
Cost: 20"""

    for line in old_message.split('\n'):
        logger.info(f"       {line}")

    logger.info("")
    logger.info("    📤 NEW FORMAT (with CoinGecko):")

    # New format with dynamic pricing
    amount = 10
    cost_value = mock_current_price * amount
    cost_message = f"${cost_value:.6f} (${mock_current_price:.6f} per {coin_symbol})"

    new_message = f"""Transaction Type: Buy
Sell: ETH
Buy: USDC
Amount: {amount}
Cost: {cost_message}"""

    for line in new_message.split('\n'):
        logger.info(f"       {line}")

    logger.info("")
    logger.info("🎉 5. Integration Benefits:")
    logger.info("    ✅ Real-time pricing from CoinGecko API")
    logger.info("    ✅ Dynamic cost calculations")
    logger.info("    ✅ Better accuracy for trade notifications")
    logger.info("    ✅ Handles price fetch errors gracefully")

    logger.info("")
    logger.info("=" * 70)
    logger.info("🚀 CoinGecko integration is ready!")

if __name__ == "__main__":
    demo_notification_format()

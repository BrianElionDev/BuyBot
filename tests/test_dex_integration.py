#!/usr/bin/env python3
"""
Test script for Uniswap DEX integration.
This test verifies the basic functionality of the Uniswap exchange integration.
"""
import asyncio
import sys
import os
import logging

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings as config
from src.exchange.uniswap_exchange import UniswapExchange
from src.services.price_service import PriceService

# Configure logging for this test
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

async def test_dex_integration():
    """Test basic DEX functionality"""
    logger.info("=" * 80)
    logger.info("UNISWAP DEX INTEGRATION TEST")
    logger.info("=" * 80)

    # Check if required configuration is present
    if not config.INFURA_PROJECT_ID or not config.WALLET_PRIVATE_KEY:
        logger.error("Missing required configuration: INFURA_PROJECT_ID and/or WALLET_PRIVATE_KEY")
        logger.info("Please set these in your .env file and try again")
        return False

    try:
        # Initialize the Uniswap exchange
        uniswap = UniswapExchange()
        price_service = PriceService()

        logger.info(f"Connected to Ethereum {config.ETHEREUM_NETWORK} network via Infura")

        # 1. Test wallet connection
        eth_balance = await uniswap.get_eth_balance()
        logger.info(f"Wallet ETH balance: {eth_balance}")

        if eth_balance <= 0:
            logger.warning(f"No ETH in wallet {config.WALLET_ADDRESS[:6]}...{config.WALLET_ADDRESS[-4:]}")
            logger.warning("You'll need ETH for gas fees to perform transactions")

        # 2. Test token balances (ETH, USDC)
        usdc_balance = await uniswap.get_token_balance(config.USDC_ADDRESS)
        logger.info(f"Wallet USDC balance: {usdc_balance}")

        # 3. Test getting price quotes
        eth_price_in_usd = await price_service.get_coin_price("ethereum")
        if eth_price_in_usd:
            logger.info(f"ETH price from CoinGecko: ${eth_price_in_usd}")

        # Test Uniswap's own price function for 1 ETH -> USDC
        eth_amount_atomic = uniswap.w3.to_wei(1, 'ether')  # 1 ETH
        usdc_amount = await uniswap.get_swap_quote(
            config.WETH_ADDRESS,
            config.USDC_ADDRESS,
            eth_amount_atomic
        )
        if usdc_amount:
            usdc_decimals = await uniswap.get_token_decimals(config.USDC_ADDRESS)
            usdc_for_1eth = usdc_amount / (10**usdc_decimals)
            logger.info(f"ETH price from Uniswap: ${usdc_for_1eth}")

        # 4. Test a mock quote for a token (NOT executing a real trade)
        test_token = "DSYNC"
        test_token_address = config.TOKEN_ADDRESS_MAP.get(test_token.upper())

        if test_token_address:
            # Get price from CoinGecko for comparison
            token_price = await price_service.get_coin_price(test_token)
            if token_price:
                logger.info(f"{test_token} price from CoinGecko: ${token_price}")

            if eth_balance > 0:
                # Calculate how much ETH would be needed for $10 worth of the token
                test_amount_usd = 10  # Test with $10
                eth_amount = test_amount_usd / eth_price_in_usd if eth_price_in_usd else 0.01
                eth_amount_atomic = uniswap.w3.to_wei(eth_amount, 'ether')

                logger.info(f"Testing quote for {eth_amount} ETH → {test_token}")

                # Get expected token amount
                token_amount = await uniswap.get_swap_quote(
                    config.WETH_ADDRESS,
                    test_token_address,
                    eth_amount_atomic
                )

                if token_amount:
                    token_decimals = await uniswap.get_token_decimals(test_token_address)
                    token_amount_readable = token_amount / (10**token_decimals)
                    effective_price = eth_amount * eth_price_in_usd / token_amount_readable
                    logger.info(f"Would receive: {token_amount_readable} {test_token}")
                    logger.info(f"Effective price: ${effective_price} per {test_token}")

                    # Calculate slippage
                    if token_price:
                        slippage = abs(effective_price - token_price) / token_price * 100
                        logger.info(f"Slippage from CoinGecko price: {slippage:.2f}%")

                        if slippage > config.DEX_SLIPPAGE_PERCENTAGE:
                            logger.warning(f"High slippage detected ({slippage:.2f}% > {config.DEX_SLIPPAGE_PERCENTAGE}%)")
                        else:
                            logger.info(f"Slippage within acceptable range ({slippage:.2f}% ≤ {config.DEX_SLIPPAGE_PERCENTAGE}%)")
        else:
            logger.warning(f"Test token {test_token} not found in TOKEN_ADDRESS_MAP")

        logger.info("\n✅ DEX integration test completed successfully")
        logger.info("Note: No actual trades were executed")
        return True

    except Exception as e:
        logger.error(f"Error during DEX integration test: {e}", exc_info=True)
        return False
    finally:
        if 'uniswap' in locals():
            await uniswap.close()
        if 'price_service' in locals() and hasattr(price_service, 'close'):
            await price_service.close()

if __name__ == "__main__":
    asyncio.run(test_dex_integration())

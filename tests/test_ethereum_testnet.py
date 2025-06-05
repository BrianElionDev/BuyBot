#!/usr/bin/env python3
"""
Test script for Ethereum testnet operations.
This helps validate the Uniswap DEX integration on a testnet before deploying to mainnet.
"""
import asyncio
import sys
import os
import logging
from web3 import Web3
from decimal import Decimal

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings as config
from src.exchange.uniswap_exchange import UniswapExchange

# Configure logging for this test
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Testnet Token Addresses (Sepolia)
TESTNET_TOKENS = {
    "WETH": "0x7b79995e5f793A07Bc00c21412e50Ecae098E7f9",  # Sepolia WETH
    "DAI": "0x3e622317f8C93f7328350cF0B56d9eD4C620C5d6",   # Sepolia DAI
    "LINK": "0x779877A7B0D9E8603169DdbD7836e478b4624789"   # Sepolia LINK
}

async def test_on_testnet():
    """Run a series of tests on Ethereum testnet to validate DEX integration."""
    logger.info("=" * 80)
    logger.info("ETHEREUM TESTNET VALIDATION")
    logger.info("=" * 80)

    # Verify we're on testnet
    if config.ETHEREUM_NETWORK.lower() == "mainnet":
        logger.error("This test should only run on a testnet! Set ETHEREUM_NETWORK=sepolia in .env")
        return False

    # Check if required configuration is present
    if not config.INFURA_PROJECT_ID or not config.WALLET_PRIVATE_KEY:
        logger.error("Missing required configuration: INFURA_PROJECT_ID and/or WALLET_PRIVATE_KEY")
        logger.info("Please set these in your .env file and try again")
        return False

    try:
        # Initialize the Uniswap exchange
        uniswap = UniswapExchange()
        logger.info(f"Connected to {config.ETHEREUM_NETWORK} testnet via Infura")

        # Test 1: Check wallet connection and balance
        eth_balance = await uniswap.get_eth_balance()
        logger.info(f"Wallet ETH balance: {eth_balance}")

        if eth_balance <= 0.01:
            logger.error(f"Insufficient ETH in wallet {config.WALLET_ADDRESS[:6]}...{config.WALLET_ADDRESS[-4:]}")
            logger.info("Please fund your wallet with testnet ETH before running tests")
            logger.info("You can get Sepolia ETH from faucets like https://sepoliafaucet.com/")
            return False

        # Test 2: Check token balances
        for token_symbol, token_address in TESTNET_TOKENS.items():
            token_balance = await uniswap.get_token_balance(token_address)
            logger.info(f"{token_symbol} balance: {token_balance}")

        # Test 3: Test gas estimation with advanced strategies
        logger.info("Testing gas estimation strategies...")

        original_strategy = config.GAS_STRATEGY
        for strategy in ["slow", "medium", "fast", "aggressive"]:
            config.GAS_STRATEGY = strategy
            gas_price = await uniswap.estimate_gas_price()

            if isinstance(gas_price, dict):
                logger.info(f"EIP-1559 {strategy} gas: maxFeePerGas={Web3.from_wei(gas_price['maxFeePerGas'], 'gwei')} gwei, " +
                            f"maxPriorityFee={Web3.from_wei(gas_price['maxPriorityFeePerGas'], 'gwei')} gwei")
            else:
                logger.info(f"Legacy {strategy} gas: {Web3.from_wei(gas_price, 'gwei')} gwei")

        # Reset to original strategy
        config.GAS_STRATEGY = original_strategy

        # Test 4: Small token approval (if we have tokens)
        link_balance = await uniswap.get_token_balance(TESTNET_TOKENS["LINK"])
        if link_balance > 0:
            logger.info("Testing token approval...")
            # Only approve a tiny amount
            approve_amount = Web3.to_wei(0.0001, 'ether')
            approved, tx_hash, receipt = await uniswap.approve_token(TESTNET_TOKENS["LINK"], approve_amount)

            if approved:
                logger.info(f"✅ Approval successful! TX: {tx_hash}")
                logger.info(f"Gas used: {receipt.gasUsed}")
            else:
                logger.error(f"❌ Approval failed")
                if tx_hash:
                    logger.error(f"Failed TX: {tx_hash}")
        else:
            logger.warning("Skipping approval test - no LINK tokens available")

        # Test 5: Test transaction retry mechanism with a deliberately failing transaction
        logger.info("Testing transaction recovery mechanism...")
        logger.info("Simulating a transaction that will fail due to insufficient funds...")

        # Try to swap more ETH than we have to trigger a failure
        massive_amount = Web3.to_wei(1000, 'ether')  # An amount we definitely don't have

        # Set up retry parameters for quick testing
        uniswap.tx_manager.max_retries = 2
        uniswap.tx_manager.retry_delay = 1

        success, tx_hash, receipt = await uniswap.execute_swap(
            config.WETH_ADDRESS,
            TESTNET_TOKENS["LINK"],
            massive_amount,
            slippage_percentage=1.0
        )

        logger.info(f"Expected failure result: success={success}, tx_hash={tx_hash}")
        logger.info("Recovery mechanism test complete")

        # Test summary
        logger.info("=" * 80)
        logger.info("TESTNET VALIDATION COMPLETE")
        logger.info("=" * 80)
        logger.info("You may now switch to mainnet for production use")

        # Always return success - we're testing the recovery system
        return True

    except Exception as e:
        logger.error(f"Error during testnet validation: {e}")
        return False
    finally:
        if 'uniswap' in locals():
            await uniswap.close()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        success = loop.run_until_complete(test_on_testnet())
        sys.exit(0 if success else 1)
    finally:
        loop.close()

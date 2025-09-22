#!/usr/bin/env python3
"""
KuCoin Balance Calculator Script

This script shows what your available balance will be after closing all positions
without actually closing them.
"""

import asyncio
import logging
import sys
import os
from typing import Dict, List, Any

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.exchange.kucoin.kucoin_exchange import KucoinExchange
from config.settings import KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE, KUCOIN_TESTNET

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def get_current_balance(exchange: KucoinExchange) -> Dict[str, Any]:
    """Get current account balance and position information."""
    try:
        # Get account info
        account_info = await exchange.get_futures_account_info()
        if not account_info:
            logger.error("Failed to get account information")
            return {}

        # Get positions
        positions = await exchange.get_futures_position_information()

        return {
            'account_info': account_info,
            'positions': positions
        }
    except Exception as e:
        logger.error(f"Error getting current balance: {e}")
        return {}


async def calculate_balance_after_closing(account_info: Dict[str, Any], positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate what the balance will be after closing all positions."""
    try:
        current_balance = account_info.get('totalWalletBalance', 0.0)
        unrealized_pnl = account_info.get('totalUnrealizedProfit', 0.0)

        # Calculate total unrealized PnL from positions
        total_unrealized_pnl = sum(pos.get('unrealizedPnl', 0.0) for pos in positions)

        # The balance after closing will be current balance + unrealized PnL
        balance_after_closing = current_balance + total_unrealized_pnl

        return {
            'current_balance': current_balance,
            'unrealized_pnl': total_unrealized_pnl,
            'balance_after_closing': balance_after_closing,
            'currency': account_info.get('currency', 'USDT')
        }
    except Exception as e:
        logger.error(f"Error calculating balance after closing: {e}")
        return {}


async def main():
    """Main function to show balance calculation."""
    try:
        # Check if API credentials are available
        if not all([KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE]):
            logger.error("KuCoin API credentials not found. Please check your .env file.")
            return

        # Initialize exchange
        exchange = KucoinExchange(
            api_key=KUCOIN_API_KEY,
            api_secret=KUCOIN_API_SECRET,
            api_passphrase=KUCOIN_API_PASSPHRASE,
            is_testnet=KUCOIN_TESTNET
        )

        # Initialize connection
        if not await exchange.initialize():
            logger.error("Failed to initialize KuCoin exchange")
            return

        logger.info("KuCoin exchange initialized successfully")

        # Get current balance and positions
        logger.info("Getting current account information...")
        balance_data = await get_current_balance(exchange)

        if not balance_data:
            logger.error("Failed to get account information")
            return

        account_info = balance_data['account_info']
        positions = balance_data['positions']

        # Display current account overview
        print("\n" + "="*60)
        print("CURRENT ACCOUNT OVERVIEW")
        print("="*60)
        print(f"Account Equity: {account_info.get('totalWalletBalance', 0.0):.6f} {account_info.get('currency', 'USDT')}")
        print(f"Unrealized PnL: {account_info.get('totalUnrealizedProfit', 0.0):.6f} {account_info.get('currency', 'USDT')}")
        print(f"Available Balance: {account_info.get('availableBalance', 0.0):.6f} {account_info.get('currency', 'USDT')}")
        print(f"Max Withdraw Amount: {account_info.get('maxWithdrawAmount', 0.0):.6f} {account_info.get('currency', 'USDT')}")

        # Display current positions
        print("\n" + "="*60)
        print("CURRENT POSITIONS")
        print("="*60)
        if positions:
            total_unrealized_pnl = 0.0
            for pos in positions:
                symbol = pos.get('symbol', 'Unknown')
                side = pos.get('side', 'Unknown')
                size = pos.get('size', 0.0)
                entry_price = pos.get('entryPrice', 0.0)
                mark_price = pos.get('markPrice', 0.0)
                unrealized_pnl = pos.get('unrealizedPnl', 0.0)
                leverage = pos.get('leverage', 1.0)
                total_unrealized_pnl += unrealized_pnl

                print(f"{symbol} | {side} | size={size} | entry={entry_price:.5f} | mark={mark_price:.5f} | uPnL={unrealized_pnl:.2f} | lev={leverage}")

            print(f"\nTotal Unrealized PnL: {total_unrealized_pnl:.6f} {account_info.get('currency', 'USDT')}")
        else:
            print("No open positions found")

        # Calculate balance after closing
        balance_calc = await calculate_balance_after_closing(account_info, positions)

        if balance_calc:
            print("\n" + "="*60)
            print("BALANCE AFTER CLOSING ALL POSITIONS")
            print("="*60)
            print(f"Current Balance: {balance_calc['current_balance']:.6f} {balance_calc['currency']}")
            print(f"Total Unrealized PnL: {balance_calc['unrealized_pnl']:.6f} {balance_calc['currency']}")
            print(f"Balance After Closing: {balance_calc['balance_after_closing']:.6f} {balance_calc['currency']}")

            # Show the difference
            difference = balance_calc['balance_after_closing'] - balance_calc['current_balance']
            if difference > 0:
                print(f"Net Gain: +{difference:.6f} {balance_calc['currency']}")
            elif difference < 0:
                print(f"Net Loss: {difference:.6f} {balance_calc['currency']}")
            else:
                print("No change in balance")
        else:
            logger.error("Failed to calculate balance after closing")

    except Exception as e:
        logger.error(f"Error in main: {e}")
    finally:
        # Close exchange connection
        if 'exchange' in locals():
            await exchange.close()
            logger.info("KuCoin exchange connection closed")


if __name__ == "__main__":
    asyncio.run(main())


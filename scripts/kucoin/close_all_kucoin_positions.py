#!/usr/bin/env python3
"""
KuCoin Position Closer Script

This script closes all open positions on KuCoin at market value and shows
the available balance after closing them.
"""

import asyncio
import logging
import sys
import os
from decimal import Decimal
from typing import Dict, List, Any

# Ensure project root is on sys.path so 'src' and 'config' are importable
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

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


async def close_all_positions(exchange: KucoinExchange) -> List[Dict[str, Any]]:
    """Close all open positions at market value."""
    try:
        positions = await exchange.get_futures_position_information()
        if not positions:
            logger.info("No open positions found")
            return []

        closed_positions = []

        for position in positions:
            symbol = position.get('symbol', '')
            size = position.get('size', 0.0)
            side = position.get('side', '')

            if size <= 0:
                continue

            logger.info(f"Closing position: {symbol} {side} size={size}")

            # Convert symbol format for closing
            # KuCoin futures symbols are like XRPUSDTM, we need to convert to XRP-USDT for the close_position method
            if symbol.endswith('USDTM'):
                base_symbol = symbol.replace('USDTM', '')
                pair = f"{base_symbol}-USDT"
            else:
                pair = symbol

            # Determine position type
            position_type = "LONG" if side.upper() == "LONG" else "SHORT"

            # Close the position
            success, result = await exchange.close_position(
                pair=pair,
                amount=size,
                position_type=position_type
            )

            if success:
                logger.info(f"Successfully closed position: {symbol}")
                closed_positions.append({
                    'symbol': symbol,
                    'side': side,
                    'size': size,
                    'result': result
                })
            else:
                logger.error(f"Failed to close position {symbol}: {result}")
                closed_positions.append({
                    'symbol': symbol,
                    'side': side,
                    'size': size,
                    'result': result,
                    'error': True
                })

        return closed_positions

    except Exception as e:
        logger.error(f"Error closing positions: {e}")
        return []


async def main():
    """Main function to close all positions and show balance."""
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
        print("\n" + "="*50)
        print("CURRENT ACCOUNT OVERVIEW")
        print("="*50)
        print(f"Account Equity: {account_info.get('totalWalletBalance', 0.0):.6f} {account_info.get('currency', 'USDT')}")
        print(f"Unrealized PnL: {account_info.get('totalUnrealizedProfit', 0.0):.6f} {account_info.get('currency', 'USDT')}")
        print(f"Available Balance: {account_info.get('availableBalance', 0.0):.6f} {account_info.get('currency', 'USDT')}")
        print(f"Max Withdraw Amount: {account_info.get('maxWithdrawAmount', 0.0):.6f} {account_info.get('currency', 'USDT')}")

        # Display current positions
        print("\n" + "="*50)
        print("CURRENT POSITIONS")
        print("="*50)
        if positions:
            for pos in positions:
                symbol = pos.get('symbol', 'Unknown')
                side = pos.get('side', 'Unknown')
                size = pos.get('size', 0.0)
                entry_price = pos.get('entryPrice', 0.0)
                mark_price = pos.get('markPrice', 0.0)
                unrealized_pnl = pos.get('unrealizedPnl', 0.0)
                leverage = pos.get('leverage', 1.0)

                print(f"{symbol} | {side} | size={size} | entry={entry_price:.5f} | mark={mark_price:.5f} | uPnL={unrealized_pnl:.2f} | lev={leverage}")
        else:
            print("No open positions found")

        # Calculate balance after closing
        balance_calc = await calculate_balance_after_closing(account_info, positions)

        if balance_calc:
            print("\n" + "="*50)
            print("BALANCE AFTER CLOSING ALL POSITIONS")
            print("="*50)
            print(f"Current Balance: {balance_calc['current_balance']:.6f} {balance_calc['currency']}")
            print(f"Total Unrealized PnL: {balance_calc['unrealized_pnl']:.6f} {balance_calc['currency']}")
            print(f"Balance After Closing: {balance_calc['balance_after_closing']:.6f} {balance_calc['currency']}")

            # Ask for confirmation
            print("\n" + "="*50)
            print("CONFIRMATION REQUIRED")
            print("="*50)
            print(f"You are about to close {len(positions)} positions at market value.")
            print(f"Your available balance will be: {balance_calc['balance_after_closing']:.6f} {balance_calc['currency']}")

            confirm = input("\nDo you want to proceed? (yes/no): ").lower().strip()

            if confirm in ['yes', 'y']:
                print("\nClosing all positions...")

                # Close all positions
                closed_positions = await close_all_positions(exchange)

                # Display results
                print("\n" + "="*50)
                print("CLOSING RESULTS")
                print("="*50)

                successful_closes = [p for p in closed_positions if not p.get('error', False)]
                failed_closes = [p for p in closed_positions if p.get('error', False)]

                print(f"Successfully closed: {len(successful_closes)} positions")
                print(f"Failed to close: {len(failed_closes)} positions")

                if successful_closes:
                    print("\nSuccessfully closed positions:")
                    for pos in successful_closes:
                        print(f"  - {pos['symbol']} {pos['side']} size={pos['size']}")

                if failed_closes:
                    print("\nFailed to close positions:")
                    for pos in failed_closes:
                        print(f"  - {pos['symbol']} {pos['side']} size={pos['size']}: {pos['result']}")

                # Get final balance
                print("\nGetting final balance...")
                final_balance_data = await get_current_balance(exchange)
                if final_balance_data:
                    final_account_info = final_balance_data['account_info']
                    print(f"\nFinal Available Balance: {final_account_info.get('availableBalance', 0.0):.6f} {final_account_info.get('currency', 'USDT')}")
                    print(f"Final Account Equity: {final_account_info.get('totalWalletBalance', 0.0):.6f} {final_account_info.get('currency', 'USDT')}")

            else:
                print("Operation cancelled by user.")
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


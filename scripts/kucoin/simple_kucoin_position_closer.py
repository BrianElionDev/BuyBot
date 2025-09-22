#!/usr/bin/env python3
"""
Simple KuCoin Position Closer Script

This script closes all open positions on KuCoin at market value using direct API calls.
"""

import asyncio
import logging
import sys
import os
import json
import time
import hmac
import hashlib
import base64
from urllib.parse import urlencode
from typing import Dict, List, Any

import aiohttp
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# KuCoin API credentials
KUCOIN_API_KEY = os.getenv("KUCOIN_API_KEY")
KUCOIN_API_SECRET = os.getenv("KUCOIN_API_SECRET")
KUCOIN_API_PASSPHRASE = os.getenv("KUCOIN_API_PASSPHRASE")

if not all([KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE]):
    logger.error("KuCoin API credentials not found. Please check your .env file.")
    sys.exit(1)


def sign_kucoin(secret: str, str_to_sign: str) -> str:
    """Create KuCoin API signature."""
    mac = hmac.new(secret.encode('utf-8'), str_to_sign.encode('utf-8'), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()


def passphrase_v2_kucoin(secret: str, passphrase: str) -> str:
    """Create KuCoin v2 passphrase signature."""
    mac = hmac.new(secret.encode('utf-8'), passphrase.encode('utf-8'), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()


async def kucoin_private_get(session, base_url: str, endpoint: str, params: Dict[str, str] = None) -> Dict:
    """Make authenticated GET request to KuCoin API."""
    params = params or {}
    ts = str(int(time.time() * 1000))
    method = 'GET'
    query = ''
    if params:
        query = '?' + urlencode(params)
    str_to_sign = ts + method + endpoint + query
    sign = sign_kucoin(KUCOIN_API_SECRET, str_to_sign)
    passphrase = passphrase_v2_kucoin(KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE)
    headers = {
        'KC-API-KEY': KUCOIN_API_KEY,
        'KC-API-SIGN': sign,
        'KC-API-TIMESTAMP': ts,
        'KC-API-PASSPHRASE': passphrase,
        'KC-API-KEY-VERSION': '2',
        'Content-Type': 'application/json'
    }
    url = base_url + endpoint + query
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        data = await resp.json()
        if not isinstance(data, dict) or data.get('code') != '200000':
            raise RuntimeError(f"KuCoin error {url}: {data}")
        return data


async def kucoin_private_post(session, base_url: str, endpoint: str, data: Dict) -> Dict:
    """Make authenticated POST request to KuCoin API."""
    ts = str(int(time.time() * 1000))
    method = 'POST'
    body = json.dumps(data)
    str_to_sign = ts + method + endpoint + body
    sign = sign_kucoin(KUCOIN_API_SECRET, str_to_sign)
    passphrase = passphrase_v2_kucoin(KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE)
    headers = {
        'KC-API-KEY': KUCOIN_API_KEY,
        'KC-API-SIGN': sign,
        'KC-API-TIMESTAMP': ts,
        'KC-API-PASSPHRASE': passphrase,
        'KC-API-KEY-VERSION': '2',
        'Content-Type': 'application/json'
    }
    url = base_url + endpoint
    async with session.post(url, headers=headers, data=body, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        response_data = await resp.json()
        if not isinstance(response_data, dict) or response_data.get('code') != '200000':
            raise RuntimeError(f"KuCoin error {url}: {response_data}")
        return response_data


async def get_account_info():
    """Get KuCoin futures account information."""
    futures_base = 'https://api-futures.kucoin.com'

    async with aiohttp.ClientSession() as session:
        try:
            account_resp = await kucoin_private_get(session, futures_base, '/api/v1/account-overview', {'currency': 'USDT'})
            return account_resp.get('data', {})
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            return {}


async def get_positions():
    """Get KuCoin futures positions."""
    futures_base = 'https://api-futures.kucoin.com'

    async with aiohttp.ClientSession() as session:
        try:
            positions_resp = await kucoin_private_get(session, futures_base, '/api/v1/positions')
            return positions_resp.get('data', [])
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []


async def close_position(symbol: str, side: str, size: int):
    """Close a KuCoin futures position."""
    futures_base = 'https://api-futures.kucoin.com'

    # Prepare order data
    order_data = {
        "clientOid": f"close_{int(time.time() * 1000)}",
        "side": side,
        "symbol": symbol,
        "type": "market",
        "size": size,
        "reduceOnly": True
    }

    async with aiohttp.ClientSession() as session:
        try:
            result = await kucoin_private_post(session, futures_base, '/api/v1/orders', order_data)
            return True, result.get('data', {})
        except Exception as e:
            logger.error(f"Failed to close position {symbol}: {e}")
            return False, str(e)


async def main():
    """Main function to close all positions."""
    try:
        print("=" * 60)
        print("KUCON POSITION CLOSER")
        print("=" * 60)

        # Get account info
        print("Getting account information...")
        account_info = await get_account_info()
        if not account_info:
            print("Failed to get account information")
            return

        print(f"Account Equity: {account_info.get('accountEquity', 0):.6f} USDT")
        print(f"Unrealized PnL: {account_info.get('unrealisedPNL', 0):.6f} USDT")
        print(f"Available Balance: {account_info.get('availableBalance', 0):.6f} USDT")

        # Get positions
        print("\nGetting positions...")
        positions = await get_positions()

        # Filter open positions
        open_positions = []
        for pos in positions:
            current_qty = float(pos.get('currentQty', 0))
            if current_qty != 0 and pos.get('isOpen', False):
                side = "sell" if current_qty > 0 else "buy"
                open_positions.append({
                    'symbol': pos.get('symbol', ''),
                    'side': side,
                    'size': abs(int(current_qty)),
                    'entry_price': float(pos.get('avgEntryPrice', 0)),
                    'mark_price': float(pos.get('markPrice', 0)),
                    'unrealized_pnl': float(pos.get('unrealisedPnl', 0))
                })

        if not open_positions:
            print("No open positions found")
            return

        print(f"\nFound {len(open_positions)} open positions:")
        total_unrealized_pnl = 0
        for pos in open_positions:
            print(f"  {pos['symbol']} | {pos['side'].upper()} | size={pos['size']} | entry={pos['entry_price']:.5f} | mark={pos['mark_price']:.5f} | uPnL={pos['unrealized_pnl']:.2f}")
            total_unrealized_pnl += pos['unrealized_pnl']

        print(f"\nTotal Unrealized PnL: {total_unrealized_pnl:.6f} USDT")

        # Calculate balance after closing
        current_balance = float(account_info.get('accountEquity', 0))
        balance_after_closing = current_balance + total_unrealized_pnl

        print(f"\nBalance After Closing: {balance_after_closing:.6f} USDT")

        # Ask for confirmation
        print("\n" + "=" * 60)
        print("CONFIRMATION REQUIRED")
        print("=" * 60)
        print(f"You are about to close {len(open_positions)} positions at market value.")
        print(f"Your available balance will be: {balance_after_closing:.6f} USDT")

        confirm = input("\nDo you want to proceed? (yes/no): ").lower().strip()

        if confirm in ['yes', 'y']:
            print("\nClosing all positions...")

            successful_closes = []
            failed_closes = []

            for pos in open_positions:
                print(f"Closing {pos['symbol']} {pos['side'].upper()} size={pos['size']}...")
                success, result = await close_position(pos['symbol'], pos['side'], pos['size'])

                if success:
                    print(f"  ✅ Successfully closed {pos['symbol']}")
                    successful_closes.append(pos)
                else:
                    print(f"  ❌ Failed to close {pos['symbol']}: {result}")
                    failed_closes.append(pos)

            # Show results
            print("\n" + "=" * 60)
            print("CLOSING RESULTS")
            print("=" * 60)
            print(f"Successfully closed: {len(successful_closes)} positions")
            print(f"Failed to close: {len(failed_closes)} positions")

            if successful_closes:
                print("\nSuccessfully closed positions:")
                for pos in successful_closes:
                    print(f"  - {pos['symbol']} {pos['side'].upper()} size={pos['size']}")

            if failed_closes:
                print("\nFailed to close positions:")
                for pos in failed_closes:
                    print(f"  - {pos['symbol']} {pos['side'].upper()} size={pos['size']}")

            # Get final balance
            print("\nGetting final balance...")
            final_account_info = await get_account_info()
            if final_account_info:
                print(f"Final Available Balance: {final_account_info.get('availableBalance', 0):.6f} USDT")
                print(f"Final Account Equity: {final_account_info.get('accountEquity', 0):.6f} USDT")

        else:
            print("Operation cancelled by user.")

    except Exception as e:
        logger.error(f"Error in main: {e}")


if __name__ == "__main__":
    asyncio.run(main())


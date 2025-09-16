#!/usr/bin/env python3
"""
Combined Balance Fetcher

Fetches balances from both Binance and KuCoin and stores them in Supabase.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
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

# Import BinanceExchange at module level
try:
    from src.exchange import BinanceExchange
except ImportError:
    BinanceExchange = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CombinedBalanceFetcher:
    """Combined balance fetcher for Binance and KuCoin."""
    
    def __init__(self):
        # Binance credentials
        self.binance_key = os.getenv('BINANCE_API_KEY')
        self.binance_secret = os.getenv('BINANCE_API_SECRET')
        self.binance_testnet = os.getenv('BINANCE_TESTNET', 'false').lower() == 'true'
        
        # KuCoin credentials
        self.kucoin_key = os.getenv('KUCOIN_API_KEY')
        self.kucoin_secret = os.getenv('KUCOIN_API_SECRET')
        self.kucoin_passphrase = os.getenv('KUCOIN_API_PASSPHRASE')
        
        # Supabase
        self.supabase = None
        
        # KuCoin API endpoint (futures uses different base URL)
        self.kucoin_base_url = "https://api-futures.kucoin.com"
    
    async def initialize(self) -> bool:
        """Initialize connections to exchanges and Supabase."""
        try:
            # Initialize Supabase
            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = os.getenv('SUPABASE_KEY')

            if not supabase_url or not supabase_key:
                logger.error("Supabase credentials not found!")
                return False

            try:
                from supabase import create_client, Client
                self.supabase = create_client(supabase_url, supabase_key)
            except ImportError:
                logger.error("Supabase library not found. Install with: pip install supabase")
                return False

            logger.info("✅ Connected to Supabase")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize connections: {e}")
            return False

    async def get_binance_futures_balances(self) -> List[Dict[str, Any]]:
        """Get futures balances from Binance using BinanceExchange class."""
        try:
            if not BinanceExchange or not self.binance_key or not self.binance_secret:
                logger.warning("Binance credentials not available")
                return []
            
            # Use the existing BinanceExchange class
            binance_exchange = BinanceExchange(
                api_key=self.binance_key,
                api_secret=self.binance_secret,
                is_testnet=self.binance_testnet
            )
            
            # Initialize the client
            await binance_exchange._init_client()
            client = binance_exchange.client
            
            if not client:
                logger.error("Failed to initialize Binance client")
                return []
            
            # Get futures account information
            futures_account = await client.futures_account()
            balances = []
            
            # Process futures balances
            for asset in futures_account.get('assets', []):
                wallet_balance = float(asset.get('walletBalance', 0))
                available_balance = float(asset.get('availableBalance', 0))
                unrealized_pnl = float(asset.get('unrealizedProfit', 0))
                
                if wallet_balance > 0 or available_balance > 0 or unrealized_pnl != 0:
                    balances.append({
                        'platform': 'binance',
                        'account_type': 'futures',
                        'asset': asset['asset'],
                        'free': available_balance,
                        'locked': wallet_balance - available_balance,
                        'total': wallet_balance,
                        'unrealized_pnl': unrealized_pnl,
                        'last_updated': datetime.now(timezone.utc).isoformat()
                    })
            
            # Close the client
            await binance_exchange.close()
            
            logger.info(f"Retrieved {len(balances)} Binance futures balances")
            return balances

        except Exception as e:
            logger.error(f"Error fetching Binance futures balances: {e}")
            return []

    async def get_kucoin_futures_balances(self) -> List[Dict[str, Any]]:
        """Get futures balances from KuCoin using direct API calls."""
        try:
            if not self.kucoin_key or not self.kucoin_secret or not self.kucoin_passphrase:
                logger.warning("KuCoin credentials not available")
                return []
            
            import aiohttp
            import time
            import hmac
            import hashlib
            import base64
            
            # KuCoin futures account endpoint
            endpoint = "/api/v1/account-overview"
            timestamp = str(int(time.time() * 1000))
            method = "GET"
            
            # Create signature
            string_to_sign = timestamp + method + endpoint + ""
            signature = base64.b64encode(
                hmac.new(
                    self.kucoin_secret.encode('utf-8'),
                    string_to_sign.encode('utf-8'),
                    hashlib.sha256
                ).digest()
            ).decode('utf-8')
            
            passphrase_signature = base64.b64encode(
                hmac.new(
                    self.kucoin_secret.encode('utf-8'),
                    self.kucoin_passphrase.encode('utf-8'),
                    hashlib.sha256
                ).digest()
            ).decode('utf-8')
            
            headers = {
                'KC-API-KEY': self.kucoin_key,
                'KC-API-SIGN': signature,
                'KC-API-TIMESTAMP': timestamp,
                'KC-API-PASSPHRASE': passphrase_signature,
                'KC-API-KEY-VERSION': '2',
                'Content-Type': 'application/json'
            }
            
            # Make request
            url = f"{self.kucoin_base_url}{endpoint}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        balances = []
                        if data.get('code') == '200000' and data.get('data'):
                            account_data = data['data']
                            
                            # KuCoin returns a single account object, not a dictionary of assets
                            available_balance = float(account_data.get('availableBalance', 0))
                            total_balance = float(account_data.get('accountEquity', 0))
                            unrealized_pnl = float(account_data.get('unrealisedPNL', 0))
                            currency = account_data.get('currency', 'USDT')
                            
                            # Store the balance, even if zero
                            balances.append({
                                'platform': 'kucoin',
                                'account_type': 'futures',
                                'asset': currency,
                                'free': available_balance,
                                'locked': total_balance - available_balance,
                                'total': total_balance,
                                'unrealized_pnl': unrealized_pnl,
                                'last_updated': datetime.now(timezone.utc).isoformat()
                            })
                        else:
                            # If no data or error, still store a zero USDT balance to track the account
                            balances.append({
                                'platform': 'kucoin',
                                'account_type': 'futures',
                                'asset': 'USDT',
                                'free': 0.0,
                                'locked': 0.0,
                                'total': 0.0,
                                'unrealized_pnl': 0.0,
                                'last_updated': datetime.now(timezone.utc).isoformat()
                            })
                        
                        logger.info(f"Retrieved {len(balances)} KuCoin futures balances")
                        return balances
                    else:
                        error_text = await response.text()
                        logger.error(f"KuCoin API error: {response.status} - {error_text}")
                        return []

        except Exception as e:
            logger.error(f"Error fetching KuCoin futures balances: {e}")
            return []

    async def store_balances_in_database(self, balances: List[Dict[str, Any]]) -> int:
        """Store balance data in Supabase balances table."""
        if not balances:
            logger.warning("No balances to store")
            return 0

        try:
            # First, delete existing balances for the same platform and account type
            if balances:
                platform = balances[0]['platform']
                account_type = balances[0]['account_type']
                
                # Delete existing records
                delete_result = self.supabase.table("balances").delete().eq("platform", platform).eq("account_type", account_type).execute()
                logger.info(f"Deleted existing {platform} {account_type} balances")

            # Insert new balances
            insert_result = self.supabase.table("balances").insert(balances).execute()
            
            if insert_result.data:
                logger.info(f"Successfully stored {len(insert_result.data)} balances in database")
                return len(insert_result.data)
            else:
                logger.error("Failed to store balances - no data returned")
                return 0

        except Exception as e:
            logger.error(f"Error storing balances in database: {e}")
            return 0

    async def fetch_and_store_all_balances(self) -> Dict[str, int]:
        """Fetch and store balance data from both exchanges."""
        results = {
            'binance_futures': 0,
            'kucoin_futures': 0,
            'total': 0
        }

        try:
            # Fetch Binance futures balances
            logger.info("🔄 Fetching Binance futures balances...")
            binance_balances = await self.get_binance_futures_balances()
            if binance_balances:
                results['binance_futures'] = await self.store_balances_in_database(binance_balances)

            # Add delay between API calls
            await asyncio.sleep(1)

            # Fetch KuCoin futures balances
            logger.info("🔄 Fetching KuCoin futures balances...")
            kucoin_balances = await self.get_kucoin_futures_balances()
            if kucoin_balances:
                results['kucoin_futures'] = await self.store_balances_in_database(kucoin_balances)

            results['total'] = results['binance_futures'] + results['kucoin_futures']
            
            logger.info(f"✅ Balance fetch completed - Binance: {results['binance_futures']}, KuCoin: {results['kucoin_futures']}, Total: {results['total']}")
            return results

        except Exception as e:
            logger.error(f"Error during balance fetch: {e}")
            return results

    async def get_stored_balances(self, platform: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve stored balances from database."""
        try:
            query = self.supabase.table("balances").select("*")
            
            if platform:
                query = query.eq("platform", platform)
            
            result = query.execute()
            return result.data if result.data else []

        except Exception as e:
            logger.error(f"Error retrieving stored balances: {e}")
            return []

    async def cleanup(self):
        """Clean up connections."""
        logger.info("Connection cleanup completed")

async def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description='Combined Balance Fetcher')
    parser.add_argument('--show-stored', action='store_true',
                        help='Show currently stored balances')
    parser.add_argument('--dry-run', action='store_true',
                        help='Fetch balances but do not store in database')
    parser.add_argument('--once', action='store_true',
                        help='Run balance update once and exit')
    parser.add_argument('--daemon', action='store_true',
                        help='Run as daemon service (continuous updates)')
    parser.add_argument('--interval', type=int, default=300,
                        help='Update interval in seconds for daemon mode (default: 300)')
    parser.add_argument('--platform', choices=['binance', 'kucoin', 'all'], default='all',
                        help='Which platform to fetch balances for')

    args = parser.parse_args()

    fetcher = CombinedBalanceFetcher()

    try:
        if not await fetcher.initialize():
            logger.error("Failed to initialize connections")
            return

        if args.show_stored:
            # Show stored balances
            balances = await fetcher.get_stored_balances(args.platform if args.platform != 'all' else None)
            if balances:
                print(f"\n📊 Stored Balances ({len(balances)} total):")
                print(f"{'Platform':<10} {'Account':<10} {'Asset':<8} {'Free':<15} {'Locked':<15} {'Total':<15} {'Unrealized PnL':<15}")
                print("-" * 100)
                
                for balance in balances:
                    print(f"{balance['platform']:<10} {balance['account_type']:<10} {balance['asset']:<8} "
                          f"{balance['free']:<15.8f} {balance['locked']:<15.8f} {balance['total']:<15.8f} "
                          f"{balance['unrealized_pnl']:<15.8f}")
            else:
                print("No stored balances found")
            return

        if args.daemon:
            # Run as daemon service
            logger.info(f"🚀 Starting daemon mode with {args.interval}s interval...")
            while True:
                try:
                    results = await fetcher.fetch_and_store_all_balances()
                    if not args.dry_run:
                        logger.info(f"✅ Updated {results['total']} balances")
                    else:
                        logger.info(f"🔍 Would update {results['total']} balances (dry run)")
                    
                    await asyncio.sleep(args.interval)
                except KeyboardInterrupt:
                    logger.info("Received interrupt signal, shutting down...")
                    break
                except Exception as e:
                    logger.error(f"Error in daemon mode: {e}")
                    await asyncio.sleep(60)  # Wait 1 minute before retrying
        else:
            # Run once
            results = await fetcher.fetch_and_store_all_balances()
            if not args.dry_run:
                print(f"✅ Balance fetch completed:")
                print(f"   Binance futures: {results['binance_futures']}")
                print(f"   KuCoin futures: {results['kucoin_futures']}")
                print(f"   Total balances: {results['total']}")
            else:
                print(f"🔍 Would store {results['total']} total balances (dry run)")

    except Exception as e:
        logger.error(f"Error in main: {e}")
    finally:
        await fetcher.cleanup()

if __name__ == "__main__":
    asyncio.run(main())

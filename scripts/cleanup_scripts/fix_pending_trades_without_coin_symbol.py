#!/usr/bin/env python3
"""
Script to fix trades that are stuck in pending state without coin_symbol.

These trades were created but never went through the AI parsing process,
so they're missing critical data like coin_symbol, parsed_signal, etc.
"""

import asyncio
import json
import logging
from supabase import create_client, Client
import os
from dotenv import load_dotenv
from datetime import datetime, timezone

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PendingTradeFixer:
    def __init__(self):
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_KEY')

        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY environment variables")

        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)

    async def find_pending_trades_without_coin_symbol(self):
        """Find trades that are pending and missing coin_symbol."""
        try:
            # Find trades with status='pending' (lowercase) and missing coin_symbol
            response = self.supabase.from_("trades").select("*").eq("status", "pending").is_("coin_symbol", "null").limit(100).execute()

            if response.data:
                logger.info(f"Found {len(response.data)} pending trades without coin_symbol")
                return response.data
            else:
                logger.info("No pending trades found without coin_symbol")
                return []

        except Exception as e:
            logger.error(f"Error finding pending trades: {e}")
            return []

    def extract_coin_symbol_from_content(self, content: str) -> str:
        """Extract coin symbol from trade content."""
        if not content:
            return "UNKNOWN"

        # Common patterns for coin symbols
        import re

        # Pattern 1: "Longed ETH" or "Short ETH"
        long_short_pattern = r'(?:Longed?|Short)\s+([A-Z]{2,10})'
        match = re.search(long_short_pattern, content, re.IGNORECASE)
        if match:
            coin_symbol = match.group(1).upper()
            if 2 <= len(coin_symbol) <= 10 and coin_symbol.isalnum():
                return coin_symbol

        # Pattern 2: "ETH 🚀" or "BTC 🚀"
        rocket_pattern = r'([A-Z]{2,10})\s*🚀'
        match = re.search(rocket_pattern, content, re.IGNORECASE)
        if match:
            coin_symbol = match.group(1).upper()
            if 2 <= len(coin_symbol) <= 10 and coin_symbol.isalnum():
                return coin_symbol

        # Pattern 3: "Link $25.85" or "BTC 114800"
        price_pattern = r'([A-Z]{2,10})\s+\$?[\d,]+\.?\d*'
        match = re.search(price_pattern, content, re.IGNORECASE)
        if match:
            coin_symbol = match.group(1).upper()
            if 2 <= len(coin_symbol) <= 10 and coin_symbol.isalnum():
                return coin_symbol

        # Pattern 4: "BTC limi" (truncated content)
        limit_pattern = r'([A-Z]{2,10})\s+limi'
        match = re.search(limit_pattern, content, re.IGNORECASE)
        if match:
            coin_symbol = match.group(1).upper()
            if 2 <= len(coin_symbol) <= 10 and coin_symbol.isalnum():
                return coin_symbol

        return "UNKNOWN"

    def create_fake_parsed_signal(self, coin_symbol: str, content: str) -> dict:
        """Create a basic parsed signal structure for trades that can't be AI parsed."""
        # Extract basic info from content
        import re

        # Try to extract entry price
        entry_price = None
        price_match = re.search(r'(\d+(?:\.\d+)?)', content)
        if price_match:
            try:
                entry_price = float(price_match.group(1))
            except:
                pass

        # Determine position type from content
        position_type = "LONG"
        if "short" in content.lower():
            position_type = "SHORT"

        # Create basic parsed signal
        parsed_signal = {
            "coin_symbol": coin_symbol,
            "position_type": position_type,
            "order_type": "MARKET",  # Default to market order
            "entry_prices": [entry_price] if entry_price else [0.0],
            "stop_loss": None,
            "take_profits": [],
            "quantity_multiplier": 1.0
        }

        return parsed_signal

    async def fix_trade(self, trade: dict) -> bool:
        """Fix a single trade by extracting coin_symbol and creating parsed_signal."""
        try:
            trade_id = trade['id']
            content = trade.get('content', '')
            discord_id = trade.get('discord_id', '')

            logger.info(f"Fixing trade {trade_id} (discord_id: {discord_id})")

            # Extract coin symbol from content
            coin_symbol = self.extract_coin_symbol_from_content(content)

            if coin_symbol == "UNKNOWN":
                logger.warning(f"Could not extract coin symbol from content: '{content[:50]}...'")
                return False

            # Create basic parsed signal
            parsed_signal = self.create_fake_parsed_signal(coin_symbol, content)

            # Update the trade
            updates = {
                'coin_symbol': coin_symbol,
                'parsed_signal': json.dumps(parsed_signal),
                'signal_type': parsed_signal['position_type'],
                'status': 'PENDING',  # Fix case
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            # Add entry price if we found one
            if parsed_signal['entry_prices'][0] and parsed_signal['entry_prices'][0] > 0:
                updates['entry_price'] = parsed_signal['entry_prices'][0]

            self.supabase.from_("trades").update(updates).eq("id", trade_id).execute()

            logger.info(f"✅ Fixed trade {trade_id}: coin_symbol={coin_symbol}, position_type={parsed_signal['position_type']}")
            return True

        except Exception as e:
            logger.error(f"Error fixing trade {trade.get('id')}: {e}")
            return False

    async def run_fix(self):
        """Run the complete fix process."""
        logger.info("Starting fix for pending trades without coin_symbol...")

        # Find pending trades without coin_symbol
        pending_trades = await self.find_pending_trades_without_coin_symbol()

        if not pending_trades:
            logger.info("No pending trades found without coin_symbol. All good!")
            return

        # Fix the trades
        fixed_count = 0
        for trade in pending_trades:
            if await self.fix_trade(trade):
                fixed_count += 1

        logger.info(f"Fix completed! Fixed {fixed_count} out of {len(pending_trades)} trades")

async def main():
    """Main function."""
    try:
        fixer = PendingTradeFixer()
        await fixer.run_fix()
    except Exception as e:
        logger.error(f"Error in main: {e}")

if __name__ == "__main__":
    asyncio.run(main())

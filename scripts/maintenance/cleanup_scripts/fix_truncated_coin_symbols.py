#!/usr/bin/env python3
"""
Fix truncated coin symbols and incorrect position types in existing trades.

This script addresses the critical issues identified in the trade data:
1. Coin symbols being truncated (BTC -> TC, ETH -> ET, ETH -> TH)
2. Position types being incorrect (SHORT signals executed as LONG)
3. Parsed_signal being null or malformed
"""

import asyncio
import json
import logging
import sys
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from supabase import create_client, Client
from config import settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TruncatedSymbolFixer:
    def __init__(self):
        self.supabase: Optional[Client] = None
        self.fixed_count = 0
        self.error_count = 0

        # Mapping of truncated symbols to correct symbols
        self.symbol_mapping = {
            'TC': 'BTC',
            'ET': 'ETH',
            'TH': 'ETH',
            'OL': 'SOL',
            'DA': 'ADA',
            'OT': 'DOT',
            'NK': 'LINK',
            'NI': 'UNI',
            'VE': 'AAVE',
            'IC': 'MATIC',
            'AX': 'AVAX',
            'AR': 'NEAR',
            'TM': 'FTM',
            'GO': 'ALGO',
            'OM': 'ATOM',
            'RP': 'XRP',
            'GE': 'DOGE',
            'IB': 'SHIB',
            'PE': 'PEPE',
            'NK': 'BONK',
            'IF': 'WIF',
            'KI': 'FLOKI',
            'HI': 'TOSHI',
            'BO': 'TURBO',
            'PE': 'HYPE',
            'IN': 'FARTCOIN'
        }

    def initialize_supabase(self) -> bool:
        """Initialize Supabase client."""
        try:
            supabase_url = settings.SUPABASE_URL
            supabase_key = settings.SUPABASE_KEY

            if not supabase_url or not supabase_key:
                logger.error("Supabase URL or Key not set in environment")
                return False

            self.supabase = create_client(supabase_url, supabase_key)
            logger.info("✅ Supabase client initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            return False

    def extract_coin_symbol_from_content(self, content: str) -> Optional[str]:
        """Extract coin symbol from trade content using regex patterns."""
        if not content:
            return None

        import re

        # Common patterns for coin symbols in trade content
        patterns = [
            r'\b(BTC|ETH|SOL|ADA|DOT|LINK|UNI|AAVE|MATIC|AVAX|NEAR|FTM|ALGO|ATOM|XRP|DOGE|SHIB|PEPE|BONK|WIF|FLOKI|TOSHI|TURBO|HYPE|FARTCOIN)\b',
            r'\b(TC|ET|TH|OL|DA|OT|NK|NI|VE|IC|AX|AR|TM|GO|OM|RP|GE|IB|PE|NK|IF|KI|HI|BO|PE|IN)\b'  # Truncated symbols
        ]

        for pattern in patterns:
            match = re.search(pattern, content.upper())
            if match:
                symbol = match.group(1)
                # If it's a truncated symbol, map it to the correct one
                if symbol in self.symbol_mapping:
                    return self.symbol_mapping[symbol]
                return symbol

        return None

    def determine_position_type_from_content(self, content: str) -> str:
        """Determine position type from trade content."""
        if not content:
            return 'LONG'  # Default

        content_lower = content.lower()

        # SHORT indicators
        short_indicators = ['short', 'shorted', 'sell', 'sold', 'going short', 'shorting']
        for indicator in short_indicators:
            if indicator in content_lower:
                return 'SHORT'

        # LONG indicators
        long_indicators = ['long', 'longed', 'buy', 'bought', 'going long', 'longing']
        for indicator in long_indicators:
            if indicator in content_lower:
                return 'LONG'

        return 'LONG'  # Default

    def create_fixed_parsed_signal(self, coin_symbol: str, position_type: str, content: str, entry_prices: list, stop_loss: Optional[float] = None) -> Dict[str, Any]:
        """Create a properly formatted parsed_signal."""
        return {
            'coin_symbol': coin_symbol,
            'position_type': position_type,
            'entry_prices': entry_prices,
            'stop_loss': stop_loss,
            'take_profits': None,
            'order_type': 'MARKET',
            'risk_level': None
        }

    def extract_prices_from_content(self, content: str) -> tuple:
        """Extract entry prices and stop loss from content."""
        import re

        # Extract numbers that could be prices
        numbers = re.findall(r'\d+(?:\.\d+)?', content)
        numbers = [float(num) for num in numbers if float(num) > 10]  # Filter out small numbers

        if not numbers:
            return [], None

        # First number is usually entry price, last number is usually stop loss
        entry_prices = [numbers[0]]
        stop_loss = numbers[-1] if len(numbers) > 1 else None

        return entry_prices, stop_loss

    async def fix_trade(self, trade: Dict[str, Any]) -> bool:
        """Fix a single trade by correcting coin symbol and position type."""
        try:
            trade_id = trade['id']
            content = trade.get('content', '')
            discord_id = trade.get('discord_id', '')

            logger.info(f"Fixing trade {trade_id} (discord_id: {discord_id})")

            # Extract correct coin symbol from content
            coin_symbol = self.extract_coin_symbol_from_content(content)
            if not coin_symbol:
                logger.warning(f"Could not extract coin symbol from content: '{content[:50]}...'")
                return False

            # Determine correct position type from content
            position_type = self.determine_position_type_from_content(content)

            # Extract prices
            entry_prices, stop_loss = self.extract_prices_from_content(content)

            # Create fixed parsed signal
            parsed_signal = self.create_fixed_parsed_signal(
                coin_symbol=coin_symbol,
                position_type=position_type,
                content=content,
                entry_prices=entry_prices,
                stop_loss=stop_loss
            )

            # Prepare updates
            updates = {
                'coin_symbol': coin_symbol,
                'parsed_signal': json.dumps(parsed_signal),
                'signal_type': position_type,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            # Add entry price if we found one
            if entry_prices and entry_prices[0] > 0:
                updates['entry_price'] = entry_prices[0]

            # Update the trade
            self.supabase.from_("trades").update(updates).eq("id", trade_id).execute()

            logger.info(f"✅ Fixed trade {trade_id}: coin_symbol={coin_symbol}, position_type={position_type}")
            return True

        except Exception as e:
            logger.error(f"Error fixing trade {trade.get('id')}: {e}")
            return False

    async def run_fix(self):
        """Run the complete fix process."""
        logger.info("🔧 Starting truncated coin symbol fix...")

        if not self.initialize_supabase():
            return

        try:
            # Find trades with truncated symbols or incorrect position types
            problematic_trades = []

            # Get trades with truncated symbols
            for truncated_symbol, correct_symbol in self.symbol_mapping.items():
                response = self.supabase.from_("trades").select("*").eq("coin_symbol", truncated_symbol).execute()
                if response.data:
                    problematic_trades.extend(response.data)

            # Get trades with null parsed_signal
            response = self.supabase.from_("trades").select("*").is_("parsed_signal", "null").execute()
            if response.data:
                problematic_trades.extend(response.data)

            # Get trades with failed status that might have parsing issues
            response = self.supabase.from_("trades").select("*").eq("status", "FAILED").execute()
            if response.data:
                problematic_trades.extend(response.data)

            # Remove duplicates based on trade ID
            unique_trades = {trade['id']: trade for trade in problematic_trades}.values()

            logger.info(f"Found {len(unique_trades)} trades to fix")

            if not unique_trades:
                logger.info("✅ No trades need fixing")
                return

            # Fix each trade
            for trade in unique_trades:
                if await self.fix_trade(trade):
                    self.fixed_count += 1
                else:
                    self.error_count += 1

            logger.info(f"✅ Fix completed: {self.fixed_count} fixed, {self.error_count} errors")

        except Exception as e:
            logger.error(f"Error in fix process: {e}")

async def main():
    """Main function."""
    fixer = TruncatedSymbolFixer()
    await fixer.run_fix()

if __name__ == "__main__":
    asyncio.run(main())

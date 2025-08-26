#!/usr/bin/env python3
"""
Script to fix incorrect coin symbols for trades before August 20th, 2025.

The AI parsing script did more harm than good, extracting wrong symbols like:
- "LIMIT" instead of "ETH"
- "SL" instead of "LINK" or "ETH"
- "SHORT" instead of "BTC"
- "TH" instead of "ETH"
"""

import asyncio
import json
import logging
import re
from supabase import create_client, Client
import os
from dotenv import load_dotenv
from datetime import datetime, timezone

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CoinSymbolFixer:
    def __init__(self):
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_KEY')

        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY environment variables")

        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)

    def clean_content(self, content: str) -> str:
        """Remove Discord invisible characters and clean content."""
        if not content:
            return ""

        # Remove Discord invisible characters (zero-width characters)
        cleaned = re.sub(r'[\u200B\u200C\u200D\uFEFF]', '', content)

        # Remove other problematic characters
        cleaned = re.sub(r'[⁠⁣⁣⁠⁣⁣⁠⁠⁢⁠⁣⁣⁠⁣⁣⁣⁣⁢⁠⁣⁣⁣⁠⁠⁣⁠⁢⁠⁣⁣⁠⁠⁣⁠⁠⁢⁠⁣⁣⁠⁣⁣⁣⁠⁢⁠⁣⁣⁠⁠⁠⁠⁣⁢⁠⁣⁣⁠⁣⁠⁠⁠⁢⁠⁣⁣⁠⁠⁣⁠⁣⁢⁠⁣⁣⁠⁠⁣⁠⁣⁢⁠⁣⁣⁠⁠⁣⁠⁠]', '', cleaned)

        return cleaned.strip()

    def extract_coin_symbol_from_content(self, content: str) -> str:
        """Extract coin symbol from cleaned content using regex patterns."""
        cleaned_content = self.clean_content(content)

        # Convert to uppercase for better matching
        content_upper = cleaned_content.upper()

        logger.info(f"Cleaned content: {cleaned_content}")
        logger.info(f"Uppercase content: {content_upper}")

        # First, try to find exact coin symbols at the beginning of words
        coin_patterns = [
            r'\b(ETH|ETHEREUM)\b',
            r'\b(BTC|BITCOIN)\b',
            r'\b(LINK|CHAINLINK)\b',
            r'\b(DSYNC)\b',
            r'\b(ADA|CARDANO)\b',
            r'\b(DOT|POLKADOT)\b',
            r'\b(SOL|SOLANA)\b',
            r'\b(BNB|BINANCE)\b',
            r'\b(XRP|RIPPLE)\b',
            r'\b(DOGE|DOGECOIN)\b',
            r'\b(MATIC|POLYGON)\b',
            r'\b(AVAX|AVALANCHE)\b',
            r'\b(UNI|UNISWAP)\b',
            r'\b(ATOM|COSMOS)\b',
            r'\b(FTM|FANTOM)\b',
            r'\b(NEAR)\b',
            r'\b(ALGO|ALGORAND)\b',
            r'\b(VET|VECHAIN)\b',
            r'\b(ICP|INTERNET COMPUTER)\b',
            r'\b(FIL|FILECOIN)\b',
            r'\b(TRX|TRON)\b',
            r'\b(ETC|ETHEREUM CLASSIC)\b',
            r'\b(LTC|LITECOIN)\b',
            r'\b(BCH|BITCOIN CASH)\b',
            r'\b(XLM|STELLAR)\b',
            r'\b(THETA)\b',
            r'\b(EOS)\b',
            r'\b(AAVE)\b',
            r'\b(COMP|COMPOUND)\b',
            r'\b(MKR|MAKER)\b',
            r'\b(SNX|SYNTHETIX)\b',
            r'\b(CRV|CURVE)\b',
            r'\b(YFI|YEARN)\b',
            r'\b(SUSHI|SUSHISWAP)\b',
            r'\b(1INCH)\b',
            r'\b(CAKE|PANCAKESWAP)\b',
            r'\b(CHZ|CHILIZ)\b',
            r'\b(HOT|HOLO)\b',
            r'\b(BAT)\b',
            r'\b(ZIL|ZILLIQA)\b',
            r'\b(ENJ|ENJIN)\b',
            r'\b(MANA|DECENTRALAND)\b',
            r'\b(SAND)\b',
            r'\b(AXS|AXIE)\b',
            r'\b(GALA)\b',
            r'\b(ROSE|OASIS)\b',
            r'\b(FLOW)\b',
            r'\b(ALICE)\b',
            r'\b(DYDX)\b',
            r'\b(IMX|IMMUTABLE)\b',
            r'\b(OP|OPTIMISM)\b',
            r'\b(ARB|ARBITRUM)\b',
            r'\b(APT|APTOS)\b',
            r'\b(SUI)\b',
            r'\b(SEI)\b',
            r'\b(TIA|CELESTIA)\b',
            r'\b(JUP|JUPITER)\b',
            r'\b(PYTH)\b',
            r'\b(BONK)\b',
            r'\b(WIF|DOGWIFHAT)\b',
            r'\b(PEPE)\b',
            r'\b(SHIB|SHIBA)\b',
            r'\b(FLOKI)\b',
            r'\b(MOON)\b',
            r'\b(SAFEMOON)\b',
            r'\b(BABYDOGE)\b',
            r'\b(SAMO)\b',
            r'\b(CATE|CATECOIN)\b',
            r'\b(HOGE)\b',
            r'\b(ELON)\b',
            r'\b(KISHU)\b',
            r'\b(AKITA)\b',
            r'\b(HOKK)\b',
            r'\b(LEASH)\b',
            r'\b(BONE)\b',
            r'\b(TREAT)\b',
            r'\b(PAW)\b',
            r'\b(WOJAK)\b',
            r'\b(WOOF)\b',
            r'\b(COPE)\b',
            r'\b(RAY|RAYDIUM)\b',
            r'\b(SRM|SERUM)\b',
            r'\b(ORCA)\b',
            r'\b(MER|MERCURIAL)\b',
            r'\b(SABER)\b',
            r'\b(SOLAR)\b',
            r'\b(STEP)\b',
            r'\b(MEDIA)\b',
        ]

        # Try exact word boundary matches first
        for pattern in coin_patterns:
            match = re.search(pattern, content_upper)
            if match:
                symbol = match.group(1).upper()
                logger.info(f"Found symbol '{symbol}' using pattern '{pattern}'")
                return symbol

        # If no exact match, try more flexible patterns
        flexible_patterns = [
            r'(ETH|ETHEREUM)',
            r'(BTC|BITCOIN)',
            r'(LINK|CHAINLINK)',
            r'(DSYNC)',
            r'(ADA|CARDANO)',
            r'(DOT|POLKADOT)',
            r'(SOL|SOLANA)',
            r'(BNB|BINANCE)',
            r'(XRP|RIPPLE)',
            r'(DOGE|DOGECOIN)',
            r'(MATIC|POLYGON)',
            r'(AVAX|AVALANCHE)',
            r'(UNI|UNISWAP)',
            r'(ATOM|COSMOS)',
            r'(FTM|FANTOM)',
            r'(NEAR)',
            r'(ALGO|ALGORAND)',
            r'(VET|VECHAIN)',
            r'(ICP)',
            r'(FIL|FILECOIN)',
            r'(TRX|TRON)',
            r'(ETC)',
            r'(LTC|LITECOIN)',
            r'(BCH|BITCOIN CASH)',
            r'(XLM|STELLAR)',
            r'(THETA)',
            r'(EOS)',
            r'(AAVE)',
            r'(COMP|COMPOUND)',
            r'(MKR|MAKER)',
            r'(SNX|SYNTHETIX)',
            r'(CRV|CURVE)',
            r'(YFI|YEARN)',
            r'(SUSHI|SUSHISWAP)',
            r'(1INCH)',
            r'(CAKE|PANCAKESWAP)',
            r'(CHZ|CHILIZ)',
            r'(HOT|HOLO)',
            r'(BAT)',
            r'(ZIL|ZILLIQA)',
            r'(ENJ|ENJIN)',
            r'(MANA|DECENTRALAND)',
            r'(SAND)',
            r'(AXS|AXIE)',
            r'(GALA)',
            r'(ROSE|OASIS)',
            r'(FLOW)',
            r'(ALICE)',
            r'(DYDX)',
            r'(IMX|IMMUTABLE)',
            r'(OP|OPTIMISM)',
            r'(ARB|ARBITRUM)',
            r'(APT|APTOS)',
            r'(SUI)',
            r'(SEI)',
            r'(TIA|CELESTIA)',
            r'(JUP|JUPITER)',
            r'(PYTH)',
            r'(BONK)',
            r'(WIF|DOGWIFHAT)',
            r'(PEPE)',
            r'(SHIB|SHIBA)',
            r'(FLOKI)',
            r'(MOON)',
            r'(SAFEMOON)',
            r'(BABYDOGE)',
            r'(SAMO)',
            r'(CATE|CATECOIN)',
            r'(HOGE)',
            r'(ELON)',
            r'(KISHU)',
            r'(AKITA)',
            r'(HOKK)',
            r'(LEASH)',
            r'(BONE)',
            r'(TREAT)',
            r'(PAW)',
            r'(WOJAK)',
            r'(WOOF)',
            r'(COPE)',
            r'(RAY|RAYDIUM)',
            r'(SRM|SERUM)',
            r'(ORCA)',
            r'(MER|MERCURIAL)',
            r'(SABER)',
            r'(SOLAR)',
            r'(STEP)',
            r'(MEDIA)',
        ]

        for pattern in flexible_patterns:
            match = re.search(pattern, content_upper)
            if match:
                symbol = match.group(1).upper()
                logger.info(f"Found symbol '{symbol}' using flexible pattern '{pattern}'")
                return symbol

        # Special handling for common cases
        if 'ETH' in content_upper or 'ETHEREUM' in content_upper:
            return 'ETH'
        elif 'BTC' in content_upper or 'BITCOIN' in content_upper:
            return 'BTC'
        elif 'LINK' in content_upper or 'CHAINLINK' in content_upper:
            return 'LINK'
        elif 'DSYNC' in content_upper:
            return 'DSYNC'

        logger.warning(f"Could not extract coin symbol from content: {cleaned_content}")
        return "UNKNOWN"

    async def get_trades_before_august_20(self) -> list:
        """Get all trades before August 20th, 2025."""
        try:
            # Get trades created before August 20th, 2025
            response = self.supabase.from_("trades").select("*").gte("timestamp", "2025-08-21T00:00:00Z").execute()

            if not response.data:
                logger.info("No trades found before August 20th, 2025")
                return []

            logger.info(f"Found {len(response.data)} trades before August 20th, 2025")
            return response.data

        except Exception as e:
            logger.error(f"Error fetching trades: {e}")
            return []

    async def fix_coin_symbols(self, dry_run: bool = True) -> None:
        """Fix coin symbols for trades before August 20th, 2025."""
        trades = await self.get_trades_before_august_20()

        if not trades:
            logger.info("No trades to fix")
            return

        fixed_count = 0
        error_count = 0

        for trade in trades:
            try:
                trade_id = trade['id']
                current_coin_symbol = trade.get('coin_symbol', '')
                content = trade.get('content', '')

                # Skip if no content
                if not content:
                    logger.warning(f"Trade {trade_id} has no content, skipping")
                    continue

                # Extract correct coin symbol from content
                correct_coin_symbol = self.extract_coin_symbol_from_content(content)

                # Skip if we couldn't extract a symbol or it's the same
                if correct_coin_symbol == "UNKNOWN":
                    logger.warning(f"Trade {trade_id}: Could not extract coin symbol from content: {content[:100]}...")
                    continue

                if correct_coin_symbol == current_coin_symbol:
                    logger.info(f"Trade {trade_id}: Coin symbol already correct ({current_coin_symbol})")
                    continue

                logger.info(f"Trade {trade_id}: {current_coin_symbol} -> {correct_coin_symbol}")
                logger.info(f"  Content: {content[:100]}...")

                if not dry_run:
                    # Update the trade
                    updates = {
                        'coin_symbol': correct_coin_symbol
                    }

                    # Also update parsed_signal if it exists
                    if trade.get('parsed_signal'):
                        try:
                            parsed_signal = json.loads(trade['parsed_signal'])
                            parsed_signal['coin_symbol'] = correct_coin_symbol
                            updates['parsed_signal'] = json.dumps(parsed_signal)
                        except:
                            pass

                    # Use synchronous update since Supabase client doesn't support await
                    self.supabase.from_("trades").update(updates).eq("id", trade_id).execute()
                    logger.info(f"  ✅ Updated trade {trade_id}")

                fixed_count += 1

            except Exception as e:
                logger.error(f"Error fixing trade {trade.get('id', 'unknown')}: {e}")
                error_count += 1

        logger.info(f"\n=== SUMMARY ===")
        logger.info(f"Total trades processed: {len(trades)}")
        logger.info(f"Trades fixed: {fixed_count}")
        logger.info(f"Errors: {error_count}")
        logger.info(f"Mode: {'DRY RUN' if dry_run else 'LIVE UPDATE'}")

async def main():
    """Main function."""
    try:
        fixer = CoinSymbolFixer()

        # First run as dry run to see what would be fixed
        logger.info("=== DRY RUN ===")
        await fixer.fix_coin_symbols(dry_run=True)

        # Ask for confirmation
        response = input("\nDo you want to apply these fixes? (y/N): ")
        if response.lower() == 'y':
            logger.info("=== APPLYING FIXES ===")
            await fixer.fix_coin_symbols(dry_run=False)
        else:
            logger.info("Fixes not applied")

    except Exception as e:
        logger.error(f"Error in main: {e}")

if __name__ == "__main__":
    asyncio.run(main())

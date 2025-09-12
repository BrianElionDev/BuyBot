#!/usr/bin/env python3
"""
Audit and fix stop-loss orders for all open positions.

This script implements the supervisor's requirements:
1. Default 5% stop-loss for all positions
2. Ensure every open position has a stop-loss order
3. Handle external stop-loss signals by replacing default SL
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from src.bot.trading_engine import TradingEngine
from src.exchange.binance_exchange import BinanceExchange
from config import settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class StopLossAuditor:
    def __init__(self):
        self.trading_engine = None
        self.audit_results = {
            'total_positions': 0,
            'positions_with_sl': 0,
            'positions_without_sl': 0,
            'sl_orders_created': 0,
            'errors': []
        }

    async def initialize(self):
        """Initialize the trading engine and exchange."""
        try:
            # Initialize Binance exchange
            api_key = settings.BINANCE_API_KEY
            api_secret = settings.BINANCE_API_SECRET
            is_testnet = settings.BINANCE_TESTNET

            if not api_key or not api_secret:
                logger.error("Binance API credentials not set")
                return False

            binance_exchange = BinanceExchange(api_key, api_secret, is_testnet)

            # Initialize trading engine
            self.trading_engine = TradingEngine(
                price_service=None,  # Not needed for this script
                binance_exchange=binance_exchange,
                db_manager=None  # Not needed for this script
            )

            logger.info("✅ Stop loss auditor initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize stop loss auditor: {e}")
            return False

    async def run_audit(self) -> Dict[str, Any]:
        """Run the complete stop-loss audit."""
        logger.info("🔍 Starting stop-loss audit for all open positions...")

        if not self.trading_engine:
            logger.error("Trading engine not initialized")
            return {'error': 'Trading engine not initialized'}

        try:
            # Run the audit using the trading engine's method
            audit_results = await self.trading_engine.audit_open_positions_for_stop_loss()

            # Log summary
            logger.info("📊 Stop-loss audit summary:")
            logger.info(f"  Total positions: {audit_results.get('total_positions', 0)}")
            logger.info(f"  Positions with SL: {audit_results.get('positions_with_sl', 0)}")
            logger.info(f"  Positions without SL: {audit_results.get('positions_without_sl', 0)}")
            logger.info(f"  SL orders created: {audit_results.get('sl_orders_created', 0)}")

            if audit_results.get('errors'):
                logger.warning(f"  Errors: {len(audit_results['errors'])}")
                for error in audit_results['errors']:
                    logger.warning(f"    - {error}")

            return audit_results

        except Exception as e:
            logger.error(f"Error during stop-loss audit: {e}")
            return {'error': str(e)}

    async def fix_specific_position(self, symbol: str, external_sl: Optional[float] = None):
        """
        Fix stop-loss for a specific position.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            external_sl: External stop-loss price (if provided)
        """
        try:
            logger.info(f"🔧 Fixing stop-loss for {symbol}")

            # Get position details
            positions = await self.trading_engine.binance_exchange.get_position_risk(symbol=symbol)

            if not positions:
                logger.warning(f"No position found for {symbol}")
                return False

            position = positions[0]  # Get first position
            position_amt = float(position.get('positionAmt', 0))

            if position_amt == 0:
                logger.info(f"No open position for {symbol}")
                return True

            # Determine position type and details
            position_type = 'LONG' if position_amt > 0 else 'SHORT'
            entry_price = float(position.get('entryPrice', 0))
            coin_symbol = symbol.replace('USDT', '')

            if not entry_price:
                logger.error(f"No entry price for {symbol}")
                return False

            logger.info(f"Position details: {symbol} {position_type} {abs(position_amt)} @ {entry_price}")

            # Ensure stop-loss for this position
            success, sl_order_id = await self.trading_engine.ensure_stop_loss_for_position(
                coin_symbol=coin_symbol,
                position_type=position_type,
                position_size=abs(position_amt),
                entry_price=entry_price,
                external_sl=external_sl
            )

            if success:
                logger.info(f"✅ Successfully created stop-loss order for {symbol}: {sl_order_id}")
                return True
            else:
                logger.error(f"❌ Failed to create stop-loss order for {symbol}")
                return False

        except Exception as e:
            logger.error(f"Error fixing stop-loss for {symbol}: {e}")
            return False

    async def list_open_positions(self):
        """List all open positions."""
        try:
            logger.info("📋 Listing all open positions...")

            positions = await self.trading_engine.binance_exchange.get_position_risk()

            if not positions:
                logger.info("No open positions found")
                return

            for position in positions:
                symbol = position.get('symbol')
                position_amt = float(position.get('positionAmt', 0))

                if position_amt == 0:
                    continue

                position_type = 'LONG' if position_amt > 0 else 'SHORT'
                entry_price = float(position.get('entryPrice', 0))
                unrealized_pnl = float(position.get('unRealizedProfit', 0))

                logger.info(f"  {symbol}: {position_type} {abs(position_amt)} @ {entry_price} (PnL: {unrealized_pnl:.2f})")

        except Exception as e:
            logger.error(f"Error listing positions: {e}")

async def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description='Audit and fix stop-loss orders')
    parser.add_argument('--audit', action='store_true', help='Run full audit')
    parser.add_argument('--fix', action='store_true', help='Fix positions without stop-loss')
    parser.add_argument('--list', action='store_true', help='List all open positions')
    parser.add_argument('--symbol', type=str, help='Fix specific symbol (e.g., BTCUSDT)')
    parser.add_argument('--sl-price', type=float, help='External stop-loss price for specific symbol')

    args = parser.parse_args()

    auditor = StopLossAuditor()

    if not await auditor.initialize():
        logger.error("Failed to initialize auditor")
        return

    try:
        if args.list:
            await auditor.list_open_positions()

        elif args.symbol:
            await auditor.fix_specific_position(args.symbol, args.sl_price)

        elif args.audit or args.fix:
            audit_results = await auditor.run_audit()

            if 'error' in audit_results:
                logger.error(f"Audit failed: {audit_results['error']}")
            else:
                logger.info("✅ Audit completed successfully")

        else:
            # Default: run audit
            audit_results = await auditor.run_audit()

            if 'error' in audit_results:
                logger.error(f"Audit failed: {audit_results['error']}")
            else:
                logger.info("✅ Audit completed successfully")

    except KeyboardInterrupt:
        logger.info("Audit interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        if auditor.trading_engine:
            await auditor.trading_engine.close()

if __name__ == "__main__":
    asyncio.run(main())

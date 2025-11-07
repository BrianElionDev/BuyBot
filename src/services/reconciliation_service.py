"""
Trade Reconciliation Service

This service reconciles and backfills missing data for existing CLOSED trades,
fixing inconsistencies and ensuring complete data.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from supabase import Client

from src.core.unified_status_updater import update_trade_status_safely
from src.core.data_enrichment import enrich_trade_data_before_close
from src.core.status_manager import StatusManager

logger = logging.getLogger(__name__)


class ReconciliationService:
    """Service for reconciling trade data inconsistencies."""

    def __init__(self, supabase: Client, bot: Optional[Any] = None):
        """
        Initialize reconciliation service.

        Args:
            supabase: Supabase client
            bot: DiscordBot instance with exchange connections
        """
        self.supabase = supabase
        self.bot = bot

    async def reconcile_closed_trades(
        self,
        days_back: int = 7,
        fix_status_inconsistencies: bool = True,
        backfill_missing_data: bool = True
    ) -> Dict[str, Any]:
        """
        Reconcile all CLOSED trades within the specified time period.

        Args:
            days_back: Number of days to look back for trades
            fix_status_inconsistencies: Whether to fix status inconsistencies
            backfill_missing_data: Whether to backfill missing exit prices and PNL

        Returns:
            Dictionary with reconciliation results
        """
        logger.info(f"Starting reconciliation for CLOSED trades (last {days_back} days)")

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()

        try:
            response = self.supabase.from_("trades").select("*").eq("status", "CLOSED").gte("created_at", cutoff).execute()
            trades = response.data or []

            logger.info(f"Found {len(trades)} CLOSED trades to reconcile")

            results = {
                'total_trades': len(trades),
                'status_fixed': 0,
                'data_backfilled': 0,
                'errors': 0
            }

            for trade in trades:
                try:
                    # Fix status inconsistencies
                    if fix_status_inconsistencies:
                        fixed = await self._fix_status_inconsistency(trade)
                        if fixed:
                            results['status_fixed'] += 1

                    # Backfill missing data
                    if backfill_missing_data:
                        backfilled = await self._backfill_missing_data(trade)
                        if backfilled:
                            results['data_backfilled'] += 1

                except Exception as e:
                    logger.error(f"Error reconciling trade {trade.get('id')}: {e}")
                    results['errors'] += 1

            logger.info(f"Reconciliation completed: {results}")
            return results

        except Exception as e:
            logger.error(f"Error in reconcile_closed_trades: {e}")
            return {'error': str(e)}

    async def _fix_status_inconsistency(self, trade: Dict[str, Any]) -> bool:
        """
        Fix status inconsistency for a trade.

        Returns:
            True if status was fixed, False otherwise
        """
        try:
            trade_id = trade.get('id')
            current_order_status = str(trade.get('order_status', 'NEW')).upper().strip()
            current_position_status = str(trade.get('status', 'PENDING')).upper().strip()

            # Validate consistency
            is_consistent = StatusManager.validate_status_consistency(
                current_order_status, current_position_status
            )

            if is_consistent:
                return False

            # Try to fix using StatusManager
            fixed_order_status, fixed_position_status = StatusManager.fix_inconsistent_status(
                current_order_status, current_position_status
            )

            # If position is CLOSED but order_status is inconsistent, query exchange
            if current_position_status == 'CLOSED' and current_order_status in ['PENDING', 'NEW']:
                success, status_update = await update_trade_status_safely(
                    supabase=self.supabase,
                    trade_id=trade_id,
                    trade=trade,
                    force_closed=True,
                    bot=self.bot
                )

                if success:
                    self.supabase.table("trades").update(status_update).eq("id", trade_id).execute()
                    logger.info(f"Fixed status inconsistency for trade {trade_id}: {status_update}")
                    return True
            else:
                # Use fixed statuses from StatusManager
                update_data = {
                    'order_status': fixed_order_status,
                    'status': fixed_position_status,
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }

                self.supabase.table("trades").update(update_data).eq("id", trade_id).execute()
                logger.info(f"Fixed status inconsistency for trade {trade_id}: {update_data}")
                return True

        except Exception as e:
            logger.error(f"Error fixing status inconsistency for trade {trade.get('id')}: {e}")
            return False

    async def _backfill_missing_data(self, trade: Dict[str, Any]) -> bool:
        """
        Backfill missing data (exit price, PNL) for a CLOSED trade.

        Returns:
            True if data was backfilled, False otherwise
        """
        try:
            trade_id = trade.get('id')
            needs_backfill = False

            # Check if exit_price is missing
            exit_price = trade.get('exit_price')
            if not exit_price or float(exit_price) == 0:
                needs_backfill = True

            # Check if PNL is missing
            pnl_usd = trade.get('pnl_usd')
            if not pnl_usd or float(pnl_usd) == 0:
                needs_backfill = True

            if not needs_backfill:
                return False

            # Enrich trade data
            enriched_data = await enrich_trade_data_before_close(trade, self.bot, self.supabase)

            if enriched_data:
                # Only update fields that are actually missing
                update_data = {}

                if (not exit_price or float(exit_price) == 0) and enriched_data.get('exit_price'):
                    update_data['exit_price'] = enriched_data['exit_price']
                    exchange_name = str(trade.get('exchange', '')).lower()
                    if exchange_name == 'binance':
                        update_data['binance_exit_price'] = enriched_data['exit_price']
                    elif exchange_name == 'kucoin':
                        update_data['exit_price'] = enriched_data['exit_price']

                if (not pnl_usd or float(pnl_usd) == 0) and enriched_data.get('pnl_usd'):
                    update_data['pnl_usd'] = enriched_data['pnl_usd']
                    if enriched_data.get('net_pnl'):
                        update_data['net_pnl'] = enriched_data['net_pnl']
                    if enriched_data.get('pnl_source'):
                        update_data['pnl_source'] = enriched_data['pnl_source']

                if enriched_data.get('exchange_response'):
                    update_data['exchange_response'] = enriched_data['exchange_response']

                if update_data:
                    update_data['updated_at'] = datetime.now(timezone.utc).isoformat()
                    self.supabase.table("trades").update(update_data).eq("id", trade_id).execute()
                    logger.info(f"Backfilled missing data for trade {trade_id}: {list(update_data.keys())}")
                    return True

        except Exception as e:
            logger.error(f"Error backfilling data for trade {trade.get('id')}: {e}")
            return False

    async def reconcile_trades_with_pnl_but_no_exit_price(self, days_back: int = 30) -> Dict[str, Any]:
        """
        Reconcile trades that have PNL but are missing exit_price.

        This calculates exit_price from PNL and entry_price (reverse calculation).
        """
        logger.info(f"Reconciling trades with PNL but no exit_price (last {days_back} days)")

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()

        try:
            response = self.supabase.from_("trades").select("*").eq("status", "CLOSED").gte("created_at", cutoff).execute()
            trades = response.data or []

            results = {
                'total_trades': len(trades),
                'fixed': 0,
                'errors': 0
            }

            for trade in trades:
                try:
                    pnl_usd = trade.get('pnl_usd') or trade.get('net_pnl')
                    exit_price = trade.get('exit_price')
                    entry_price = trade.get('entry_price')

                    # Check if PNL exists but exit_price is missing
                    if (pnl_usd and float(pnl_usd) != 0 and
                        (not exit_price or float(exit_price) == 0) and
                        entry_price):

                        exit_price_calculated = await self._calculate_exit_price_from_pnl(
                            trade, float(pnl_usd)
                        )

                        if exit_price_calculated and exit_price_calculated > 0:
                            update_data = {
                                'exit_price': str(exit_price_calculated),
                                'updated_at': datetime.now(timezone.utc).isoformat()
                            }

                            exchange_name = str(trade.get('exchange', '')).lower()
                            if exchange_name == 'binance':
                                update_data['binance_exit_price'] = str(exit_price_calculated)
                            elif exchange_name == 'kucoin':
                                update_data['exit_price'] = str(exit_price_calculated)

                            self.supabase.table("trades").update(update_data).eq("id", trade['id']).execute()
                            results['fixed'] += 1
                            logger.info(f"Calculated exit_price {exit_price_calculated} from PNL for trade {trade['id']}")

                except Exception as e:
                    logger.error(f"Error reconciling trade {trade.get('id')}: {e}")
                    results['errors'] += 1

            logger.info(f"Reconciliation completed: {results}")
            return results

        except Exception as e:
            logger.error(f"Error in reconcile_trades_with_pnl_but_no_exit_price: {e}")
            return {'error': str(e)}

    async def _calculate_exit_price_from_pnl(
        self,
        trade: Dict[str, Any],
        pnl_usd: float
    ) -> Optional[float]:
        """
        Calculate exit price from PNL and entry price (reverse calculation).

        For LONG: pnl = (exit_price - entry_price) * position_size
        For SHORT: pnl = (entry_price - exit_price) * position_size
        """
        try:
            entry_price_str = trade.get('entry_price')
            position_size_str = trade.get('position_size')

            if not entry_price_str or not position_size_str:
                return None

            entry_price = float(entry_price_str)
            position_size = float(position_size_str)

            if entry_price <= 0 or position_size <= 0:
                return None

            signal_type = str(trade.get('signal_type', 'LONG')).upper()

            if signal_type == 'LONG':
                # pnl = (exit_price - entry_price) * position_size
                # exit_price = (pnl / position_size) + entry_price
                exit_price = (pnl_usd / position_size) + entry_price
            elif signal_type == 'SHORT':
                # pnl = (entry_price - exit_price) * position_size
                # exit_price = entry_price - (pnl / position_size)
                exit_price = entry_price - (pnl_usd / position_size)
            else:
                return None

            return round(exit_price, 8)

        except Exception as e:
            logger.warning(f"Error calculating exit price from PNL: {e}")
            return None


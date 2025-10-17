#!/usr/bin/env python3
"""
KuCoin Transaction History Fetcher

This module handles fetching transaction history from KuCoin exchange
and transforming it to match the database schema.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from src.exchange.kucoin.kucoin_exchange import KucoinExchange
from src.exchange.kucoin.kucoin_symbol_converter import symbol_converter

logger = logging.getLogger(__name__)

# Comprehensive mapping of KuCoin business types to transaction history types
KUCOIN_TYPE_MAPPING = {
    # Realized PnL
    'RealisedPNL': 'REALIZED_PNL',
    'RealizedPNL': 'REALIZED_PNL',
    'PnL': 'REALIZED_PNL',

    # Trading fees and commissions
    'Trade': 'COMMISSION',
    'Trading': 'COMMISSION',
    'Commission': 'COMMISSION',
    'Fee': 'COMMISSION',

    # Funding fees
    'Funding': 'FUNDING_FEE',
    'FundingFee': 'FUNDING_FEE',
    'FundingFeeDeduction': 'FUNDING_FEE',

    # Transfers and deposits/withdrawals
    'Deposit': 'TRANSFER',
    'Withdrawal': 'TRANSFER',
    'TransferIn': 'TRANSFER',
    'TransferOut': 'TRANSFER',
    'Transfer': 'TRANSFER',
    'InternalTransfer': 'TRANSFER',

    # Bonuses and rewards
    'Bonus': 'WELCOME_BONUS',
    'WelcomeBonus': 'WELCOME_BONUS',
    'Reward': 'WELCOME_BONUS',
    'Promotion': 'WELCOME_BONUS',

    # Insurance and risk management
    'Insurance': 'INSURANCE_CLEAR',
    'InsuranceClear': 'INSURANCE_CLEAR',
    'RiskManagement': 'INSURANCE_CLEAR',
    'Liquidation': 'INSURANCE_CLEAR',

    # Other transaction types
    'Margin': 'MARGIN',
    'Lending': 'LENDING',
    'Staking': 'STAKING',
    'Vote': 'VOTE',
    'Airdrop': 'AIRDROP',
    'Dividend': 'DIVIDEND',
    'Interest': 'INTEREST',
    'Refund': 'REFUND',
    'Adjustment': 'ADJUSTMENT',
    'Settlement': 'SETTLEMENT',
    'Rebate': 'REBATE',
    'Cashback': 'CASHBACK',
    'Referral': 'REFERRAL',
    'KCS': 'KCS_BONUS',  # KuCoin Shares bonus
    'KCSBonus': 'KCS_BONUS',
    'KCSDividend': 'KCS_BONUS',
}

# Business types that should be treated as outgoing (negative amounts)
OUTGOING_BIZ_TYPES = {
    'Withdrawal', 'TransferOut', 'Commission', 'Fee', 'Trading', 'Trade',
    'FundingFeeDeduction', 'Insurance', 'Liquidation', 'Margin'
}

# Business types that should be treated as incoming (positive amounts)
INCOMING_BIZ_TYPES = {
    'Deposit', 'TransferIn', 'Bonus', 'WelcomeBonus', 'Reward', 'Promotion',
    'Airdrop', 'Dividend', 'Interest', 'Refund', 'Rebate', 'Cashback',
    'Referral', 'KCS', 'KCSBonus', 'KCSDividend', 'RealisedPNL', 'RealizedPNL'
}


class KucoinTransactionFetcher:
    """
    Fetches and transforms transaction history from KuCoin exchange.
    """

    def __init__(self, kucoin_exchange: KucoinExchange):
        """
        Initialize the KuCoin transaction fetcher.

        Args:
            kucoin_exchange: Initialized KuCoin exchange instance
        """
        self.kucoin_exchange = kucoin_exchange
        self.symbol_converter = symbol_converter

    async def fetch_transaction_history(self,
                                      symbol: str = "",
                                      start_time: int = 0,
                                      end_time: int = 0,
                                      limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Fetch comprehensive transaction history from KuCoin using all available data sources.

        Args:
            symbol: Trading pair symbol (empty for all)
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            limit: Maximum number of records

        Returns:
            List of transaction records formatted for database
        """
        try:
            logger.info(f"Fetching comprehensive KuCoin transaction history for {symbol or 'ALL SYMBOLS'}")

            # Convert symbol to KuCoin format if needed
            kucoin_symbol = ""
            if symbol:
                kucoin_symbol = self.symbol_converter.convert_bot_to_kucoin_futures(symbol)
                logger.info(f"Converted {symbol} to KuCoin format: {kucoin_symbol}")

            # Respect KuCoin 7-day window: chunk requests if needed
            window_ms = 7 * 24 * 60 * 60 * 1000
            chunks: List[Tuple[int, int]] = []
            if start_time and end_time and end_time > start_time:
                cursor = start_time
                while cursor < end_time:
                    chunk_end = min(cursor + window_ms, end_time)
                    chunks.append((cursor, chunk_end))
                    cursor = chunk_end
            else:
                # Default to last 24h if no times provided
                now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                chunks.append((now_ms - 24 * 60 * 60 * 1000, now_ms))

            # Fetch from all data sources across chunks
            all_transactions = []

            for chunk_start, chunk_end in chunks:
                logger.info(f"Processing chunk: {datetime.fromtimestamp(chunk_start/1000, tz=timezone.utc)} to {datetime.fromtimestamp(chunk_end/1000, tz=timezone.utc)}")

                # 1. Fetch account ledgers (primary source for comprehensive data)
                account_ledgers = await self._fetch_account_ledgers(kucoin_symbol, chunk_start, chunk_end, limit)

                # 2. Fetch futures account ledgers (for futures-specific activities)
                futures_ledgers = await self._fetch_futures_account_ledgers(kucoin_symbol, chunk_start, chunk_end, limit)

                # 3. Fetch trade history (for detailed trade information)
                trades = await self._fetch_trade_history(kucoin_symbol, chunk_start, chunk_end, limit)

                # 4. Fetch income/funding history
                income_records = await self._fetch_income_history(kucoin_symbol, chunk_start, chunk_end, limit)

                # Transform all data sources
                chunk_transactions = []

                # Transform account ledgers
                for ledger in account_ledgers:
                    transaction = self._transform_ledger_to_transaction(ledger, symbol)
                    if transaction:
                        chunk_transactions.append(transaction)

                # Transform futures account ledgers
                for ledger in futures_ledgers:
                    transaction = self._transform_ledger_to_transaction(ledger, symbol)
                    if transaction:
                        chunk_transactions.append(transaction)

                # Transform trades (for commission data)
                for trade in trades:
                    transaction = self._transform_trade_to_transaction(trade, symbol)
                    if transaction:
                        chunk_transactions.append(transaction)

                # Transform income records
                for income in income_records:
                    transaction = self._transform_income_to_transaction(income, symbol)
                    if transaction:
                        chunk_transactions.append(transaction)

                all_transactions.extend(chunk_transactions)

                # Rate limiting between chunks
                await asyncio.sleep(0.5)

            # Deduplicate transactions
            all_transactions = self._deduplicate_transactions(all_transactions)

            # Sort by time
            all_transactions.sort(key=lambda x: x.get('time', ''))

            logger.info(f"Fetched {len(all_transactions)} comprehensive KuCoin transactions")
            return all_transactions

        except Exception as e:
            logger.error(f"Error fetching comprehensive KuCoin transaction history: {e}")
            return []

    async def _fetch_trade_history(self, symbol: str, start_time: int, end_time: int, limit: int) -> List[Dict[str, Any]]:
        """Fetch trade history from KuCoin."""
        try:
            trades = await self.kucoin_exchange.get_user_trades(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                limit=limit
            )
            logger.info(f"Fetched {len(trades)} KuCoin trades")
            return trades
        except Exception as e:
            logger.error(f"Error fetching KuCoin trade history: {e}")
            return []

    async def _fetch_income_history(self, symbol: str, start_time: int, end_time: int, limit: int) -> List[Dict[str, Any]]:
        """Fetch income history from KuCoin."""
        try:
            income_records = await self.kucoin_exchange.get_income_history(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                limit=limit
            )
            logger.info(f"Fetched {len(income_records)} KuCoin income records")
            return income_records
        except Exception as e:
            logger.error(f"Error fetching KuCoin income history: {e}")
            return []

    async def _fetch_account_ledgers(self, symbol: str, start_time: int, end_time: int, limit: int) -> List[Dict[str, Any]]:
        """Fetch account ledgers from KuCoin."""
        try:
            # Extract currency from symbol if provided
            currency = ""
            if symbol:
                # Extract base currency from symbol (e.g., BTC from BTCUSDT)
                currency = symbol.replace('USDT', '').replace('USDC', '').replace('BTC', '').replace('ETH', '')
                if not currency:
                    currency = "USDT"  # Default to USDT if can't extract

            ledger_records = await self.kucoin_exchange.get_account_ledgers(
                currency=currency,
                start_time=start_time,
                end_time=end_time,
                limit=limit
            )
            logger.info(f"Fetched {len(ledger_records)} KuCoin account ledger records")
            return ledger_records
        except Exception as e:
            logger.error(f"Error fetching KuCoin account ledgers: {e}")
            return []

    async def _fetch_futures_account_ledgers(self, symbol: str, start_time: int, end_time: int, limit: int) -> List[Dict[str, Any]]:
        """Fetch futures account ledgers from KuCoin."""
        try:
            # Extract currency from symbol if provided
            currency = ""
            if symbol:
                # Extract base currency from symbol (e.g., BTC from BTCUSDT)
                currency = symbol.replace('USDT', '').replace('USDC', '').replace('BTC', '').replace('ETH', '')
                if not currency:
                    currency = "USDT"  # Default to USDT if can't extract

            ledger_records = await self.kucoin_exchange.get_futures_account_ledgers(
                currency=currency,
                start_time=start_time,
                end_time=end_time,
                limit=limit
            )
            logger.info(f"Fetched {len(ledger_records)} KuCoin futures account ledger records")
            return ledger_records
        except Exception as e:
            logger.error(f"Error fetching KuCoin futures account ledgers: {e}")
            return []

    def _transform_trade_to_transaction(self, trade: Dict[str, Any], original_symbol: str = "") -> Optional[Dict[str, Any]]:
        """
        Transform a KuCoin trade record to transaction history format.

        Args:
            trade: KuCoin trade record
            original_symbol: Original symbol from bot format

        Returns:
            Transaction record formatted for database
        """
        try:
            # Extract trade data
            trade_id = trade.get('id', '')
            symbol = trade.get('symbol', '')
            side = trade.get('side', '')
            trade_type = trade.get('type', '')
            size = float(trade.get('size', 0))
            price = float(trade.get('price', 0))
            fee = float(trade.get('fee', 0))
            fee_currency = trade.get('feeCurrency', 'USDT')
            time_ms = trade.get('time', 0)

            # Convert time to timestamp with timezone
            if time_ms:
                dt = datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc)
                time_timestampz = dt.isoformat()
            else:
                time_timestampz = datetime.now(timezone.utc).isoformat()

            # Convert symbol back to bot format if needed
            if original_symbol:
                symbol = original_symbol
            else:
                # Convert from KuCoin format to bot format
                symbol = self.symbol_converter.convert_kucoin_to_bot(symbol)

            # Map to COMMISSION entry (negative fee), matching existing table semantics
            transaction = {
                'time': time_timestampz,
                'type': 'COMMISSION',
                'amount': -abs(fee),
                'asset': fee_currency,
                'symbol': symbol,
                'exchange': 'kucoin',
                'raw_data': {
                    'trade_id': trade_id,
                    'side': side,
                    'trade_type': trade_type,
                    'price': price,
                    'size': size,
                    'fee': fee,
                    'fee_currency': fee_currency
                }
            }

            return transaction

        except Exception as e:
            logger.error(f"Error transforming KuCoin trade to transaction: {e}")
            return None

    def _transform_ledger_to_transaction(self, ledger: Dict[str, Any], original_symbol: str = "") -> Optional[Dict[str, Any]]:
        """
        Transform a KuCoin ledger record to transaction history format.

        Args:
            ledger: KuCoin ledger record
            original_symbol: Original symbol from bot format

        Returns:
            Transaction record formatted for database
        """
        try:
            # Extract ledger data
            ledger_id = ledger.get('id', '')
            currency = ledger.get('currency', '')
            amount = float(ledger.get('amount', 0))
            fee = float(ledger.get('fee', 0))
            balance = float(ledger.get('balance', 0))
            biz_type = ledger.get('bizType', '')
            direction = ledger.get('direction', '')
            context = ledger.get('context', '')
            time_ms = ledger.get('createdAt', 0)

            # Convert time to timestamp with timezone
            if time_ms:
                dt = datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc)
                time_timestampz = dt.isoformat()
            else:
                time_timestampz = datetime.now(timezone.utc).isoformat()

            # Map business type to transaction type
            transaction_type = KUCOIN_TYPE_MAPPING.get(biz_type, 'UNKNOWN')

            # Handle amount direction
            final_amount = amount
            if direction == 'out' and amount > 0:
                final_amount = -amount
            elif direction == 'in' and amount < 0:
                final_amount = abs(amount)

            # Extract symbol from context or use original symbol
            symbol = original_symbol
            if not symbol and context:
                # Try to extract symbol from context
                # Context might contain trading pair information
                if 'USDT' in context or 'USDC' in context:
                    # Simple extraction - this could be enhanced
                    symbol = context.split()[0] if context.split() else ''

            # Convert symbol to bot format if needed
            if symbol and not original_symbol:
                symbol = self.symbol_converter.convert_kucoin_to_bot(symbol)

            # Create transaction record
            transaction = {
                'time': time_timestampz,
                'type': transaction_type,
                'amount': final_amount,
                'asset': currency,
                'symbol': symbol or '',
                'exchange': 'kucoin',
                'raw_data': {
                    'ledger_id': ledger_id,
                    'biz_type': biz_type,
                    'direction': direction,
                    'fee': fee,
                    'balance': balance,
                    'context': context
                }
            }

            return transaction

        except Exception as e:
            logger.error(f"Error transforming KuCoin ledger to transaction: {e}")
            return None

    def _transform_income_to_transaction(self, income: Dict[str, Any], original_symbol: str = "") -> Optional[Dict[str, Any]]:
        """
        Transform a KuCoin income record to transaction history format.

        Args:
            income: KuCoin income record
            original_symbol: Original symbol from bot format

        Returns:
            Transaction record formatted for database
        """
        try:
            # Extract income data
            income_id = income.get('id', '')
            symbol = income.get('symbol', '')
            income_type = income.get('type', 'FUNDING_FEE')
            amount = float(income.get('amount', 0))
            currency = income.get('currency', 'USDT')
            time_ms = income.get('time', 0)

            # Convert time to timestamp with timezone
            if time_ms:
                dt = datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc)
                time_timestampz = dt.isoformat()
            else:
                time_timestampz = datetime.now(timezone.utc).isoformat()

            # Convert symbol back to bot format if needed
            if original_symbol:
                symbol = original_symbol
            else:
                # Convert from KuCoin format to bot format
                symbol = self.symbol_converter.convert_kucoin_to_bot(symbol)

            # Create transaction record
            transaction = {
                'time': time_timestampz,
                'type': income_type,
                'amount': amount,
                'asset': currency,
                'symbol': symbol,
                'exchange': 'kucoin',
                'raw_data': {
                    'income_id': income_id,
                    'original_type': income_type
                }
            }

            return transaction

        except Exception as e:
            logger.error(f"Error transforming KuCoin income to transaction: {e}")
            return None

    async def get_last_transaction_time(self, symbol: str = "") -> int:
        """
        Get the timestamp of the last transaction for a symbol.

        Args:
            symbol: Trading pair symbol (empty for all)

        Returns:
            Timestamp in milliseconds of the last transaction
        """
        try:
            # Get recent transactions (last 24 hours)
            end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
            start_time = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp() * 1000)

            transactions = await self.fetch_transaction_history(
                symbol=symbol,
                start_time=start_time,
                end_time=end_time,
                limit=1
            )

            if transactions:
                # Get the most recent transaction time
                last_transaction = max(transactions, key=lambda x: x.get('time', ''))
                time_str = last_transaction.get('time', '')
                if time_str:
                    dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                    return int(dt.timestamp() * 1000)

            return 0

        except Exception as e:
            logger.error(f"Error getting last KuCoin transaction time: {e}")
            return 0

    def get_supported_symbols(self) -> List[str]:
        """
        Get list of symbols supported by KuCoin.

        Returns:
            List of supported symbols in bot format
        """
        try:
            # This would ideally fetch from KuCoin API, but for now return common symbols
            common_symbols = [
                "BTCUSDT", "ETHUSDT", "SOLUSDT", "ASTERUSDT", "XPLUSDT",
                "ADAUSDT", "DOTUSDT", "LINKUSDT", "UNIUSDT", "AVAXUSDT"
            ]
            return common_symbols
        except Exception as e:
            logger.error(f"Error getting supported KuCoin symbols: {e}")
            return []

    def _deduplicate_transactions(self, transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove duplicate transactions based on time, type, amount, and symbol.

        Args:
            transactions: List of transaction records

        Returns:
            Deduplicated list of transactions
        """
        try:
            seen = set()
            deduplicated = []

            for transaction in transactions:
                # Create a unique key for deduplication
                time_str = transaction.get('time', '')
                transaction_type = transaction.get('type', '')
                amount = transaction.get('amount', 0)
                symbol = transaction.get('symbol', '')
                asset = transaction.get('asset', '')

                # Create unique identifier
                unique_key = f"{time_str}_{transaction_type}_{amount}_{symbol}_{asset}"

                if unique_key not in seen:
                    seen.add(unique_key)
                    deduplicated.append(transaction)
                else:
                    logger.debug(f"Duplicate transaction found and removed: {unique_key}")

            logger.info(f"Deduplication: {len(transactions)} -> {len(deduplicated)} transactions")
            return deduplicated

        except Exception as e:
            logger.error(f"Error during transaction deduplication: {e}")
            return transactions

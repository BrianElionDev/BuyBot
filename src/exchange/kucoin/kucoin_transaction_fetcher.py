#!/usr/bin/env python3
"""
KuCoin Transaction History Fetcher

This module handles fetching transaction history from KuCoin exchange
and transforming it to match the database schema.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from src.exchange.kucoin.kucoin_exchange import KucoinExchange
from src.exchange.kucoin.kucoin_symbol_converter import symbol_converter

logger = logging.getLogger(__name__)


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
        Fetch transaction history from KuCoin.

        Args:
            symbol: Trading pair symbol (empty for all)
            start_time: Start time in milliseconds
            end_time: End time in milliseconds
            limit: Maximum number of records

        Returns:
            List of transaction records formatted for database
        """
        try:
            logger.info(f"Fetching KuCoin transaction history for {symbol or 'ALL SYMBOLS'}")

            # Convert symbol to KuCoin format if needed
            kucoin_symbol = ""
            if symbol:
                kucoin_symbol = self.symbol_converter.convert_bot_to_kucoin_futures(symbol)
                logger.info(f"Converted {symbol} to KuCoin format: {kucoin_symbol}")

            # Fetch both trade history and income history
            trades = await self._fetch_trade_history(kucoin_symbol, start_time, end_time, limit)
            income_records = await self._fetch_income_history(kucoin_symbol, start_time, end_time, limit)

            # Transform and combine all records
            all_transactions = []

            # Transform trades
            for trade in trades:
                transaction = self._transform_trade_to_transaction(trade, symbol)
                if transaction:
                    all_transactions.append(transaction)

            # Transform income records
            for income in income_records:
                transaction = self._transform_income_to_transaction(income, symbol)
                if transaction:
                    all_transactions.append(transaction)

            # Sort by time
            all_transactions.sort(key=lambda x: x.get('time', 0))

            logger.info(f"Fetched {len(all_transactions)} KuCoin transactions")
            return all_transactions

        except Exception as e:
            logger.error(f"Error fetching KuCoin transaction history: {e}")
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

            # Determine transaction type based on trade side
            transaction_type = f"TRADE_{side.upper()}"

            # Create transaction record
            transaction = {
                'time': time_timestampz,
                'type': transaction_type,
                'amount': size,  # Trade size
                'asset': fee_currency,  # Use fee currency as asset
                'symbol': symbol,
                'exchange': 'kucoin',
                'raw_data': {
                    'trade_id': trade_id,
                    'side': side,
                    'trade_type': trade_type,
                    'price': price,
                    'fee': fee,
                    'fee_currency': fee_currency
                }
            }

            return transaction

        except Exception as e:
            logger.error(f"Error transforming KuCoin trade to transaction: {e}")
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

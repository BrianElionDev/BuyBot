import asyncio
from datetime import datetime, timezone
from datetime import datetime, timezone
from datetime import datetime, timezone
import logging
import re
import time
from typing import Dict, Any, Optional, Union, List, Tuple
import os
from dotenv import load_dotenv
import uuid
import json

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config.logging_config import get_trade_logger

from src.bot.order_management.order_creator import FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET
from src.bot.trading_engine import TradingEngine
from src.bot.kucoin_trading_engine import KucoinTradingEngine
from src.bot.signal_router import SignalRouter
from discord_bot.signal_processing import DiscordSignalParser
from discord_bot.signal_processing.signal_parser import client
from discord_bot.models import InitialDiscordSignal, DiscordUpdateSignal
from discord_bot.database import DatabaseManager
from config import settings as config
from supabase import create_client, Client
from src.services.pricing.price_service import PriceService
from src.exchange import BinanceExchange, KucoinExchange
from discord_bot.websocket import DiscordBotWebSocketManager
from config import settings
from src.services.notifications.notification_manager import NotificationManager


# Setup logging
logger = get_trade_logger()

class DiscordBot:
    def __init__(self):
        # Load environment variables
        load_dotenv()

        # --- Binance API Initialization ---
        api_key = settings.BINANCE_API_KEY
        api_secret = settings.BINANCE_API_SECRET
        is_testnet = settings.BINANCE_TESTNET
        if not api_key or not api_secret:
            logger.critical("Binance API key/secret not set. Cannot start Trading Engine.")
            raise ValueError("Binance API key/secret not set.")

        # --- Supabase Initialization ---
        supabase_url = settings.SUPABASE_URL
        supabase_key = settings.SUPABASE_KEY
        if not supabase_url or not supabase_key:
            logger.critical("Supabase URL or Key not set. Cannot connect to the database.")
            raise ValueError("Supabase URL or Key not set.")

        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.db_manager = DatabaseManager(self.supabase)

        # --- Component Initialization ---
        self.binance_exchange = BinanceExchange(api_key, api_secret, is_testnet)

        # Initialize KuCoin exchange
        kucoin_api_key = settings.KUCOIN_API_KEY
        kucoin_api_secret = settings.KUCOIN_API_SECRET
        kucoin_api_passphrase = settings.KUCOIN_API_PASSPHRASE
        kucoin_is_testnet = settings.KUCOIN_TESTNET

        if kucoin_api_key and kucoin_api_secret and kucoin_api_passphrase:
            self.kucoin_exchange = KucoinExchange(
                api_key=kucoin_api_key,
                api_secret=kucoin_api_secret,
                api_passphrase=kucoin_api_passphrase,
                is_testnet=kucoin_is_testnet
            )
            logger.info("KuCoin exchange initialized")
        else:
            self.kucoin_exchange = None
            logger.warning("KuCoin credentials not provided, KuCoin trading disabled")

        # Initialize price service with both exchanges
        self.price_service = PriceService(
            binance_exchange=self.binance_exchange,
            kucoin_exchange=self.kucoin_exchange
        )

        # Initialize trading engines
        self.trading_engine = TradingEngine(
            price_service=self.price_service,
            exchange=self.binance_exchange,
            db_manager=self.db_manager
        )

        if self.kucoin_exchange:
            self.kucoin_trading_engine = KucoinTradingEngine(
                price_service=self.price_service,
                kucoin_exchange=self.kucoin_exchange,
                db_manager=self.db_manager
            )
            logger.info("KuCoin trading engine initialized")
        else:
            self.kucoin_trading_engine = None

        # Initialize signal router for trader-based exchange routing
        self.signal_router = SignalRouter(
            binance_trading_engine=self.trading_engine,
            kucoin_trading_engine=self.kucoin_trading_engine
        )

        self.signal_parser = DiscordSignalParser()

        self.notification_manager = NotificationManager()

        # Initialize WebSocket manager for real-time database sync
        self.websocket_manager = DiscordBotWebSocketManager(self, self.db_manager)

        logger.info(f"DiscordBot initialized with {'AI' if client else 'simple'} Signal Parser.")

    def _clean_text_for_llm(self, text: str) -> str:
        """Delegate to signal processor for text cleaning."""
        from discord_bot.signal_processing import SignalValidator
        validator = SignalValidator()
        return validator.sanitize_signal_content(text)

    def _parse_parsed_signal(self, parsed_signal_data) -> Dict[str, Any]:
        """Delegate to signal processor for parsing."""
        from discord_bot.signal_processing import SignalProcessor
        processor = SignalProcessor()
        return processor.parse_parsed_signal(parsed_signal_data)

    def parse_alert_content(self, content, trade_row=None):
        """Delegate to signal processor for alert content parsing."""
        from discord_bot.signal_processing import SignalProcessor
        processor = SignalProcessor()
        alert_action = processor.process_alert_content(content, trade_row)
        return alert_action.to_dict()

    def _generate_alert_hash(self, discord_id: str, content: str) -> str:
        """Generate a hash for alert deduplication."""
        return self.db_manager.generate_alert_hash(discord_id, content)

    async def _is_duplicate_alert(self, alert_hash: str) -> bool:
        """Check if an alert hash already exists in the database."""
        return await self.db_manager.check_duplicate_alert(alert_hash)

    async def _store_alert_hash(self, alert_hash: str) -> bool:
        """Store an alert hash to prevent duplicate processing."""
        return await self.db_manager.store_alert_hash(alert_hash)



    async def process_initial_signal(self, signal: InitialDiscordSignal) -> Dict[str, Any]:
        """Process an initial Discord signal."""
        try:
            logger.info(f"Processing initial signal from {signal.trader} (discord_id: {signal.discord_id})")

            if not await self.signal_router.is_trader_supported(signal.trader or ""):
                logger.error(f"❌ UNSUPPORTED TRADER REJECTED: {signal.trader}")
                return {
                    "status": "rejected",
                    "message": f"Trader {signal.trader} is not supported. Please check trader configuration in database.",
                    "exchange": "none"
                }

            # Determine target exchange for this trader (e.g., '@-Tareeq' -> 'kucoin')
            exchange_type = await self.signal_router.get_exchange_for_trader(signal.trader or "")

            # Validate required fields
            if not signal.discord_id or not signal.trader or not signal.content:
                logger.error(f"Missing required fields in signal: discord_id={signal.discord_id}, trader={signal.trader}, content_length={len(signal.content) if signal.content else 0}")
                return {"status": "error", "message": "Missing required fields in signal"}

            trade_row = await self.db_manager.find_trade_by_discord_id(signal.discord_id)
            if not trade_row:
                logger.info(f"No trade found for discord_id {signal.discord_id}, creating new trade record")

                # Create a new trade record
                trade_data = {
                    'discord_id': signal.discord_id,
                    'trader': signal.trader,
                    'timestamp': signal.timestamp,
                    'content': signal.content,
                    'status': 'PENDING',
                    'exchange': exchange_type.value,
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }

                trade_row = await self.db_manager.save_signal_to_db(trade_data)
                if not trade_row:
                    logger.error(f"Failed to create trade record for discord_id {signal.discord_id}")
                    return {"status": "error", "message": "Failed to create trade record"}

                logger.info(f"Created new trade for discord_id {signal.discord_id}: ID {trade_row['id']}")
            else:
                logger.info(f"Found existing trade for discord_id {signal.discord_id}: ID {trade_row['id']}")

            # Parse signal with AI
            try:
                parsed_signal = await self.signal_parser.parse_new_trade_signal(signal.structured)
                if not parsed_signal or not parsed_signal.get('coin_symbol'):
                    logger.error(f"Failed to parse signal or extract coin_symbol for trade {trade_row['id']}")
                    # Update trade with error status using existing columns
                    await self.db_manager.update_existing_trade(trade_id=trade_row['id'], updates={
                        'status': 'FAILED',
                        'sync_error_count': 1,
                        'exchange_response': ['Processing issue:Failed to parse signal or extract coin symbol'],
                        'manual_verification_needed': True
                    })
                    return {"status": "error", "message": "Failed to parse signal or extract coin symbol"}

                logger.info(f"Successfully parsed signal for trade {trade_row['id']}: {parsed_signal['coin_symbol']}")

                # Update trade with parsed signal data
                trade_updates = {
                    'parsed_signal': json.dumps(parsed_signal) if isinstance(parsed_signal, dict) else str(parsed_signal),
                    'coin_symbol': parsed_signal['coin_symbol'],
                    'signal_type': parsed_signal.get('position_type'),  # Use position_type as signal_type
                    'position_size': parsed_signal.get('position_size'),
                    'entry_price': parsed_signal.get('entry_prices', [None])[0] if parsed_signal.get('entry_prices') else None,
                    # Ensure exchange column reflects routed exchange on first update
                    'exchange': exchange_type.value
                }

                await self.db_manager.update_existing_trade(trade_id=trade_row['id'], updates=trade_updates)
                logger.info(f"Updated trade {trade_row['id']} with parsed signal data")

                # Execute the trade on Binance
                try:
                    logger.info(f"Executing trade on Binance for {parsed_signal['coin_symbol']}")

                    # Extract parameters for trading engine
                    coin_symbol = parsed_signal['coin_symbol']
                    position_type = parsed_signal.get('position_type', 'LONG')
                    order_type = parsed_signal.get('order_type', 'MARKET')
                    entry_prices = parsed_signal.get('entry_prices', [])
                    stop_loss = parsed_signal.get('stop_loss')
                    take_profits = parsed_signal.get('take_profits')

                    # Use first entry price as signal price
                    signal_price = entry_prices[0] if entry_prices else None
                    if not signal_price:
                        logger.error(f"No entry price found for trade {trade_row['id']}")
                        return {"status": "error", "message": "No entry price found"}

                    # Route the trade to the appropriate exchange based on trader
                    success, exchange_response = await self.signal_router.route_initial_signal(
                        coin_symbol=coin_symbol,
                        signal_price=signal_price,
                        position_type=position_type,
                        trader=signal.trader,
                        order_type=order_type,
                        stop_loss=stop_loss,
                        take_profits=take_profits,
                        entry_prices=entry_prices,
                        client_order_id=signal.discord_id,
                        discord_id=signal.discord_id
                    )

                    if success:
                        logger.info(f"✅ Trade executed successfully on {exchange_type.value} for {coin_symbol}")

                        # Update trade with exchange response
                        if isinstance(exchange_response, dict):
                            await self.db_manager.update_trade_with_original_response(
                                trade_id=trade_row['id'],
                                original_response=exchange_response
                            )

                            try:
                                order_id = str(exchange_response.get('orderId') or exchange_response.get('order_id') or '')
                                raw_avg = exchange_response.get('avgPrice') or exchange_response.get('price')
                                entry_price_val = float(raw_avg) if raw_avg else float(signal_price)
                                raw_qty = exchange_response.get('executedQty') or exchange_response.get('origQty') or trade_updates.get('position_size')
                                quantity_val = float(raw_qty) if raw_qty else 0.0
                                await self.notification_manager.send_trade_execution_notification(
                                    coin_symbol,
                                    position_type,
                                    entry_price_val,
                                    quantity_val,
                                    order_id,
                                    status='SUCCESS',
                                    exchange=exchange_type.value,
                                    error_message=None
                                )
                            except Exception as e:
                                logger.error(f"Failed to send standardized execution notification: {e}")
                        else:
                            # If exchange_response is a string (error message), store it generically
                            await self.db_manager.update_existing_trade(trade_id=trade_row['id'], updates={
                                'exchange_response': str(exchange_response)
                            })

                        return {
                            "status": "success",
                            "message": "Trade processed and executed successfully",
                            "trade_id": trade_row['id'],
                            "exchange_response": exchange_response
                        }
                    else:
                        logger.error(f"❌ Trade execution failed for {coin_symbol}: {exchange_response}")

                        # Update trade with error using existing columns
                        # Update database with failure status
                        db_update_success = await self.db_manager.update_existing_trade(trade_id=trade_row['id'], updates={
                            'status': 'FAILED',
                            'order_status': 'FAILED',
                            'sync_error_count': 1,
                            'exchange_response': [f'Trade execution failed: {exchange_response}'],
                            'manual_verification_needed': True
                        })

                        if not db_update_success:
                            logger.error(f"❌ CRITICAL: Failed to update database for trade {trade_row['id']} - status validation or database error")
                            # Try alternative update method
                            try:
                                await self.db_manager.update_trade_failure(
                                    trade_id=trade_row['id'],
                                    error_message=f"Trade execution failed: {exchange_response}",
                                    exchange_response=str(exchange_response)
                                )
                                logger.info(f"✅ Successfully updated trade {trade_row['id']} using alternative method")
                            except Exception as alt_error:
                                logger.error(f"❌ CRITICAL: Alternative database update also failed for trade {trade_row['id']}: {alt_error}")
                        else:
                            logger.info(f"✅ Successfully updated trade {trade_row['id']} with failure status")

                        try:
                            # Extract proper error message from exchange response
                            error_message = None
                            if isinstance(exchange_response, dict):
                                error_message = exchange_response.get('error', exchange_response.get('message', str(exchange_response)))
                            elif isinstance(exchange_response, str):
                                error_message = exchange_response
                            else:
                                error_message = str(exchange_response)

                            await self.notification_manager.send_trade_execution_notification(
                                coin_symbol,
                                position_type,
                                float(signal_price),
                                float(parsed_signal.get('position_size') or 0.0),
                                order_id=str((exchange_response.get('orderId') if isinstance(exchange_response, dict) else '') or ''),
                                status='FAILURE',
                                exchange=exchange_type.value,
                                error_message=error_message
                            )
                        except Exception as e:
                            logger.error(f"Failed to send standardized failure notification: {e}")

                        exchange_type = await self.signal_router.get_exchange_for_trader(signal.trader)

                        return {
                            "status": "error",
                            "message": f"Trade execution failed on {exchange_type.value}: {exchange_response}",
                            "trade_id": trade_row['id'],
                            "exchange": exchange_type.value
                        }

                except Exception as exec_error:
                    logger.error(f"Error executing trade for {parsed_signal['coin_symbol']}: {exec_error}")

                    # Update database with failure status
                    db_update_success = await self.db_manager.update_existing_trade(trade_id=trade_row['id'], updates={
                        'status': 'FAILED',
                        'order_status': 'FAILED',
                        'sync_error_count': 1,
                        'exchange_response': [f'Execution error: {str(exec_error)}'],
                        'manual_verification_needed': True
                    })

                    if not db_update_success:
                        logger.error(f"❌ CRITICAL: Failed to update database for trade {trade_row['id']} - status validation or database error")
                        # Try alternative update method
                        try:
                            await self.db_manager.update_trade_failure(
                                trade_id=trade_row['id'],
                                error_message=f"Execution error: {str(exec_error)}",
                                exchange_response=str(exec_error)
                            )
                            logger.info(f"✅ Successfully updated trade {trade_row['id']} using alternative method")
                        except Exception as alt_error:
                            logger.error(f"❌ CRITICAL: Alternative database update also failed for trade {trade_row['id']}: {alt_error}")
                    else:
                        logger.info(f"✅ Successfully updated trade {trade_row['id']} with failure status")

                    return {
                        "status": "error",
                        "message": f"Execution error: {str(exec_error)}",
                        "trade_id": trade_row['id']
                    }

            except Exception as parse_error:
                logger.error(f"Error parsing signal for trade {trade_row['id']}: {parse_error}")
                # Update trade with error status
                await self.db_manager.update_existing_trade(trade_id=trade_row['id'], updates={
                    'status': 'FAILED',
                    'error_message': f'Parse error: {str(parse_error)}'
                })
                return {"status": "error", "message": f"Parse error: {str(parse_error)}"}

        except Exception as e:
            logger.error(f"Error processing initial signal: {e}")
            return {"status": "error", "message": str(e)}

    def _validate_required_fields(self, updates: Dict[str, Any], trade_id: int) -> None:
        """
        CRITICAL: Validate that all required fields are populated to prevent fraud.
        """
        try:
            required_fields = {
                'entry_price': 'Entry price from signal',
                'coin_symbol': 'Coin symbol for trade identification',
                'signal_type': 'Position type (LONG/SHORT) for PnL calculation'
            }

            missing_fields = []

            for field, description in required_fields.items():
                if field not in updates or not updates[field]:
                    missing_fields.append(f"{field}: {description}")

            if missing_fields:
                logger.error(f"CRITICAL: Trade {trade_id} missing required fields: {missing_fields}")
                logger.critical(f"FRAUD RISK: Trade {trade_id} has missing critical fields")

                # Add validation issues to updates
                if 'sync_issues' not in updates:
                    updates['sync_issues'] = []
                updates['sync_issues'].extend(missing_fields)
                updates['manual_verification_needed'] = True
            else:
                logger.info(f"✅ Trade {trade_id} has all required fields populated")

        except Exception as e:
            logger.error(f"Error validating required fields for trade {trade_id}: {e}")

    async def process_update_signal(self, signal_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Process follow-up signal (stop loss hit, position closed, etc.)
        Routes the signal to the appropriate exchange based on trader.
        """
        try:
            signal = DiscordUpdateSignal(**signal_data)
            logger.info(f"Processing update signal from trader {signal.trader}: {signal.content}")

            # Validate trader and determine exchange
            if not await self.signal_router.is_trader_supported(signal.trader or ""):
                logger.error(f"❌ UNSUPPORTED TRADER REJECTED: {signal.trader}")
                return {
                    "status": "rejected",
                    "message": f"Trader {signal.trader} is not supported. Please check trader configuration in database.",
                    "exchange": "none"
                }

            exchange_type = await self.signal_router.get_exchange_for_trader(signal.trader or "")
            logger.info(f"✅ Routing follow-up signal from {signal.trader} to {exchange_type.value} exchange")

            # Check for duplicate alerts
            alert_hash = self._generate_alert_hash(signal.discord_id, signal.content)
            if await self._is_duplicate_alert(alert_hash):
                logger.warning(f"Duplicate alert detected: {signal.content}")
                return {"status": "skipped", "message": "Duplicate alert"}

            alert_result = None
            try:
                existing_alert = self.db_manager.supabase.table("alerts").select("id").eq("discord_id", signal.discord_id).limit(1).execute()
                if existing_alert.data:
                    alert_result = existing_alert.data[0]
                    logger.info(f"Found existing alert in database: {alert_result['id']}")
                else:
                    logger.warning(f"No existing alert found for discord_id: {signal.discord_id}")
            except Exception as e:
                logger.error(f"Error finding existing alert: {e}")

            # Route the follow-up signal to the appropriate exchange
            result = await self.signal_router.route_followup_signal(signal_data, signal.trader or "")

            # Add exchange information to result
            if 'exchange' not in result:
                result['exchange'] = exchange_type.value

            if alert_result:
                try:
                    updates = {
                        'status': 'PROCESSED' if result.get("status") == "success" else 'FAILED',
                        'parsed_alert': result.get('parsed_alert'),
                        'exchange_response': result.get('exchange_response')
                                           or result.get('binance_response')
                                           or result.get('kucoin_response'),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }
                    updates['exchange'] = exchange_type.value
                    await self.db_manager.alert_ops.update_existing_alert(alert_result['id'], updates)
                    logger.info(f"Updated alert {alert_result['id']} with processing result")
                except Exception as e:
                    logger.error(f"Error updating alert with result: {e}")

            if result.get("status") == "success":
                logger.info(f"✅ Follow-up signal processed successfully on {exchange_type.value}")
                return result
            else:
                logger.error(f"❌ Follow-up signal processing failed on {exchange_type.value}: {result.get('message')}")
                return result

        except Exception as e:
            logger.error(f"Error processing update signal: {e}")
            return {"status": "error", "message": str(e)}

    def _calculate_pnl(self, position_type: str, entry_price: float, exit_price: float, position_size: float) -> float:
        """Calculate PnL in USD for a position, considering LONG or SHORT."""
        if entry_price <= 0 or exit_price <= 0 or position_size <= 0:
            return 0.0

        if position_type.upper() == 'LONG':
            pnl = (exit_price - entry_price) * position_size
        elif position_type.upper() == 'SHORT':
            pnl = (entry_price - exit_price) * position_size
        else:
            pnl = 0.0

        return pnl

    async def update_trade_position_size(self, trade_id: int, new_position_size: float) -> bool:
        """Update the position_size field in a trade record."""
        try:
            updates = {"position_size": float(new_position_size)}
            success = await self.db_manager.update_existing_trade(trade_id=trade_id, updates=updates)
            if success:
                logger.info(f"Updated position_size for trade {trade_id} to {new_position_size}")
            return success
        except Exception as e:
            logger.error(f"Failed to update position_size for trade {trade_id}: {e}")
            return False

    async def update_trade_coin_symbol(self, trade_id: int, new_coin_symbol: str) -> bool:
        """Update the coin_symbol field in a trade record."""
        try:
            updates = {"coin_symbol": new_coin_symbol}
            success = await self.db_manager.update_existing_trade(trade_id=trade_id, updates=updates)
            if success:
                logger.info(f"Updated coin_symbol for trade {trade_id} to {new_coin_symbol}")
            return success
        except Exception as e:
            logger.error(f"Failed to update coin_symbol for trade {trade_id}: {e}")
            return False

    async def close(self):
        """Gracefully shutdown the trading engine and WebSocket manager."""
        try:
            if hasattr(self, 'websocket_manager') and self.websocket_manager:
                await self.websocket_manager.stop()
            logger.info("DiscordBot closed successfully")
        except Exception as e:
            logger.error(f"Error closing DiscordBot: {e}")

    async def start_websocket_sync(self):
        """Start WebSocket real-time database synchronization."""
        try:
            if hasattr(self, 'websocket_manager') and self.websocket_manager:
                success = await self.websocket_manager.start()
                if success:
                    logger.info("WebSocket real-time sync started successfully")
                    return True
                else:
                    logger.error("Failed to start WebSocket sync")
                    return False
            else:
                logger.warning("WebSocket manager not available")
        except Exception as e:
            logger.error(f"Error starting WebSocket sync: {e}")

    def get_websocket_status(self) -> dict:
        """Get WebSocket manager status."""
        if hasattr(self, 'websocket_manager'):
            return self.websocket_manager.get_status()
        return {"status": "not_available"}

    async def _execute_single_action(self, action: Dict[str, Any], trade_row: Dict[str, Any], signal) -> Tuple[bool, Any]:
        """
        Execute a single action from the parsed alert content.
        """
        try:
            action_type = action.get('action_type')
            logger.info(f"Executing action: {action_type}")

            if action_type == "stop_loss_hit" or action_type == "position_closed":
                logger.info(f"Processing '{action_type}' for trade {trade_row['id']}. Closing position.")
                success, response = await self.trading_engine.close_position_at_market(trade_row, reason=action_type)
                return success, response

            elif action_type == "take_profit_1":
                logger.info(f"Processing TP1 for trade {trade_row['id']}. Closing 50% of position.")
                success, response = await self.trading_engine.close_position_at_market(trade_row, reason="take_profit_1", close_percentage=50.0)
                return success, response

            elif action_type == "stop_loss_update":
                stop_loss = action.get('stop_loss')
                if stop_loss and stop_loss != "BE":
                    return await self.trading_engine.update_stop_loss(trade_row, float(stop_loss))
                else:
                    # Handle break-even stop loss - calculate the break-even price first
                    try:
                        coin_symbol = self._parse_parsed_signal(trade_row.get('parsed_signal')).get('coin_symbol')
                        if coin_symbol:
                            trading_pair = f"{coin_symbol}USDT"
                            positions = await self.binance_exchange.get_futures_position_information()

                            # Find the specific position
                            position = None
                            for pos in positions:
                                if pos['symbol'] == trading_pair and float(pos['positionAmt']) != 0:
                                    position = pos
                                    break

                            if position:
                                # Use the entry price from Binance position data as break-even
                                entry_price = float(position['entryPrice'])
                                be_price = round(entry_price, 2)
                                return await self.trading_engine.update_stop_loss(trade_row, be_price)
                            else:
                                # Fallback to database entry price
                                original_entry_price = trade_row.get('entry_price')
                                if original_entry_price:
                                    be_price = round(float(original_entry_price), 2)
                                    return await self.trading_engine.update_stop_loss(trade_row, be_price)
                    except Exception as e:
                        logger.error(f"Error calculating break-even price: {e}")

                    return False, {"error": "Could not calculate break-even price"}
            elif action_type == "limit_order_filled":
                # Order already filled, just log and return success
                logger.info(f"Limit order already filled for trade {trade_row.get('id')}")
                return True, {"message": "Limit order already filled"}
            elif action_type == "unknown_update":
                # Log unknown updates but don't fail - they might be informational
                logger.info(f"Unknown update type for trade {trade_row.get('id')}: {action.get('reason', 'No reason provided')}")
                return True, {"message": "Unknown update type - informational only"}
            elif action_type == "flagged_for_review":
                # Log flagged alerts for manual review
                logger.error(f"Alert flagged for manual review for trade {trade_row.get('id')}: {action.get('reason', 'No reason provided')}")
                return True, {"message": "Alert flagged for manual review"}
            elif action_type == "invalid_price":
                # Log invalid price alerts
                logger.error(f"Invalid price in alert for trade {trade_row.get('id')}: {action.get('reason', 'No reason provided')}")
                return False, {"error": "Invalid price in alert"}
            elif action_type == "liquidation":
                # Handle liquidation events
                logger.warning(f"Position liquidated for trade {trade_row.get('id')}")
                return True, {"message": "Position liquidated"}
            elif action_type == "partial_fill":
                # Handle partial fills
                logger.info(f"Partial fill for trade {trade_row.get('id')}")
                return True, {"message": "Partial fill processed"}
            elif action_type == "update_leverage":
                # Handle leverage updates
                leverage = action.get('leverage')
                logger.info(f"Updating leverage to {leverage}x for trade {trade_row.get('id')}")
                return True, {"message": f"Leverage updated to {leverage}x"}
            elif action_type == "trailing_stop_loss":
                # Handle trailing stop loss
                trailing_percentage = action.get('trailing_percentage')
                logger.info(f"Setting trailing stop loss at {trailing_percentage}% for trade {trade_row.get('id')}")
                return True, {"message": f"Trailing stop loss set at {trailing_percentage}%"}
            elif action_type == "adjust_position_size":
                # Handle position size adjustments
                multiplier = action.get('position_multiplier')
                logger.info(f"Adjusting position size with multiplier {multiplier} for trade {trade_row.get('id')}")
                return True, {"message": f"Position size adjusted with multiplier {multiplier}"}
            else:
                logger.warning(f"Unknown action type: {action_type}")
                return False, f"Unknown action type: {action_type}"

        except Exception as e:
            logger.error(f"Error executing action {action.get('action_type', 'unknown')}: {e}")
            return False, {"error": str(e)}

# Global bot instance
discord_bot = DiscordBot()

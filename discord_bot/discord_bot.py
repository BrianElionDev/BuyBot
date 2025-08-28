import asyncio
import logging
import re
import time
from typing import Dict, Any, Optional, Union, List, Tuple
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
import uuid
import json

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.bot.trading_engine import TradingEngine
from discord_bot.discord_signal_parser import DiscordSignalParser, client
from discord_bot.models import InitialDiscordSignal, DiscordUpdateSignal
from discord_bot.database_original import DatabaseManager
from config import settings as config
from supabase import create_client, Client
from src.services.price_service import PriceService
from src.exchange.binance_exchange import BinanceExchange
from discord_bot.websocket_manager import DiscordBotWebSocketManager
from config import settings

# Setup logging
logger = logging.getLogger(__name__)

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
        self.price_service = PriceService()
        self.binance_exchange = BinanceExchange(api_key, api_secret, is_testnet)
        self.trading_engine = TradingEngine(
            price_service=self.price_service,
            binance_exchange=self.binance_exchange,
            db_manager=self.db_manager
        )
        self.signal_parser = DiscordSignalParser()

        # Initialize Telegram notification service
        from src.services.telegram_notification_service import TelegramNotificationService
        self.telegram_notifications = TelegramNotificationService()

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
                }

    def _generate_alert_hash(self, discord_id: str, content: str) -> str:
        """
        Generate a hash for alert deduplication.
        """
        import hashlib
        return hashlib.sha256(f"{discord_id}:{content}".encode()).hexdigest()

    async def _is_duplicate_alert(self, alert_hash: str) -> bool:
        """
        Check if an alert hash already exists in the database.
        """
        try:
            # Check if this alert hash has been processed recently (last 24 hours)
            # This is a simple implementation - you might want to store this in a separate table
            # For now, we'll use the alerts table with a hash field
            response = await self.db_manager.supabase.table("alerts").select("id").eq("alert_hash", alert_hash).execute()
            return len(response.data) > 0
        except Exception as e:
            # If the alert_hash column doesn't exist, skip duplicate checking
            if "column alerts.alert_hash does not exist" in str(e):
                logger.warning("alert_hash column not found in alerts table, skipping duplicate check")
                return False
            logger.error(f"Error checking for duplicate alert: {e}")
            return False

    async def _store_alert_hash(self, alert_hash: str) -> bool:
        """
        Store an alert hash to prevent duplicate processing.
        """
        try:
            # Store the hash in the alerts table
            await self.db_manager.supabase.table("alerts").insert({"alert_hash": alert_hash}).execute()
            return True
        except Exception as e:
            # If the alert_hash column doesn't exist, skip storing
            if "column alerts.alert_hash does not exist" in str(e):
                logger.warning("alert_hash column not found in alerts table, skipping hash storage")
                return True  # Return True to not block processing
            logger.error(f"Error storing alert hash: {e}")
            return False

    def _extract_coin_symbol_from_content(self, content: str) -> str:
        """Delegate to signal processor for coin symbol extraction."""
        from discord_bot.signal_processing import SignalProcessor
        processor = SignalProcessor()
        coin_symbol = processor.get_coin_symbol(content)
        return coin_symbol or "UNKNOWN"

    async def process_initial_signal(self, signal: InitialDiscordSignal) -> Dict[str, Any]:
        """Process an initial Discord signal."""
        try:
            logger.info(f"Processing initial signal from {signal.trader} (discord_id: {signal.discord_id})")

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
                        'sync_issues': ['Failed to parse signal or extract coin symbol'],
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
                    'entry_price': parsed_signal.get('entry_prices', [None])[0] if parsed_signal.get('entry_prices') else None
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

                    # Execute the trade
                    success, binance_response = await self.trading_engine.process_signal(
                        coin_symbol=coin_symbol,
                        signal_price=signal_price,
                        position_type=position_type,
                        order_type=order_type,
                        stop_loss=stop_loss,
                        take_profits=take_profits,
                        entry_prices=entry_prices,
                        client_order_id=signal.discord_id
                    )

                    if success:
                        logger.info(f"✅ Trade executed successfully on Binance for {coin_symbol}")

                        # Update trade with Binance response
                        if isinstance(binance_response, dict):
                            await self.db_manager.update_trade_with_original_response(
                                trade_id=trade_row['id'],
                                original_response=binance_response
                            )

                            # Send Telegram notification for successful trade
                            try:
                                await self.telegram_notifications.send_trade_execution_notification(
                                    coin_symbol=coin_symbol,
                                    position_type=position_type,
                                    entry_price=signal_price,
                                    quantity=float(binance_response.get('origQty', 0)),
                                    order_id=str(binance_response.get('orderId', '')),
                                    status="SUCCESS"
                                )
                            except Exception as e:
                                logger.error(f"Failed to send Telegram notification: {e}")
                        else:
                            # If binance_response is a string (error message), store it differently
                            await self.db_manager.update_existing_trade(trade_id=trade_row['id'], updates={
                                'binance_response': str(binance_response)
                            })

                        return {
                            "status": "success",
                            "message": "Trade processed and executed successfully",
                            "trade_id": trade_row['id'],
                            "binance_response": binance_response
                        }
                    else:
                        logger.error(f"❌ Trade execution failed for {coin_symbol}: {binance_response}")

                        # Update trade with error using existing columns
                        await self.db_manager.update_existing_trade(trade_id=trade_row['id'], updates={
                            'status': 'FAILED',
                            'sync_error_count': 1,
                            'sync_issues': [f'Trade execution failed: {binance_response}'],
                            'manual_verification_needed': True
                        })

                        # Send Telegram notification for failed trade
                        try:
                            await self.telegram_notifications.send_trade_execution_notification(
                                coin_symbol=coin_symbol,
                                position_type=position_type,
                                entry_price=signal_price,
                                quantity=0,
                                order_id="",
                                status="FAILED",
                                error_message=str(binance_response)
                            )
                        except Exception as e:
                            logger.error(f"Failed to send Telegram notification: {e}")

                        return {
                            "status": "error",
                            "message": f"Trade execution failed: {binance_response}",
                            "trade_id": trade_row['id']
                        }

                except Exception as exec_error:
                    logger.error(f"Error executing trade for {parsed_signal['coin_symbol']}: {exec_error}")

                    # Update trade with error using existing columns
                    await self.db_manager.update_existing_trade(trade_id=trade_row['id'], updates={
                        'status': 'FAILED',
                        'sync_error_count': 1,
                        'sync_issues': [f'Execution error: {str(exec_error)}'],
                        'manual_verification_needed': True
                    })

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
        Updates the existing trade row with new information.
        """
        binance_response_log = None # To store any response from a trading action
        try:
            signal = DiscordUpdateSignal(**signal_data)
            logger.info(f"Processing update signal: {signal.content}")

            # Check for duplicate alerts
            alert_hash = self._generate_alert_hash(signal.discord_id, signal.content)
            if await self._is_duplicate_alert(alert_hash):
                logger.warning(f"Duplicate alert detected: {signal.content}")
                return {"status": "skipped", "message": "Duplicate alert"}

            # The 'trade' field in the update signal refers to the discord_id of the original trade
            trade_row = await self.db_manager.find_trade_by_discord_id(signal.trade)
            if not trade_row:
                error_msg = f"No original trade found for discord_id: {signal.trade}"
                logger.error(error_msg)
                return {"status": "error", "message": error_msg}

            # --- SKIP follow-up if original trade is FAILED or UNFILLED ---
            if trade_row.get('order_status') in ('REJECTED', 'CANCELED', 'EXPIRED') or trade_row.get('status') == 'NONE':
                logger.warning(f"Skipping follow-up: original trade {trade_row['id']} has order_status={trade_row.get('order_status')} and position_status={trade_row.get('status')}")
                # Update alert to reflect no open position
                alert_updates = {
                    "parsed_alert": {
                        "original_content": signal.content,
                        "processed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                        "original_trade_id": trade_row['id'],
                        "coin_symbol": self._parse_parsed_signal(trade_row.get('parsed_signal')).get('coin_symbol'),
                        "trader": signal.trader,
                        "note": "Skipped: original trade is FAILED or UNFILLED. No open position to update."
                    },
                    "binance_response": None,
                    "status": "SKIPPED"
                }
                trade_val = getattr(signal, 'trade', None)
                if not isinstance(trade_val, str):
                    trade_val = None
                await self.db_manager.update_alert_by_discord_id_or_trade(
                    discord_id=signal.discord_id,
                    trade=trade_val,
                    updates=alert_updates
                )
                return {"status": "skipped", "message": "No open position to update (original trade is FAILED or UNFILLED)"}

            # Parse the alert content to determine action(s)
            parsed_action = self.parse_alert_content(signal.content, trade_row)

            # Ensure parsed_action is not None
            if parsed_action is None:
                error_msg = f"Failed to parse alert content: {signal.content}"
                logger.error(error_msg)
                return {"status": "error", "message": error_msg}

            # Handle multiple actions
            if parsed_action.get("multiple_actions"):
                logger.info(f"Processing multiple actions: {len(parsed_action['actions'])} actions")

                trade_updates = {}
                all_actions_successful = True

                for i, action in enumerate(parsed_action['actions']):
                    logger.info(f"Executing action {i+1}/{len(parsed_action['actions'])}: {action['action_type']}")

                    # Execute each action using the existing logic
                    action_successful, binance_response_log = await self._execute_single_action(action, trade_row, signal)

                    if not action_successful:
                        logger.error(f"Action {i+1} failed: {action['action_type']}")
                        all_actions_successful = False
                        break
                    else:
                        # Merge trade updates from each action
                        if binance_response_log and isinstance(binance_response_log, dict):
                            if 'trade_updates' in binance_response_log:
                                trade_updates.update(binance_response_log['trade_updates'])

                action_successful = all_actions_successful
                action_type = "multiple_actions"

                if action_successful:
                    return {"status": "success", "message": f"Processed {len(parsed_action['actions'])} actions successfully"}
                else:
                    return {"status": "error", "message": f"Failed to process all {len(parsed_action['actions'])} actions"}
            else:
                # Execute single action (existing logic)
                trade_updates = {}
                action_type = parsed_action["action_type"]
                action_successful = False # Flag to track if the engine action succeeded

            # Determine what trading action to take based on the parsed action
            if action_type == "stop_loss_hit" or action_type == "position_closed":
                logger.info(f"Processing '{action_type}' for trade {trade_row['id']}. Closing position.")
                action_successful, binance_response_log = await self.trading_engine.close_position_at_market(trade_row, reason=action_type)
                if action_successful:
                    trade_updates["status"] = "CLOSED"

                    # Set closed_at timestamp when trade is closed via alert
                    from discord_bot.utils.timestamp_manager import ensure_closed_at
                    await ensure_closed_at(self.supabase, trade_row['id'])
                    logger.info(f"✅ Set closed_at timestamp for trade {trade_row['id']} via alert closure")

                    # Ensure coin_symbol is stored in database
                    if not trade_row.get('coin_symbol') and parsed_action.get('coin_symbol'):
                        trade_updates["coin_symbol"] = parsed_action.get('coin_symbol')
                        logger.info(f"Updated coin_symbol to {parsed_action.get('coin_symbol')} for trade {trade_row['id']}")

                    # --- Fetch binance_exit_price from Binance ---
                    coin_symbol_exit = self._parse_parsed_signal(trade_row.get('parsed_signal')).get('coin_symbol')
                    if coin_symbol_exit and isinstance(coin_symbol_exit, str):
                        try:
                            from src.services.price_service import PriceService
                            price_service = PriceService()
                            binance_exit_price = await price_service.get_coin_price(coin_symbol_exit)
                            if binance_exit_price is not None:
                                trade_updates["binance_exit_price"] = float(binance_exit_price)
                                logger.info(f"Fetched binance_exit_price for {coin_symbol_exit}: {binance_exit_price}")
                        except Exception as e:
                            logger.warning(f"Could not fetch binance_exit_price: {e}")

            elif action_type == "take_profit_1":
                logger.info(f"Processing TP1 for trade {trade_row['id']}. Closing 50% of position.")
                action_successful, binance_response_log = await self.trading_engine.close_position_at_market(trade_row, reason="take_profit_1", close_percentage=50.0)
                if action_successful:
                    trade_updates["status"] = "PARTIALLY_CLOSED"

                    # Update position_size in database - remaining 50%
                    current_position_size = float(trade_row.get('position_size', 0.0))
                    new_position_size = current_position_size * 0.5  # 50% remaining
                    trade_updates["position_size"] = new_position_size
                    logger.info(f"Updated position_size from {current_position_size} to {new_position_size} after TP1")

            elif action_type == "tp1_and_sl_to_be":
                logger.info(f"Processing TP1 + SL to BE for trade {trade_row['id']}. Closing 50% and moving SL to break-even.")

                # Step 1: Close 50% of position (TP1)
                action_successful, binance_response_log = await self.trading_engine.close_position_at_market(trade_row, reason="take_profit_1", close_percentage=50.0)
                if action_successful:
                    trade_updates["status"] = "PARTIALLY_CLOSED"

                    # Update position_size in database - remaining 50%
                    current_position_size = float(trade_row.get('position_size', 0.0))
                    new_position_size = current_position_size * 0.5  # 50% remaining
                    trade_updates["position_size"] = new_position_size
                    logger.info(f"Updated position_size from {current_position_size} to {new_position_size} after TP1")

                    # Step 2: Move stop loss to break-even for remaining position
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
                                new_sl_price = round(entry_price, 2)

                                logger.info(f"Moving SL to break-even at {new_sl_price} for remaining position ({new_position_size})")

                                # Update stop loss to break-even with the new position size
                                # First, update the trade row with new position size for the SL update
                                trade_row['position_size'] = new_position_size

                                sl_update_successful, sl_response = await self.trading_engine.update_stop_loss(trade_row, new_sl_price)
                                if sl_update_successful:
                                    logger.info(f"Successfully moved SL to break-even for trade {trade_row['id']}")
                                    # Store the new SL order ID in trade updates
                                    if isinstance(sl_response, dict) and 'orderId' in sl_response:
                                        trade_updates['stop_loss_order_id'] = str(sl_response['orderId'])
                                else:
                                    logger.warning(f"Failed to move SL to break-even: {sl_response}")
                            else:
                                logger.warning(f"Could not find position for {trading_pair} to move SL to break-even")
                        else:
                            logger.warning(f"Could not determine coin symbol for SL update on trade {trade_row['id']}")
                    except Exception as e:
                        logger.error(f"Error moving SL to break-even: {str(e)}")

            elif action_type == "take_profit_2":
                logger.info(f"Processing TP2 for trade {trade_row['id']}. Closing remaining position.")
                action_successful, binance_response_log = await self.trading_engine.close_position_at_market(trade_row, reason="take_profit_2", close_percentage=100.0)
                if action_successful:
                    trade_updates["status"] = "CLOSED"

                    # Set closed_at timestamp when trade is fully closed via TP2
                    from discord_bot.utils.timestamp_manager import ensure_closed_at
                    await ensure_closed_at(self.supabase, trade_row['id'])
                    logger.info(f"✅ Set closed_at timestamp for trade {trade_row['id']} via TP2 closure")

                    # Update position_size to 0 since position is fully closed
                    trade_updates["position_size"] = 0.0
                    logger.info(f"Updated position_size to 0.0 after TP2 (fully closed)")

                    # --- Fetch binance_exit_price from Binance ---
                    coin_symbol_exit = self._parse_parsed_signal(trade_row.get('parsed_signal')).get('coin_symbol')
                    if coin_symbol_exit and isinstance(coin_symbol_exit, str):
                        try:
                            from src.services.price_service import PriceService
                            price_service = PriceService()
                            binance_exit_price = await price_service.get_coin_price(coin_symbol_exit)
                            if binance_exit_price is not None:
                                trade_updates["binance_exit_price"] = float(binance_exit_price)
                                logger.info(f"Fetched binance_exit_price for {coin_symbol_exit}: {binance_exit_price}")
                        except Exception as e:
                            logger.warning(f"Could not fetch binance_exit_price: {e}")

            elif action_type == "stop_loss_update":
                logger.info(f"Processing stop loss update for trade {trade_row['id']}")
                new_sl_price = 0.0

                # Check for "BE" (Break Even) signal
                if parsed_action.get("stop_loss") == "BE" or "be" in signal.content.lower():
                    # Get the actual position data from Binance for accurate break-even calculation
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
                                new_sl_price = entry_price

                                # Round to 2 decimal places for precision
                                new_sl_price = round(new_sl_price, 2)

                                logger.info(f"Determined break-even price as {new_sl_price} (using entry price directly)")
                            else:
                                # Fallback to database entry price
                                original_entry_price = trade_row.get('entry_price')
                                if original_entry_price:
                                    # Use entry price directly as break-even
                                    new_sl_price = float(original_entry_price)

                                    # Round to 2 decimal places for precision
                                    new_sl_price = round(new_sl_price, 2)

                                    logger.info(f"Determined break-even price as {new_sl_price} from database entry price.")
                                else:
                                    logger.error(f"Could not determine entry price for BE stop loss on trade {trade_row['id']}")
                        else:
                            logger.error(f"Could not determine coin symbol for BE stop loss on trade {trade_row['id']}")
                    except Exception as e:
                        logger.warning(f"Could not fetch position data from Binance: {e}. Using database entry price.")
                        # Fallback to database entry price
                        original_entry_price = trade_row.get('entry_price')
                        if original_entry_price:
                            # Use entry price directly as break-even
                            new_sl_price = float(original_entry_price)

                            # Round to 2 decimal places for precision
                            new_sl_price = round(new_sl_price, 2)

                            logger.info(f"Determined break-even price as {new_sl_price} from database entry price.")
                        else:
                            logger.error(f"Could not determine entry price for BE stop loss on trade {trade_row['id']}")
                else:
                    # Get the new price from the parsed data if available
                    new_sl_price = float(parsed_action.get("stop_loss", 0.0))
                print(f"New SL price determined from parsed action: {new_sl_price}")
                if new_sl_price > 0:
                    action_successful, binance_response_log = await self.trading_engine.update_stop_loss(trade_row, new_sl_price)
                    if action_successful and isinstance(binance_response_log, dict):
                        # The response from a successful SL update contains the new order details
                        trade_updates['stop_loss_order_id'] = str(binance_response_log.get('orderId', ''))
                else:
                    logger.warning(f"Could not determine a valid new stop loss price for trade {trade_row['id']}")
            elif action_type == "cancelled_stoploss_order_and_create_new":
                logger.info(f"Processing stop loss update for trade {trade_row['id']}")

                try:
                    coin_symbol = self._parse_parsed_signal(trade_row.get('parsed_signal')).get('coin_symbol')
                    position_type = trade_row.get('signal_type', 'UNKNOWN')
                    if not coin_symbol:
                        logger.error(f"Could not determine coin symbol for trade {trade_row['id']}")
                        return {"status": "error", "message": "Could not determine coin symbol for stop loss update."}

                    stop_loss_percentage = parsed_action.get('stop_loss_percentage', 2.0)
                    if stop_loss_percentage <= 0 or stop_loss_percentage > 50:
                        logger.error(f"Invalid stop loss percentage: {stop_loss_percentage}%. Must be between 0.1 and 50.")
                        return {"status": "error", "message": f"Invalid stop loss percentage: {stop_loss_percentage}%. Must be between 0.1 and 50."}

                    new_sl_price = await self.trading_engine.calculate_percentage_stop_loss(coin_symbol, position_type, stop_loss_percentage)
                    print(f"New SL price determined from percentage: {new_sl_price}")
                    if not new_sl_price:
                        logger.error(f"Could not calculate {stop_loss_percentage}% stop loss for {coin_symbol}")
                        return {"status": "error", "message": f"Could not calculate {stop_loss_percentage}% stop loss for {coin_symbol}"}
                    if new_sl_price > 0:
                        action_successful, binance_response_log = await self.trading_engine.update_stop_loss(trade_row, new_sl_price)
                        if action_successful and isinstance(binance_response_log, dict):
                            trade_updates['stop_loss_order_id'] = str(binance_response_log.get('orderId', ''))
                        else:
                            logger.warning(f"Stop loss update failed for trade {trade_row['id']}. Binance response: {binance_response_log}")
                    else:
                        logger.warning(f"Could not determine a valid new stop loss price for trade {trade_row['id']}. new_sl_price was {new_sl_price}")
                except Exception as e:
                    logger.error(f"An error occurred while updating stop loss for trade {trade_row['id']}: {e}")
            elif action_type == "take_profit_taken_hit":
                logger.info(f"Processing take profit taken hit for trade {trade_row['id']} - creating new TP and moving SL to entry")

                try:
                    coin_symbol = self._parse_parsed_signal(trade_row.get('parsed_signal')).get('coin_symbol')
                    position_type = trade_row.get('signal_type', 'UNKNOWN')
                    if not coin_symbol:
                        logger.error(f"Could not determine coin symbol for trade {trade_row['id']}")
                        return {"status": "error", "message": "Could not determine coin symbol for take profit taken hit."}

                    trading_pair = f"{coin_symbol}USDT"
                    positions = await self.binance_exchange.get_position_risk(symbol=trading_pair)
                    current_position_size = 0.0
                    for position in positions:
                        if position.get('symbol') == trading_pair and float(position.get('positionAmt', 0)) != 0:
                            current_position_size = abs(float(position.get('positionAmt', 0)))
                            break

                    if current_position_size <= 0:
                        logger.warning(f"No open position found for {trading_pair} - position may have been fully closed")
                        return {"status": "warning", "message": f"No open position found for {trading_pair}"}

                    logger.info(f"Current position size for {trading_pair}: {current_position_size}")

                    # Step 2: Get current market price
                    current_price = await self.binance_exchange.get_futures_mark_price(trading_pair)
                    if not current_price or current_price <= 0:
                        logger.error(f"Could not get current price for {trading_pair}")
                        return {"status": "error", "message": f"Could not get current price for {trading_pair}"}

                    logger.info(f"Current price for {trading_pair}: {current_price}")

                    # Step 3: Calculate new TP price (3% away from current price)
                    if position_type.upper() == 'LONG':
                        new_tp_price = current_price * 1.03  # 3% above current price
                    else:  # SHORT
                        new_tp_price = current_price * 0.97  # 3% below current price

                    logger.info(f"New TP price calculated: {new_tp_price} (3% {'above' if position_type.upper() == 'LONG' else 'below'} current price)")

                                         # Step 4: Get entry price for break-even stop loss
                    entry_price = float(self._parse_parsed_signal(trade_row.get('parsed_signal')).get('entry_prices', [0.0])[0])
                    if entry_price <= 0:
                         logger.error(f"Could not determine entry price for trade {trade_row['id']}")
                         return {"status": "error", "message": f"Could not determine entry price for trade {trade_row['id']}"}

                    logger.info(f"Entry price for break-even SL: {entry_price}")

                    # Step 5: Cancel existing TP/SL orders
                    logger.info(f"Canceling existing TP/SL orders for {trading_pair}")
                    await self.trading_engine.cancel_tp_sl_orders(trading_pair, trade_row)

                    # Step 6: Create new TP order for remaining position
                    tp_side = 'SELL' if position_type.upper() == 'LONG' else 'BUY'
                    new_tp_order = await self.binance_exchange.create_futures_order(
                        pair=trading_pair,
                        side=tp_side,
                        order_type_market='TAKE_PROFIT_MARKET',
                        amount=current_position_size,
                        stop_price=new_tp_price,
                        reduce_only=True
                    )

                    if not new_tp_order or 'orderId' not in new_tp_order:
                        logger.error(f"Failed to create new TP order: {new_tp_order}")
                        return {"status": "error", "message": f"Failed to create new TP order for {trading_pair}"}

                    logger.info(f"Successfully created new TP order: {new_tp_order['orderId']} at {new_tp_price}")

                    # Step 7: Update stop loss to entry (break-even)
                    action_successful, binance_response_log = await self.trading_engine.update_stop_loss(trade_row, entry_price)
                    if action_successful and isinstance(binance_response_log, dict):
                        trade_updates['stop_loss_order_id'] = str(binance_response_log.get('orderId', ''))
                        logger.info(f"Successfully moved stop loss to entry price: {entry_price}")
                    else:
                        logger.warning(f"Stop loss update to entry failed for trade {trade_row['id']}. Binance response: {binance_response_log}")

                    # Step 8: Update trade status and position size
                    trade_updates["status"] = "PARTIALLY_CLOSED"
                    trade_updates["position_size"] = current_position_size

                    # Store the new TP order information
                    if 'tp_sl_orders' not in trade_updates:
                        trade_updates['tp_sl_orders'] = []
                    trade_updates['tp_sl_orders'].append({
                        'orderId': new_tp_order['orderId'],
                        'order_type': 'TAKE_PROFIT',
                        'tp_level': 2,  # This is the second TP
                        'stopPrice': str(new_tp_price),
                        'symbol': trading_pair,
                        'amount': str(current_position_size)
                    })

                    action_successful = True
                    binance_response_log = {
                        'message': f'TP taken hit processed - new TP at {new_tp_price}, SL moved to entry {entry_price}',
                        'new_tp_order': new_tp_order,
                        'position_size': current_position_size
                    }

                except Exception as e:
                    logger.error(f"An error occurred while processing take profit taken hit for trade {trade_row['id']}: {e}")
                    return {"status": "error", "message": f"Error processing take profit taken hit: {str(e)}"}
            elif action_type == "limit_order_cancelled":
                logger.info(f"Processing cancellation for trade {trade_row['id']}")
                action_successful, binance_response_log = await self.trading_engine.cancel_order(trade_row)
                await self.trading_engine.cancel_tp_sl_orders(f"{trade_row.get('coin_symbol', 'UNKNOWN')}USDT", trade_row)
                if action_successful:
                    trade_updates["status"] = "CANCELLED"

            elif action_type == "order_filled":
                 # Usually, the initial signal opens the position. This is just an informational update.
                 # We can update the status to ensure it reflects 'OPEN'.
                 logger.info(f"Received 'order filled' notification for trade {trade_row['id']}. Status confirmed as OPEN.")
                 trade_updates["status"] = "OPEN"
                 action_successful = True # No engine action, but we mark as successful to log correctly.
                 binance_response_log = {"message": "Order fill notification processed."}

            # After executing action, update the database
            if action_successful:
                logger.info(f"Successfully executed '{action_type}' for trade {trade_row['id']}. Binance Response: {binance_response_log}")

                # --- PNL and Exit Price Calculation ---
                if binance_response_log and 'fill_price' in binance_response_log and 'executed_qty' in binance_response_log:
                    exit_price = float(binance_response_log['fill_price'])
                    qty_closed = float(binance_response_log['executed_qty'])

                    if exit_price > 0 and qty_closed > 0:
                        # Safely get entry price and position type from the trade row
                        entry_price = float(self._parse_parsed_signal(trade_row.get('parsed_signal')).get('entry_prices', [0.0])[0])
                        position_type = trade_row.get('signal_type', 'UNKNOWN')

                        # Calculate PnL for this specific action
                        newly_realized_pnl = self._calculate_pnl(position_type, entry_price, exit_price, qty_closed)

                        # Get existing PnL and add the new PnL
                        current_pnl = float(trade_row.get('pnl_usd', 0.0) or 0.0)
                        total_pnl = current_pnl + newly_realized_pnl

                        trade_updates["pnl_usd"] = total_pnl
                        trade_updates["exit_price"] = exit_price # This will store the latest exit price

                        logger.info(f"PnL for this action: {newly_realized_pnl:.2f}. Total realized PnL for trade: {total_pnl:.2f}")

                # Extract Binance execution timestamp if available for accurate updated_at
                binance_execution_time = None
                if isinstance(binance_response_log, dict) and 'updateTime' in binance_response_log:
                    execution_timestamp = binance_response_log['updateTime']
                    # Convert milliseconds to ISO format
                    from datetime import datetime, timezone
                    binance_execution_time = datetime.fromtimestamp(execution_timestamp / 1000, tz=timezone.utc).isoformat()
                    logger.info(f"Using Binance execution timestamp for updated_at: {binance_execution_time}")

                # Update the trade with new status or SL order ID
                if trade_updates:
                    await self.db_manager.update_existing_trade(
                        trade_id=trade_row["id"],
                        updates=trade_updates,
                        binance_execution_time=binance_execution_time
                    )
                    logger.info(f"Updated trade {trade_row['id']} with: {trade_updates}")
            elif binance_response_log: # Action was attempted but failed
                logger.error(f"Failed to execute '{action_type}' for trade {trade_row['id']}. Reason: {binance_response_log}")


            # Always update the alert record with the outcome
            alert_updates = {
                "parsed_alert": {
                    "original_content": signal.content,
                    "processed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    "action_determined": parsed_action,
                    "original_trade_id": trade_row['id'],
                    "coin_symbol": parsed_action.get('coin_symbol', self._parse_parsed_signal(trade_row.get('parsed_signal')).get('coin_symbol')),
                    "trader": signal.trader
                },
                "binance_response": binance_response_log, # This will be None if no action was taken, or the dict from Binance
                "status": "SUCCESS" if action_successful else "ERROR"
            }

            # Always fetch the alert row by discord_id before updating
            alert_row = None
            try:
                alert_response = self.db_manager.supabase.from_("alerts").select("*").eq("discord_id", signal.discord_id).limit(1).execute()
                if alert_response.data and len(alert_response.data) > 0:
                    alert_row = alert_response.data[0]
            except Exception as e:
                logger.error(f"Error fetching alert row for update: {e}")

            if alert_row and alert_row.get('id'):
                logger.info(f"Updating alert by found alert id {alert_row['id']} with processed data.")
                await self.db_manager.update_existing_alert(alert_row['id'], alert_updates)
            else:
                # Create a new alert if none exists
                logger.info(f"Creating new alert for discord_id {signal.discord_id}")
                new_alert_data = {
                    "timestamp": signal.timestamp,
                    "discord_id": signal.discord_id,
                    "trade": signal.trade,
                    "content": signal.content,
                    "trader": signal.trader,
                    **alert_updates
                }
                await self.db_manager.save_alert_to_database(new_alert_data)

            return {
                "status": "success",
                "message": f"Update signal processed: {parsed_action['action_description']}"
            }

        except Exception as e:
            error_msg = f"Error processing update signal: {str(e)}"
            logger.error(error_msg, exc_info=True)

            # Update alert status to ERROR if we can find the alert
            try:
                if 'signal' in locals():
                    alert_response = self.db_manager.supabase.from_("alerts").select("*").eq("discord_id", signal.discord_id).limit(1).execute()
                    if alert_response.data and len(alert_response.data) > 0:
                        alert_row = alert_response.data[0]
                        await self.db_manager.update_existing_alert(alert_row['id'], {
                            "status": "ERROR",
                            "binance_response": {"error": error_msg}
                        })
            except Exception as alert_error:
                logger.error(f"Could not update alert status: {alert_error}")

            return {"status": "error", "message": error_msg}

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

        return round(pnl, 2)

    async def update_trade_position_size(self, trade_id: int, new_position_size: float) -> bool:
        """Update the position_size field in a trade record."""
        try:
            updates = {"position_size": float(new_position_size)}
            success = await self.db_manager.update_existing_trade(trade_id=trade_id, updates=updates)
            if success:
                logger.info(f"Updated position_size to {new_position_size} for trade {trade_id}")
            return success
        except Exception as e:
            logger.error(f"Error updating position_size for trade {trade_id}: {e}")
            return False

    async def update_trade_coin_symbol(self, trade_id: int, new_coin_symbol: str) -> bool:
        """Update the coin_symbol field in a trade record."""
        try:
            updates = {"coin_symbol": str(new_coin_symbol)}
            success = await self.db_manager.update_existing_trade(trade_id=trade_id, updates=updates)
            if success:
                logger.info(f"Updated coin_symbol to {new_coin_symbol} for trade {trade_id}")
            return success
        except Exception as e:
            logger.error(f"Error updating coin_symbol for trade {trade_id}: {e}")
            return False

    async def close(self):
        """Gracefully shutdown the trading engine and WebSocket manager."""
        try:
            # Stop WebSocket manager
            if hasattr(self, 'websocket_manager') and self.websocket_manager:
                await self.websocket_manager.stop()

            # Close trading engine
            await self.trading_engine.close()

            logger.info("DiscordBot closed successfully.")
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
                logger.error("WebSocket manager not initialized")
                return False
        except Exception as e:
            logger.error(f"Error starting WebSocket sync: {e}")
            return False

    def get_websocket_status(self) -> dict:
        """Get WebSocket manager status."""
        if hasattr(self, 'websocket_manager') and self.websocket_manager:
            return self.websocket_manager.get_status()
        else:
            return {
                'running': False,
                'initialized': False,
                'error': 'WebSocket manager not available'
            }

    async def _execute_single_action(self, action: Dict[str, Any], trade_row: Dict[str, Any], signal) -> Tuple[bool, Any]:
        """
        Execute a single action from the parsed alert content.
        """
        try:
            action_type = action.get('action_type')
            if not action_type:
                logger.error(f"No action_type found in action: {action}")
                return False, {"error": "No action_type found"}

            # Execute the action based on type
            if action_type == "stop_loss_hit" or action_type == "position_closed":
                return await self.trading_engine.close_position_at_market(trade_row, reason=action_type)
            elif action_type == "take_profit_1":
                return await self.trading_engine.close_position_at_market(trade_row, reason="take_profit_1", close_percentage=50.0)
            elif action_type == "take_profit_2":
                return await self.trading_engine.close_position_at_market(trade_row, reason="take_profit_2", close_percentage=100.0)
            elif action_type == "limit_order_cancelled":
                return await self.trading_engine.cancel_order(trade_row)
            elif action_type == "stop_loss_update":
                stop_loss = action.get('stop_loss')
                if stop_loss and stop_loss != "BE":
                    return await self.trading_engine.update_stop_loss(trade_row, float(stop_loss))
                else:
                    # Handle break-even stop loss
                    return await self.trading_engine.update_stop_loss(trade_row, "BE")
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
                logger.warning(f"Unknown action_type: {action_type}")
                return False, {"error": f"Unknown action_type: {action_type}"}

        except Exception as e:
            logger.error(f"Error executing action {action.get('action_type', 'unknown')}: {e}")
            return False, {"error": str(e)}

# Global bot instance
discord_bot = DiscordBot()

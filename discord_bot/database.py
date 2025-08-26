import os
import logging
from typing import Optional, Dict, Any, List
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import json

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# --- Supabase setup ---
url: Optional[str] = os.environ.get("SUPABASE_URL")
key: Optional[str] = os.environ.get("SUPABASE_KEY")

if not url or not key:
    logger.warning("Supabase URL or Key not found in environment variables. Database functionality will be disabled.")
    supabase = None
else:
    try:
        supabase = create_client(url, key)
        logger.info("Successfully connected to Supabase.")
    except Exception as e:
        logger.error(f"Failed to connect to Supabase: {e}", exc_info=True)
        supabase = None


class DatabaseManager:
    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client

    async def find_active_trade_by_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Finds the most recent active trade for a given coin symbol.
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return None

        try:
            # Look for trades with status 'OPEN' for this symbol
            response = self.supabase.from_("trades").select("*").eq("coin_symbol", symbol).eq("status", "OPEN").order("timestamp", desc=True).limit(1).execute()

            if response.data:
                logger.info(f"Found active trade for {symbol}: ID {response.data[0]['id']}")
                return response.data[0]
            else:
                logger.info(f"No active trade found for {symbol}.")
                return None
        except Exception as e:
            logger.error(f"Error querying for active trade for {symbol}: {e}", exc_info=True)
            return None

    async def find_trade_by_timestamp(self, timestamp: str) -> Optional[Dict[str, Any]]:
        """
        Find trade by timestamp match using a time range for robustness.
        This handles millisecond precision issues.
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return None

        try:
            # 1. Clean the timestamp string
            clean_timestamp_str = timestamp.replace('T', ' ').rstrip('Z')
            logger.info(f"Querying for timestamp: original='{timestamp}', cleaned='{clean_timestamp_str}'")

            # 2. Convert to datetime object
            dt_object = datetime.fromisoformat(clean_timestamp_str)

            # 3. Create a small time range (e.g., one millisecond) to handle precision differences
            start_time = dt_object
            end_time = dt_object + timedelta(milliseconds=1)

            # 4. Use gte (>=) and lt (<) for the range query
            response = self.supabase.from_("trades").select("*") \
                .gte("timestamp", start_time.isoformat()) \
                .lt("timestamp", end_time.isoformat()) \
                .order("timestamp", desc=True).limit(1).execute()

            if response.data:
                logger.info(f"Found trade by timestamp range for {clean_timestamp_str}: ID {response.data[0]['id']}")
                return response.data[0]
            else:
                logger.info(f"No trade found in timestamp range for: {clean_timestamp_str}")
                return None

        except Exception as e:
            logger.error(f"Error finding trade by timestamp: {e}", exc_info=True)
            return None

    async def find_trade_by_content(self, content: str) -> Optional[Dict[str, Any]]:
        """
        Find trade by exact content string match.
        Used for initial signals that don't have a trade reference.
        DEPRECATED: Use find_trade_by_timestamp instead.
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return None

        try:
            # Find trade by exact content match, get the most recent one
            response = self.supabase.from_("trades").select("*").eq("content", content).order("timestamp", desc=True).limit(1).execute()

            if response.data:
                logger.info(f"Found trade by content: ID {response.data[0]['id']}")
                return response.data[0]
            else:
                logger.info(f"No trade found for content: {content[:50]}...")
                return None

        except Exception as e:
            logger.error(f"Error finding trade by content: {e}", exc_info=True)
            return None

    async def find_trade_by_signal_id(self, signal_id: str) -> Optional[Dict[str, Any]]:
        """
        Find trade by signal_id field.
        Used for follow-up signals that reference the original trade.
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return None

        try:
            # Find trade by signal_id - this should match the 'trade' field from follow-up signals
            response = self.supabase.from_("trades").select("*").eq("signal_id", signal_id).execute()

            if response.data:
                logger.info(f"Found trade by signal_id {signal_id}: ID {response.data[0]['id']}")
                return response.data[0]
            else:
                logger.info(f"No trade found for signal_id: {signal_id}")
                return None

        except Exception as e:
            logger.error(f"Error finding trade by signal_id {signal_id}: {e}", exc_info=True)
            return None

    async def find_trade_by_discord_id(self, discord_id: str) -> Optional[Dict[str, Any]]:
        """
        Find a trade by its unique Discord message ID.
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return None

        try:
            response = self.supabase.from_("trades").select("*").eq("discord_id", discord_id).limit(1).execute()

            if response.data:
                logger.info(f"Found trade by discord_id {discord_id}: ID {response.data[0]['id']}")
                return response.data[0]
            else:
                logger.info(f"No trade found for discord_id: {discord_id}")
                return None

        except Exception as e:
            logger.error(f"Error finding trade by discord_id {discord_id}: {e}", exc_info=True)
            return None

    async def get_trade_by_id(self, trade_id: int) -> Optional[Dict[str, Any]]:
        """
        Find a trade by its primary key ID.
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return None
        try:
            response = self.supabase.from_("trades").select("*").eq("id", trade_id).limit(1).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error finding trade by id {trade_id}: {e}", exc_info=True)
            return None

    async def update_existing_trade(self, signal_id: str = "", trade_id: int = 0, updates: Dict = {}, alert_timestamp: Optional[str] = None, binance_execution_time: Optional[str] = None) -> bool:
        """
        Updates an existing trade record in the database.
        Enhanced to preserve original order responses and track sync issues.
        
        Args:
            signal_id: Discord signal ID (optional, used if trade_id not provided)
            trade_id: Database trade ID (optional, used if signal_id not provided)
            updates: Dictionary of fields to update
            alert_timestamp: Optional alert timestamp to use for updated_at (for accuracy in PnL calculations)
            binance_execution_time: Optional Binance execution timestamp (most accurate for PnL calculations)
            
        Returns:
            bool: Success status
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return False

        if not updates:
            logger.error("No updates provided.")
            return False

        try:
            # Use Binance execution timestamp if provided (most accurate for PnL calculations)
            if binance_execution_time:
                updates["updated_at"] = binance_execution_time
                logger.info(f"Using Binance execution timestamp for updated_at: {binance_execution_time}")
            elif alert_timestamp:
                updates["updated_at"] = alert_timestamp
                logger.info(f"Using alert timestamp for updated_at: {alert_timestamp}")
            else:
                updates["updated_at"] = datetime.now(timezone.utc).isoformat()

            # CRITICAL: Ensure closed_at is set when status becomes CLOSED
            if updates.get("status") == "CLOSED":
                # Check if we need to set closed_at
                if "closed_at" not in updates:
                    # Get current trade data to check if closed_at already exists
                    current_trade = None
                    if trade_id:
                        response = self.supabase.from_("trades").select("closed_at, updated_at").eq("id", trade_id).execute()
                        current_trade = response.data[0] if response.data else None
                    elif signal_id:
                        response = self.supabase.from_("trades").select("closed_at, updated_at").eq("signal_id", signal_id).execute()
                        current_trade = response.data[0] if response.data else None
                    
                    # Only set closed_at if it doesn't already exist
                    if current_trade and not current_trade.get("closed_at"):
                        # Use updated_at as fallback (more accurate than current time)
                        # This preserves historical accuracy for PnL calculations
                        fallback_time = current_trade.get("updated_at") or datetime.now(timezone.utc).isoformat()
                        updates["closed_at"] = fallback_time
                        logger.info(f"✅ Automatically set closed_at for trade {trade_id or signal_id} using updated_at fallback: {fallback_time}")

            if trade_id:
                # For updates using database ID
                response = self.supabase.from_("trades").update(updates).eq("id", trade_id).execute()
            elif signal_id:
                # For updates using signal_id
                response = self.supabase.from_("trades").update(updates).eq("signal_id", signal_id).execute()
            else:
                logger.error("Must provide either signal_id or trade_id")
                return False

            logger.info(f"Updated trade with: {updates}")
            return True

        except Exception as e:
            logger.error(f"Error updating trade: {e}", exc_info=True)
            return False

    async def update_trade_with_original_response(self, trade_id: int, original_response: Dict, status_response: Optional[Dict] = None, sync_error: Optional[str] = None) -> bool:
        """
        Updates a trade while preserving the original order response.
        This is critical for financial accuracy.
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return False

        try:
            updates: Dict[str, Any] = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "binance_response": json.dumps(original_response) if isinstance(original_response, dict) else str(original_response)
            }

            # Determine if order was actually created successfully
            order_created_successfully = self._is_order_actually_successful(original_response)

            if order_created_successfully:
                # Order was created successfully - preserve original response
                updates["binance_response"] = json.dumps(original_response) if isinstance(original_response, dict) else str(original_response)
                
                # CRITICAL: Set correct initial status based on order type and execution
                order_type = original_response.get('type', 'MARKET')
                executed_qty = float(original_response.get('executedQty', 0))
                orig_qty = float(original_response.get('origQty', 0))
                
                if order_type == 'MARKET':
                    # Market orders are typically filled immediately
                    if executed_qty > 0:
                        updates["order_status"] = "FILLED"
                        updates["status"] = "OPEN"  # Position is open
                    else:
                        # Rare case: market order not filled
                        updates["order_status"] = "UNFILLED"
                        updates["status"] = "NONE"
                else:
                    # Limit orders
                    if executed_qty > 0:
                        if executed_qty >= orig_qty:
                            # Fully executed
                            updates["order_status"] = "FILLED"
                            updates["status"] = "OPEN"
                        else:
                            # Partially executed
                            updates["order_status"] = "PARTIALLY_FILLED"
                            updates["status"] = "OPEN"
                    else:
                        # Order was placed but not yet executed
                        updates["order_status"] = "UNFILLED"
                        updates["status"] = "NONE"

                if "orderId" in original_response:
                    updates["exchange_order_id"] = str(original_response.get("orderId", ""))

                                    # CRITICAL: Extract and store position_size and execution price from the successful order response
                    if isinstance(original_response, dict):
                        position_size_set = False
                        execution_price_set = False

                        # Try to get position size from executedQty (most reliable)
                        executed_qty = original_response.get('executedQty')
                        if executed_qty and float(executed_qty) > 0:
                            updates["position_size"] = float(executed_qty)
                            logger.info(f"Stored position_size from executedQty: {executed_qty} for trade {trade_id}")
                            position_size_set = True
                        else:
                            # Fallback to origQty if executedQty is not available
                            orig_qty = original_response.get('origQty')
                            if orig_qty and float(orig_qty) > 0:
                                updates["position_size"] = float(orig_qty)
                                logger.info(f"Stored position_size from origQty: {orig_qty} for trade {trade_id}")
                                position_size_set = True
                            else:
                                # Final fallback: calculate from fills array
                                fills = original_response.get('fills', [])
                                if fills:
                                    total_filled_qty = sum(float(fill.get('qty', 0.0)) for fill in fills)
                                    if total_filled_qty > 0:
                                        updates["position_size"] = total_filled_qty
                                        logger.info(f"Stored position_size from fills array: {total_filled_qty} for trade {trade_id}")
                                        position_size_set = True

                        # CRITICAL: Extract execution price (binance_entry_price) from the order response
                        # Determine if this is an entry or exit order
                        is_exit_order = original_response.get('reduceOnly', False) or original_response.get('closePosition', False)
                        
                        if is_exit_order:
                            # This is an exit order - set binance_exit_price
                            avg_price = original_response.get('avgPrice')
                            if avg_price and float(avg_price) > 0:
                                updates["binance_exit_price"] = float(avg_price)
                                logger.info(f"Stored binance_exit_price from execution: {avg_price} for trade {trade_id}")
                                execution_price_set = True
                            else:
                                # Try to get from fills array
                                fills = original_response.get('fills', [])
                                if fills:
                                    total_qty = sum(float(fill.get('qty', 0.0)) for fill in fills)
                                    total_price = sum(float(fill.get('price', 0.0)) * float(fill.get('qty', 0.0)) for fill in fills)
                                    if total_qty > 0:
                                        avg_price = total_price / total_qty
                                        updates["binance_exit_price"] = avg_price
                                        logger.info(f"Stored binance_exit_price from fills: {avg_price} for trade {trade_id}")
                                        execution_price_set = True
                        else:
                            # This is an entry order - set binance_entry_price
                            # CRITICAL: Only set binance_entry_price if there's actual execution (executedQty > 0)
                            executed_qty = float(original_response.get('executedQty', 0))
                            avg_price = original_response.get('avgPrice')
                            
                            if executed_qty > 0 and avg_price and float(avg_price) > 0:
                                updates["binance_entry_price"] = float(avg_price)
                                logger.info(f"Stored binance_entry_price from execution: {avg_price} for trade {trade_id}")
                                execution_price_set = True
                            elif executed_qty > 0:
                                # Try to get from fills array
                                fills = original_response.get('fills', [])
                                if fills:
                                    total_qty = sum(float(fill.get('qty', 0.0)) for fill in fills)
                                    total_price = sum(float(fill.get('price', 0.0)) * float(fill.get('qty', 0.0)) for fill in fills)
                                    if total_qty > 0:
                                        avg_price = total_price / total_qty
                                        updates["binance_entry_price"] = avg_price
                                        logger.info(f"Stored binance_entry_price from fills: {avg_price} for trade {trade_id}")
                                        execution_price_set = True
                            else:
                                logger.info(f"Order not executed yet (executedQty={executed_qty}) - binance_entry_price will be set when order is filled")

                        # CRITICAL: If position_size is still not set, mark for manual verification
                        if not position_size_set:
                            logger.error(f"CRITICAL: Could not extract position_size from order response for trade {trade_id}")
                            updates["sync_issues"] = ["Missing position_size - manual verification required"]
                            updates["manual_verification_needed"] = True

                        # CRITICAL: If execution price is not set, mark for manual verification
                        if not execution_price_set:
                            logger.warning(f"Execution price not available in initial order response for trade {trade_id} - will be updated by WebSocket")
                            # Don't mark for manual verification since WebSocket will handle this
                            # The WebSocket handler will update binance_entry_price when the order is filled

                # Store TP/SL order information if present
                if "tp_sl_orders" in original_response:
                    updates["tp_sl_orders"] = json.dumps(original_response["tp_sl_orders"])
                    logger.info(f"Stored {len(original_response['tp_sl_orders'])} TP/SL orders for trade {trade_id}")

                # Store stop loss order ID if present
                if "stop_loss_order_id" in original_response:
                    updates["stop_loss_order_id"] = str(original_response["stop_loss_order_id"])
                    logger.info(f"Stored stop loss order ID for trade {trade_id}: {original_response['stop_loss_order_id']}")

                # If status check failed, track the error but don't overwrite success
                if sync_error:
                    updates["sync_error_count"] = 1
                    updates["sync_issues"] = [sync_error]
                    updates["manual_verification_needed"] = True
                    logger.warning(f"Order created successfully but status check failed: {sync_error}")
                elif status_response:
                    # Status check succeeded
                    updates["order_status_response"] = json.dumps(status_response) if isinstance(status_response, dict) else str(status_response)
                    updates["last_successful_sync"] = datetime.now(timezone.utc).isoformat()
                    updates["sync_error_count"] = 0
                    updates["sync_issues"] = []
                    updates["manual_verification_needed"] = False

                    # CRITICAL: Determine correct order and position status
                    order_status, position_status = self._determine_order_and_position_status(status_response)
                    
                    # Get current trade data to compare statuses
                    current_trade = await self.get_trade_by_id(trade_id)
                    if current_trade:
                        # Only update status if it's more accurate than what we already have
                        current_order_status = current_trade.get('order_status', 'UNFILLED')
                        current_position_status = current_trade.get('status', 'NONE')
                        
                        # Update order_status if we have more specific information
                        if order_status != 'UNFILLED' or current_order_status == 'UNFILLED':
                            updates["order_status"] = order_status
                        
                        # Update position status if we have more specific information
                        if position_status != 'NONE' or current_position_status == 'NONE':
                            updates["status"] = position_status
                    else:
                        # Fallback if trade not found
                        updates["order_status"] = order_status
                        updates["status"] = position_status
            else:
                # Order creation failed - this is a legitimate failure
                updates["binance_response"] = json.dumps(original_response) if isinstance(original_response, dict) else str(original_response)
                updates["order_status"] = "REJECTED"
                updates["status"] = "NONE"  # No position created
                logger.error(f"Order creation failed: {original_response}")

            response = self.supabase.from_("trades").update(updates).eq("id", trade_id).execute()
            logger.info(f"Updated trade {trade_id} with preserved original response")
            return True

        except Exception as e:
            logger.error(f"Error updating trade with original response: {e}", exc_info=True)
            return False

    async def update_tp_sl_orders(self, trade_id: int, tp_sl_orders: List[Dict]) -> bool:
        """
        Update TP/SL orders for a specific trade.
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return False

        try:
            updates = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "tp_sl_orders": json.dumps(tp_sl_orders)
            }

            response = self.supabase.from_("trades").update(updates).eq("id", trade_id).execute()
            logger.info(f"Updated TP/SL orders for trade {trade_id}: {len(tp_sl_orders)} orders")
            return True

        except Exception as e:
            logger.error(f"Error updating TP/SL orders for trade {trade_id}: {e}", exc_info=True)
            return False

    def _is_order_actually_successful(self, order_response) -> bool:
        """
        Check if order was actually created successfully.
        Critical for financial accuracy.
        """
        if isinstance(order_response, dict):
            # Success indicators
            has_order_id = 'orderId' in order_response
            no_error = 'error' not in order_response
            has_symbol = 'symbol' in order_response

            return has_order_id and no_error and has_symbol
        return False

    def _determine_final_status(self, status_response) -> Optional[str]:
        """
        Determine final status from order status response.
        """
        if not isinstance(status_response, dict):
            return None

        status = status_response.get('status', '').upper()

        if status in ['FILLED', 'PARTIALLY_FILLED']:
            return 'OPEN'
        elif status in ['CANCELED', 'EXPIRED', 'REJECTED']:
            return 'FAILED'
        elif status == 'NEW':
            return 'OPEN'  # Order is open but not filled yet
        else:
            return None  # Unknown status, don't change

    def _determine_order_and_position_status(self, status_response, position_size: float = 0) -> tuple[str, str]:
        """
        Determine both order_status and position_status from Binance response.

        Returns:
            tuple: (order_status, position_status)
        """
        from .status_constants import map_binance_order_status, determine_position_status_from_order

        if not isinstance(status_response, dict):
            return 'UNFILLED', 'NONE'

        binance_status = status_response.get('status', '').upper()
        order_status = map_binance_order_status(binance_status)
        
        # CRITICAL: Check if this is an exit order
        is_exit_order = status_response.get('reduceOnly', False) or status_response.get('closePosition', False)
        
        # Get executed quantity for position status determination
        executed_qty = float(status_response.get('executedQty', 0))
        position_status = determine_position_status_from_order(order_status, executed_qty, is_exit_order)

        return order_status, position_status

    async def save_signal_to_db(self, signal_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Saves a new signal record to the database.
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return None

        try:
            response = self.supabase.from_("trades").insert(signal_data).execute()

            if response.data:
                logger.info(f"Successfully saved signal to database. ID: {response.data[0]['id']}")
                return response.data[0]
            else:
                logger.error("Failed to save signal to database: no data returned")
                return None

        except Exception as e:
            logger.error(f"Error saving signal to database: {e}", exc_info=True)
            return None

    async def save_alert_to_database(self, alert_data: Dict[str, Any]) -> bool:
        """
        Saves an alert record to the alerts table with default status.
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return False

        try:
            # Set default status to 'PENDING' if not provided
            if 'status' not in alert_data:
                alert_data['status'] = 'PENDING'

            response = self.supabase.from_("alerts").insert(alert_data).execute()

            if response.data:
                logger.info(f"Successfully saved alert to database. ID: {response.data[0]['id']} with status: {alert_data.get('status')}")
                return True
            else:
                logger.error("Failed to save alert to database: no data returned")
                return False

        except Exception as e:
            logger.error(f"Error saving alert to database: {e}", exc_info=True)
            return False

    async def update_existing_alert(self, alert_id: int, updates: Dict) -> bool:
        """
        Updates an existing alert record in the database.
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return False

        if not updates:
            logger.error("No updates provided for alert.")
            return False

        try:
            response = self.supabase.from_("alerts").update(updates).eq("id", alert_id).execute()
            logger.info(f"Successfully updated alert ID {alert_id} with: {updates}")
            return True
        except Exception as e:
            logger.error(f"Error updating alert ID {alert_id}: {e}", exc_info=True)
            return False

    async def update_alert_by_discord_id_or_trade(self, discord_id: Optional[str] = None, trade: Optional[str] = None, updates: Dict = {}) -> bool:
        """
        Updates an existing alert record in the database by discord_id or trade.
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return False
        if not updates:
            logger.error("No updates provided for alert.")
            return False
        if not discord_id and not trade:
            logger.error("Must provide either discord_id or trade to update alert.")
            return False
        try:
            query = self.supabase.from_("alerts").update(updates)
            if discord_id:
                query = query.eq("discord_id", discord_id)
            if trade:
                query = query.eq("trade", trade)
            response = query.execute()
            if response.data:
                logger.info(f"Successfully updated alert by discord_id/trade with: {updates}")
                return True
            else:
                logger.error("Failed to update alert: no matching record found")
                return False
        except Exception as e:
            logger.error(f"Error updating alert by discord_id/trade: {e}", exc_info=True)
            return False

    async def update_trade_status(self, trade_group_id: str, is_active: bool):
        """
        Updates the is_active status of a trade group.
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return None

        try:
            self.supabase.from_("trades").update({"is_active": is_active}).eq("trade_group_id", trade_group_id).execute()
            logger.info(f"Set is_active={is_active} for trade group {trade_group_id}")
        except Exception as e:
            logger.error(f"Error updating trade status for {trade_group_id}: {e}", exc_info=True)

    async def insert_transaction_history(self, transaction_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Insert a new transaction history record.
        
        Args:
            transaction_data: Dict with fields: time, type, amount, asset, symbol
            
        Returns:
            Inserted record or None if failed
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return None

        try:
            # Convert time from milliseconds to ISO format if it's a number
            if 'time' in transaction_data and isinstance(transaction_data['time'], (int, float)):
                # Convert milliseconds to datetime and then to ISO format
                from datetime import datetime, timezone
                dt = datetime.fromtimestamp(transaction_data['time'] / 1000, tz=timezone.utc)
                transaction_data['time'] = dt.isoformat()

            response = self.supabase.from_("transaction_history").insert(transaction_data).execute()
            if response.data:
                logger.info(f"Successfully inserted transaction history record: {transaction_data}")
                return response.data[0]
            else:
                logger.error("Failed to insert transaction history record: no data returned")
                return None
        except Exception as e:
            logger.error(f"Error inserting transaction history record: {e}", exc_info=True)
            return None

    async def insert_transaction_history_batch(self, transactions: List[Dict[str, Any]]) -> bool:
        """
        Insert multiple transaction history records in batch.
        
        Args:
            transactions: List of transaction data dictionaries
            
        Returns:
            True if successful, False otherwise
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return False

        if not transactions:
            logger.warning("No transactions provided for batch insert")
            return True

        try:
            # Convert time from milliseconds to ISO format for all transactions
            from datetime import datetime, timezone
            for transaction in transactions:
                if 'time' in transaction and isinstance(transaction['time'], (int, float)):
                    dt = datetime.fromtimestamp(transaction['time'] / 1000, tz=timezone.utc)
                    transaction['time'] = dt.isoformat()

            response = self.supabase.from_("transaction_history").insert(transactions).execute()
            logger.info(f"Successfully inserted {len(transactions)} transaction history records")
            return True
        except Exception as e:
            logger.error(f"Error inserting transaction history batch: {e}", exc_info=True)
            return False

    async def get_transaction_history(self, symbol: str = "", start_time: int = 0, end_time: int = 0, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get transaction history records with optional filtering.
        
        Args:
            symbol: Filter by symbol
            start_time: Filter by start time (milliseconds)
            end_time: Filter by end time (milliseconds)
            limit: Maximum number of records to return
            
        Returns:
            List of transaction history records
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return []

        try:
            query = self.supabase.from_("transaction_history").select("*")
            
            if symbol:
                query = query.eq("symbol", symbol)
            if start_time:
                # Convert milliseconds to ISO format for filtering
                from datetime import datetime, timezone
                start_dt = datetime.fromtimestamp(start_time / 1000, tz=timezone.utc)
                query = query.gte("time", start_dt.isoformat())
            if end_time:
                # Convert milliseconds to ISO format for filtering
                from datetime import datetime, timezone
                end_dt = datetime.fromtimestamp(end_time / 1000, tz=timezone.utc)
                query = query.lte("time", end_dt.isoformat())
            
            query = query.order("time", desc=True).limit(limit)
            response = query.execute()
            
            return response.data or []
        except Exception as e:
            logger.error(f"Error getting transaction history: {e}", exc_info=True)
            return []

    async def get_last_transaction_sync_time(self) -> int:
        """
        Get the timestamp of the most recent transaction in our database.
        This is used to avoid re-syncing transactions we already have.
        
        Returns:
            Timestamp in milliseconds, or 0 if no transactions exist
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return 0

        try:
            response = self.supabase.from_("transaction_history").select("time").order("time", desc=True).limit(1).execute()
            
            if response.data and response.data[0]['time']:
                # Convert ISO time back to milliseconds
                from datetime import datetime, timezone
                dt = datetime.fromisoformat(response.data[0]['time'].replace('Z', '+00:00'))
                return int(dt.timestamp() * 1000)
            return 0
        except Exception as e:
            logger.error(f"Error getting last transaction sync time: {e}", exc_info=True)
            return 0

    async def check_transaction_exists(self, time: int, type: str, amount: float, asset: str, symbol: str) -> bool:
        """
        Check if a transaction record already exists to avoid duplicates.
        
        Args:
            time: Transaction timestamp in milliseconds
            type: Transaction type
            amount: Transaction amount
            asset: Asset name
            symbol: Trading symbol
            
        Returns:
            True if record exists, False otherwise
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return False

        try:
            # Ensure time is an integer
            if isinstance(time, str):
                time = int(time)
            
            # Convert time from milliseconds to ISO format for comparison
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(time / 1000, tz=timezone.utc)
            iso_time = dt.isoformat()
            
            # Use exact matching for ALL transaction types
            # If we already have a record with the exact same timestamp, type, amount, asset, and symbol, don't create another one
            response = self.supabase.from_("transaction_history").select("id").eq("time", iso_time).eq("type", type).eq("amount", amount).eq("asset", asset).eq("symbol", symbol).limit(1).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error checking transaction existence: {e}", exc_info=True)
            return False



    async def cleanup_transaction_duplicates(self, symbol: str = "", transaction_type: str = "") -> Dict[str, int]:
        """
        Clean up exact transaction duplicates, keeping only one copy of each unique transaction.
        
        Args:
            symbol: Optional symbol to limit cleanup to specific trading pair
            transaction_type: Optional transaction type to limit cleanup
            
        Returns:
            Dict with cleanup statistics
        """
        if not self.supabase:
            logger.error("Supabase client not available.")
            return {"cleaned": 0, "errors": 0}

        try:
            # Define transaction types to process
            if transaction_type:
                duplicate_types = [transaction_type]
            else:
                duplicate_types = ['COMMISSION', 'FUNDING_FEE', 'REALIZED_PNL', 'TRANSFER', 'WITHDRAW', 'DEPOSIT']
            
            cleaned_count = 0
            error_count = 0
            
            # Process each transaction type
            for tx_type in duplicate_types:
                logger.info(f"Cleaning up {tx_type} duplicates...")
                
                # Get all entries of this type
                query = self.supabase.from_("transaction_history").select("*").eq("type", tx_type)
                if symbol:
                    query = query.eq("symbol", symbol)
                
                response = query.execute()
                records = response.data or []
                
                # Group by unique combination of time, type, amount, asset, symbol
                groups = {}
                for record in records:
                    key = (record['time'], record['type'], record['amount'], record['asset'], record['symbol'])
                    if key not in groups:
                        groups[key] = []
                    groups[key].append(record)
                
                # Find groups with duplicates (more than 1 record)
                duplicate_groups = {key: records for key, records in groups.items() if len(records) > 1}
                
                for (time, tx_type, amount, asset, symbol), group_records in duplicate_groups.items():
                    # Keep the first record, delete the rest
                    records_to_delete = group_records[1:]
                    
                    for record in records_to_delete:
                        try:
                            # Delete the duplicate
                            self.supabase.from_("transaction_history").delete().eq("id", record['id']).execute()
                            cleaned_count += 1
                            logger.info(f"Cleaned duplicate {tx_type}: {symbol} at {time} amount {amount}")
                        except Exception as e:
                            logger.error(f"Error deleting duplicate {tx_type} record {record['id']}: {e}")
                            error_count += 1
            
            logger.info(f"Transaction cleanup completed: {cleaned_count} duplicates removed, {error_count} errors")
            return {"cleaned": cleaned_count, "errors": error_count}
            
        except Exception as e:
            logger.error(f"Error during transaction cleanup: {e}", exc_info=True)
            return {"cleaned": 0, "errors": 1}

def create_trades_table(supabase):
    """Create trades table if it doesn't exist"""
    try:
        # Check if table exists
        result = supabase.table("trades").select("id").limit(1).execute()
        logger.info("Trades table already exists")
    except Exception:
        # the table already exists, so we don't need to create it
        logger.info("Trades table already exists")
        return

def insert_trade(supabase, trade_data: dict) -> Optional[dict]:
    """Insert a new trade record"""
    try:
        result = supabase.table("trades").insert(trade_data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Failed to insert trade: {e}")
        return None

def update_trade_pnl(supabase, trade_id: int, pnl_data: dict) -> bool:
    """Update trade record with P&L data"""
    try:
        pnl_data['updated_at'] = datetime.now(timezone.utc).isoformat()
        supabase.table("trades").update(pnl_data).eq("id", trade_id).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to update trade P&L: {e}")
        return False

def get_trades_needing_pnl_sync(supabase) -> list:
    """Get trades that need P&L data sync"""
    try:
        # Get trades without P&L data or with old sync timestamp
        result = supabase.table("trades").select("*").or_(
            "entry_price.is.null,last_pnl_sync.is.null"
        ).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to get trades needing P&L sync: {e}")
        return []
import os
import asyncio
import logging
from dotenv import load_dotenv
from supabase import create_client, Client
from discord_bot.discord_bot import DiscordBot
from src.exchange.binance_exchange import BinanceExchange
import json
from config import settings

# --- Setup ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BINANCE_API_KEY = settings.BINANCE_API_KEY
BINANCE_API_SECRET = settings.BINANCE_API_SECRET
BINANCE_TESTNET = settings.BINANCE_TESTNET
SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_KEY = settings.SUPABASE_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = DiscordBot()
binance = BinanceExchange(BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_TESTNET)

async def reconcile_and_process():
    await binance._init_client()
    open_orders = await binance.client.futures_get_open_orders()
    logging.info(f"Fetched {len(open_orders)} open futures orders from Binance.")

    # Fetch all open trades from DB
    trades_resp = supabase.table("trades").select("*").eq("status", "OPEN").execute()
    trades = trades_resp.data if hasattr(trades_resp, "data") else []
    logging.info(f"Fetched {len(trades)} open trades from DB.")

    # Build lookup by orderId and clientOrderId
    trade_by_order_id = {}
    trade_by_client_id = {}
    for trade in trades:
        order_id = trade.get("exchange_order_id")
        if not order_id and trade.get("binance_response"):
            try:
                resp = json.loads(trade["binance_response"])
                order_id = str(resp.get("orderId"))
                client_id = resp.get("clientOrderId")
                if client_id:
                    trade_by_client_id[client_id] = trade
            except Exception:
                pass
        if order_id:
            trade_by_order_id[str(order_id)] = trade

    # For each open order, find the trade and relevant alerts
    for order in open_orders:
        order_id = str(order.get("orderId"))
        client_id = order.get("clientOrderId")
        trade = trade_by_order_id.get(order_id) or trade_by_client_id.get(client_id)
        if not trade:
            logging.warning(f"Orphaned open order on Binance: {order_id} (symbol={order.get('symbol')}). Attempting to cancel...")
            try:
                await binance.client.futures_cancel_order(symbol=order['symbol'], orderId=order_id)
                logging.info(f"Cancelled orphaned order {order_id} for symbol {order['symbol']}")
            except Exception as e:
                logging.error(f"Failed to cancel orphaned order {order_id}: {e}")
            continue

        # Find alerts for this trade
        trade_discord_id = trade.get("discord_id")
        alerts_resp = supabase.table("alerts").select("*").eq("trade", trade_discord_id).execute()
        alerts = alerts_resp.data if hasattr(alerts_resp, "data") else []

        # If trade is not closed, process the alert(s)
        for alert in alerts:
            # Only process if not already closed
            if not alert.get("parsed_alert") or (alert.get("parsed_alert") and alert["parsed_alert"].get("status") != "closed"):
                logging.info(f"Processing alert {alert['id']} for trade {trade_discord_id} (order {order_id})")
                # Advanced alert parsing
                content = alert.get("content", "").lower()
                details = {}
                action = None
                if "tp1" in content or "take profit 1" in content:
                    action = "take_profit_1"
                    if "close" in content and "%" in content:
                        try:
                            pct = int(content.split("close")[-1].split("%")[-2].split()[-1])
                            details["close_percentage"] = pct
                        except Exception:
                            details["close_percentage"] = 50
                    else:
                        details["close_percentage"] = 50
                elif "tp2" in content or "take profit 2" in content:
                    action = "take_profit_2"
                    details["close_percentage"] = 25
                elif "tp3" in content or "take profit 3" in content:
                    action = "take_profit_3"
                    details["close_percentage"] = 25
                elif "move stop" in content or "sl to be" in content or "stop to be" in content:
                    action = "stop_loss_update"
                    details["stop_price"] = "BE"
                elif "stopped out" in content or "stop loss hit" in content:
                    action = "stop_loss_hit"
                elif "close" in content:
                    action = "position_closed"
                    if "%" in content:
                        try:
                            pct = int(content.split("close")[-1].split("%")[-2].split()[-1])
                            details["close_percentage"] = pct
                        except Exception:
                            details["close_percentage"] = 100
                    else:
                        details["close_percentage"] = 100
                else:
                    action = None

                signal_payload = {
                    "timestamp": alert.get("timestamp"),
                    "content": alert.get("content"),
                    "trade": alert.get("trade"),
                    "discord_id": alert.get("discord_id"),
                    "trader": alert.get("trader"),
                    "structured": alert.get("structured"),
                }
                if action:
                    signal_payload["action"] = action
                    signal_payload["details"] = details
                result = await bot.process_update_signal(signal_payload, alert_id=alert["id"])
                logging.info(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(reconcile_and_process())
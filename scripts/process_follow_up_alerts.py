import os
import time
import requests
import json
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables from .env file
load_dotenv()

# Get Supabase credentials from environment variables
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")

if not supabase_url or not supabase_key:
    print("Error: SUPABASE_URL and SUPABASE_KEY must be set in the .env file.")
    exit(1)

# Supabase client initialization
try:
    supabase: Client = create_client(supabase_url, supabase_key)
    print("Successfully connected to Supabase.")
except Exception as e:
    print(f"Error connecting to Supabase: {e}")
    exit(1)

def parse_alert_content(content, original_trade_data):
    """
    Parse alert content and determine what action should be taken.
    Returns structured data for logging.
    """
    content_lower = content.lower()

    # Safely extract coin symbol with fallback
    coin_symbol = 'UNKNOWN'
    if original_trade_data and isinstance(original_trade_data.get('parsed_signal'), dict):
        coin_symbol = original_trade_data.get('parsed_signal', {}).get('coin_symbol', 'UNKNOWN')

    # Determine action type and details
    if "stopped out" in content_lower or "stop loss" in content_lower or "stopped be" in content_lower:
        return {
            "action_type": "stop_loss_hit",
            "action_description": f"Stop loss hit for {coin_symbol}",
            "binance_action": "MARKET_SELL",
            "position_status": "CLOSED",
            "reason": "Stop loss triggered"
        }

    elif "closed" in content_lower and ("profit" in content_lower or "be" in content_lower):
        return {
            "action_type": "position_closed",
            "action_description": f"Position closed for {coin_symbol}",
            "binance_action": "MARKET_SELL",
            "position_status": "CLOSED",
            "reason": "Manual close" if "profit" in content_lower else "Break even close"
        }

    elif "tp1" in content_lower:
        return {
            "action_type": "take_profit_1",
            "action_description": f"Take Profit 1 hit for {coin_symbol}",
            "binance_action": "PARTIAL_SELL",
            "position_status": "PARTIALLY_CLOSED",
            "reason": "TP1 target reached"
        }

    elif "tp2" in content_lower:
        return {
            "action_type": "take_profit_2",
            "action_description": f"Take Profit 2 hit for {coin_symbol}",
            "binance_action": "PARTIAL_SELL",
            "position_status": "PARTIALLY_CLOSED",
            "reason": "TP2 target reached"
        }

    elif "stops moved to be" in content_lower or "sl to be" in content_lower:
        return {
            "action_type": "stop_loss_update",
            "action_description": f"Stop loss moved to break even for {coin_symbol}",
            "binance_action": "UPDATE_STOP_ORDER",
            "position_status": "ACTIVE",
            "reason": "Risk management - move to break even"
        }

    elif "limit order cancelled" in content_lower:
        return {
            "action_type": "order_cancelled",
            "action_description": f"Limit order cancelled for {coin_symbol}",
            "binance_action": "CANCEL_ORDER",
            "position_status": "CANCELLED",
            "reason": "Order cancellation"
        }

    else:
        return {
            "action_type": "unknown_update",
            "action_description": f"Update for {coin_symbol}: {content}",
            "binance_action": "NO_ACTION",
            "position_status": "UNKNOWN",
            "reason": "Unrecognized alert type"
        }

def process_alerts():
    """
    Process alerts from the alerts table and update parsed_alert column
    with structured logging information.
    """
    try:
        # Fetch all alerts that haven't been processed yet (where parsed_alert is null)
        response = supabase.table("alerts").select("*").is_("parsed_alert", "null").execute()

        if not hasattr(response, 'data') or not response.data:
            print("No unprocessed alerts found.")
            return

        alerts = response.data
        print(f"Found {len(alerts)} unprocessed alerts.")

        for alert in alerts:
            print(f"\nProcessing alert ID {alert['id']}: {alert['content']}")

            try:
                # Get the original trade data
                trade_response = supabase.table("trades").select("*").eq("discord_id", alert["trade"]).execute()

                if not trade_response.data:
                    print(f"Warning: No original trade found for discord_id {alert['trade']}")
                    # Still create a parsed_alert entry for tracking
                    parsed_alert_data = {
                        "alert_id": alert["id"],
                        "original_content": alert["content"],
                        "processed_at": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                        "error": "Original trade not found",
                        "coin_symbol": "UNKNOWN",
                        "trader": alert["trader"]
                    }
                else:
                    original_trade = trade_response.data[0]

                    # Parse the alert content
                    parsed_action = parse_alert_content(alert["content"], original_trade)

                    # Create the parsed_alert data structure
                    parsed_alert_data = {
                        "alert_id": alert["id"],
                        "original_content": alert["content"],
                        "processed_at": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                        "action_determined": parsed_action,
                        "original_trade_id": original_trade.get("id"),
                        "coin_symbol": original_trade.get('parsed_signal', {}).get('coin_symbol', 'UNKNOWN') if original_trade.get('parsed_signal') else 'UNKNOWN',
                        "trader": alert["trader"]
                    }

                # Update the alerts table with parsed information
                update_response = supabase.table("alerts").update({
                    "parsed_alert": parsed_alert_data
                }).eq("id", alert["id"]).execute()

                if "error" in parsed_alert_data:
                    print(f"⚠ Updated alert ID {alert['id']} - Error: {parsed_alert_data['error']}")
                else:
                    print(f"✓ Updated alert ID {alert['id']} - Action: {parsed_action['action_type']}")

            except Exception as e:
                print(f"Error processing alert ID {alert['id']}: {e}")
                # Create an error entry
                try:
                    error_data = {
                        "alert_id": alert["id"],
                        "original_content": alert["content"],
                        "processed_at": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                        "error": str(e),
                        "trader": alert.get("trader", "UNKNOWN")
                    }
                    supabase.table("alerts").update({
                        "parsed_alert": error_data
                    }).eq("id", alert["id"]).execute()
                except:
                    pass  # If we can't even save the error, just continue

            # Small delay between processing
            time.sleep(0.5)

    except Exception as e:
        print(f"Error processing alerts: {e}")

if __name__ == "__main__":
    process_alerts()
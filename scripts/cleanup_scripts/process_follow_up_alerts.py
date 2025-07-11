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
    Returns a structured command for execution.
    """
    content_lower = content.lower()

    # Safely extract coin symbol for context, though not part of the command
    coin_symbol = 'UNKNOWN'
    if original_trade_data and isinstance(original_trade_data.get('parsed_signal'), dict):
        coin_symbol = original_trade_data.get('parsed_signal', {}).get('coin_symbol', 'UNKNOWN')

    # Determine the command to be executed
    if "stopped out" in content_lower or "stop loss" in content_lower or "stopped be" in content_lower:
        return {
            "action_type": "CLOSE_POSITION",
            "reason": f"Stop loss hit for {coin_symbol}"
        }

    elif "closed" in content_lower and ("profit" in content_lower or "be" in content_lower):
        return {
            "action_type": "CLOSE_POSITION",
            "reason": "Position closed manually"
        }

    elif "tp1" in content_lower:
        return {
            "action_type": "TAKE_PROFIT",
            "value": 1,
            "reason": f"TP1 hit for {coin_symbol}"
        }

    elif "tp2" in content_lower:
        return {
            "action_type": "TAKE_PROFIT",
            "value": 2,
            "reason": f"TP2 hit for {coin_symbol}"
        }

    elif "stops moved to be" in content_lower or "sl to be" in content_lower:
        return {
            "action_type": "UPDATE_SL",
            "value": "breakeven",
            "reason": f"Stop loss moved to break even for {coin_symbol}"
        }

    elif "limit order cancelled" in content_lower:
        return {
            "action_type": "CANCEL_ORDER",
            "reason": f"Limit order cancelled for {coin_symbol}"
        }

    else:
        return {
            "action_type": "UNKNOWN",
            "reason": f"Unrecognized alert type for {coin_symbol}"
        }

def process_alerts():
    """
    Process alerts from the alerts table and update parsed_alert column
    with structured logging information.
    """
    try:
        # Fetch all alerts that haven't been processed yet (where parsed_alert is null)
        response = supabase.table("alerts").select("*").execute()

        if not hasattr(response, 'data') or not response.data:
            print("No unprocessed alerts found.")
            return

        alerts = response.data
        print(f"Found {len(alerts)} unprocessed alerts.")

        for alert in alerts:
            print(f"\nProcessing alert ID {alert['id']}: {alert['content']}")

            try:
                # Get the original trade data
                # Assuming 'trade' column in alerts links to 'discord_id' in trades
                response = supabase.table("trades").select("*").eq("discord_id", alert["trade"]).limit(1).execute()

                if not response.data:
                    print(f"Warning: No original trade found for discord_id {alert['trade']}")
                    parsed_alert_data = {
                        "error": "Original trade not found",
                        "original_content": alert["content"],
                    }
                else:
                    original_trade = response.data[0]

                    # Parse the alert content to get the executable command
                    command_to_execute = parse_alert_content(alert["content"], original_trade)

                    # This is what will be stored in the parsed_alert column
                    parsed_alert_data = command_to_execute

                # Update the alerts table with the parsed command
                update_response = supabase.table("alerts").update({
                    "parsed_alert": parsed_alert_data
                }).eq("id", alert["id"]).execute()

                if "error" in parsed_alert_data:
                    print(f"⚠ Updated alert ID {alert['id']} - Error: {parsed_alert_data['error']}")
                else:
                    print(f"✓ Updated alert ID {alert['id']} - Command: {parsed_alert_data}")

            except Exception as e:
                print(f"Error processing alert ID {alert['id']}: {e}")
                # Create an error entry
                try:
                    error_data = {
                        "error": str(e),
                        "original_content": alert.get("content", "N/A"),
                    }
                    supabase.table("alerts").update({
                        "parsed_alert": error_data
                    }).eq("id", alert["id"]).execute()
                except Exception as db_error:
                    print(f"Could not even save the error to the database: {db_error}")

            # Small delay between processing
            time.sleep(1) # Reduced for faster processing if needed

    except Exception as e:
        print(f"An error occurred in the main processing loop: {e}")

if __name__ == "__main__":
    process_alerts()
"""
Example: Enhanced Alert Processing with Timestamp-Based Order Matching

This example demonstrates how to use the enhanced SignalRouter to process alerts
that affect multiple orders in a position using timestamp-based matching.
"""

import asyncio
import json
from datetime import datetime, timezone
from src.bot.signal_router import SignalRouter
from src.bot.trading_engine import TradingEngine
from src.bot.kucoin_trading_engine import KucoinTradingEngine

async def example_alert_processing():
    """
    Example of processing an alert that affects multiple orders in a position.
    """

    # Initialize trading engines (you would use your actual configuration)
    binance_engine = None  # Initialize with your Binance engine
    kucoin_engine = None   # Initialize with your KuCoin engine

    # Initialize signal router
    signal_router = SignalRouter(binance_engine, kucoin_engine)

    # Example alert data (similar to your database structure)
    alert_data = {
        "coin_symbol": "ETH",
        "timestamp": "2025-09-12T00:45:26.771Z",
        "trader": "@Johnny",
        "action_determined": {
            "action_type": "stop_loss_hit",
            "coin_symbol": "ETH",
            "content": "ETH 🚀|  Stopped out  | @Johnny",
            "action_description": "Position closed for ETH",
            "binance_action": "MARKET_SELL",
            "position_status": "CLOSED",
            "reason": "Position closed"
        },
        "trade_group_id": "1e106c6b-6bee-459c-a29a-e514f97cdf8b"  # Optional grouping
    }

    # Process the alert using the enhanced router
    result = await signal_router.route_alert_signal(alert_data, "@Johnny")

    print("Alert Processing Result:")
    print(json.dumps(result, indent=2))

    # The result will contain:
    # - status: "success" or "error"
    # - message: Description of the processing
    # - results: List of individual order processing results
    # - total_orders_affected: Number of orders that were processed

async def example_followup_processing():
    """
    Example of processing a follow-up signal with enhanced order matching.
    """

    # Initialize signal router
    signal_router = SignalRouter(None, None)  # Use your actual engines

    # Example follow-up signal data
    followup_data = {
        "trade": "1415767167743557704",
        "content": "ETH 🚀|  Stopped out  | @Johnny",
        "timestamp": "2025-09-12T00:45:26.771Z",
        "parsed_alert": json.dumps({
            "coin_symbol": "ETH",
            "action_determined": {
                "action_type": "stop_loss_hit"
            }
        }),
        "trade_group_id": "1e106c6b-6bee-459c-a29a-e514f97cdf8b"
    }

    # Process the follow-up signal
    result = await signal_router.route_followup_signal(followup_data, "@Johnny")

    print("Follow-up Processing Result:")
    print(json.dumps(result, indent=2))

def demonstrate_timestamp_matching():
    """
    Demonstrate how timestamp matching works.
    """

    signal_router = SignalRouter(None, None)

    # Example timestamps from your data
    discord_timestamp = "2025-09-11T18:33:41.655Z"
    binance_update_time = 1757662264120  # milliseconds
    alert_timestamp = "2025-09-12T00:45:26.771Z"

    # Parse timestamps
    trade_time = signal_router._parse_discord_timestamp(discord_timestamp)
    binance_time = signal_router._convert_binance_timestamp(binance_update_time)
    alert_time = signal_router._parse_discord_timestamp(alert_timestamp)

    print(f"Trade time: {trade_time}")
    print(f"Binance time: {binance_time}")
    print(f"Alert time: {alert_time}")

    # Check if timestamps are within range
    is_within_range = signal_router._is_timestamp_within_range(
        alert_time, trade_time, binance_time, tolerance_minutes=5
    )

    print(f"Timestamps within range: {is_within_range}")

if __name__ == "__main__":
    print("Enhanced Alert Processing Example")
    print("=" * 50)

    # Demonstrate timestamp matching
    print("\n1. Timestamp Matching Demo:")
    demonstrate_timestamp_matching()

    # Note: The async examples would need actual trading engines to run
    print("\n2. Alert Processing Example (requires trading engines):")
    print("   - Initialize your trading engines")
    print("   - Call signal_router.route_alert_signal(alert_data, trader)")
    print("   - Process the results")

    print("\n3. Key Features:")
    print("   - Timestamp-based order matching")
    print("   - Support for multiple orders per position")
    print("   - Trade group ID support")
    print("   - Enhanced error handling and logging")
    print("   - Detailed processing results")

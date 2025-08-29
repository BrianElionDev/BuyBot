#!/usr/bin/env python3
"""
Test script for the enhanced update endpoint.
Sends a few test alerts to verify the parsing logic works.
"""

import requests
import time

# API endpoint
api_url = "http://0.0.0.0:8001/api/v1/discord/signal/update"
headers = {"Content-Type": "application/json"}

# Test cases
test_alerts = [
    {
        "discord_id": "test_123_stop_loss",
        "trader": "@TestTrader",
        "trade": "1384557844120207502",  # Use an existing trade discord_id
        "timestamp": "2025-07-01T15:30:00.000Z",
        "content": "ETH 🚀|trades🚀: Stopped BE @TestTrader"
    },
    {
        "discord_id": "test_124_tp1",
        "trader": "@TestTrader",
        "trade": "1384577137218027697",  # Use another existing trade discord_id
        "timestamp": "2025-07-01T15:35:00.000Z",
        "content": "ETH 🚀|trades🚀: TP1 & Stops moved to BE @TestTrader"
    },
    {
        "discord_id": "test_125_closed",
        "trader": "@TestTrader",
        "trade": "1384466390290927728",  # Use another existing trade discord_id
        "timestamp": "2025-07-01T15:40:00.000Z",
        "content": "HYPE 🚀|trades🚀: Closed in profits @TestTrader"
    }
]

def test_endpoint():
    print("Testing enhanced update endpoint...")

    for i, alert in enumerate(test_alerts, 1):
        print(f"\n--- Test {i}: {alert['content'][:50]}... ---")

        try:
            response = requests.post(api_url, json=alert, headers=headers)
            response.raise_for_status()

            print(f"✅ Status: {response.status_code}")
            print(f"✅ Response: {response.text}")

        except requests.exceptions.RequestException as e:
            print(f"❌ Error: {e}")

        # Small delay between requests
        time.sleep(2)

if __name__ == "__main__":
    test_endpoint()
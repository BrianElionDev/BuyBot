#!/usr/bin/env python3
"""
Debug script to test WebSocket order ID extraction logic.
"""

import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_order_id_extraction():
    """Test the order ID extraction logic from WebSocket messages."""
    
    # Sample WebSocket messages from the logs
    test_messages = [
        # ORDER_TRADE_UPDATE with NEW status
        {
            "e": "ORDER_TRADE_UPDATE",
            "T": 1756200698126,
            "E": 1756200698127,
            "o": {
                "s": "BTCUSDT",
                "c": "31364",
                "S": "BUY",
                "o": "MARKET",
                "f": "GTC",
                "q": "0.001",
                "p": "0",
                "ap": "0",
                "sp": "0",
                "x": "NEW",
                "X": "NEW",
                "i": 759476308787
            }
        },
        # ORDER_TRADE_UPDATE with FILLED status
        {
            "e": "ORDER_TRADE_UPDATE",
            "T": 1756200698126,
            "E": 1756200698127,
            "o": {
                "s": "BTCUSDT",
                "c": "31364",
                "S": "BUY",
                "o": "MARKET",
                "f": "GTC",
                "q": "0.001",
                "p": "0",
                "ap": "110287.7",
                "sp": "0",
                "x": "TRADE",
                "X": "FILLED",
                "i": 759476308787
            }
        }
    ]
    
    for i, message in enumerate(test_messages):
        logger.info(f"\n=== Testing Message {i+1} ===")
        logger.info(f"Message: {json.dumps(message, indent=2)}")
        
        # Test the extraction logic
        if 'o' in message:
            # This is an ORDER_TRADE_UPDATE event
            order_data = message['o']
            order_id = order_data.get('i')  # Binance order ID
            symbol = order_data.get('s')    # Symbol (e.g., 'BTCUSDT')
            status = order_data.get('X')    # Order status (NEW, FILLED, PARTIALLY_FILLED, etc.)
            executed_qty = float(order_data.get('z', 0))  # Cumulative filled quantity
            avg_price = float(order_data.get('ap', 0))    # Average fill price
            realized_pnl = float(order_data.get('Y', 0))  # Realized PnL from Binance
            side = order_data.get('S')      # Side (BUY/SELL)
            
            logger.info(f"Extracted from 'o' object:")
            logger.info(f"  order_id: {order_id} (type: {type(order_id)})")
            logger.info(f"  symbol: {symbol}")
            logger.info(f"  status: {status}")
            logger.info(f"  executed_qty: {executed_qty}")
            logger.info(f"  avg_price: {avg_price}")
            logger.info(f"  realized_pnl: {realized_pnl}")
            logger.info(f"  side: {side}")
        else:
            # This is a direct execution report
            order_id = message.get('i')  # Binance order ID
            symbol = message.get('s')    # Symbol (e.g., 'BTCUSDT')
            status = message.get('X')    # Order status (NEW, FILLED, PARTIALLY_FILLED, etc.)
            executed_qty = float(message.get('z', 0))  # Cumulative filled quantity
            avg_price = float(message.get('ap', 0))    # Average fill price
            realized_pnl = float(message.get('Y', 0))  # Realized PnL from Binance
            side = message.get('S')      # Side (BUY/SELL)
            
            logger.info(f"Extracted from root object:")
            logger.info(f"  order_id: {order_id} (type: {type(order_id)})")
            logger.info(f"  symbol: {symbol}")
            logger.info(f"  status: {status}")
            logger.info(f"  executed_qty: {executed_qty}")
            logger.info(f"  avg_price: {avg_price}")
            logger.info(f"  realized_pnl: {realized_pnl}")
            logger.info(f"  side: {side}")

if __name__ == "__main__":
    test_order_id_extraction()

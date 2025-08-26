#!/usr/bin/env python3
"""
Test script to debug WebSocket data structure and order ID extraction.
"""

import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_websocket_message_parsing():
    """Test parsing of WebSocket messages from the logs."""
    
    # Sample WebSocket messages from the actual logs (truncated)
    test_messages = [
        # This is what we see in the logs (truncated)
        '{"e":"ORDER_TRADE_UPDATE","T":1756200698126,"E":1756200698127,"o":{"s":"BTCUSDT","c":"31364","S":"BUY","o":"MARKET","f":"GTC","q":"0.001","p":"0","ap":"0","sp":"0","x":"NEW","X":"NEW","i":759476308787...',
        
        # This is what the complete message should look like
        '{"e":"ORDER_TRADE_UPDATE","T":1756200698126,"E":1756200698127,"o":{"s":"BTCUSDT","c":"31364","S":"BUY","o":"MARKET","f":"GTC","q":"0.001","p":"0","ap":"0","sp":"0","x":"NEW","X":"NEW","i":759476308787}}',
        
        # FILLED order
        '{"e":"ORDER_TRADE_UPDATE","T":1756200698126,"E":1756200698127,"o":{"s":"BTCUSDT","c":"31364","S":"BUY","o":"MARKET","f":"GTC","q":"0.001","p":"0","ap":"110287.7","sp":"0","x":"TRADE","X":"FILLED","i":759476308787}}'
    ]
    
    for i, message in enumerate(test_messages):
        logger.info(f"\n=== Testing Message {i+1} ===")
        logger.info(f"Original message: {message}")
        
        try:
            # Parse the JSON
            data = json.loads(message)
            logger.info(f"Parsed data: {data}")
            
            # Extract order data
            order_data = data.get('o', {})
            logger.info(f"Order data: {order_data}")
            
            # Extract order ID
            order_id = order_data.get('i', 'Unknown')
            logger.info(f"Order ID: {order_id} (type: {type(order_id)})")
            
            # Extract other fields
            symbol = order_data.get('s', 'Unknown')
            status = order_data.get('X', 'Unknown')
            executed_qty = float(order_data.get('z', 0))
            avg_price = float(order_data.get('ap', 0))
            
            logger.info(f"Symbol: {symbol}")
            logger.info(f"Status: {status}")
            logger.info(f"Executed Qty: {executed_qty}")
            logger.info(f"Avg Price: {avg_price}")
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            logger.info("This is expected for truncated messages")

if __name__ == "__main__":
    test_websocket_message_parsing()

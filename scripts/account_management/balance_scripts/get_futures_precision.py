#!/usr/bin/env python3
"""
Get precision information for Binance Futures symbols and create a precision mapping.
This helps ensure orders are placed with the correct decimal places.
"""

import os
import sys
import json
import logging
from config import settings

# Add the project root to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from binance.client import Client
from binance.exceptions import BinanceAPIException

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_futures_precision():
    """Extract precision information for all futures symbols and create mapping files."""
    try:
        # Load environment variables
        api_key = settings.BINANCE_API_KEY
        api_secret = settings.BINANCE_API_SECRET
        is_testnet = settings.BINANCE_TESTNET

        if not api_key or not api_secret:
            logging.error("BINANCE_API_KEY and BINANCE_API_SECRET must be set")
            return False

        # Initialize Binance client
        client = Client(api_key, api_secret, testnet=is_testnet)

        # Get futures exchange info
        logging.info("Fetching futures exchange info...")
        exchange_info = client.futures_exchange_info()

        # Extract precision information
        symbol_precision = {}
        price_precision = {}

        for symbol_info in exchange_info['symbols']:
            symbol = symbol_info['symbol']

            # Get quantity precision from LOT_SIZE filter
            quantity_precision = 8  # Default
            min_qty = 0.0
            max_qty = 0.0
            step_size = 0.0

            # Get price precision from PRICE_FILTER
            price_precision_val = 8  # Default
            min_price = 0.0
            max_price = 0.0
            tick_size = 0.0

            for filter_info in symbol_info['filters']:
                if filter_info['filterType'] == 'LOT_SIZE':
                    step_size = float(filter_info['stepSize'])
                    min_qty = float(filter_info['minQty'])
                    max_qty = float(filter_info['maxQty'])

                    # Calculate precision from step size
                    if step_size > 0:
                        step_str = f"{step_size:.10f}".rstrip('0')
                        if '.' in step_str:
                            quantity_precision = len(step_str.split('.')[1])
                        else:
                            quantity_precision = 0

                elif filter_info['filterType'] == 'PRICE_FILTER':
                    tick_size = float(filter_info['tickSize'])
                    min_price = float(filter_info['minPrice'])
                    max_price = float(filter_info['maxPrice'])

                    # Calculate precision from tick size
                    if tick_size > 0:
                        tick_str = f"{tick_size:.10f}".rstrip('0')
                        if '.' in tick_str:
                            price_precision_val = len(tick_str.split('.')[1])
                        else:
                            price_precision_val = 0

            symbol_precision[symbol] = {
                'quantity_precision': quantity_precision,
                'min_qty': min_qty,
                'max_qty': max_qty,
                'step_size': step_size,
                'base_asset': symbol_info['baseAsset'],
                'quote_asset': symbol_info['quoteAsset'],
                'status': symbol_info['status']
            }

            price_precision[symbol] = {
                'price_precision': price_precision_val,
                'min_price': min_price,
                'max_price': max_price,
                'tick_size': tick_size
            }

        logging.info(f"Found precision info for {len(symbol_precision)} futures symbols")

        # Save precision mapping to Python file
        precision_file = os.path.join(project_root, 'config', 'binance_futures_precision.py')
        with open(precision_file, 'w') as f:
            f.write('"""\n')
            f.write('Binance Futures Symbol Precision Information\n')
            f.write('Auto-generated file containing precision rules for futures trading.\n')
            f.write('"""\n\n')

            # Write quantity precision mapping
            f.write('# Quantity precision information for futures symbols\n')
            f.write('FUTURES_QUANTITY_PRECISION = {\n')
            for symbol, info in sorted(symbol_precision.items()):
                f.write(f'    "{symbol}": {{\n')
                f.write(f'        "quantity_precision": {info["quantity_precision"]},\n')
                f.write(f'        "min_qty": {info["min_qty"]},\n')
                f.write(f'        "max_qty": {info["max_qty"]},\n')
                f.write(f'        "step_size": {info["step_size"]},\n')
                f.write(f'        "base_asset": "{info["base_asset"]}",\n')
                f.write(f'        "quote_asset": "{info["quote_asset"]}",\n')
                f.write(f'        "status": "{info["status"]}"\n')
                f.write('    },\n')
            f.write('}\n\n')

            # Write price precision mapping
            f.write('# Price precision information for futures symbols\n')
            f.write('FUTURES_PRICE_PRECISION = {\n')
            for symbol, info in sorted(price_precision.items()):
                f.write(f'    "{symbol}": {{\n')
                f.write(f'        "price_precision": {info["price_precision"]},\n')
                f.write(f'        "min_price": {info["min_price"]},\n')
                f.write(f'        "max_price": {info["max_price"]},\n')
                f.write(f'        "tick_size": {info["tick_size"]}\n')
                f.write('    },\n')
            f.write('}\n\n')

            # Add helper functions
            f.write('def get_quantity_precision(symbol: str) -> int:\n')
            f.write('    """\n')
            f.write('    Get the quantity precision for a futures symbol.\n')
            f.write('    \n')
            f.write('    Args:\n')
            f.write('        symbol: Trading pair symbol (e.g., "BTCUSDT")\n')
            f.write('    \n')
            f.write('    Returns:\n')
            f.write('        Number of decimal places allowed for quantity\n')
            f.write('    """\n')
            f.write('    return FUTURES_QUANTITY_PRECISION.get(symbol, {}).get("quantity_precision", 8)\n\n')

            f.write('def get_price_precision(symbol: str) -> int:\n')
            f.write('    """\n')
            f.write('    Get the price precision for a futures symbol.\n')
            f.write('    \n')
            f.write('    Args:\n')
            f.write('        symbol: Trading pair symbol (e.g., "BTCUSDT")\n')
            f.write('    \n')
            f.write('    Returns:\n')
            f.write('        Number of decimal places allowed for price\n')
            f.write('    """\n')
            f.write('    return FUTURES_PRICE_PRECISION.get(symbol, {}).get("price_precision", 8)\n\n')

            f.write('def round_quantity(symbol: str, quantity: float) -> float:\n')
            f.write('    """\n')
            f.write('    Round quantity to the correct precision for a futures symbol.\n')
            f.write('    \n')
            f.write('    Args:\n')
            f.write('        symbol: Trading pair symbol (e.g., "BTCUSDT")\n')
            f.write('        quantity: Quantity to round\n')
            f.write('    \n')
            f.write('    Returns:\n')
            f.write('        Rounded quantity\n')
            f.write('    """\n')
            f.write('    precision = get_quantity_precision(symbol)\n')
            f.write('    return round(quantity, precision)\n\n')

            f.write('def round_price(symbol: str, price: float) -> float:\n')
            f.write('    """\n')
            f.write('    Round price to the correct precision for a futures symbol.\n')
            f.write('    \n')
            f.write('    Args:\n')
            f.write('        symbol: Trading pair symbol (e.g., "BTCUSDT")\n')
            f.write('        price: Price to round\n')
            f.write('    \n')
            f.write('    Returns:\n')
            f.write('        Rounded price\n')
            f.write('    """\n')
            f.write('    precision = get_price_precision(symbol)\n')
            f.write('    return round(price, precision)\n\n')

            f.write('def validate_quantity(symbol: str, quantity: float) -> bool:\n')
            f.write('    """\n')
            f.write('    Validate if quantity meets minimum requirements for a futures symbol.\n')
            f.write('    \n')
            f.write('    Args:\n')
            f.write('        symbol: Trading pair symbol (e.g., "BTCUSDT")\n')
            f.write('        quantity: Quantity to validate\n')
            f.write('    \n')
            f.write('    Returns:\n')
            f.write('        True if quantity is valid, False otherwise\n')
            f.write('    """\n')
            f.write('    info = FUTURES_QUANTITY_PRECISION.get(symbol, {})\n')
            f.write('    min_qty = info.get("min_qty", 0)\n')
            f.write('    max_qty = info.get("max_qty", float("inf"))\n')
            f.write('    \n')
            f.write('    return min_qty <= quantity <= max_qty\n')

        logging.info(f"✅ Precision mapping saved to: {precision_file}")

        # Also save a JSON version for reference
        json_file = os.path.join(project_root, 'config', 'binance_futures_precision.json')
        with open(json_file, 'w') as f:
            json.dump({
                'quantity_precision': symbol_precision,
                'price_precision': price_precision
            }, f, indent=2)

        logging.info(f"✅ JSON precision data saved to: {json_file}")

        # Print some examples
        print("\n📊 Sample precision information:")
        common_symbols = ['BTCUSDT', 'ETHUSDT', 'ADAUSDT', 'DOGEUSDT', 'SOLUSDT']
        for symbol in common_symbols:
            if symbol in symbol_precision:
                q_info = symbol_precision[symbol]
                p_info = price_precision[symbol]
                print(f"   {symbol}:")
                print(f"     Quantity: {q_info['quantity_precision']} decimal places (min: {q_info['min_qty']}, step: {q_info['step_size']})")
                print(f"     Price: {p_info['price_precision']} decimal places (tick: {p_info['tick_size']})")

        return True

    except BinanceAPIException as e:
        logging.error(f"Binance API error: {e}")
        return False
    except Exception as e:
        logging.error(f"Error getting precision info: {e}")
        return False

if __name__ == "__main__":
    success = get_futures_precision()
    if success:
        print("\n🎉 Futures precision information extracted successfully!")
    else:
        print("\n❌ Failed to extract precision information")
        sys.exit(1)
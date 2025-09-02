import logging
import re
from typing import Dict, Optional, Tuple
import json
import openai
from config import settings

logger = logging.getLogger(__name__)

def extract_quantity_from_signal(signal_content: str) -> tuple:
    """
    Extract quantity and coin symbol from signals like "1000TOSHI|Entry:|0.7172|SL:|0.692"
    Returns: (quantity, coin_symbol, cleaned_signal)
    """
    if not signal_content:
        return None, None, signal_content

    # Common memecoin patterns with known symbols
    memecoin_patterns = [
        (r'^(\d+)(PEPE)', 'PEPE'),
        (r'^(\d+)(TOSHI)', 'TOSHI'),
        (r'^(\d+)(TURBO)', 'TURBO'),
        (r'^(\d+)(FARTCOIN)', 'FARTCOIN'),
        (r'^(\d+)(HYPE)', 'HYPE'),
        (r'^(\d+)(DOGE)', 'DOGE'),
        (r'^(\d+)(SHIB)', 'SHIB'),
        (r'^(\d+)(BONK)', 'BONK'),
        (r'^(\d+)(WIF)', 'WIF'),
        (r'^(\d+)(FLOKI)', 'FLOKI'),
        # Generic pattern for other coins (less greedy)
        (r'^(\d+)([A-Z]{2,10})', None),  # 2-10 uppercase letters
    ]

    for pattern, expected_symbol in memecoin_patterns:
        match = re.match(pattern, signal_content)
        if match:
            quantity = int(match.group(1))
            coin_symbol = match.group(2)

            # Use expected symbol if provided, otherwise use matched symbol
            final_symbol = expected_symbol if expected_symbol else coin_symbol

            # Remove the quantity prefix from the signal
            cleaned_signal = signal_content.replace(f"{quantity}{coin_symbol}", final_symbol, 1)
            logger.info(f"Detected quantity prefix: {quantity}{coin_symbol} -> {final_symbol}")
            return quantity, final_symbol, cleaned_signal

    return None, None, signal_content

# --- OpenAI setup ---
# It's good practice to handle the case where the key might be missing.
api_key = settings.OPENAI_API_KEY
if not api_key:
    logger.warning("OPENAI_API_KEY not found. AI parsing disabled.")
    client = None
else:
    client = openai.AsyncOpenAI(api_key=api_key)

async def _get_coin_symbol_from_signal(signal_content: str) -> Optional[str]:
    """
    A cheap and fast AI call to extract just the coin symbol from the signal.
    """
    if not client: return None
    try:
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an assistant that extracts the main coin symbol (like BTC, ETH, SOL) from a trading signal text. Respond with ONLY the symbol in uppercase. For 'Eth limit long 2382 - 2354', you reply 'ETH'."},
                {"role": "user", "content": signal_content},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content
        if not content:
            logger.error("Could not extract symbol from signal: OpenAI response content is empty.")
            return None

        symbol = content.strip().upper()
        logger.info(f"Extracted symbol '{symbol}' from signal.")
        return symbol
    except Exception as e:
        logger.error(f"Could not extract symbol from signal: {e}")
        return None

async def _parse_with_openai(signal_content: str, active_trade: Optional[Dict] = None) -> Optional[Dict]:
    if not client:
        logger.error("OpenAI client not initialized.")
        return None

    if active_trade:
        # This is a TRADE UPDATE
        system_prompt = f"""
        You are an expert financial analyst. Your task is to parse an update for an existing trade.
        The existing trade is for {active_trade.get('coin_symbol')} with entry price around {active_trade.get('entry_prices')}.
        Analyze the new signal and determine the action to take based on the following rules.

        - If the signal mentions moving stops to 'BE' or 'breakeven', respond with: {{"action_type": "UPDATE_SL", "value": "BE"}}
        - If the signal mentions a new stop loss price (e.g., 'stops moved to 123', 'new SL 123'), respond with: {{"action_type": "UPDATE_SL", "value": 123}}
        - If it provides a new entry price (e.g., 'market entered at 456', 'new entry 456'), respond with: {{"action_type": "UPDATE_ENTRY", "value": 456}}
        - If it mentions a take profit level being hit (e.g., 'TP1 hit'), respond with: {{"action_type": "TAKE_PROFIT", "value": 1}}
        - If the signal says 'limit order filled', you MUST respond with: {{"action_type": "ORDER_FILLED"}}
        - If it says to close or exit the trade (e.g., 'closed in loss'), respond with: {{"action_type": "CLOSE_POSITION"}}
        - If it says an order was cancelled (e.g., 'limit order cancelled'), respond with: {{"action_type": "ORDER_CANCELLED"}}

        If the action has a value, include it. If not, just provide the action_type.
        Return ONLY the JSON object.
        """
        user_prompt = f"Parse this trade update signal: `{signal_content}`"
        expected_keys = ["action_type"]
    else:
        # This is a NEW TRADE
        system_prompt = """
        You are an expert financial analyst. Your task is to parse trading signals from text
        and convert them into a structured JSON format. You must identify the coin symbol,
        position type, entry prices, stop loss, and take profit levels.

        CRITICAL RULES - ALL FIELDS ARE REQUIRED:
        - 'coin_symbol': The ticker (e.g., BTC, ETH, SOL, PUMPFUN). This is the MOST IMPORTANT field.
          NEVER abbreviate or truncate the coin symbol. If you see "BTC", return "BTC", not "TC".
          If you see "ETH", return "ETH", not "ET". If you see "SOL", return "SOL", not "OL".
          If you see "PUMPFUN", return "PUMPFUN", not "UMPFUN".
          Common symbols: BTC, ETH, SOL, ADA, DOT, LINK, UNI, AAVE, MATIC, AVAX, NEAR, FTM, ALGO, ATOM, XRP, DOGE, SHIB, PEPE, BONK, WIF, FLOKI, TOSHI, TURBO, HYPE, FARTCOIN, PUMPFUN, DSYNC.

        - 'position_type': MUST be 'LONG' or 'SHORT'. Look for these exact words:
          * LONG: "long", "longed", "buy", "bought", "going long", "longing"
          * SHORT: "short", "shorted", "sell", "sold", "going short", "shorting"
          * If the signal says "Shorted BTC" or "Short BTC", position_type MUST be "SHORT"
          * If the signal says "Longed BTC" or "Long BTC", position_type MUST be "LONG"
          * Default to 'LONG' only if no position direction is mentioned at all.
          * THIS FIELD IS MANDATORY - NEVER return null or omit it.

        - 'entry_prices': A list of floats. Consolidate all entry points, including price ranges (e.g., "2567/2546") and DCA levels, into this list.
        - 'stop_loss': A float or a string. If it's a simple price, make it a float. If it's a condition like 'BE', '4h close below 212', or '2x 5m < 104900', keep it as a string.
        - 'take_profits': A list of floats.
        - 'order_type': Should be 'MARKET', 'LIMIT', or 'SPOT'. Infer this from the text. If specific entry prices are given, it's a 'LIMIT' order. If "spot" is mentioned, it's 'SPOT'. If "now" or "market" is mentioned, it's 'MARKET'. Default to 'LIMIT' if entry prices are present.
        - 'risk_level': A string describing any risk instructions, like "1% risk" or "Half risk". If not present, this key should be null.
        - If a value (like take_profits) is not present in the signal, the corresponding JSON key should have a value of null.

        EXAMPLES:
        - "Shorted BTC 111100 sl 112392" → {"coin_symbol": "BTC", "position_type": "SHORT", "entry_prices": [111100], "stop_loss": 112392, "take_profits": null, "order_type": "MARKET"}
        - "Longed ETH 4525 sl 4432" → {"coin_symbol": "ETH", "position_type": "LONG", "entry_prices": [4525], "stop_loss": 4432, "take_profits": null, "order_type": "MARKET"}
        - "BTC limit short 113811-144680 sl 116189" → {"coin_symbol": "BTC", "position_type": "SHORT", "entry_prices": [113811, 144680], "stop_loss": 116189, "take_profits": null, "order_type": "LIMIT"}

        Return ONLY the JSON object, without any explanatory text or markdown.
        """
        user_prompt = f"Parse this new trade signal: `{signal_content}`"
        expected_keys = ["coin_symbol", "entry_prices", "position_type"]

    try:
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,  # Reduced temperature for more consistent parsing
        )
        content = response.choices[0].message.content
        if not content:
            logger.error("OpenAI response content is empty.")
            return None
        parsed_data = json.loads(content)

        # Enhanced validation
        if not all(key in parsed_data for key in expected_keys):
            logger.warning(f"AI response missing expected keys for this context. Response: {parsed_data}")
            return None

        # Additional validation for required fields
        if not active_trade:
            if not parsed_data.get('coin_symbol'):
                logger.error("AI response missing coin_symbol")
                return None
            if not parsed_data.get('position_type'):
                logger.error("AI response missing position_type")
                return None
            if not parsed_data.get('entry_prices'):
                logger.error("AI response missing entry_prices")
                return None

        # Additional validation for coin symbols
        if not active_trade and parsed_data.get('coin_symbol'):
            coin_symbol = parsed_data['coin_symbol'].upper()
            # Check for common truncation errors
            if len(coin_symbol) < 2:
                logger.error(f"Coin symbol too short: {coin_symbol}")
                return None

            # Validate position type
            position_type = parsed_data.get('position_type')
            if not position_type:
                logger.error(f"Missing position_type in AI response")
                return None

            position_type = str(position_type).upper()
            if position_type not in ['LONG', 'SHORT']:
                logger.error(f"Invalid position type: {position_type}")
                return None

        logger.info(f"OpenAI parsed data: {parsed_data}")
        return parsed_data
    except Exception as e:
        logger.error(f"Error calling OpenAI API: {e}", exc_info=True)
        return None

class DiscordSignalParser:
    def __init__(self):
        # These can be kept for validation or other non-AI parsing logic if needed
        self.supported_order_types = ['LIMIT', 'MARKET', 'SPOT']

    async def get_coin_symbol(self, signal_content: str) -> Optional[str]:
        return await _get_coin_symbol_from_signal(signal_content)

    async def parse_new_trade_signal(self, signal_content: str) -> Optional[Dict]:
        # Preprocess to handle quantity prefixes like "1000TOSHI"
        quantity, coin_symbol, cleaned_signal = extract_quantity_from_signal(signal_content)

        # Parse the cleaned signal
        parsed_data = await _parse_with_openai(cleaned_signal)
        if not parsed_data:
            return None

        parsed_data['order_type'] = 'LIMIT' if "LIMIT" in signal_content.upper() else 'MARKET'
        if quantity and coin_symbol:
            # Add quantity information to the parsed data
            parsed_data['quantity_multiplier'] = quantity
            logger.info(f"Added quantity multiplier {quantity} for {coin_symbol}")

        return parsed_data

    async def parse_trade_update_signal(self, signal_content: str, active_trade: Dict) -> Optional[Dict]:
        return await _parse_with_openai(signal_content, active_trade=active_trade)

    def validate_signal(self, signal: Dict) -> Tuple[bool, Optional[str]]:
        if not signal.get('coin_symbol'):
            return False, "Missing coin symbol"

        order_type = signal.get('order_type', 'LIMIT').upper()
        if order_type != 'MARKET' and (not signal.get('signal_price') or signal['signal_price'] <= 0):
            return False, "Invalid signal price for non-market order"

        return True, None

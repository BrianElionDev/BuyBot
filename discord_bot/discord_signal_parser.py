import logging
from typing import Dict, List, Optional, Tuple
import json
import os
import openai
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# --- OpenAI setup ---
# It's good practice to handle the case where the key might be missing.
api_key = os.getenv("OPENAI_API_KEY")
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
        symbol = response.choices[0].message.content.strip().upper()
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
        Analyze the new signal and determine the action to take.

        - If the signal mentions moving stops to 'BE' or 'breakeven', the action is 'UPDATE_SL'. The value should be the original entry price.
        - If the signal mentions a new stop loss price, the action is 'UPDATE_SL' and the value is the new price.
        - If the signal mentions a take profit level being hit (e.g., 'TP1 hit'), the action is 'TAKE_PROFIT'.
        - If the signal is to close or exit the trade, the action is 'CLOSE_POSITION'.
        - Respond with a JSON object like: {{"action_type": "UPDATE_SL", "value": 123.45}} or {{"action_type": "TAKE_PROFIT", "value": 1}}.
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

        - 'coin_symbol': The ticker (e.g., BTC, ETH, HYPE). This is the most important field.
          It is almost always the first word of the signal. Extract it with high accuracy. Do not abbreviate or change it.
        - 'position_type': Should be 'LONG' or 'SHORT'. Infer this from words like "long", "longed", "short", "shorted". If not specified, default to 'LONG'.
        - 'entry_prices': A list of floats. Consolidate all entry points, including price ranges (e.g., "2567/2546") and DCA levels, into this list.
        - 'stop_loss': A float or a string. If it's a simple price, make it a float. If it's a condition like 'BE', '4h close below 212', or '2x 5m < 104900', keep it as a string.
        - 'take_profits': A list of floats.
        - 'order_type': Should be 'MARKET', 'LIMIT', or 'SPOT'. Infer this from the text. If specific entry prices are given, it's a 'LIMIT' order. If "spot" is mentioned, it's 'SPOT'. If "now" or "market" is mentioned, it's 'MARKET'. Default to 'LIMIT' if entry prices are present.
        - 'risk_level': A string describing any risk instructions, like "1% risk" or "Half risk". If not present, this key should be null.
        - If a value (like take_profits) is not present in the signal, the corresponding JSON key should have a value of null.

        Return ONLY the JSON object, without any explanatory text or markdown.
        """
        user_prompt = f"Parse this new trade signal: `{signal_content}`"
        expected_keys = ["coin_symbol", "entry_prices"]

    try:
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        parsed_data = json.loads(response.choices[0].message.content)

        # Basic validation
        if not all(key in parsed_data for key in expected_keys):
            logger.warning(f"AI response missing expected keys for this context. Response: {parsed_data}")
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
        return await _parse_with_openai(signal_content)

    async def parse_trade_update_signal(self, signal_content: str, active_trade: Dict) -> Optional[Dict]:
        return await _parse_with_openai(signal_content, active_trade=active_trade)

    def validate_signal(self, signal: Dict) -> Tuple[bool, Optional[str]]:
        if not signal.get('coin_symbol'):
            return False, "Missing coin symbol"

        order_type = signal.get('order_type', 'LIMIT').upper()
        if order_type != 'MARKET' and (not signal.get('signal_price') or signal['signal_price'] <= 0):
            return False, "Invalid signal price for non-market order"

        return True, None
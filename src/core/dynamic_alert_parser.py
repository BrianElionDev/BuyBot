"""
Dynamic Alert Parser

A unified, dynamic parser for processing follow-up trading alerts that can handle
any coin symbol and action type without hardcoded dependencies.
"""

import logging
import re
import json
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class DynamicAlertParser:
    """
    Dynamic parser for trading alerts that adapts to any coin symbol and action type.
    Uses AI-powered parsing with fallback regex patterns for maximum flexibility.
    """

    def __init__(self):
        """Initialize the dynamic alert parser."""
        self.openai_client = None
        self._initialize_openai()

    def _initialize_openai(self):
        """Initialize OpenAI client if API key is available."""
        try:
            from config import settings
            import openai

            api_key = settings.OPENAI_API_KEY
            if api_key:
                self.openai_client = openai.AsyncOpenAI(api_key=api_key)
                logger.info("OpenAI client initialized for dynamic parsing")
            else:
                logger.warning("OpenAI API key not found. Using regex fallback only.")
        except Exception as e:
            logger.warning(f"Failed to initialize OpenAI client: {e}")

    async def parse_alert_content(self, content: str, trade_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Parse alert content dynamically using AI with regex fallback.

        Args:
            content: The alert content to parse
            trade_context: Optional trade context for better parsing

        Returns:
            Dict containing parsed action information
        """
        if not content or not isinstance(content, str):
            return self._create_error_result("Invalid content provided")

        # Normalize/sanitize incoming text: strip zero-width and BOM/invisible characters, trim whitespace
        try:
            # Remove zero-width spaces and BOMs that break regex/AI parsing
            content = re.sub(r'[\u200B-\u200D\uFEFF]', '', content)
            # Normalize repeated whitespace
            content = re.sub(r'\s+', ' ', content or '').strip()
        except Exception:
            # Best-effort; proceed with original content if normalization fails
            pass

        # Try AI parsing first if available
        if self.openai_client:
            try:
                ai_result = await self._parse_with_ai(content, trade_context)
                if ai_result and ai_result.get('action_type') != 'unknown':
                    logger.info(f"AI parsing successful: {ai_result}")
                    return ai_result
            except Exception as e:
                logger.warning(f"AI parsing failed, falling back to regex: {e}")

        # Fallback to dynamic regex parsing
        regex_result = self._parse_with_regex(content)
        logger.info(f"Regex parsing result: {regex_result}")
        return regex_result

    async def _parse_with_ai(self, content: str, trade_context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Parse alert content using OpenAI for maximum flexibility.

        Args:
            content: Alert content to parse
            trade_context: Optional trade context

        Returns:
            Parsed result or None if parsing fails
        """
        try:
            if not self.openai_client:
                logger.error("OpenAI client not initialized")
                return None

            system_prompt = self._build_ai_system_prompt(trade_context)
            user_prompt = f"Parse this trading alert: `{content}`"

            response = await self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
            )

            response_content = response.choices[0].message.content
            if not response_content:
                logger.error("OpenAI response content is empty")
                return None

            result = json.loads(response_content)

            # Validate and enhance the result
            return self._validate_and_enhance_ai_result(result, content)

        except Exception as e:
            logger.error(f"AI parsing error: {e}")
            return None

    def _build_ai_system_prompt(self, trade_context: Optional[Dict[str, Any]] = None) -> str:
        """Build the system prompt for AI parsing."""
        context_info = ""
        if trade_context:
            context_info = f"""
            Trade Context:
            - Coin Symbol: {trade_context.get('coin_symbol', 'Unknown')}
            - Position Type: {trade_context.get('position_type', 'Unknown')}
            - Entry Price: {trade_context.get('entry_price', 'Unknown')}
            - Current Status: {trade_context.get('status', 'Unknown')}
            """

        return f"""You are an expert trading signal parser. Parse trading alerts and return a JSON object with the following structure:

{context_info}

Required JSON structure:
{{
    "action_type": "string", // One of: stop_loss_hit, position_closed, take_profit_1, take_profit_2, stop_loss_update, limit_order_cancelled, limit_order_filled, limit_order_not_filled, break_even, tp1_and_break_even, unknown
    "coin_symbol": "string", // Extract the coin symbol (e.g., BTC, ETH, SOL, PEPE, etc.)
    "action_description": "string", // Human-readable description
    "exchange_action": "string", // Exchange-specific action (MARKET_SELL, PARTIAL_SELL, UPDATE_STOP_ORDER, CANCEL_ORDER, NO_ACTION)
    "position_status": "string", // OPEN, CLOSED, PARTIALLY_CLOSED
    "reason": "string", // Reason for the action
    "stop_loss_price": "number|string|null", // New stop loss price if applicable
    "close_percentage": "number|null" // Percentage to close if partial
}}

Action Type Guidelines:
- stop_loss_hit: "stopped out", "stopped be", "stopped at", "stop loss hit" (when position is closed due to stop loss)
- position_closed: "closed in profit", "closed in loss", "closed be" (when position is manually closed)
- take_profit_1: "tp1", "take profit 1", "first target hit" (when only TP1 is mentioned)
- take_profit_2: "tp2", "take profit 2", "second target hit"
- stop_loss_update: "stops moved to", "stop loss updated to", "move stops to" (when moving to specific price)
- limit_order_cancelled: "limit order cancelled", "order cancelled"
- limit_order_filled: "limit order filled", "order filled"
- limit_order_not_filled: "limit order wasn't filled", "order not filled", "still valid"
- break_even: "stops moved to be", "moved to be", "break even" (when only moving stops to BE)
- tp1_and_break_even: "tp1 & stops moved to be", "tp1 and stops moved to be" (when BOTH TP1 AND stops moved to BE are mentioned)
- unknown: If no clear action can be determined

CRITICAL RULES:
1. If the alert mentions BOTH "TP1" AND "stops moved to BE" in the same message, use action_type "tp1_and_break_even"
2. "Stopped BE" means the stop loss was hit at break-even, so use "stop_loss_hit"
3. "Closed BE" means the position was manually closed at break-even, so use "position_closed"
4. Distinguish between "stopped" (stop loss hit) and "closed" (manual closure)

Coin Symbol Extraction:
- Extract the main coin symbol from the alert
- Handle any coin symbol format (BTC, ETH, PEPE, TOSHI, etc.)
- Return the symbol in uppercase

Return ONLY the JSON object, no additional text."""

    def _validate_and_enhance_ai_result(self, result: Dict[str, Any], original_content: str) -> Dict[str, Any]:
        """Validate and enhance AI parsing result."""
        # Ensure required fields
        required_fields = ['action_type', 'coin_symbol', 'action_description', 'exchange_action', 'position_status', 'reason']
        for field in required_fields:
            if field not in result:
                result[field] = self._get_default_value(field)

        # Validate action_type
        valid_actions = [
            'stop_loss_hit', 'position_closed', 'take_profit_1', 'take_profit_2',
            'stop_loss_update', 'limit_order_cancelled', 'limit_order_filled',
            'limit_order_not_filled', 'break_even', 'tp1_and_break_even', 'unknown'
        ]
        if result['action_type'] not in valid_actions:
            result['action_type'] = 'unknown'

        if result['action_type'] == 'take_profit_1' and result.get('close_percentage') is None:
            result['close_percentage'] = 50.0
        elif result['action_type'] == 'take_profit_2' and result.get('close_percentage') is None:
            result['close_percentage'] = 25.0
        elif result['action_type'] in ['stop_loss_hit', 'position_closed'] and result.get('close_percentage') is None:
            # Default full close for stop-loss or manual close
            result['close_percentage'] = 100.0

        # Enhance with additional data
        result['original_content'] = original_content
        result['parsed_at'] = datetime.now(timezone.utc).isoformat()
        result['parsing_method'] = 'ai'

        # Heuristic reclassification for vague alerts (regex-independent safety net)
        try:
            text = (original_content or "").lower()
            if result['action_type'] == 'unknown':
                if 'stop' in text and ('be' in text or 'break even' in text or 'breakeven' in text):
                    result['action_type'] = 'break_even'
                elif ('updated stop' in text) or ('stoploss' in text) or ('stops moved' in text):
                    result['action_type'] = 'stop_loss_update'
        except Exception:
            pass

        return result

    def _parse_with_regex(self, content: str) -> Dict[str, Any]:
        """
        Parse alert content using dynamic regex patterns.

        Args:
            content: Alert content to parse

        Returns:
            Parsed result
        """
        content_lower = content.lower()
        coin_symbol = self._extract_coin_symbol_dynamic(content)

        # Dynamic action detection patterns
        action_patterns = {
            'stop_loss_hit': [
                r'stopped\s+out', r'stopped\s+be', r'stopped\s+at\s+be',
                r'stop\s+loss\s+hit', r'stopped\s+breakeven'
            ],
            'position_closed': [
                r'closed\s+in\s+profit[s]?', r'closed\s+in\s+loss',
                r'closed\s+be\b', r'position\s+closed'
            ],
            'take_profit_1': [
                r'tp1\b', r'take\s+profit\s+1', r'first\s+target\s+hit'
            ],
            'take_profit_2': [
                r'tp2\b', r'take\s+profit\s+2', r'second\s+target\s+hit'
            ],
            'stop_loss_update': [
                r'stops?\s+moved\s+to\s+([-+]?\d*\.?\d+)',
                r'stop\s+loss\s+updated?\s+to\s+([-+]?\d*\.?\d+)',
                r'move\s+stops?\s+to\s+([-+]?\d*\.?\d+)'
            ],
            'limit_order_cancelled': [
                r'limit\s+order\s+cancelled?', r'order\s+cancelled?'
            ],
            'limit_order_filled': [
                r'limit\s+order\s+filled', r'order\s+filled'
            ],
            'limit_order_not_filled': [
                r'limit\s+order\s+wasn\'t\s+filled', r'order\s+not\s+filled',
                r'still\s+valid', r'wasn\'t\s+filled'
            ],
            'break_even': [
                r'stops?\s+moved\s+to\s+be', r'moved\s+to\s+be',
                r'stops?\s+to\s+be', r'break\s+even'
            ]
        }

        # Check for combined actions (e.g., "TP1 & stops moved to BE")
        combined_patterns = {
            'tp1_and_break_even': [
                r'tp1\s*&\s*stops?\s+moved\s+to\s+be',
                r'tp1\s*&\s*stops?\s+to\s+be',
                r'tp1\s+and\s+stops?\s+moved\s+to\s+be',
                r'tp1\s+and\s+stops?\s+to\s+be'
            ]
        }

        # Check combined patterns first
        for action_type, patterns in combined_patterns.items():
            for pattern in patterns:
                if re.search(pattern, content_lower):
                    return self._create_combined_action_result(action_type, coin_symbol, content, pattern)

        # Check individual patterns
        for action_type, patterns in action_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, content_lower)
                if match:
                    return self._create_action_result(action_type, coin_symbol, content, match, pattern)

        # Heuristic: handle common “updated stoploss” style messages without explicit price
        try:
            if 'updated stoploss' in content_lower or 'updated stop loss' in content_lower or 'updated sl' in content_lower:
                # Treat as stop loss update to break-even when price absent
                m = re.search(r'.', content_lower)
                if m:
                    result = self._create_action_result('stop_loss_update', coin_symbol, content, m, 'heuristic:updated_stoploss')
                    result['stop_loss_price'] = 'BE'
                    return result
                else:
                    # Construct minimal result if match cannot be created
                    return {
                        'action_type': 'stop_loss_update',
                        'coin_symbol': coin_symbol,
                        'action_description': self._get_action_description('stop_loss_update', coin_symbol),
                        'exchange_action': self._get_exchange_action('stop_loss_update'),
                        'position_status': self._get_position_status('stop_loss_update'),
                        'reason': self._get_action_reason('stop_loss_update', coin_symbol),
                        'original_content': content,
                        'parsed_at': datetime.now(timezone.utc).isoformat(),
                        'parsing_method': 'regex',
                        'matched_pattern': 'heuristic:updated_stoploss',
                        'stop_loss_price': 'BE'
                    }
        except Exception:
            pass

        # No pattern matched
        return self._create_unknown_result(coin_symbol, content)

    def _extract_coin_symbol_dynamic(self, content: str) -> Optional[str]:
        """
        Dynamically extract coin symbol from content.

        Args:
            content: Alert content

        Returns:
            Extracted coin symbol or None
        """
        if not content:
            return None

        # Remove common prefixes and suffixes
        cleaned = re.sub(r'[🚀|@\w+\s]*', '', content)

        # Extract symbol patterns
        patterns = [
            r'^([A-Z]{1,10})\s*[|🚀]',  # Symbol at start with separator
            r'[|🚀]\s*([A-Z]{1,10})\s*[|🚀]',  # Symbol between separators
            r'\b([A-Z]{2,10})\b',  # Any uppercase word 2-10 chars
            r'^([A-Z]{1,10})\s',  # Symbol at start followed by space
        ]

        for pattern in patterns:
            match = re.search(pattern, content.upper())
            if match:
                symbol = match.group(1)
                # Filter out common non-symbol words
                if symbol not in ['THE', 'AND', 'OR', 'TO', 'BE', 'AT', 'IN', 'ON', 'OF', 'FOR', 'WITH']:
                    logger.info(f"Extracted coin symbol: {symbol}")
                    return symbol

        logger.warning(f"No coin symbol found in content: {content}")
        return None

    def _create_action_result(self, action_type: str, coin_symbol: Optional[str],
                            content: str, match: re.Match, pattern: str) -> Dict[str, Any]:
        """Create result for a matched action."""
        result = {
            'action_type': action_type,
            'coin_symbol': coin_symbol,
            'action_description': self._get_action_description(action_type, coin_symbol),
            'exchange_action': self._get_exchange_action(action_type),
            'position_status': self._get_position_status(action_type),
            'reason': self._get_action_reason(action_type, coin_symbol),
            'original_content': content,
            'parsed_at': datetime.now(timezone.utc).isoformat(),
            'parsing_method': 'regex',
            'matched_pattern': pattern
        }

        # Add specific data based on action type
        if action_type == 'stop_loss_update' and match.groups():
            try:
                price = float(match.group(1))
                result['stop_loss_price'] = price
            except (ValueError, IndexError):
                result['stop_loss_price'] = 'BE'
        elif action_type in ['take_profit_1', 'take_profit_2']:
            result['close_percentage'] = 50 if action_type == 'take_profit_1' else 25
        elif action_type == 'position_closed':
            result['close_percentage'] = 100

        return result

    def _create_combined_action_result(self, action_type: str, coin_symbol: Optional[str],
                                     content: str, pattern: str) -> Dict[str, Any]:
        """Create result for combined actions."""
        result = {
            'action_type': 'tp1_and_break_even',
            'coin_symbol': coin_symbol,
            'action_description': f'TP1 hit and stop loss moved to break even for {coin_symbol}',
            'exchange_action': 'PARTIAL_SELL_AND_UPDATE_STOP_ORDER',
            'position_status': 'PARTIALLY_CLOSED',
            'reason': 'TP1 hit and risk management - move to break even',
            'stop_loss_price': 'BE',
            'close_percentage': 50,
            'original_content': content,
            'parsed_at': datetime.now(timezone.utc).isoformat(),
            'parsing_method': 'regex',
            'matched_pattern': pattern
        }
        return result

    def _create_unknown_result(self, coin_symbol: Optional[str], content: str) -> Dict[str, Any]:
        """Create result for unknown actions."""
        return {
            'action_type': 'unknown',
            'coin_symbol': coin_symbol,
            'action_description': f'Unknown action for {coin_symbol}',
            'exchange_action': 'NO_ACTION',
            'position_status': 'UNKNOWN',
            'reason': 'Unable to determine action from content',
            'original_content': content,
            'parsed_at': datetime.now(timezone.utc).isoformat(),
            'parsing_method': 'regex'
        }

    def _create_error_result(self, error_message: str) -> Dict[str, Any]:
        """Create error result."""
        return {
            'action_type': 'error',
            'coin_symbol': None,
            'action_description': 'Parsing error',
            'exchange_action': 'NO_ACTION',
            'position_status': 'UNKNOWN',
            'reason': error_message,
            'original_content': '',
            'parsed_at': datetime.now(timezone.utc).isoformat(),
            'parsing_method': 'error'
        }

    def _get_action_description(self, action_type: str, coin_symbol: Optional[str]) -> str:
        """Get human-readable action description."""
        descriptions = {
            'stop_loss_hit': f'Position closed for {coin_symbol}',
            'position_closed': f'Position closed for {coin_symbol}',
            'take_profit_1': f'Take Profit 1 hit for {coin_symbol}',
            'take_profit_2': f'Take Profit 2 hit for {coin_symbol}',
            'stop_loss_update': f'Stop loss updated for {coin_symbol}',
            'limit_order_cancelled': f'Limit order cancelled for {coin_symbol}',
            'limit_order_filled': f'Limit order filled for {coin_symbol}',
            'limit_order_not_filled': f'Limit order not filled for {coin_symbol}',
            'break_even': f'Stop loss moved to break even for {coin_symbol}',
            'unknown': f'Unknown action for {coin_symbol}'
        }
        return descriptions.get(action_type, f'Action for {coin_symbol}')

    def _get_exchange_action(self, action_type: str) -> str:
        """Get exchange-specific action."""
        actions = {
            'stop_loss_hit': 'MARKET_SELL',
            'position_closed': 'MARKET_SELL',
            'take_profit_1': 'PARTIAL_SELL',
            'take_profit_2': 'PARTIAL_SELL',
            'stop_loss_update': 'UPDATE_STOP_ORDER',
            'limit_order_cancelled': 'CANCEL_ORDER',
            'limit_order_filled': 'NO_ACTION',
            'limit_order_not_filled': 'NO_ACTION',
            'break_even': 'UPDATE_STOP_ORDER',
            'unknown': 'NO_ACTION'
        }
        return actions.get(action_type, 'NO_ACTION')

    def _get_position_status(self, action_type: str) -> str:
        """Get position status after action."""
        statuses = {
            'stop_loss_hit': 'CLOSED',
            'position_closed': 'CLOSED',
            'take_profit_1': 'PARTIALLY_CLOSED',
            'take_profit_2': 'PARTIALLY_CLOSED',
            'stop_loss_update': 'OPEN',
            'limit_order_cancelled': 'CLOSED',
            'limit_order_filled': 'OPEN',
            'limit_order_not_filled': 'OPEN',
            'break_even': 'OPEN',
            'unknown': 'UNKNOWN'
        }
        return statuses.get(action_type, 'UNKNOWN')

    def _get_action_reason(self, action_type: str, coin_symbol: Optional[str]) -> str:
        """Get action reason."""
        reasons = {
            'stop_loss_hit': 'Stop loss triggered',
            'position_closed': 'Position closed',
            'take_profit_1': 'TP1 target reached',
            'take_profit_2': 'TP2 target reached',
            'stop_loss_update': 'Stop loss updated',
            'limit_order_cancelled': 'Order cancelled',
            'limit_order_filled': 'Order filled - position now open',
            'limit_order_not_filled': 'Order not filled - still valid',
            'break_even': 'Risk management - move to break even',
            'unknown': 'Unable to determine reason'
        }
        return reasons.get(action_type, 'Unknown reason')

    def _get_default_value(self, field: str) -> Any:
        """Get default value for a field."""
        defaults = {
            'action_type': 'unknown',
            'coin_symbol': None,
            'action_description': 'Unknown action',
            'exchange_action': 'NO_ACTION',
            'position_status': 'UNKNOWN',
            'reason': 'Unknown reason'
        }
        return defaults.get(field, None)

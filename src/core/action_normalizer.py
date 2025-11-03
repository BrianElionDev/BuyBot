import re
from typing import Optional


class ActionNormalizer:
    """
    Normalize diverse follow-up action strings into a canonical internal schema
    that the bot understands.

    Canonical actions returned:
    - take_profit
    - take_profit_1 .. take_profit_5
    - stop_loss_hit
    - stop_loss_update
    - position_closed
    - limit_order_cancelled
    - order_filled (entry fills; may be handled upstream by execution detection)
    - unknown
    """

    @staticmethod
    def normalize(action_raw: Optional[str]) -> str:
        if not action_raw:
            return "unknown"

        text = str(action_raw).strip().lower()

        # Pass-through for already canonical actions used across engines
        passthrough = {
            "take_profit_1",
            "take_profit_2",
            "take_profit_3",
            "take_profit_4",
            "take_profit_5",
            "take_profit",
            "stop_loss_hit",
            "stop_loss_update",
            "position_closed",
            "limit_order_cancelled",
            "order_filled",
            "tp1_and_break_even",
            "break_even",
            "limit_order_not_filled",
        }
        if text in passthrough:
            # Normalize break_even to stop_loss_update for execution
            if text == "break_even":
                return "stop_loss_update"
            return text

        # Common TP variants: "tp1", "tp 1", "tp-1", "take profit 1"
        tp_match = re.match(r"^(?:tp|take\s*profit)[\s\-]*([1-5])$", text)
        if tp_match:
            return f"take_profit_{tp_match.group(1)}"

        # Generic take profit without index
        if text in {"tp", "take profit", "take_profit"}:
            return "take_profit"

        # Stop loss moved to BE / break-even updates
        if text in {
            "stopped be",
            "stops moved to be",
            "stop moved to be",
            "be",
            "move stop to be",
            "move sl to be",
        }:
            return "stop_loss_update"

        # Literal "break_even" variants
        if text in {"break even", "break_even"}:
            return "stop_loss_update"

        # Stop out variants
        if text in {"stopped out", "stop loss hit", "stop_loss_hit", "sl hit"}:
            return "stop_loss_hit"

        # Position closed / manual close
        if text in {"closed in profits", "closed", "position closed", "close position"}:
            return "position_closed"

        # Limit order cancelled
        if text in {"limit order cancelled", "limit cancelled", "order cancelled", "order canceled"}:
            return "limit_order_cancelled"

        # Order filled notifications (entry fills)
        if text in {"limit order filled", "limit_order_filled", "order filled", "filled"}:
            return "order_filled"

        # Order not filled / still valid acknowledgements
        if text in {"limit order not filled", "limit_order_not_filled", "order not filled", "still valid"}:
            return "limit_order_not_filled"

        return "unknown"



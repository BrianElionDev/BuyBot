from typing import Any, Dict


def normalize_exchange_response(exchange: str, response: Any) -> Dict[str, Any]:
    """
    Normalize raw exchange responses (Binance/KuCoin) into a unified dict shape.

    Ensures keys: orderId, clientOrderId, symbol, side, type, origQty,
    status, avgPrice (if available), price, stopPrice.
    """
    if response is None:
        return {}

    if not isinstance(response, dict):
        try:
            if hasattr(response, "__dict__"):
                response = dict(getattr(response, "__dict__"))
            else:
                return {}
        except Exception:
            return {}

    data: Dict[str, Any] = dict(response)

    if "clientOid" in data and "clientOrderId" not in data:
        data["clientOrderId"] = data.get("clientOid")
    if "size" in data and "origQty" not in data:
        data["origQty"] = str(data.get("size"))
    if "filledValue" in data and "filledSize" in data and "avgPrice" not in data:
        try:
            fs = float(data.get("filledSize") or 0)
            fv = float(data.get("filledValue") or 0)
            if fs > 0 and fv > 0:
                data["avgPrice"] = fv / fs
        except Exception:
            pass

    for k in ("orderId", "clientOrderId", "symbol", "side", "type", "status"):
        if k in data and data[k] is not None:
            data[k] = str(data[k])

    if "status" in data and isinstance(data["status"], str):
        data["status"] = data["status"].upper()

    return data



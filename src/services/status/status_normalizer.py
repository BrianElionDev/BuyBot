from typing import Optional


ALLOWED_STATUSES = {
    "PENDING",
    "ACTIVE",
    "OPEN",
    "CLOSED",
    "FAILED",
    "CANCELLED",
    "REJECTED",
    "PARTIALLY_FILLED",
    "MERGED",
}

_ALIASES = {
    "pending": "PENDING",
    "open": "OPEN",
    "active": "ACTIVE",
    "closed": "CLOSED",
    "failed": "FAILED",
    "fail": "FAILED",
    "cancelled": "CANCELLED",
    "canceled": "CANCELLED",
    "rejected": "REJECTED",
    "partial": "PARTIALLY_FILLED",
    "partially_filled": "PARTIALLY_FILLED",
    "merged": "MERGED",
}


def normalize_status(status: Optional[str]) -> str:
    if not status:
        return "PENDING"
    s = str(status).strip()
    if s in ALLOWED_STATUSES:
        return s
    up = s.upper()
    if up in ALLOWED_STATUSES:
        return up
    low = s.lower()
    mapped = _ALIASES.get(low)
    if mapped:
        return mapped
    # default to PENDING for unknowns
    return "PENDING"



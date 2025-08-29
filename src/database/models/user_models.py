"""
User Database Models

This module contains data models for user-related database operations.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum

class UserRole(Enum):
    """User role enumeration."""
    ADMIN = "ADMIN"
    TRADER = "TRADER"
    VIEWER = "VIEWER"
    ANALYST = "ANALYST"

class UserStatus(Enum):
    """User status enumeration."""
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    SUSPENDED = "SUSPENDED"
    PENDING = "PENDING"

@dataclass
class User:
    """User data model."""
    id: Optional[int] = None
    discord_id: str = ""
    username: str = ""
    email: Optional[str] = None
    role: str = UserRole.TRADER.value
    status: str = UserStatus.ACTIVE.value
    trader_name: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    testnet_enabled: bool = False
    max_position_size: Optional[float] = None
    risk_tolerance: Optional[str] = None
    notification_preferences: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_login: Optional[str] = None

@dataclass
class UserProfile:
    """User profile data model."""
    user_id: int
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    timezone: str = "UTC"
    language: str = "en"
    theme: str = "dark"
    trading_experience: Optional[str] = None
    preferred_pairs: List[str] = field(default_factory=list)
    risk_management_settings: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass
class UserSession:
    """User session data model."""
    id: Optional[int] = None
    user_id: int = 0
    session_token: str = ""
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    expires_at: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None
    last_activity: Optional[str] = None

@dataclass
class UserActivity:
    """User activity data model."""
    id: Optional[int] = None
    user_id: int = 0
    activity_type: str = ""
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: Optional[str] = None

@dataclass
class UserFilter:
    """User filter model for queries."""
    role: Optional[str] = None
    status: Optional[str] = None
    trader_name: Optional[str] = None
    discord_id: Optional[str] = None
    email: Optional[str] = None
    testnet_enabled: Optional[bool] = None

@dataclass
class UserUpdate:
    """User update model."""
    username: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    trader_name: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    testnet_enabled: Optional[bool] = None
    max_position_size: Optional[float] = None
    risk_tolerance: Optional[str] = None
    notification_preferences: Optional[Dict[str, Any]] = None
    last_login: Optional[str] = None

@dataclass
class UserStats:
    """User statistics model."""
    total_trades: int = 0
    successful_trades: int = 0
    failed_trades: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    avg_trade_pnl: float = 0.0
    max_drawdown: float = 0.0
    total_volume: float = 0.0
    active_positions: int = 0
    last_trade_date: Optional[str] = None

@dataclass
class UserSummary:
    """User summary model."""
    user: User = field(default_factory=User)
    profile: Optional[UserProfile] = None
    stats: UserStats = field(default_factory=UserStats)
    recent_activity: List[UserActivity] = field(default_factory=list)
    active_sessions: List[UserSession] = field(default_factory=list)

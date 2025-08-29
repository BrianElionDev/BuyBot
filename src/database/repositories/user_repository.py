"""
User Repository

This module provides user-specific database operations.
"""

import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from supabase import Client

from src.database.core.database_manager import DatabaseManager
from src.database.models.user_models import (
    User, UserProfile, UserSession, UserActivity, UserFilter, UserUpdate, UserStats, UserSummary
)

logger = logging.getLogger(__name__)

class UserRepository:
    """Repository for user-related database operations."""
    
    def __init__(self, db_manager: DatabaseManager):
        """Initialize the user repository."""
        self.db_manager = db_manager
        self.client = db_manager.client
    
    async def create_user(self, user_data: Dict[str, Any]) -> Optional[User]:
        """Create a new user record."""
        try:
            # Add timestamps
            now = datetime.now(timezone.utc).isoformat()
            user_data.update({
                "created_at": now,
                "updated_at": now
            })
            
            result = await self.db_manager.insert("users", user_data)
            
            if result and result.get("data"):
                user_dict = result["data"][0] if isinstance(result["data"], list) else result["data"]
                return User(**user_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            raise
    
    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get a user by ID."""
        try:
            result = await self.db_manager.select(
                "users",
                filters={"id": user_id}
            )
            
            if result and result.get("data"):
                user_dict = result["data"][0]
                return User(**user_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user by ID {user_id}: {e}")
            raise
    
    async def get_user_by_discord_id(self, discord_id: str) -> Optional[User]:
        """Get a user by Discord ID."""
        try:
            result = await self.db_manager.select(
                "users",
                filters={"discord_id": discord_id}
            )
            
            if result and result.get("data"):
                user_dict = result["data"][0]
                return User(**user_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user by Discord ID {discord_id}: {e}")
            raise
    
    async def get_users_by_filter(self, user_filter: UserFilter, 
                                limit: Optional[int] = None,
                                offset: Optional[int] = None) -> List[User]:
        """Get users by filter criteria."""
        try:
            filters = {}
            
            if user_filter.role:
                filters["role"] = user_filter.role
            if user_filter.status:
                filters["status"] = user_filter.status
            if user_filter.trader_name:
                filters["trader_name"] = user_filter.trader_name
            if user_filter.discord_id:
                filters["discord_id"] = user_filter.discord_id
            if user_filter.email:
                filters["email"] = user_filter.email
            if user_filter.testnet_enabled is not None:
                filters["testnet_enabled"] = user_filter.testnet_enabled
            
            result = await self.db_manager.select(
                "users",
                filters=filters,
                order_by="created_at.desc",
                limit=limit
            )
            
            users = []
            if result and result.get("data"):
                for user_dict in result["data"]:
                    users.append(User(**user_dict))
            
            return users
            
        except Exception as e:
            logger.error(f"Failed to get users by filter: {e}")
            raise
    
    async def update_user(self, user_id: int, updates: UserUpdate) -> Optional[User]:
        """Update a user record."""
        try:
            # Convert UserUpdate to dict, excluding None values
            update_data = {}
            for field, value in updates.__dict__.items():
                if value is not None:
                    update_data[field] = value
            
            # Add updated_at timestamp
            update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            result = await self.db_manager.update(
                "users",
                update_data,
                filters={"id": user_id}
            )
            
            if result and result.get("data"):
                user_dict = result["data"][0]
                return User(**user_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to update user {user_id}: {e}")
            raise
    
    async def delete_user(self, user_id: int) -> bool:
        """Delete a user record."""
        try:
            result = await self.db_manager.delete(
                "users",
                filters={"id": user_id}
            )
            
            return result is not None
            
        except Exception as e:
            logger.error(f"Failed to delete user {user_id}: {e}")
            raise
    
    async def create_user_profile(self, profile_data: Dict[str, Any]) -> Optional[UserProfile]:
        """Create a new user profile record."""
        try:
            # Add timestamps
            now = datetime.now(timezone.utc).isoformat()
            profile_data.update({
                "created_at": now,
                "updated_at": now
            })
            
            result = await self.db_manager.insert("user_profiles", profile_data)
            
            if result and result.get("data"):
                profile_dict = result["data"][0] if isinstance(result["data"], list) else result["data"]
                return UserProfile(**profile_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to create user profile: {e}")
            raise
    
    async def get_user_profile(self, user_id: int) -> Optional[UserProfile]:
        """Get a user profile by user ID."""
        try:
            result = await self.db_manager.select(
                "user_profiles",
                filters={"user_id": user_id}
            )
            
            if result and result.get("data"):
                profile_dict = result["data"][0]
                return UserProfile(**profile_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user profile for user {user_id}: {e}")
            raise
    
    async def update_user_profile(self, user_id: int, updates: Dict[str, Any]) -> Optional[UserProfile]:
        """Update a user profile record."""
        try:
            # Add updated_at timestamp
            updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            
            result = await self.db_manager.update(
                "user_profiles",
                updates,
                filters={"user_id": user_id}
            )
            
            if result and result.get("data"):
                profile_dict = result["data"][0]
                return UserProfile(**profile_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to update user profile for user {user_id}: {e}")
            raise
    
    async def create_user_session(self, session_data: Dict[str, Any]) -> Optional[UserSession]:
        """Create a new user session record."""
        try:
            # Add timestamps
            now = datetime.now(timezone.utc).isoformat()
            session_data.update({
                "created_at": now,
                "last_activity": now
            })
            
            result = await self.db_manager.insert("user_sessions", session_data)
            
            if result and result.get("data"):
                session_dict = result["data"][0] if isinstance(result["data"], list) else result["data"]
                return UserSession(**session_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to create user session: {e}")
            raise
    
    async def get_active_sessions(self, user_id: int) -> List[UserSession]:
        """Get active sessions for a user."""
        try:
            result = await self.db_manager.select(
                "user_sessions",
                filters={
                    "user_id": user_id,
                    "is_active": True
                },
                order_by="created_at.desc"
            )
            
            sessions = []
            if result and result.get("data"):
                for session_dict in result["data"]:
                    sessions.append(UserSession(**session_dict))
            
            return sessions
            
        except Exception as e:
            logger.error(f"Failed to get active sessions for user {user_id}: {e}")
            raise
    
    async def update_session_activity(self, session_id: int) -> Optional[UserSession]:
        """Update session last activity timestamp."""
        try:
            updates = {
                "last_activity": datetime.now(timezone.utc).isoformat()
            }
            
            result = await self.db_manager.update(
                "user_sessions",
                updates,
                filters={"id": session_id}
            )
            
            if result and result.get("data"):
                session_dict = result["data"][0]
                return UserSession(**session_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to update session activity for session {session_id}: {e}")
            raise
    
    async def deactivate_session(self, session_id: int) -> bool:
        """Deactivate a user session."""
        try:
            updates = {
                "is_active": False,
                "last_activity": datetime.now(timezone.utc).isoformat()
            }
            
            result = await self.db_manager.update(
                "user_sessions",
                updates,
                filters={"id": session_id}
            )
            
            return result is not None
            
        except Exception as e:
            logger.error(f"Failed to deactivate session {session_id}: {e}")
            raise
    
    async def create_user_activity(self, activity_data: Dict[str, Any]) -> Optional[UserActivity]:
        """Create a new user activity record."""
        try:
            # Add timestamp
            activity_data["created_at"] = datetime.now(timezone.utc).isoformat()
            
            result = await self.db_manager.insert("user_activities", activity_data)
            
            if result and result.get("data"):
                activity_dict = result["data"][0] if isinstance(result["data"], list) else result["data"]
                return UserActivity(**activity_dict)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to create user activity: {e}")
            raise
    
    async def get_user_activities(self, user_id: int, limit: Optional[int] = None) -> List[UserActivity]:
        """Get user activities."""
        try:
            result = await self.db_manager.select(
                "user_activities",
                filters={"user_id": user_id},
                order_by="created_at.desc",
                limit=limit
            )
            
            activities = []
            if result and result.get("data"):
                for activity_dict in result["data"]:
                    activities.append(UserActivity(**activity_dict))
            
            return activities
            
        except Exception as e:
            logger.error(f"Failed to get user activities for user {user_id}: {e}")
            raise
    
    async def get_user_stats(self, user_id: int, 
                           start_date: Optional[str] = None,
                           end_date: Optional[str] = None) -> UserStats:
        """Get user statistics."""
        try:
            # This would typically involve aggregating data from trades table
            # For now, return empty stats - implementation would depend on trade data
            stats = UserStats()
            
            # TODO: Implement actual statistics calculation based on trade data
            # This would involve querying the trades table and calculating metrics
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get user stats for user {user_id}: {e}")
            raise
    
    async def get_user_summary(self, user_id: int) -> Optional[UserSummary]:
        """Get comprehensive user summary."""
        try:
            # Get user
            user = await self.get_user_by_id(user_id)
            if not user:
                return None
            
            # Get profile
            profile = await self.get_user_profile(user_id)
            
            # Get stats
            stats = await self.get_user_stats(user_id)
            
            # Get recent activities
            activities = await self.get_user_activities(user_id, limit=10)
            
            # Get active sessions
            sessions = await self.get_active_sessions(user_id)
            
            return UserSummary(
                user=user,
                profile=profile,
                stats=stats,
                recent_activity=activities,
                active_sessions=sessions
            )
            
        except Exception as e:
            logger.error(f"Failed to get user summary for user {user_id}: {e}")
            raise

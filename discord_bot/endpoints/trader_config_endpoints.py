"""
Trader Configuration Management Endpoints

This module provides API endpoints for managing trader-to-exchange configurations
dynamically through the database.
"""

import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from src.services.trader_config_service import (
    trader_config_service, ExchangeType, TraderConfig
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trader-config", tags=["trader-config"])


class TraderConfigRequest(BaseModel):
    """Request model for trader configuration operations."""
    trader_id: str = Field(..., description="Trader identifier (e.g., '@Johnny')")
    exchange: str = Field(..., description="Exchange name ('binance' or 'kucoin')")
    leverage: int = Field(..., ge=1, le=100, description="Leverage value (1-100)")
    updated_by: Optional[str] = Field(None, description="Who made the update")


class TraderConfigResponse(BaseModel):
    """Response model for trader configuration."""
    trader_id: str
    exchange: str
    leverage: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


class TraderConfigListResponse(BaseModel):
    """Response model for listing trader configurations."""
    traders: List[TraderConfigResponse]
    total_count: int


@router.get("/", response_model=TraderConfigListResponse)
async def get_all_trader_configs():
    """
    Get all trader configurations from the database.

    Returns:
        List of all trader configurations
    """
    try:
        supported_traders = await trader_config_service.get_supported_traders()
        configs = []

        for trader_id in supported_traders:
            config = await trader_config_service.get_trader_config(trader_id)
            if config:
                configs.append(TraderConfigResponse(
                    trader_id=config.trader_id,
                    exchange=config.exchange.value,
                    leverage=config.leverage,
                    created_at=config.created_at,
                    updated_at=config.updated_at,
                    updated_by=config.updated_by
                ))

        return TraderConfigListResponse(
            traders=configs,
            total_count=len(configs)
        )

    except Exception as e:
        logger.error(f"Error getting trader configs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get trader configs: {str(e)}")


@router.get("/{trader_id}", response_model=TraderConfigResponse)
async def get_trader_config(trader_id: str):
    """
    Get configuration for a specific trader.

    Args:
        trader_id: The trader identifier

    Returns:
        Trader configuration
    """
    try:
        config = await trader_config_service.get_trader_config(trader_id)
        if not config:
            raise HTTPException(status_code=404, detail=f"Trader {trader_id} not found")

        return TraderConfigResponse(
            trader_id=config.trader_id,
            exchange=config.exchange.value,
            leverage=config.leverage,
            created_at=config.created_at,
            updated_at=config.updated_at,
            updated_by=config.updated_by
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trader config for {trader_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get trader config: {str(e)}")


@router.post("/", response_model=TraderConfigResponse)
async def create_trader_config(request: TraderConfigRequest):
    """
    Create or update a trader configuration.

    Args:
        request: Trader configuration data

    Returns:
        Created/updated trader configuration
    """
    try:
        # Validate exchange
        try:
            exchange_type = ExchangeType(request.exchange.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid exchange '{request.exchange}'. Must be 'binance' or 'kucoin'"
            )

        # Create/update configuration
        success = await trader_config_service.add_trader_config(
            trader_id=request.trader_id,
            exchange=exchange_type,
            leverage=request.leverage,
            updated_by=request.updated_by
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to create/update trader config")

        # Return the created/updated configuration
        config = await trader_config_service.get_trader_config(request.trader_id)
        if not config:
            raise HTTPException(status_code=500, detail="Failed to retrieve created config")

        return TraderConfigResponse(
            trader_id=config.trader_id,
            exchange=config.exchange.value,
            leverage=config.leverage,
            created_at=config.created_at,
            updated_at=config.updated_at,
            updated_by=config.updated_by
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating trader config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create trader config: {str(e)}")


@router.delete("/{trader_id}")
async def delete_trader_config(trader_id: str):
    """
    Delete a trader configuration.

    Args:
        trader_id: The trader identifier

    Returns:
        Success message
    """
    try:
        # Check if trader exists
        config = await trader_config_service.get_trader_config(trader_id)
        if not config:
            raise HTTPException(status_code=404, detail=f"Trader {trader_id} not found")

        # Delete configuration
        success = await trader_config_service.remove_trader_config(trader_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete trader config")

        return {"message": f"Trader {trader_id} configuration deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting trader config for {trader_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete trader config: {str(e)}")


@router.get("/exchange/{exchange}", response_model=TraderConfigListResponse)
async def get_traders_for_exchange(exchange: str):
    """
    Get all traders configured for a specific exchange.

    Args:
        exchange: Exchange name ('binance' or 'kucoin')

    Returns:
        List of traders for the exchange
    """
    try:
        # Validate exchange
        try:
            exchange_type = ExchangeType(exchange.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid exchange '{exchange}'. Must be 'binance' or 'kucoin'"
            )

        # Get traders for exchange
        trader_ids = await trader_config_service.get_traders_for_exchange(exchange_type)
        configs = []

        for trader_id in trader_ids:
            config = await trader_config_service.get_trader_config(trader_id)
            if config:
                configs.append(TraderConfigResponse(
                    trader_id=config.trader_id,
                    exchange=config.exchange.value,
                    leverage=config.leverage,
                    created_at=config.created_at,
                    updated_at=config.updated_at,
                    updated_by=config.updated_by
                ))

        return TraderConfigListResponse(
            traders=configs,
            total_count=len(configs)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting traders for exchange {exchange}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get traders for exchange: {str(e)}")


@router.get("/supported/traders")
async def get_supported_traders():
    """
    Get list of all supported traders.

    Returns:
        List of supported trader IDs
    """
    try:
        traders = await trader_config_service.get_supported_traders()
        return {
            "traders": traders,
            "total_count": len(traders)
        }

    except Exception as e:
        logger.error(f"Error getting supported traders: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get supported traders: {str(e)}")


@router.post("/validate/{trader_id}")
async def validate_trader_support(trader_id: str):
    """
    Check if a trader is supported (has configuration).

    Args:
        trader_id: The trader identifier

    Returns:
        Validation result
    """
    try:
        is_supported = await trader_config_service.is_trader_supported(trader_id)
        exchange_type = None

        if is_supported:
            config = await trader_config_service.get_trader_config(trader_id)
            if config:
                exchange_type = config.exchange.value

        return {
            "trader_id": trader_id,
            "is_supported": is_supported,
            "exchange": exchange_type
        }

    except Exception as e:
        logger.error(f"Error validating trader {trader_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to validate trader: {str(e)}")


@router.post("/cache/clear")
async def clear_trader_config_cache(trader_id: Optional[str] = None):
    """
    Clear trader configuration cache.

    Args:
        trader_id: Optional specific trader to clear cache for

    Returns:
        Success message
    """
    try:
        trader_config_service.clear_cache(trader_id)
        message = f"Cache cleared for trader {trader_id}" if trader_id else "All trader config cache cleared"
        return {"message": message}

    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")

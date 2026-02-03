"""Configuration API endpoints.

This module provides REST endpoints for managing user configuration,
such as household size for recipe scaling.

Issue #30: Portionenanzahl & automatische Rezept-Skalierung
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.auth import verify_token
from src.core.user_config import get_household_size, load_config, set_household_size

router = APIRouter(prefix="/config", tags=["config"])


class ConfigResponse(BaseModel):
    """Configuration response model."""

    household_size: int
    updated_at: str | None = None


class UpdateConfigRequest(BaseModel):
    """Request model for updating configuration."""

    household_size: int = Field(
        ..., ge=1, le=10, description="Anzahl Personen im Haushalt (1-10)"
    )


@router.get("", response_model=ConfigResponse)
async def get_config(_: str = Depends(verify_token)):
    """Get current configuration.

    Returns:
        Current configuration including household size
    """
    config = load_config()
    return ConfigResponse(
        household_size=config.get("household_size", 2),
        updated_at=config.get("updated_at"),
    )


@router.put("", response_model=ConfigResponse)
async def update_config(
    request: UpdateConfigRequest,
    _: str = Depends(verify_token),
):
    """Update configuration.

    Args:
        request: Configuration update request

    Returns:
        Updated configuration

    Raises:
        HTTPException: If validation fails
    """
    try:
        set_household_size(request.household_size)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    config = load_config()
    return ConfigResponse(
        household_size=config["household_size"],
        updated_at=config.get("updated_at"),
    )


@router.get("/household-size", response_model=int)
async def get_household_size_endpoint(_: str = Depends(verify_token)):
    """Get household size.

    Returns:
        Number of people in household
    """
    return get_household_size()

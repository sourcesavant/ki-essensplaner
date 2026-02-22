"""Configuration API endpoints.

This module provides REST endpoints for managing user configuration,
such as household size for recipe scaling.

Issue #30: Portionenanzahl & automatische Rezept-Skalierung
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from src.api.auth import verify_token
from src.core.user_config import (
    get_household_size,
    get_rotation_policy,
    load_config,
    set_household_size,
    set_rotation_policy,
)

router = APIRouter(prefix="/config", tags=["config"])


class ConfigResponse(BaseModel):
    """Configuration response model."""

    household_size: int
    rotation_policy: dict[str, float | int]
    updated_at: str | None = None


class RotationPolicyRequest(BaseModel):
    """Rotation policy request model."""

    no_repeat_weeks: int = Field(
        ..., ge=0, le=12, description="Anzahl Wochen ohne direkte Wiederholung"
    )
    favorite_min_return_weeks: int = Field(
        ..., ge=0, le=24, description="Früheste Rückkehr von Favoriten in Wochen"
    )
    favorite_return_bonus_per_week: float = Field(
        ..., ge=0, le=20, description="Score-Bonus pro zusätzlicher Wartewoche"
    )
    favorite_return_bonus_max: float = Field(
        ..., ge=0, le=100, description="Maximaler Rotations-Bonus"
    )


class UpdateConfigRequest(BaseModel):
    """Request model for updating configuration."""

    household_size: int | None = Field(
        default=None, ge=1, le=10, description="Anzahl Personen im Haushalt (1-10)"
    )
    rotation_policy: RotationPolicyRequest | None = None

    @model_validator(mode="after")
    def validate_not_empty(self):
        if self.household_size is None and self.rotation_policy is None:
            raise ValueError("At least one of household_size or rotation_policy must be provided.")
        return self


@router.get("", response_model=ConfigResponse)
async def get_config(_: str = Depends(verify_token)):
    """Get current configuration.

    Returns:
        Current configuration including household size
    """
    config = load_config()
    return ConfigResponse(
        household_size=config.get("household_size", 2),
        rotation_policy=get_rotation_policy(),
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
        if request.household_size is not None:
            set_household_size(request.household_size)
        if request.rotation_policy is not None:
            set_rotation_policy(request.rotation_policy.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    config = load_config()
    return ConfigResponse(
        household_size=config.get("household_size", 2),
        rotation_policy=get_rotation_policy(),
        updated_at=config.get("updated_at"),
    )


@router.get("/household-size", response_model=int)
async def get_household_size_endpoint(_: str = Depends(verify_token)):
    """Get household size.

    Returns:
        Number of people in household
    """
    return get_household_size()

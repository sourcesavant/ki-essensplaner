"""Seasonality API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Path, status

from src.api.auth import verify_token
from src.api.schemas.seasonality import SeasonalityResponse
from src.scoring.seasonality import get_seasonal_ingredients

router = APIRouter(prefix="/api", tags=["seasonality"])

MONTH_NAMES = {
    1: "Januar",
    2: "Februar",
    3: "März",
    4: "April",
    5: "Mai",
    6: "Juni",
    7: "Juli",
    8: "August",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Dezember",
}


@router.get("/seasonality/{month}", response_model=SeasonalityResponse)
def get_seasonality(
    month: int = Path(..., ge=1, le=12, description="Month number (1-12)"),
    _token: str = Depends(verify_token),
) -> SeasonalityResponse:
    """Get seasonal ingredients for a specific month.

    Returns a list of all ingredients that are in season during the specified month.
    Month must be between 1 (January) and 12 (December).
    """
    if month not in MONTH_NAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid month: {month}. Must be between 1 and 12.",
        )

    ingredients = get_seasonal_ingredients(month)

    return SeasonalityResponse(
        month=month,
        month_name=MONTH_NAMES[month],
        ingredients=sorted(ingredients),
        total_count=len(ingredients),
    )

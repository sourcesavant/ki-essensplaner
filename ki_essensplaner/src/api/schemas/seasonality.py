"""Seasonality API schemas."""

from pydantic import BaseModel


class SeasonalityResponse(BaseModel):
    """Response for seasonality endpoint."""

    month: int
    month_name: str
    ingredients: list[str]
    total_count: int


class IngredientSeasonCheck(BaseModel):
    """Check result for a single ingredient."""

    ingredient: str
    in_season: bool | None
    available_months: list[int] | None = None

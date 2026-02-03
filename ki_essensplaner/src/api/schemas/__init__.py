"""API schemas package."""

from src.api.schemas.bioland import BiolandProduct, BiolandProductList, BiolandRefreshResponse
from src.api.schemas.common import ErrorResponse, HealthResponse
from src.api.schemas.profile import (
    IngredientPreference,
    OverallNutrition,
    ProfileMetadata,
    ProfileRefreshResponse,
    ProfileResponse,
    ProfileSummary,
    SlotPattern,
    WeekdayPattern,
)
from src.api.schemas.seasonality import IngredientSeasonCheck, SeasonalityResponse

__all__ = [
    "ErrorResponse",
    "HealthResponse",
    "BiolandProduct",
    "BiolandProductList",
    "BiolandRefreshResponse",
    "ProfileResponse",
    "ProfileRefreshResponse",
    "ProfileMetadata",
    "IngredientPreference",
    "OverallNutrition",
    "ProfileSummary",
    "SlotPattern",
    "WeekdayPattern",
    "SeasonalityResponse",
    "IngredientSeasonCheck",
]

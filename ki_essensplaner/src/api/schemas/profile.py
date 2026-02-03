"""Profile-related API schemas."""

from typing import Any

from pydantic import BaseModel


class SlotPattern(BaseModel):
    """Pattern data for a specific meal slot."""

    meal_count: int
    recipe_meals: int
    pseudo_meals: int
    avg_prep_time_min: float | None = None
    avg_calories: float | None = None
    avg_protein_g: float | None = None
    avg_carbs_g: float | None = None
    avg_fat_g: float | None = None
    top_ingredients: list[str] = []


class WeekdayPattern(BaseModel):
    """Pattern data for a single weekday."""

    Mittagessen: SlotPattern | None = None
    Abendessen: SlotPattern | None = None


class ProfileMetadata(BaseModel):
    """Profile metadata."""

    last_profile_update: str
    version: str
    meals_analyzed: int


class IngredientPreference(BaseModel):
    """Single ingredient preference entry."""

    base_ingredient: str
    total_count: int
    recipe_count: int


class OverallNutrition(BaseModel):
    """Overall nutrition statistics."""

    meals_with_nutrition: int
    avg_calories: float | None = None
    avg_protein_g: float | None = None
    avg_carbs_g: float | None = None
    avg_fat_g: float | None = None
    avg_prep_time_min: float | None = None


class ProfileSummary(BaseModel):
    """Profile summary statistics."""

    total_meals: int
    meals_with_recipes: int
    pseudo_meals: int
    unique_ingredients: int
    filtered_universal: int


class ProfileResponse(BaseModel):
    """Full preference profile response."""

    metadata: ProfileMetadata
    universal_ingredients: list[str]
    ingredient_preferences: list[IngredientPreference]
    weekday_patterns: dict[str, dict[str, Any]]
    overall_nutrition: OverallNutrition
    summary: ProfileSummary


class ProfileRefreshResponse(BaseModel):
    """Response after refreshing the profile."""

    success: bool
    was_updated: bool
    meals_analyzed: int

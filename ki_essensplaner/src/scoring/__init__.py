"""Scoring module for recipe recommendations."""

from src.scoring.recipe_scorer import (
    MIN_OBTAINABLE_RATIO,
    WEIGHT_BIOLAND_AVAILABILITY,
    WEIGHT_INGREDIENT_AFFINITY,
    WEIGHT_SEASONALITY,
    WEIGHT_TIME_COMPATIBILITY,
    ScoreBreakdown,
    ScoringContext,
    calculate_score,
    generate_reasoning,
    get_unobtainable_ingredients,
    is_ingredient_obtainable,
    is_recipe_viable,
    load_profile,
    score_recipes,
)
from src.scoring.seasonality import (
    SEASONAL_CALENDAR,
    get_out_of_season_ingredients,
    get_season_score,
    get_seasonal_ingredients,
    is_in_season,
)

__all__ = [
    # Seasonality
    "is_in_season",
    "get_out_of_season_ingredients",
    "get_seasonal_ingredients",
    "get_season_score",
    "SEASONAL_CALENDAR",
    # Recipe scoring
    "calculate_score",
    "score_recipes",
    "generate_reasoning",
    "load_profile",
    "ScoringContext",
    "ScoreBreakdown",
    "WEIGHT_INGREDIENT_AFFINITY",
    "WEIGHT_TIME_COMPATIBILITY",
    "WEIGHT_BIOLAND_AVAILABILITY",
    "WEIGHT_SEASONALITY",
    # Availability filter
    "is_ingredient_obtainable",
    "is_recipe_viable",
    "get_unobtainable_ingredients",
    "MIN_OBTAINABLE_RATIO",
]

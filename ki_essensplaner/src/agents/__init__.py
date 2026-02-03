"""Recipe recommendation agents."""

from src.agents.models import (
    MEAL_SLOTS,
    SLOT_GROUP_MAPPING,
    WEEKDAYS,
    ScoredRecipe,
    SearchQuery,
    SlotGroup,
    SlotRecommendation,
    WeeklyRecommendation,
    load_weekly_plan,
    save_weekly_plan,
)
from src.agents.recipe_search_agent import run_search_agent

__all__ = [
    # Main functions
    "run_search_agent",
    "save_weekly_plan",
    "load_weekly_plan",
    # Models
    "ScoredRecipe",
    "SlotRecommendation",
    "WeeklyRecommendation",
    "SearchQuery",
    "SlotGroup",
    # Constants
    "WEEKDAYS",
    "MEAL_SLOTS",
    "SLOT_GROUP_MAPPING",
]

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
)
from src.agents.recipe_search_agent import run_search_agent

__all__ = [
    # Main function
    "run_search_agent",
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

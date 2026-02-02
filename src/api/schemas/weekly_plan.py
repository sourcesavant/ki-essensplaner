"""Pydantic schemas for weekly plan endpoints."""

from pydantic import BaseModel, Field


class RecipeResponse(BaseModel):
    """A single recipe in a slot recommendation."""

    title: str
    url: str | None = None
    score: float
    reasoning: str
    is_new: bool
    recipe_id: int | None = None
    prep_time_minutes: int | None = None
    calories: int | None = None
    ingredients: list[str] = Field(default_factory=list)


class SlotResponse(BaseModel):
    """Recommendations for a single meal slot."""

    weekday: str
    slot: str
    recommendations: list[RecipeResponse] = Field(default_factory=list)
    selected_index: int = 0


class WeeklyPlanResponse(BaseModel):
    """Complete weekly meal plan with recommendations."""

    generated_at: str
    week_start: str
    favorites_count: int
    new_count: int
    slots: list[SlotResponse] = Field(default_factory=list)


class SelectRecipeRequest(BaseModel):
    """Request to select a recipe for a specific slot."""

    weekday: str = Field(..., description="German weekday name (Montag, Dienstag, ...)")
    slot: str = Field(..., description="Meal slot (Mittagessen, Abendessen)")
    recipe_index: int = Field(..., ge=0, le=4, description="Recipe index (0-4)")


class GenerateWeeklyPlanResponse(BaseModel):
    """Response when starting weekly plan generation."""

    message: str
    task_id: str | None = None

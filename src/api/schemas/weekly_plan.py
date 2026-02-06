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
    reuse_from: dict | None = None  # {"weekday": "...", "slot": "..."}
    prep_days: int = 1
    is_reuse_slot: bool = False


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


class SetMultiDayRequest(BaseModel):
    """Request to configure multi-day meal prep."""

    primary_weekday: str = Field(..., description="Weekday when cooking")
    primary_slot: str = Field(..., description="Meal slot (Mittagessen/Abendessen)")
    reuse_slots: list[dict] = Field(..., description="Slots that reuse this recipe")

    class Config:
        json_schema_extra = {
            "example": {
                "primary_weekday": "Sonntag",
                "primary_slot": "Abendessen",
                "reuse_slots": [
                    {"weekday": "Montag", "slot": "Abendessen"},
                    {"weekday": "Dienstag", "slot": "Abendessen"},
                ],
            }
        }


class MultiDayGroupResponse(BaseModel):
    """Response for a multi-day group."""

    primary_weekday: str
    primary_slot: str
    recipe_title: str | None
    reuse_slots: list[dict]
    total_days: int
    multiplier: float


class MultiDayResponse(BaseModel):
    """Response after setting multi-day configuration."""

    success: bool
    groups: list[MultiDayGroupResponse]
    affected_slots: list[str]


class MultiDaySlot(BaseModel):
    """A single slot for multi-day preferences."""

    weekday: str
    slot: str


class MultiDayPreferenceGroup(BaseModel):
    """Preference group for multi-day planning (applies before generation)."""

    primary_weekday: str
    primary_slot: str
    reuse_slots: list[MultiDaySlot]


class MultiDayPreferencesRequest(BaseModel):
    """Request to set multi-day preferences."""

    groups: list[MultiDayPreferenceGroup]


class MultiDayPreferencesResponse(BaseModel):
    """Response for multi-day preferences."""

    groups: list[MultiDayPreferenceGroup]


MultiDayGroupResponse.model_rebuild()
MultiDayResponse.model_rebuild()

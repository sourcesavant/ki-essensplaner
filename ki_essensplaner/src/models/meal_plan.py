"""Pydantic models for meal plans."""

from datetime import date, datetime
from enum import IntEnum, StrEnum

from pydantic import BaseModel, Field


class DayOfWeek(IntEnum):
    """Days of the week (0=Monday, 6=Sunday)."""

    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


class MealSlot(StrEnum):
    """Meal slots during the day."""

    LUNCH = "lunch"
    DINNER = "dinner"


class Meal(BaseModel):
    """A single meal entry in a meal plan."""

    id: int | None = None
    meal_plan_id: int | None = None
    day_of_week: DayOfWeek
    slot: MealSlot
    recipe_id: int | None = None
    recipe_title: str | None = Field(
        default=None, description="Recipe title if recipe not in DB"
    )

    class Config:
        from_attributes = True


class MealCreate(BaseModel):
    """Data required to create a new meal entry."""

    day_of_week: DayOfWeek
    slot: MealSlot
    recipe_id: int | None = None
    recipe_title: str | None = None


class MealPlan(BaseModel):
    """A weekly meal plan imported from OneNote."""

    id: int | None = None
    onenote_page_id: str | None = Field(
        default=None, description="Unique OneNote page identifier"
    )
    week_start: date | None = None
    raw_content: str | None = Field(
        default=None, description="Original OneNote HTML content"
    )
    parsed_at: datetime | None = None
    meals: list[Meal] = Field(default_factory=list)

    class Config:
        from_attributes = True


class MealPlanCreate(BaseModel):
    """Data required to create a new meal plan."""

    onenote_page_id: str | None = None
    week_start: date | None = None
    raw_content: str | None = None
    meals: list[MealCreate] = Field(default_factory=list)

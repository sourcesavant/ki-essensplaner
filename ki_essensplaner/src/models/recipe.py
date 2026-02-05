"""Pydantic models for recipes."""

from datetime import datetime

from pydantic import BaseModel, Field


class Recipe(BaseModel):
    """A recipe with ingredients and instructions."""

    id: int | None = None
    title: str
    source: str = Field(description="Origin: 'eatsmarter', 'onenote', etc.")
    source_url: str | None = None
    prep_time_minutes: int | None = None
    ingredients: list[str] = Field(default_factory=list)
    instructions: str | None = None
    # Nutrition info
    calories: int | None = None
    fat_g: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    servings: int | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class RecipeCreate(BaseModel):
    """Data required to create a new recipe."""

    title: str
    source: str
    source_url: str | None = None
    prep_time_minutes: int | None = None
    ingredients: list[str] = Field(default_factory=list)
    instructions: str | None = None
    # Nutrition info
    calories: int | None = None
    fat_g: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    servings: int | None = None

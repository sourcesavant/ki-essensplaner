"""Pydantic schemas for recipe management endpoints."""

from pydantic import BaseModel, Field


class RateRecipeRequest(BaseModel):
    """Request to rate a recipe."""

    rating: int = Field(..., ge=1, le=5, description="Rating (1-5 stars)")


class RecipeRatingResponse(BaseModel):
    """Response with recipe rating."""

    recipe_id: int
    rating: int | None = None


class ExcludeIngredientRequest(BaseModel):
    """Request to exclude an ingredient."""

    ingredient_name: str = Field(..., min_length=1, description="Ingredient to exclude")


class ExcludeIngredientResponse(BaseModel):
    """Response after excluding an ingredient."""

    message: str
    ingredient_name: str


class ExcludedIngredientsResponse(BaseModel):
    """Response with list of excluded ingredients."""

    ingredients: list[str] = Field(default_factory=list)

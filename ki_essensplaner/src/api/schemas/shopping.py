"""Pydantic schemas for shopping list endpoints."""

from pydantic import BaseModel, Field


class ShoppingItemResponse(BaseModel):
    """A single item on the shopping list."""

    ingredient: str
    amount: float | None = None
    unit: str | None = None
    recipes: list[str] = Field(default_factory=list)


class ShoppingListResponse(BaseModel):
    """Aggregated shopping list from weekly plan."""

    week_start: str
    recipe_count: int
    items: list[ShoppingItemResponse] = Field(default_factory=list)


class SplitShoppingListResponse(BaseModel):
    """Shopping list split by store (Bioland/Rewe)."""

    week_start: str
    bioland: list[ShoppingItemResponse] = Field(default_factory=list)
    rewe: list[ShoppingItemResponse] = Field(default_factory=list)

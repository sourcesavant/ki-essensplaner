"""Shopping list API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from src.agents.models import load_weekly_plan
from src.api.auth import verify_token
from src.api.schemas.shopping import (
    ShoppingItemResponse,
    ShoppingListResponse,
    SplitShoppingListResponse,
)
from src.shopping.shopping_list import generate_shopping_list

router = APIRouter(prefix="/api/shopping-list", tags=["shopping"])
_LOGGER = logging.getLogger(__name__)


def _convert_item(item) -> ShoppingItemResponse:
    """Convert ShoppingItem to API response."""
    return ShoppingItemResponse(
        ingredient=item.ingredient,
        amount=item.amount,
        unit=item.unit,
        recipes=item.recipes,
    )


@router.get("", response_model=ShoppingListResponse)
def get_shopping_list(_token: str = Depends(verify_token)) -> ShoppingListResponse:
    """Generate shopping list from current weekly plan.

    On-demand generation from the saved weekly plan.
    Aggregates all ingredients from selected recipes.

    Returns 404 if no weekly plan exists.
    """
    plan = load_weekly_plan()

    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No weekly plan found. Generate one first using POST /api/weekly-plan/generate.",
        )

    selected = plan.get_selected_recipes()
    _LOGGER.info(
        "Shopping list request: selected_recipes=%s",
        [f"{w} {s}: {r.title}" for w, s, r in selected],
    )
    shopping_list = generate_shopping_list(plan)
    _LOGGER.info(
        "Shopping list generated: recipe_count=%s items=%s",
        shopping_list.recipe_count,
        len(shopping_list.items),
    )

    return ShoppingListResponse(
        week_start=shopping_list.week_start,
        recipe_count=shopping_list.recipe_count,
        items=[_convert_item(item) for item in shopping_list.items],
    )


@router.get("/split", response_model=SplitShoppingListResponse)
def get_split_shopping_list(
    _token: str = Depends(verify_token),
) -> SplitShoppingListResponse:
    """Generate shopping list split by store (Bioland/Rewe).

    On-demand generation from the saved weekly plan.
    Items available at Bioland Hüsgen go to the Bioland list,
    everything else goes to Rewe.

    Returns 404 if no weekly plan exists.
    """
    plan = load_weekly_plan()

    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No weekly plan found. Generate one first using POST /api/weekly-plan/generate.",
        )

    shopping_list = generate_shopping_list(plan)
    split_list = shopping_list.split_by_store()

    return SplitShoppingListResponse(
        week_start=split_list.week_start,
        bioland=[_convert_item(item) for item in split_list.bioland],
        rewe=[_convert_item(item) for item in split_list.rewe],
    )

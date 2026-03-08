"""Shopping list API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.agents.models import load_weekly_plan
from src.api.auth import verify_token
from src.api.schemas.shopping import (
    CheckedItemsResponse,
    ShoppingItemResponse,
    ShoppingListResponse,
    SplitShoppingListResponse,
)
from src.core.database import clear_checked_items, get_checked_items, set_item_checked
from src.shopping.shopping_list import generate_shopping_list

router = APIRouter(prefix="/api/shopping-list", tags=["shopping"])


class ToggleCheckedRequest(BaseModel):
    item_key: str
    checked: bool


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

    shopping_list = generate_shopping_list(plan)

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


def _get_current_week_start() -> str:
    """Return the week_start of the current plan, or raise 404."""
    plan = load_weekly_plan()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No weekly plan found.",
        )
    return plan.week_start


@router.get("/checked", response_model=CheckedItemsResponse)
def get_checked(_token: str = Depends(verify_token)) -> CheckedItemsResponse:
    """Return checked item keys for the current week."""
    week_start = _get_current_week_start()
    checked = get_checked_items(week_start)
    return CheckedItemsResponse(week_start=week_start, checked_items=sorted(checked))


@router.post("/checked", status_code=status.HTTP_204_NO_CONTENT)
def toggle_checked(
    body: ToggleCheckedRequest, _token: str = Depends(verify_token)
) -> None:
    """Mark or unmark a shopping item as checked."""
    week_start = _get_current_week_start()
    set_item_checked(week_start, body.item_key, body.checked)


@router.delete("/checked", status_code=status.HTTP_204_NO_CONTENT)
def delete_checked(_token: str = Depends(verify_token)) -> None:
    """Clear all checked items for the current week."""
    week_start = _get_current_week_start()
    clear_checked_items(week_start)

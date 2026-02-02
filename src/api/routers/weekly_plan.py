"""Weekly plan API endpoints."""

import asyncio
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from src.agents.models import (
    WEEKDAYS,
    MEAL_SLOTS,
    WeeklyRecommendation,
    load_weekly_plan,
    save_weekly_plan,
)
from src.agents.recipe_search_agent import run_search_agent
from src.api.auth import verify_token
from src.api.schemas.weekly_plan import (
    GenerateWeeklyPlanResponse,
    RecipeResponse,
    SelectRecipeRequest,
    SlotResponse,
    WeeklyPlanResponse,
)

router = APIRouter(prefix="/api/weekly-plan", tags=["weekly-plan"])


def _convert_to_response(plan: WeeklyRecommendation) -> WeeklyPlanResponse:
    """Convert internal WeeklyRecommendation to API response."""
    slots = []
    for slot in plan.slots:
        recommendations = [
            RecipeResponse(
                title=r.title,
                url=r.url,
                score=r.score,
                reasoning=r.reasoning,
                is_new=r.is_new,
                recipe_id=r.recipe_id,
                prep_time_minutes=r.prep_time_minutes,
                calories=r.calories,
                ingredients=r.ingredients,
            )
            for r in slot.recommendations
        ]
        slots.append(
            SlotResponse(
                weekday=slot.weekday,
                slot=slot.slot,
                recommendations=recommendations,
                selected_index=slot.selected_index,
            )
        )

    return WeeklyPlanResponse(
        generated_at=plan.generated_at,
        week_start=plan.week_start,
        favorites_count=plan.favorites_count,
        new_count=plan.new_count,
        slots=slots,
    )


def _generate_plan_sync() -> None:
    """Synchronous wrapper for plan generation (runs in background)."""
    try:
        print("[API] Starting weekly plan generation...")
        plan = run_search_agent()
        save_weekly_plan(plan)
        print(f"[API] Weekly plan generated successfully: {len(plan.slots)} slots")
    except Exception as e:
        print(f"[API] Error generating weekly plan: {e}")
        raise


@router.get("", response_model=WeeklyPlanResponse)
def get_weekly_plan(_token: str = Depends(verify_token)) -> WeeklyPlanResponse:
    """Get the current weekly meal plan.

    Returns the saved weekly plan with all recommendations and user selections.
    Returns 404 if no plan exists yet.
    """
    plan = load_weekly_plan()

    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No weekly plan found. Generate one first using POST /api/weekly-plan/generate.",
        )

    return _convert_to_response(plan)


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED, response_model=GenerateWeeklyPlanResponse)
def generate_weekly_plan(
    background_tasks: BackgroundTasks,
    _token: str = Depends(verify_token),
) -> GenerateWeeklyPlanResponse:
    """Generate a new weekly meal plan.

    This operation runs in the background as it takes 30-120 seconds.
    Returns 202 Accepted immediately. Use GET /api/weekly-plan to check
    when the plan is ready.

    The plan generation includes:
    - Loading favorites from database (60%)
    - Searching new recipes on eatsmarter (40%)
    - Scoring and ranking all recipes
    - Assigning top 5 recommendations per slot
    """
    # Add background task to generate the plan
    background_tasks.add_task(_generate_plan_sync)

    return GenerateWeeklyPlanResponse(
        message="Weekly plan generation started. This may take 30-120 seconds. Poll GET /api/weekly-plan to check status.",
        task_id=None,  # Simple implementation without task tracking
    )


@router.post("/select", response_model=WeeklyPlanResponse)
def select_recipe(
    request: SelectRecipeRequest,
    _token: str = Depends(verify_token),
) -> WeeklyPlanResponse:
    """Select a recipe for a specific meal slot.

    Updates the user's selection for a given weekday/slot and persists the change.
    Returns the updated weekly plan.
    """
    plan = load_weekly_plan()

    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No weekly plan found. Generate one first.",
        )

    # Validate weekday and slot
    if request.weekday not in WEEKDAYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid weekday. Must be one of: {', '.join(WEEKDAYS)}",
        )

    if request.slot not in MEAL_SLOTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid slot. Must be one of: {', '.join(MEAL_SLOTS)}",
        )

    # Get the slot
    slot_rec = plan.get_slot(request.weekday, request.slot)
    if slot_rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Slot not found: {request.weekday} {request.slot}",
        )

    # Validate recipe index
    if not (0 <= request.recipe_index < len(slot_rec.recommendations)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Recipe index out of range (0-{len(slot_rec.recommendations) - 1})",
        )

    # Update selection
    success = plan.select_recipe(request.weekday, request.slot, request.recipe_index)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update recipe selection",
        )

    # Save updated plan
    save_weekly_plan(plan)

    return _convert_to_response(plan)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_weekly_plan(_token: str = Depends(verify_token)) -> None:
    """Delete the current weekly plan.

    Removes the saved weekly plan file.
    """
    from src.agents.models import WEEKLY_PLAN_FILE

    if WEEKLY_PLAN_FILE.exists():
        WEEKLY_PLAN_FILE.unlink()

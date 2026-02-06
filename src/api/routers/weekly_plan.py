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
    MultiDayGroupResponse,
    MultiDayResponse,
    MultiDayPreferencesRequest,
    MultiDayPreferencesResponse,
    RecipeResponse,
    SelectRecipeRequest,
    SetMultiDayRequest,
    SkipSlotsRequest,
    SkipSlotsResponse,
    SlotResponse,
    WeeklyPlanResponse,
)
from src.core.user_config import (
    get_multi_day_preferences,
    get_skipped_slots,
    set_multi_day_preferences,
    set_skipped_slots,
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

        # If reuse slot, show recipe from primary slot
        if slot.is_reuse_slot and slot.reuse_from:
            primary = plan.get_slot(*slot.reuse_from)
            if primary and primary.recommendations:
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
                    for r in [primary.recommendations[primary.selected_index]]
                ]

        slots.append(
            SlotResponse(
                weekday=slot.weekday,
                slot=slot.slot,
                recommendations=recommendations,
                selected_index=slot.selected_index,
                reuse_from=(
                    {"weekday": slot.reuse_from[0], "slot": slot.reuse_from[1]}
                    if slot.reuse_from
                    else None
                ),
                prep_days=slot.prep_days,
                is_reuse_slot=slot.is_reuse_slot,
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
        preferences = get_multi_day_preferences()
        skipped = get_skipped_slots()
        plan = run_search_agent(
            multi_day_preferences=preferences,
            skipped_slots=skipped,
        )
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


# Multi-Day Meal Prep Endpoints


@router.post("/multi-day")
def set_multi_day(
    request: SetMultiDayRequest,
    _token: str = Depends(verify_token),
) -> MultiDayResponse:
    """Configure a recipe for multiple days (meal prep).

    Allows setting up a primary slot where cooking happens, and reuse slots
    where the same meal is eaten on following days. Quantities in the shopping
    list are automatically adjusted.
    """
    from src.api.schemas.weekly_plan import MultiDayGroupResponse, MultiDayResponse

    plan = load_weekly_plan()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No weekly plan found. Generate one first.",
        )

    # Convert reuse_slots dicts to tuples
    reuse_list = [(r["weekday"], r["slot"]) for r in request.reuse_slots]

    success = plan.set_multi_day(request.primary_weekday, request.primary_slot, reuse_list)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid slot configuration",
        )

    # Save updated plan
    save_weekly_plan(plan)

    # Build response
    affected = [f"{request.primary_weekday} {request.primary_slot}"]
    affected.extend([f"{w} {s}" for w, s in reuse_list])

    groups = []
    for g in plan.multi_day_groups:
        recipe = plan.get_recipe_for_slot(g.primary_weekday, g.primary_slot)
        groups.append(
            MultiDayGroupResponse(
                primary_weekday=g.primary_weekday,
                primary_slot=g.primary_slot,
                recipe_title=recipe.title if recipe else None,
                reuse_slots=[{"weekday": w, "slot": s} for w, s in g.reuse_slots],
                total_days=g.total_days,
                multiplier=g.multiplier,
            )
        )

    return MultiDayResponse(success=True, groups=groups, affected_slots=affected)


@router.delete("/multi-day/{weekday}/{slot}")
def clear_multi_day(
    weekday: str,
    slot: str,
    _token: str = Depends(verify_token),
) -> dict:
    """Remove multi-day configuration for a slot.

    Clears the meal prep setup for the specified slot, returning it to
    single-day mode.
    """
    plan = load_weekly_plan()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No weekly plan found",
        )

    success = plan.clear_multi_day(weekday, slot)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slot not found",
        )

    save_weekly_plan(plan)

    return {"success": True, "message": f"Multi-day configuration removed for {weekday} {slot}"}


@router.get("/multi-day")
def get_multi_day_groups(
    _token: str = Depends(verify_token),
) -> list[MultiDayGroupResponse]:
    """Get all multi-day meal prep groups.

    Returns information about all configured meal prep setups, including
    which recipes are cooked once and eaten multiple times.
    """
    from src.api.schemas.weekly_plan import MultiDayGroupResponse

    plan = load_weekly_plan()
    if not plan:
        return []

    groups = []
    for g in plan.multi_day_groups:
        recipe = plan.get_recipe_for_slot(g.primary_weekday, g.primary_slot)
        groups.append(
            MultiDayGroupResponse(
                primary_weekday=g.primary_weekday,
                primary_slot=g.primary_slot,
                recipe_title=recipe.title if recipe else None,
                reuse_slots=[{"weekday": w, "slot": s} for w, s in g.reuse_slots],
                total_days=g.total_days,
                multiplier=g.multiplier,
            )
        )

    return groups


def _validate_multi_day_preferences(
    groups: list[dict],
) -> list[dict]:
    """Validate and normalize multi-day preference groups."""
    seen_slots: set[tuple[str, str]] = set()
    normalized: list[dict] = []

    for group in groups:
        primary_weekday = group.get("primary_weekday")
        primary_slot = group.get("primary_slot")
        reuse_slots = group.get("reuse_slots") or []

        if primary_weekday not in WEEKDAYS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid weekday: {primary_weekday}",
            )
        if primary_slot not in MEAL_SLOTS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid slot: {primary_slot}",
            )

        if not reuse_slots:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="reuse_slots must contain at least one slot",
            )

        group_slots: list[tuple[str, str]] = [(primary_weekday, primary_slot)]
        normalized_reuse: list[dict] = []

        for reuse in reuse_slots:
            weekday = reuse.get("weekday")
            slot = reuse.get("slot")
            if weekday not in WEEKDAYS:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid weekday: {weekday}",
                )
            if slot not in MEAL_SLOTS:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Invalid slot: {slot}",
                )
            if weekday == primary_weekday and slot == primary_slot:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="reuse_slots cannot include the primary slot",
                )
            group_slots.append((weekday, slot))
            normalized_reuse.append({"weekday": weekday, "slot": slot})

        for slot_key in group_slots:
            if slot_key in seen_slots:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Slot appears in multiple groups: {slot_key[0]} {slot_key[1]}",
                )
            seen_slots.add(slot_key)

        normalized.append(
            {
                "primary_weekday": primary_weekday,
                "primary_slot": primary_slot,
                "reuse_slots": normalized_reuse,
            }
        )

    return normalized


@router.get("/multi-day/preferences", response_model=MultiDayPreferencesResponse)
def get_multi_day_preferences_endpoint(
    _token: str = Depends(verify_token),
) -> MultiDayPreferencesResponse:
    """Get stored multi-day preferences for future plan generation."""
    return MultiDayPreferencesResponse(groups=get_multi_day_preferences())


@router.put("/multi-day/preferences", response_model=MultiDayPreferencesResponse)
def set_multi_day_preferences_endpoint(
    request: MultiDayPreferencesRequest,
    _token: str = Depends(verify_token),
) -> MultiDayPreferencesResponse:
    """Set multi-day preferences to be applied before plan generation."""
    normalized = _validate_multi_day_preferences(
        [g.model_dump() for g in request.groups]
    )
    set_multi_day_preferences(normalized)
    return MultiDayPreferencesResponse(groups=normalized)


@router.delete("/multi-day/preferences")
def clear_multi_day_preferences_endpoint(
    _token: str = Depends(verify_token),
) -> dict:
    """Clear all stored multi-day preferences."""
    set_multi_day_preferences([])
    return {"success": True, "message": "Multi-day preferences cleared"}


def _validate_skipped_slots(slots: list[dict]) -> list[dict]:
    """Validate and normalize skipped slots."""
    seen: set[tuple[str, str]] = set()
    normalized: list[dict] = []

    for slot in slots:
        weekday = slot.get("weekday")
        meal_slot = slot.get("slot")
        if weekday not in WEEKDAYS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid weekday: {weekday}",
            )
        if meal_slot not in MEAL_SLOTS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid slot: {meal_slot}",
            )
        key = (weekday, meal_slot)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"weekday": weekday, "slot": meal_slot})

    return normalized


@router.get("/skip-slots", response_model=SkipSlotsResponse)
def get_skip_slots_endpoint(
    _token: str = Depends(verify_token),
) -> SkipSlotsResponse:
    """Get stored skipped slots for plan generation."""
    return SkipSlotsResponse(slots=get_skipped_slots())


@router.put("/skip-slots", response_model=SkipSlotsResponse)
def set_skip_slots_endpoint(
    request: SkipSlotsRequest,
    _token: str = Depends(verify_token),
) -> SkipSlotsResponse:
    """Set skipped slots to be applied before plan generation."""
    normalized = _validate_skipped_slots([s.model_dump() for s in request.slots])
    set_skipped_slots(normalized)
    return SkipSlotsResponse(slots=normalized)


@router.delete("/skip-slots")
def clear_skip_slots_endpoint(
    _token: str = Depends(verify_token),
) -> dict:
    """Clear all stored skipped slots."""
    set_skipped_slots([])
    return {"success": True, "message": "Skipped slots cleared"}

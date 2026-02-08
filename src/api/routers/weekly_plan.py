"""Weekly plan API endpoints."""

import logging

import asyncio
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from src.agents.models import (
    WEEKDAYS,
    MEAL_SLOTS,
    ScoredRecipe,
    WeeklyRecommendation,
    load_weekly_plan,
    save_weekly_plan,
)
from src.agents.recipe_search_agent import run_search_agent
from src.api.auth import verify_token
from src.api.schemas.weekly_plan import (
    CompleteWeeklyPlanRequest,
    CompleteWeeklyPlanResponse,
    GenerateWeeklyPlanResponse,
    MultiDayGroupResponse,
    MultiDayResponse,
    MultiDayPreferencesRequest,
    MultiDayPreferencesResponse,
    RecipeResponse,
    SelectRecipeRequest,
    SelectRecipeUrlRequest,
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
from src.core.database import get_recipe_by_url, upsert_meal_plan, upsert_recipe
from src.models.meal_plan import DayOfWeek, MealCreate, MealPlanCreate, MealSlot
from src.scrapers.recipe_fetcher import scrape_recipe

router = APIRouter(prefix="/api/weekly-plan", tags=["weekly-plan"])
_LOGGER = logging.getLogger(__name__)


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
            if (
                primary
                and primary.recommendations
                and primary.selected_index is not None
                and 0 <= primary.selected_index < len(primary.recommendations)
            ):
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
        completed_at=plan.completed_at,
        favorites_count=plan.favorites_count,
        new_count=plan.new_count,
        slots=slots,
    )


def _map_weekday(weekday: str) -> DayOfWeek | None:
    mapping = {
        "Montag": DayOfWeek.MONDAY,
        "Dienstag": DayOfWeek.TUESDAY,
        "Mittwoch": DayOfWeek.WEDNESDAY,
        "Donnerstag": DayOfWeek.THURSDAY,
        "Freitag": DayOfWeek.FRIDAY,
        "Samstag": DayOfWeek.SATURDAY,
        "Sonntag": DayOfWeek.SUNDAY,
    }
    return mapping.get(weekday)


def _map_slot(slot: str) -> MealSlot | None:
    mapping = {
        "Mittagessen": MealSlot.LUNCH,
        "Abendessen": MealSlot.DINNER,
    }
    return mapping.get(slot)


def _build_meal_plan(plan: WeeklyRecommendation) -> tuple[MealPlanCreate, int, int]:
    """Create a MealPlanCreate from selected primary slots in the weekly plan."""
    meals: list[MealCreate] = []
    skipped = 0

    for slot in plan.slots:
        if slot.is_reuse_slot:
            skipped += 1
            continue
        recipe = slot.selected_recipe
        if recipe is None:
            skipped += 1
            continue
        day_of_week = _map_weekday(slot.weekday)
        meal_slot = _map_slot(slot.slot)
        if day_of_week is None or meal_slot is None:
            skipped += 1
            continue

        meals.append(
            MealCreate(
                day_of_week=day_of_week,
                slot=meal_slot,
                recipe_id=recipe.recipe_id,
                recipe_title=None if recipe.recipe_id else recipe.title,
            )
        )

    plan_id = f"ha-week-{plan.week_start}"
    meal_plan = MealPlanCreate(
        onenote_page_id=plan_id,
        week_start=datetime.fromisoformat(plan.week_start).date()
        if plan.week_start
        else None,
        raw_content=None,
        meals=meals,
    )
    return meal_plan, len(meals), skipped


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


@router.post("/complete", response_model=CompleteWeeklyPlanResponse)
def complete_weekly_plan(
    request: CompleteWeeklyPlanRequest,
    background_tasks: BackgroundTasks,
    _token: str = Depends(verify_token),
) -> CompleteWeeklyPlanResponse:
    """Mark the current weekly plan as completed and persist cooked meals.

    No-op if no weekly plan exists.
    """
    plan = load_weekly_plan()
    if plan is None:
        return CompleteWeeklyPlanResponse(
            success=False,
            message="No weekly plan found. Nothing to complete.",
            week_start=None,
            meals_written=0,
            skipped_slots=0,
            completed_at=None,
            generated_next=False,
        )

    if request.week_start and request.week_start != plan.week_start:
        return CompleteWeeklyPlanResponse(
            success=False,
            message=(
                "Weekly plan week_start does not match request. "
                "No changes were made."
            ),
            week_start=plan.week_start,
            meals_written=0,
            skipped_slots=0,
            completed_at=plan.completed_at,
            generated_next=False,
        )

    meal_plan, meals_written, skipped = _build_meal_plan(plan)
    upsert_meal_plan(meal_plan)

    if not plan.completed_at:
        plan.completed_at = datetime.now().isoformat()
        save_weekly_plan(plan)

    if request.generate_next:
        background_tasks.add_task(_generate_plan_sync)

    return CompleteWeeklyPlanResponse(
        success=True,
        message="Weekly plan completed and meals persisted.",
        week_start=plan.week_start,
        meals_written=meals_written,
        skipped_slots=skipped,
        completed_at=plan.completed_at,
        generated_next=request.generate_next,
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
    if request.recipe_index != -1 and not (
        0 <= request.recipe_index < len(slot_rec.recommendations)
    ):
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
    slot_after = plan.get_slot(request.weekday, request.slot)
    selected = slot_after.selected_recipe if slot_after else None
    _LOGGER.info(
        "Select recipe: %s %s index=%s selected=%s",
        request.weekday,
        request.slot,
        request.recipe_index,
        selected.title if selected else None,
    )

    return _convert_to_response(plan)


@router.post("/select-url", response_model=WeeklyPlanResponse)
def select_recipe_url(
    request: SelectRecipeUrlRequest,
    _token: str = Depends(verify_token),
) -> WeeklyPlanResponse:
    """Select a recipe by URL for a specific meal slot.

    Scrapes the recipe URL, stores it in the DB, adds it to the slot
    recommendations, and selects it.
    """
    plan = load_weekly_plan()

    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No weekly plan found. Generate one first.",
        )

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

    slot_rec = plan.get_slot(request.weekday, request.slot)
    if slot_rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Slot not found: {request.weekday} {request.slot}",
        )

    if slot_rec.is_reuse_slot:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot set a custom recipe for a reuse slot. Update the primary slot instead.",
        )

    recipe_url = request.recipe_url.strip()
    if not recipe_url.startswith("http"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="recipe_url must be a valid URL starting with http/https",
        )

    # Check if the recipe is already in the slot recommendations
    for idx, rec in enumerate(slot_rec.recommendations):
        if rec.url == recipe_url:
            slot_rec.selected_index = idx
            save_weekly_plan(plan)
            return _convert_to_response(plan)

    # Use existing DB entry if present, otherwise scrape
    recipe = get_recipe_by_url(recipe_url)
    if recipe is None:
        recipe_data = scrape_recipe(recipe_url)
        if recipe_data is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Failed to scrape recipe from URL",
            )
        recipe = upsert_recipe(recipe_data)
    else:
        # If recipe already exists, prefer selecting existing recommendation by ID
        for idx, rec in enumerate(slot_rec.recommendations):
            if rec.recipe_id and recipe.id and rec.recipe_id == recipe.id:
                slot_rec.selected_index = idx
                save_weekly_plan(plan)
                return _convert_to_response(plan)

    custom_recipe = ScoredRecipe(
        title=recipe.title,
        url=recipe.source_url or recipe_url,
        score=0.0,
        reasoning="Manuell hinzugefuegt",
        is_new=False,
        recipe_id=recipe.id,
        prep_time_minutes=recipe.prep_time_minutes,
        calories=recipe.calories,
        ingredients=recipe.ingredients,
        servings=recipe.servings,
    )

    slot_rec.recommendations.append(custom_recipe)
    slot_rec.selected_index = len(slot_rec.recommendations) - 1
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

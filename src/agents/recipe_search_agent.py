"""Recipe search agent that orchestrates all components.

This agent generates weekly meal recommendations by:
1. Loading favorites from DB (60%)
2. Searching new recipes on eatsmarter (40%)
3. Scoring and filtering all recipes
4. Assigning top 5 recipes per slot

Example usage:
    >>> from src.agents.recipe_search_agent import run_search_agent
    >>> result = run_search_agent()  # Full week
    >>> print(result.summary())

    >>> result = run_search_agent(target_day="Mittwoch", target_slot="Abendessen")
    >>> print(result.slots[0])
"""

import time
from collections import defaultdict

from src.agents.models import (
    MEAL_SLOTS,
    SLOT_GROUP_MAPPING,
    WEEKDAYS,
    ScoredRecipe,
    SearchQuery,
    SlotGroup,
    SlotRecommendation,
    WeeklyRecommendation,
    save_weekly_plan,
)
from src.core.database import (
    get_all_ratings,
    get_available_base_ingredients,
    get_blacklisted_recipe_ids,
    get_connection,
    get_excluded_ingredients,
    get_recipe,
)
from src.models.recipe import Recipe
from src.profile.preference_profile import ensure_profile_current
from src.scrapers.bioland_huesgen import ensure_bioland_current
from src.scoring.recipe_scorer import (
    ScoringContext,
    calculate_score,
    is_recipe_viable,
)

# Target ratio for favorites vs new recipes
TARGET_FAVORITES_RATIO = 0.6

# Number of recommendations per slot
RECOMMENDATIONS_PER_SLOT = 5

# Maximum new recipes to fetch details for (per search)
MAX_DETAIL_FETCH = 10


def _get_favorites_from_db() -> list[tuple[Recipe, int]]:
    """Load favorite recipes from DB (those used in meals).

    Returns:
        List of (Recipe, cook_count) tuples, sorted by cook_count descending
    """
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT r.id, COUNT(m.id) as meal_count
            FROM recipes r
            JOIN meals m ON r.id = m.recipe_id
            WHERE r.id IS NOT NULL
            GROUP BY r.id
            ORDER BY meal_count DESC
        """).fetchall()

    favorites = []
    for row in rows:
        recipe = get_recipe(row["id"])
        if recipe:
            favorites.append((recipe, row["meal_count"]))

    return favorites


def _get_slot_groups_to_search(
    target_day: str | None,
    target_slot: str | None,
) -> dict[SlotGroup, list[tuple[str, str]]]:
    """Determine which slot groups need to be searched.

    Args:
        target_day: Specific day to search for, or None for all
        target_slot: Specific slot to search for, or None for all

    Returns:
        Dict mapping SlotGroup to list of (weekday, slot) tuples
    """
    groups: dict[SlotGroup, list[tuple[str, str]]] = defaultdict(list)

    for weekday in WEEKDAYS:
        if target_day and weekday != target_day:
            continue
        for slot in MEAL_SLOTS:
            if target_slot and slot != target_slot:
                continue
            group = SLOT_GROUP_MAPPING.get((weekday, slot), SlotGroup.NORMAL)
            groups[group].append((weekday, slot))

    return dict(groups)


def _build_search_queries(
    groups: dict[SlotGroup, list[tuple[str, str]]],
    profile: dict,
) -> list[SearchQuery]:
    """Build search queries for each slot group.

    Uses the top ingredients and avg prep time from the profile for each group.

    Args:
        groups: Dict mapping SlotGroup to slots
        profile: User preference profile

    Returns:
        List of SearchQuery objects
    """
    queries = []
    weekday_patterns = profile.get("weekday_patterns", {})

    for group, slots in groups.items():
        # Collect ingredients and times from all slots in this group
        all_ingredients: list[str] = []
        all_times: list[float] = []

        for weekday, slot in slots:
            slot_data = weekday_patterns.get(weekday, {}).get(slot, {})
            top_ings = slot_data.get("top_ingredients", [])
            avg_time = slot_data.get("avg_prep_time_min")

            all_ingredients.extend(top_ings[:5])
            if avg_time:
                all_times.append(avg_time)

        # Get most common ingredients for this group
        ingredient_counts: dict[str, int] = defaultdict(int)
        for ing in all_ingredients:
            ingredient_counts[ing] += 1

        top_ingredients = sorted(
            ingredient_counts.keys(),
            key=lambda x: ingredient_counts[x],
            reverse=True
        )[:5]

        # Average time for group
        avg_time = int(sum(all_times) / len(all_times)) if all_times else None

        if top_ingredients:
            queries.append(SearchQuery(
                group=group,
                ingredients=top_ingredients,
                max_time=avg_time,
            ))

    return queries


def _search_new_recipes(
    queries: list[SearchQuery],
    context: ScoringContext,
    max_per_query: int = 20,
) -> list[ScoredRecipe]:
    """Search for new recipes on eatsmarter.

    Args:
        queries: List of search queries (one per slot group)
        context: Scoring context
        max_per_query: Maximum results per query

    Returns:
        List of scored new recipes
    """
    from src.scrapers.eatsmarter_search import search_recipes

    all_results: list[ScoredRecipe] = []
    seen_urls: set[str] = set()

    for query in queries:
        print(f"  Searching: {query}")

        # Search with top 2-3 ingredients
        search_ingredients = query.ingredients[:3]

        try:
            results = search_recipes(
                include_ingredients=search_ingredients,
                max_time=query.max_time,
                max_results=max_per_query,
                headless=True,
            )
        except Exception as e:
            print(f"    Search failed: {e}")
            continue

        # Score and deduplicate results
        for result in results:
            if result.url in seen_urls:
                continue
            seen_urls.add(result.url)

            # Create a temporary Recipe object for scoring
            # (without full ingredient details yet)
            temp_recipe = Recipe(
                title=result.title,
                source="eatsmarter",
                source_url=result.url,
                prep_time_minutes=result.prep_time_minutes,
                calories=result.calories,
                ingredients=[],  # Will be loaded later for top candidates
            )

            # Quick viability check based on title keywords
            # Full check will be done after loading details
            score = calculate_score(temp_recipe, context)

            scored = ScoredRecipe(
                title=result.title,
                url=result.url,
                score=score.total_score,
                reasoning=score.reasoning,
                is_new=True,
                prep_time_minutes=result.prep_time_minutes,
                calories=result.calories,
            )
            all_results.append(scored)

        time.sleep(0.5)  # Rate limiting between searches

    # Sort by score
    all_results.sort(key=lambda x: x.score, reverse=True)

    return all_results


def _load_recipe_details(recipes: list[ScoredRecipe], context: ScoringContext) -> list[ScoredRecipe]:
    """Load full ingredient details for top recipe candidates.

    Uses recipe-scrapers to fetch ingredients, then re-scores with full data.

    Args:
        recipes: List of recipes to load details for
        context: Scoring context for re-scoring

    Returns:
        List of recipes with updated scores (filtered for viability)
    """
    from recipe_scrapers import scrape_me

    detailed_recipes: list[ScoredRecipe] = []

    for recipe in recipes[:MAX_DETAIL_FETCH]:
        if not recipe.url:
            continue

        try:
            print(f"    Loading details: {recipe.title[:40]}...")
            scraper = scrape_me(recipe.url)

            # Create full Recipe object
            full_recipe = Recipe(
                title=scraper.title(),
                source="eatsmarter",
                source_url=recipe.url,
                prep_time_minutes=scraper.total_time() or recipe.prep_time_minutes,
                ingredients=scraper.ingredients(),
                calories=recipe.calories,
            )

            # Check viability with full ingredients
            is_viable, unobtainable, ratio = is_recipe_viable(full_recipe, context)

            if not is_viable:
                print(f"      Filtered: {unobtainable}")
                continue

            # Re-score with full ingredients
            score = calculate_score(full_recipe, context)

            detailed = ScoredRecipe(
                title=full_recipe.title,
                url=recipe.url,
                score=score.total_score,
                reasoning=score.reasoning,
                is_new=True,
                prep_time_minutes=full_recipe.prep_time_minutes,
                calories=recipe.calories,
                ingredients=full_recipe.ingredients,
            )
            detailed_recipes.append(detailed)

            time.sleep(0.3)  # Rate limiting

        except Exception as e:
            print(f"      Failed to load: {e}")
            # Keep the recipe with preliminary score
            detailed_recipes.append(recipe)

    return detailed_recipes


def _score_favorites(
    favorites: list[tuple[Recipe, int]],
    context: ScoringContext,
) -> list[ScoredRecipe]:
    """Score favorite recipes from DB.

    Args:
        favorites: List of (Recipe, cook_count) tuples
        context: Scoring context

    Returns:
        List of scored favorites
    """
    scored_favorites: list[ScoredRecipe] = []

    for recipe, cook_count in favorites:
        # Check viability
        is_viable, _, _ = is_recipe_viable(recipe, context)
        if not is_viable:
            continue

        score = calculate_score(recipe, context)

        # Boost score slightly based on how often it was cooked (max +10 points)
        cook_bonus = min(10, cook_count * 2)
        adjusted_score = min(100, score.total_score + cook_bonus)

        scored = ScoredRecipe(
            title=recipe.title,
            url=recipe.source_url,
            score=adjusted_score,
            reasoning=f"{score.reasoning} Bereits {cook_count}x gekocht.",
            is_new=False,
            recipe_id=recipe.id,
            prep_time_minutes=recipe.prep_time_minutes,
            calories=recipe.calories,
            ingredients=recipe.ingredients,
        )
        scored_favorites.append(scored)

    # Sort by score
    scored_favorites.sort(key=lambda x: x.score, reverse=True)

    return scored_favorites


def _assign_recipes_to_slots(
    slots: list[tuple[str, str]],
    favorites: list[ScoredRecipe],
    new_recipes: list[ScoredRecipe],
    context: ScoringContext,
    target_favorites_ratio: float = TARGET_FAVORITES_RATIO,
) -> list[SlotRecommendation]:
    """Assign recipes to slots with 60/40 favorites/new mix.

    Args:
        slots: List of (weekday, slot) tuples
        favorites: Scored favorite recipes
        new_recipes: Scored new recipes
        context: Scoring context
        target_favorites_ratio: Target ratio for favorites (default 0.6)

    Returns:
        List of SlotRecommendation objects
    """
    total_slots = len(slots)
    target_favorites = int(total_slots * target_favorites_ratio)

    # Track which recipes have been assigned as top choice
    used_favorite_ids: set[int] = set()
    used_new_urls: set[str] = set()

    recommendations: list[SlotRecommendation] = []

    # First pass: assign favorites to best-matching slots
    favorites_assigned = 0
    for weekday, slot in slots:
        if favorites_assigned >= target_favorites:
            break

        # Find best unused favorite for this slot
        best_favorite = None
        for fav in favorites:
            if fav.recipe_id and fav.recipe_id not in used_favorite_ids:
                best_favorite = fav
                break

        if best_favorite and best_favorite.recipe_id:
            used_favorite_ids.add(best_favorite.recipe_id)
            favorites_assigned += 1

            # Get top 5 for this slot (mix of favorites)
            slot_recipes = [best_favorite]
            for fav in favorites:
                if len(slot_recipes) >= RECOMMENDATIONS_PER_SLOT:
                    break
                if fav.recipe_id not in used_favorite_ids or fav.recipe_id == best_favorite.recipe_id:
                    if fav not in slot_recipes:
                        slot_recipes.append(fav)

            recommendations.append(SlotRecommendation(
                weekday=weekday,
                slot=slot,
                recommendations=slot_recipes[:RECOMMENDATIONS_PER_SLOT],
            ))

    # Second pass: assign new recipes to remaining slots
    assigned_slots = {(r.weekday, r.slot) for r in recommendations}

    for weekday, slot in slots:
        if (weekday, slot) in assigned_slots:
            continue

        # Find best unused new recipe
        slot_recipes: list[ScoredRecipe] = []
        for new in new_recipes:
            if len(slot_recipes) >= RECOMMENDATIONS_PER_SLOT:
                break
            if new.url and new.url not in used_new_urls:
                slot_recipes.append(new)
                if len(slot_recipes) == 1:  # Mark top choice as used
                    used_new_urls.add(new.url)

        # Fill remaining slots with favorites if not enough new recipes
        if len(slot_recipes) < RECOMMENDATIONS_PER_SLOT:
            for fav in favorites:
                if len(slot_recipes) >= RECOMMENDATIONS_PER_SLOT:
                    break
                if fav not in slot_recipes:
                    slot_recipes.append(fav)

        recommendations.append(SlotRecommendation(
            weekday=weekday,
            slot=slot,
            recommendations=slot_recipes,
        ))

    # Sort by weekday and slot
    day_order = {day: i for i, day in enumerate(WEEKDAYS)}
    slot_order = {"Mittagessen": 0, "Abendessen": 1}
    recommendations.sort(key=lambda r: (day_order.get(r.weekday, 99), slot_order.get(r.slot, 99)))

    return recommendations


def run_search_agent(
    target_day: str | None = None,
    target_slot: str | None = None,
) -> WeeklyRecommendation:
    """Run the recipe search agent.

    Args:
        target_day: Specific weekday to generate for (e.g., "Mittwoch"), or None for full week
        target_slot: Specific slot to generate for (e.g., "Abendessen"), or None for all

    Returns:
        WeeklyRecommendation with top 5 recipes per slot
    """
    print("=" * 60)
    print("Recipe Search Agent")
    print("=" * 60)

    # Load profile (auto-update if outdated)
    print("\n1. Loading profile...")
    profile, was_updated = ensure_profile_current()
    if was_updated:
        print("   Profile was regenerated (outdated or missing)")
    print(f"   Profile loaded: {profile.get('summary', {}).get('total_meals', 0)} meals")

    # Load Bioland availability (auto-update if outdated)
    print("\n2. Loading Bioland availability...")
    product_count, bioland_updated = ensure_bioland_current()
    if bioland_updated:
        print("   Bioland data was refreshed (outdated or missing)")
    available = get_available_base_ingredients("bioland_huesgen")
    print(f"   {len(available)} ingredients available")

    # Load ratings
    print("\n3. Loading ratings...")
    ratings = get_all_ratings()
    blacklisted = get_blacklisted_recipe_ids()
    print(f"   {len(ratings)} ratings, {len(blacklisted)} blacklisted")

    # Load excluded ingredients
    print("\n4. Loading excluded ingredients...")
    excluded = get_excluded_ingredients()
    print(f"   {len(excluded)} excluded ingredients")

    # Create scoring context
    context = ScoringContext(
        weekday=target_day or "Montag",  # Default for scoring
        meal_slot=target_slot or "Abendessen",
        profile=profile,
        available_ingredients=available,
        recipe_ratings=ratings,
        blacklisted_ids=blacklisted,
        excluded_ingredients=excluded,
    )

    # Determine slots to search
    print("\n5. Determining slots...")
    groups = _get_slot_groups_to_search(target_day, target_slot)
    all_slots = [(day, slot) for slots in groups.values() for day, slot in slots]
    print(f"   {len(all_slots)} slots to fill")

    # Load favorites from DB
    print("\n6. Loading favorites from DB...")
    favorites_raw = _get_favorites_from_db()
    print(f"   {len(favorites_raw)} recipes found in DB")

    favorites = _score_favorites(favorites_raw, context)
    print(f"   {len(favorites)} viable favorites after filtering")

    # Build search queries
    print("\n7. Building search queries...")
    queries = _build_search_queries(groups, profile)
    for q in queries:
        print(f"   {q}")

    # Search new recipes
    print("\n8. Searching new recipes...")
    new_recipes_raw = _search_new_recipes(queries, context)
    print(f"   {len(new_recipes_raw)} candidates found")

    # Load details for top candidates
    print("\n9. Loading details for top candidates...")
    new_recipes = _load_recipe_details(new_recipes_raw, context)
    print(f"   {len(new_recipes)} viable new recipes")

    # Assign recipes to slots
    print("\n10. Assigning recipes to slots...")
    slot_recommendations = _assign_recipes_to_slots(
        all_slots, favorites, new_recipes, context
    )

    # Calculate stats
    favorites_count = sum(
        1 for r in slot_recommendations
        if r.top_recipe and not r.top_recipe.is_new
    )
    new_count = len(slot_recommendations) - favorites_count

    result = WeeklyRecommendation(
        favorites_count=favorites_count,
        new_count=new_count,
        slots=slot_recommendations,
    )

    # Save the plan
    print("\n11. Saving weekly plan...")
    save_path = save_weekly_plan(result)
    print(f"   Saved to {save_path}")

    print("\n" + "=" * 60)
    print("Results")
    print("=" * 60)
    print(result.summary())

    return result


if __name__ == "__main__":
    # Test: single slot
    print("\n### Test: Single Slot ###\n")
    result = run_search_agent(target_day="Mittwoch", target_slot="Abendessen")

    print("\n### Test: Full Week ###\n")
    # Uncomment to run full week (takes longer)
    # result = run_search_agent()

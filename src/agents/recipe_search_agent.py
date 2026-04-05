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
from dataclasses import replace
from datetime import date
from urllib.parse import urlsplit, urlunsplit

from src.agents.models import (
    MEAL_SLOTS,
    SLOT_GROUP_MAPPING,
    WEEKDAYS,
    ScoredRecipe,
    SearchQuery,
    SlotGroup,
    SlotRecommendation,
    WeeklyRecommendation,
    load_weekly_plan,
    save_weekly_plan,
)
from src.core.database import (
    get_all_ratings,
    get_available_base_ingredients,
    get_blacklisted_recipe_ids,
    get_connection,
    get_excluded_ingredients,
    get_recent_ha_week_recipe_history,
    get_recipe,
    get_recipe_by_url,
    upsert_recipe,
)
from src.models.recipe import Recipe, RecipeCreate
from src.profile.preference_profile import ensure_profile_current
from src.scrapers.bioland_huesgen import ensure_bioland_current
from src.scoring.recipe_scorer import (
    ScoringContext,
    calculate_score,
    is_recipe_viable,
)
from src.scoring.seasonality import get_seasonal_ingredients

# Target ratio for favorites vs new recipes
TARGET_FAVORITES_RATIO = 0.6

# Number of recommendations per slot
RECOMMENDATIONS_PER_SLOT = 5

# Maximum new recipes to fetch details for (per search)
MAX_DETAIL_FETCH = 20

# Cuisine keywords for rotating query diversity (rotated by ISO week number)
CUISINE_KEYWORDS = [
    "vegetarisch", "mediterran", "asiatisch", "Suppe", "Eintopf",
    "Pasta", "Fisch", "Hähnchen", "Linsen", "Nudeln",
]

# Rotation defaults (can be overridden via user config rotation_policy)
DEFAULT_NO_REPEAT_WEEKS = 1
DEFAULT_FAVORITE_MIN_RETURN_WEEKS = 3
DEFAULT_FAVORITE_RETURN_BONUS_PER_WEEK = 2.0
DEFAULT_FAVORITE_RETURN_BONUS_MAX = 10.0


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
    skipped_slots: set[tuple[str, str]] | None = None,
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
            if skipped_slots and (weekday, slot) in skipped_slots:
                continue
            group = SLOT_GROUP_MAPPING.get((weekday, slot), SlotGroup.NORMAL)
            groups[group].append((weekday, slot))

    return dict(groups)


def _build_search_queries(
    groups: dict[SlotGroup, list[tuple[str, str]]],
    profile: dict,
) -> list[SearchQuery]:
    """Build diverse search queries for each slot group.

    Builds up to 4 queries per group using different ingredient combinations:
    1. Top 3 profile ingredients (existing behaviour)
    2. Profile ingredients rank 4-8 (fresh combination)
    3. 2-3 seasonal ingredients (current month)
    4. Cuisine keyword rotation + 1-2 profile ingredients

    Args:
        groups: Dict mapping SlotGroup to slots
        profile: User preference profile

    Returns:
        List of SearchQuery objects (up to 4 per slot group)
    """
    queries = []
    weekday_patterns = profile.get("weekday_patterns", {})

    # Seasonal and cuisine context (shared across groups)
    today = date.today()
    seasonal = get_seasonal_ingredients(today.month)
    iso_week = today.isocalendar()[1]
    cuisine_kw = CUISINE_KEYWORDS[iso_week % len(CUISINE_KEYWORDS)]

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

        # Get ranked ingredient list for this group
        ingredient_counts: dict[str, int] = defaultdict(int)
        for ing in all_ingredients:
            ingredient_counts[ing] += 1

        ranked_ingredients = sorted(
            ingredient_counts.keys(),
            key=lambda x: ingredient_counts[x],
            reverse=True,
        )

        # Average time for group
        avg_time = int(sum(all_times) / len(all_times)) if all_times else None

        # Query 1: Top 3 profile ingredients
        if ranked_ingredients[:3]:
            queries.append(SearchQuery(
                group=group,
                ingredients=ranked_ingredients[:3],
                max_time=avg_time,
            ))

        # Query 2: Profile ingredients rank 4-8 (fresh combination)
        secondary = ranked_ingredients[3:6]
        if secondary:
            queries.append(SearchQuery(
                group=group,
                ingredients=secondary[:3],
                max_time=avg_time,
            ))

        # Query 3: Seasonal ingredients (2-3, skipping already used ones)
        seasonal_candidates = [s for s in seasonal if s not in ranked_ingredients[:6]]
        if seasonal_candidates:
            queries.append(SearchQuery(
                group=group,
                ingredients=seasonal_candidates[:3],
                max_time=avg_time,
            ))

        # Query 4: Cuisine keyword + 1-2 top profile ingredients
        if ranked_ingredients:
            cuisine_ings = [cuisine_kw] + ranked_ingredients[:2]
            queries.append(SearchQuery(
                group=group,
                ingredients=cuisine_ings[:3],
                max_time=avg_time,
            ))

    return queries


def _search_new_recipes(
    queries: list[SearchQuery],
    context: ScoringContext,
    max_per_query: int = 30,
) -> list[ScoredRecipe]:
    """Search for new recipes on eatsmarter.

    Args:
        queries: List of search queries (up to 4 per slot group)
        context: Scoring context
        max_per_query: Maximum results per query

    Returns:
        List of scored new recipes
    """
    from src.scrapers.eatsmarter_search import search_recipes_batch

    all_results: list[ScoredRecipe] = []
    seen_urls: set[str] = set()

    search_payloads: list[dict] = []
    for query in queries:
        print(f"  Searching: {query}")
        search_payloads.append(
            {
                "include_ingredients": query.ingredients[:3],
                "max_time": query.max_time,
                "max_results": max_per_query,
            }
        )

    try:
        batched_results = search_recipes_batch(
            search_payloads,
            headless=True,
            use_cache=True,
        )
    except Exception as e:
        print(f"    Batch search failed: {e}")
        return all_results

    for results in batched_results:

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
                servings=None,  # Not available yet, will be loaded if selected
            )
            all_results.append(scored)

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

        db_recipe = get_recipe_by_url(recipe.url)

        try:
            print(f"    Loading details: {recipe.title[:40]}...")
            scraper = scrape_me(recipe.url)

            # Get servings
            servings = None
            try:
                from src.scrapers.recipe_fetcher import parse_servings
                yields_str = scraper.yields()
                servings = parse_servings(yields_str)
            except Exception:
                pass

            # Create full Recipe object
            full_recipe = Recipe(
                title=scraper.title(),
                source="eatsmarter",
                source_url=recipe.url,
                prep_time_minutes=scraper.total_time() or recipe.prep_time_minutes,
                ingredients=scraper.ingredients(),
                calories=recipe.calories,
                servings=servings,
            )

            if db_recipe is None:
                db_recipe = upsert_recipe(
                    RecipeCreate(
                        title=full_recipe.title,
                        source=full_recipe.source,
                        source_url=full_recipe.source_url,
                        prep_time_minutes=full_recipe.prep_time_minutes,
                        ingredients=full_recipe.ingredients,
                        calories=full_recipe.calories,
                        servings=full_recipe.servings,
                    )
                )
            full_recipe.id = db_recipe.id

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
                recipe_id=db_recipe.id if db_recipe else None,
                prep_time_minutes=full_recipe.prep_time_minutes,
                calories=recipe.calories,
                ingredients=full_recipe.ingredients,
                servings=servings,
            )
            detailed_recipes.append(detailed)

            time.sleep(0.3)  # Rate limiting

        except Exception as e:
            print(f"      Failed to load: {e}")
            # Persist URL as minimal recipe so it can be rated/blacklisted immediately.
            if db_recipe is None:
                try:
                    db_recipe = upsert_recipe(
                        RecipeCreate(
                            title=recipe.title,
                            source="eatsmarter",
                            source_url=recipe.url,
                            prep_time_minutes=recipe.prep_time_minutes,
                            ingredients=[],
                            calories=recipe.calories,
                        )
                    )
                except Exception:
                    db_recipe = None

            # Keep the recipe with preliminary score, but include DB ID if available.
            detailed_recipes.append(
                replace(recipe, recipe_id=db_recipe.id if db_recipe else recipe.recipe_id)
            )

    return detailed_recipes


def _remove_selected_recipe_duplicates_from_alternatives(
    recommendations: list[SlotRecommendation],
) -> None:
    """Ensure selected recipes of other slots are not shown as alternatives."""
    selected_aliases_by_slot: dict[tuple[str, str], set[tuple[str, str | int]]] = {}
    selected_aliases: set[tuple[str, str | int]] = set()

    for slot_rec in recommendations:
        if not slot_rec.recommendations:
            continue
        if 0 <= slot_rec.selected_index < len(slot_rec.recommendations):
            selected = slot_rec.recommendations[slot_rec.selected_index]
        else:
            selected = slot_rec.recommendations[0]
            slot_rec.selected_index = 0

        recipe_aliases = _recipe_alias_keys(selected)
        if not recipe_aliases:
            continue
        slot_key = (slot_rec.weekday, slot_rec.slot)
        selected_aliases_by_slot[slot_key] = recipe_aliases
        selected_aliases.update(recipe_aliases)

    for slot_rec in recommendations:
        slot_key = (slot_rec.weekday, slot_rec.slot)
        own_selected_aliases = selected_aliases_by_slot.get(slot_key, set())

        filtered: list[ScoredRecipe] = []
        for recipe in slot_rec.recommendations:
            alias_keys = _recipe_alias_keys(recipe)
            if not alias_keys:
                filtered.append(recipe)
                continue
            if alias_keys & own_selected_aliases:
                filtered.append(recipe)
                continue
            if not (alias_keys & selected_aliases):
                filtered.append(recipe)
        slot_rec.recommendations = filtered
        if not slot_rec.recommendations:
            slot_rec.selected_index = -1
        elif slot_rec.selected_index < 0 or slot_rec.selected_index >= len(slot_rec.recommendations):
            slot_rec.selected_index = 0


def _top_up_slot_recommendations(
    recommendations: list[SlotRecommendation],
    fallback_candidates: list[ScoredRecipe],
    *,
    banned_keys: set[tuple[str, str | int]] | None = None,
    target_count: int = RECOMMENDATIONS_PER_SLOT,
) -> None:
    """Refill each slot recommendation list up to target_count where possible."""
    banned = banned_keys or set()

    selected_aliases_by_slot: dict[tuple[str, str], set[tuple[str, str | int]]] = {}
    selected_aliases: set[tuple[str, str | int]] = set()
    for slot_rec in recommendations:
        if not slot_rec.recommendations:
            continue
        idx = slot_rec.selected_index if 0 <= slot_rec.selected_index < len(slot_rec.recommendations) else 0
        slot_rec.selected_index = idx
        selected = slot_rec.recommendations[idx]
        alias_keys = _recipe_alias_keys(selected)
        if not alias_keys:
            continue
        slot_key = (slot_rec.weekday, slot_rec.slot)
        selected_aliases_by_slot[slot_key] = alias_keys
        selected_aliases.update(alias_keys)

    for slot_rec in recommendations:
        slot_key = (slot_rec.weekday, slot_rec.slot)
        own_selected_aliases = selected_aliases_by_slot.get(slot_key, set())
        existing_keys: set[tuple[str, str | int]] = set()
        for existing in slot_rec.recommendations:
            existing_keys.update(_recipe_alias_keys(existing))

        if len(slot_rec.recommendations) >= target_count:
            continue

        for candidate in fallback_candidates:
            if len(slot_rec.recommendations) >= target_count:
                break
            alias_keys = _recipe_alias_keys(candidate)
            if not alias_keys:
                continue
            if alias_keys & banned:
                continue
            if alias_keys & existing_keys:
                continue
            if (alias_keys & selected_aliases) and not (alias_keys & own_selected_aliases):
                continue
            slot_rec.recommendations.append(candidate)
            existing_keys.update(alias_keys)

        if not slot_rec.recommendations:
            slot_rec.selected_index = -1
        elif slot_rec.selected_index < 0 or slot_rec.selected_index >= len(slot_rec.recommendations):
            slot_rec.selected_index = 0


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
            servings=recipe.servings,
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

    Every recipe appears in at most one slot's recommendation list so the
    user never sees the same dish as a suggestion in two different slots.

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

    # Global pool tracking — each recipe assigned anywhere is removed from
    # future slots so it never appears in two different slot lists.
    globally_used: set[tuple[str, str | int]] = set()

    def _pick_next(pool: list[ScoredRecipe]) -> ScoredRecipe | None:
        """Return the highest-scored recipe from pool not yet globally used."""
        for recipe in pool:
            keys = _recipe_alias_keys(recipe)
            if keys and not (keys & globally_used):
                return recipe
        return None

    def _fill_slot(pool: list[ScoredRecipe], top: ScoredRecipe | None) -> list[ScoredRecipe]:
        """Build a recommendation list of up to RECOMMENDATIONS_PER_SLOT unique recipes."""
        slot_recipes: list[ScoredRecipe] = []
        if top is not None:
            slot_recipes.append(top)
            globally_used.update(_recipe_alias_keys(top))
        for recipe in pool:
            if len(slot_recipes) >= RECOMMENDATIONS_PER_SLOT:
                break
            keys = _recipe_alias_keys(recipe)
            if keys and not (keys & globally_used):
                slot_recipes.append(recipe)
                globally_used.update(keys)
        return slot_recipes

    recommendations: list[SlotRecommendation] = []

    # First pass: assign favorite-led slots (60 %)
    favorites_assigned = 0
    for weekday, slot in slots:
        if favorites_assigned >= target_favorites:
            break
        top = _pick_next(favorites)
        if top is None:
            break
        slot_recipes = _fill_slot(favorites, top)
        favorites_assigned += 1
        recommendations.append(SlotRecommendation(
            weekday=weekday,
            slot=slot,
            recommendations=slot_recipes,
        ))

    # Second pass: assign new-recipe-led slots (remaining)
    assigned_slots = {(r.weekday, r.slot) for r in recommendations}
    for weekday, slot in slots:
        if (weekday, slot) in assigned_slots:
            continue
        top = _pick_next(new_recipes)
        # Fall back to favorites if no new recipe available
        if top is None:
            top = _pick_next(favorites)
        # Merge pool: new recipes first, then favorites as alternatives
        combined_pool = new_recipes + favorites
        slot_recipes = _fill_slot(combined_pool, top)
        # Edge case: no unique recipe left at all — reuse highest-scored favorite
        if not slot_recipes and favorites:
            slot_recipes = [favorites[0]]
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


def _normalize_recipe_url(url: str | None) -> str | None:
    """Normalize URLs to improve duplicate detection."""
    if not url:
        return None
    try:
        parsed = urlsplit(url.strip())
    except Exception:
        return url.strip()

    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    # Ignore query/fragment for deduplication to catch tracking variants.
    return urlunsplit((scheme, netloc, path, "", ""))


def _normalize_recipe_title(title: str | None) -> str | None:
    if not title:
        return None
    normalized = " ".join(title.strip().lower().split())
    return normalized or None


def _recipe_alias_keys(recipe: ScoredRecipe) -> set[tuple[str, str | int]]:
    """Return all stable keys that can identify the same recipe."""
    keys: set[tuple[str, str | int]] = set()
    normalized_url = _normalize_recipe_url(recipe.url)
    if normalized_url:
        keys.add(("url", normalized_url))
    if recipe.recipe_id is not None:
        keys.add(("id", int(recipe.recipe_id)))
    normalized_title = _normalize_recipe_title(recipe.title)
    if normalized_title:
        keys.add(("title", normalized_title))
    return keys


def _recipe_key(recipe: ScoredRecipe) -> tuple[str, str | int] | None:
    """Build a stable key to detect duplicate recipes across slots.

    Uses URL as primary key to ensure consistency across new and saved recipes.
    Falls back to recipe_id if no URL, then title.
    """
    normalized_url = _normalize_recipe_url(recipe.url)
    if normalized_url:
        return ("url", normalized_url)
    if recipe.recipe_id is not None:
        return ("id", int(recipe.recipe_id))
    normalized_title = _normalize_recipe_title(recipe.title)
    if normalized_title:
        return ("title", normalized_title)
    return None


def _normalize_rotation_policy(policy: dict | None) -> dict[str, float | int]:
    """Normalize rotation policy with safe defaults."""
    raw = policy or {}
    try:
        no_repeat_weeks = int(raw.get("no_repeat_weeks", DEFAULT_NO_REPEAT_WEEKS))
    except (TypeError, ValueError):
        no_repeat_weeks = DEFAULT_NO_REPEAT_WEEKS

    try:
        favorite_min_return = int(
            raw.get("favorite_min_return_weeks", DEFAULT_FAVORITE_MIN_RETURN_WEEKS)
        )
    except (TypeError, ValueError):
        favorite_min_return = DEFAULT_FAVORITE_MIN_RETURN_WEEKS

    try:
        bonus_per_week = float(
            raw.get("favorite_return_bonus_per_week", DEFAULT_FAVORITE_RETURN_BONUS_PER_WEEK)
        )
    except (TypeError, ValueError):
        bonus_per_week = DEFAULT_FAVORITE_RETURN_BONUS_PER_WEEK

    try:
        bonus_max = float(raw.get("favorite_return_bonus_max", DEFAULT_FAVORITE_RETURN_BONUS_MAX))
    except (TypeError, ValueError):
        bonus_max = DEFAULT_FAVORITE_RETURN_BONUS_MAX

    return {
        "no_repeat_weeks": max(0, no_repeat_weeks),
        "favorite_min_return_weeks": max(0, favorite_min_return),
        "favorite_return_bonus_per_week": max(0.0, bonus_per_week),
        "favorite_return_bonus_max": max(0.0, bonus_max),
    }


def _build_recipe_recency_map(week_history: list[dict]) -> dict[tuple[str, str | int], int]:
    """Build recipe key -> weeks_since_last_seen map from recent completed weeks.

    Most recent completed week has value 1.
    """
    recency: dict[tuple[str, str | int], int] = {}
    for idx, week in enumerate(week_history):
        weeks_since = idx + 1
        for recipe in week.get("recipes", []):
            url = recipe.get("url")
            recipe_id = recipe.get("recipe_id")
            title = recipe.get("title")

            key: tuple[str, str | int] | None = None
            normalized_url = _normalize_recipe_url(url)
            normalized_title = _normalize_recipe_title(title)
            if normalized_url:
                key = ("url", normalized_url)
            elif recipe_id is not None:
                key = ("id", int(recipe_id))
            elif normalized_title:
                key = ("title", normalized_title)

            if key is None or key in recency:
                continue
            recency[key] = weeks_since
    return recency


def _filter_new_recipes_by_rotation(
    recipes: list[ScoredRecipe],
    recency_map: dict[tuple[str, str | int], int],
    no_repeat_weeks: int,
) -> list[ScoredRecipe]:
    """Filter new recipes using hard no-repeat window."""
    filtered: list[ScoredRecipe] = []
    for recipe in recipes:
        key = _recipe_key(recipe)
        weeks_since = recency_map.get(key) if key else None
        if weeks_since is not None and weeks_since <= no_repeat_weeks:
            continue
        filtered.append(recipe)
    return filtered


def _filter_and_boost_favorites_by_rotation(
    favorites: list[ScoredRecipe],
    recency_map: dict[tuple[str, str | int], int],
    no_repeat_weeks: int,
    favorite_min_return_weeks: int,
    bonus_per_week: float,
    bonus_max: float,
) -> list[ScoredRecipe]:
    """Apply cooldown and comeback bonus to favorites.

    Rules:
    - Never repeat inside no_repeat_weeks.
    - Favorites can return only after favorite_min_return_weeks.
    - Older favorites get a score bonus to reintroduce proven dishes regularly.
    """
    boosted: list[ScoredRecipe] = []
    for favorite in favorites:
        key = _recipe_key(favorite)
        weeks_since = recency_map.get(key) if key else None

        if weeks_since is not None and weeks_since <= no_repeat_weeks:
            continue
        if weeks_since is not None and weeks_since < favorite_min_return_weeks:
            continue

        score_bonus = 0.0
        reasoning = favorite.reasoning
        if weeks_since is not None and favorite_min_return_weeks > 0:
            eligible_gap = max(0, weeks_since - favorite_min_return_weeks + 1)
            score_bonus = min(bonus_max, eligible_gap * bonus_per_week)
            if score_bonus > 0:
                reasoning = f"{reasoning} Rotation: zuletzt vor {weeks_since} Wochen gekocht."

        boosted.append(
            replace(
                favorite,
                score=min(100.0, favorite.score + score_bonus),
                reasoning=reasoning,
            )
        )

    boosted.sort(key=lambda x: x.score, reverse=True)
    return boosted


def _get_last_plan_recipe_keys(plan: WeeklyRecommendation | None) -> set[tuple[str, str | int]]:
    """Alle 5 Vorschläge jedes Slots sperren (nicht nur ausgewählte)."""
    if not plan:
        return set()

    keys: set[tuple[str, str | int]] = set()
    for slot in plan.slots:
        for recipe in slot.recommendations:  # alle 5
            keys.update(_recipe_alias_keys(recipe))
    return keys


def _build_multi_day_maps(
    preferences: list[dict] | None,
) -> tuple[dict[tuple[str, str], int], set[tuple[str, str]]]:
    """Build lookup maps for multi-day preferences."""
    group_id_by_slot: dict[tuple[str, str], int] = {}
    planned_reuse_slots: set[tuple[str, str]] = set()

    if not preferences:
        return group_id_by_slot, planned_reuse_slots

    for idx, group in enumerate(preferences):
        primary = (group.get("primary_weekday"), group.get("primary_slot"))
        if None in primary:
            continue
        group_id_by_slot[primary] = idx
        for reuse in group.get("reuse_slots", []):
            slot = (reuse.get("weekday"), reuse.get("slot"))
            if None in slot:
                continue
            group_id_by_slot[slot] = idx
            planned_reuse_slots.add(slot)

    return group_id_by_slot, planned_reuse_slots


def _select_unique_recipes(
    recommendations: list[SlotRecommendation],
    group_id_by_slot: dict[tuple[str, str], int],
    planned_reuse_slots: set[tuple[str, str]],
    banned_keys: set[tuple[str, str | int]] | None = None,
) -> None:
    """Pick unique default selections across slots."""
    used_aliases: set[tuple[str, str | int]] = set()
    banned_keys = banned_keys or set()

    for slot_rec in recommendations:
        slot_key = (slot_rec.weekday, slot_rec.slot)

        # Planned reuse slots will be overridden later
        if slot_key in planned_reuse_slots:
            continue

        chosen_index = -1
        found_allowed = False
        for idx, recipe in enumerate(slot_rec.recommendations):
            alias_keys = _recipe_alias_keys(recipe)
            if not alias_keys:
                continue
            if alias_keys & banned_keys:
                continue
            if alias_keys & used_aliases:
                continue
            chosen_index = idx
            found_allowed = True
            break

        if not found_allowed:
            # All recommendations already used elsewhere — pick the least-bad option:
            # prefer a recipe already used (duplicate) over one that is banned.
            # This avoids blank slots while still respecting the banned list first.
            for idx, recipe in enumerate(slot_rec.recommendations):
                alias_keys = _recipe_alias_keys(recipe)
                if not alias_keys or alias_keys & banned_keys:
                    continue
                # Accept duplicate only if not already selected for this exact slot
                chosen_index = idx
                found_allowed = True
                break

        slot_rec.selected_index = chosen_index
        if slot_rec.recommendations and found_allowed:
            chosen = slot_rec.recommendations[chosen_index]
            used_aliases.update(_recipe_alias_keys(chosen))


def _filter_slot_recommendations_by_banned_keys(
    recommendations: list[SlotRecommendation],
    banned_keys: set[tuple[str, str | int]],
) -> None:
    """Remove banned recipes from slot recommendation lists."""
    if not banned_keys:
        return

    for slot_rec in recommendations:
        slot_rec.recommendations = [
            recipe
            for recipe in slot_rec.recommendations
            if not (_recipe_alias_keys(recipe) & banned_keys)
        ]


def run_search_agent(
    target_day: str | None = None,
    target_slot: str | None = None,
    *,
    multi_day_preferences: list[dict] | None = None,
    skipped_slots: list[dict] | None = None,
    exclude_recipe_urls: list[str] | None = None,
    rotation_policy: dict | None = None,
) -> WeeklyRecommendation:
    """Run the recipe search agent.

    Args:
        target_day: Specific weekday to generate for (e.g., "Mittwoch"), or None for full week
        target_slot: Specific slot to generate for (e.g., "Abendessen"), or None for all
        multi_day_preferences: Optional multi-day meal prep configurations
        skipped_slots: Optional list of slots to skip during generation
        exclude_recipe_urls: Optional list of recipe URLs to exclude (e.g., from previous week)
        rotation_policy: Optional rotation config overrides

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

    # Load rotation history
    rotation = _normalize_rotation_policy(rotation_policy)
    week_history = get_recent_ha_week_recipe_history(
        max(rotation["favorite_min_return_weeks"], rotation["no_repeat_weeks"], 1) + 8
    )
    recency_map = _build_recipe_recency_map(week_history)
    print(
        "   Rotation policy:"
        f" no_repeat_weeks={rotation['no_repeat_weeks']},"
        f" favorite_min_return_weeks={rotation['favorite_min_return_weeks']}"
    )
    print(f"   Rotation history loaded: {len(week_history)} weeks, {len(recency_map)} recipes")

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
    skipped_set: set[tuple[str, str]] = set()
    if skipped_slots:
        for slot in skipped_slots:
            weekday = slot.get("weekday")
            meal_slot = slot.get("slot")
            if weekday and meal_slot:
                skipped_set.add((weekday, meal_slot))

    groups = _get_slot_groups_to_search(target_day, target_slot, skipped_set)
    all_slots = [(day, slot) for slots in groups.values() for day, slot in slots]
    print(f"   {len(all_slots)} slots to fill")

    # Load favorites from DB
    print("\n6. Loading favorites from DB...")
    favorites_raw = _get_favorites_from_db()
    print(f"   {len(favorites_raw)} recipes found in DB")

    favorites = _score_favorites(favorites_raw, context)
    favorites = _filter_and_boost_favorites_by_rotation(
        favorites,
        recency_map,
        no_repeat_weeks=rotation["no_repeat_weeks"],
        favorite_min_return_weeks=rotation["favorite_min_return_weeks"],
        bonus_per_week=rotation["favorite_return_bonus_per_week"],
        bonus_max=rotation["favorite_return_bonus_max"],
    )
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
    new_recipes = _filter_new_recipes_by_rotation(
        new_recipes,
        recency_map,
        no_repeat_weeks=rotation["no_repeat_weeks"],
    )
    print(f"   {len(new_recipes)} viable new recipes")

    # Assign recipes to slots
    print("\n10. Assigning recipes to slots...")
    slot_recommendations = _assign_recipes_to_slots(
        all_slots, favorites, new_recipes, context
    )

    # Build banned keys from previous plan (if provided) or by loading saved plan
    if exclude_recipe_urls:
        # Use explicitly provided exclusion list (from API)
        banned_keys = {
            ("url", normalized)
            for normalized in (_normalize_recipe_url(url) for url in exclude_recipe_urls)
            if normalized
        }
        print(f"\n   Excluding {len(banned_keys)} recipes from previous week")
    else:
        # Fallback: load previous plan from disk (for backward compatibility)
        last_plan = load_weekly_plan()
        banned_keys = _get_last_plan_recipe_keys(last_plan)
        print(f"\n   Loaded {len(banned_keys)} banned recipes from previous plan")

    group_id_by_slot, planned_reuse_slots = _build_multi_day_maps(multi_day_preferences)
    _filter_slot_recommendations_by_banned_keys(slot_recommendations, banned_keys)
    _select_unique_recipes(
        slot_recommendations,
        group_id_by_slot,
        planned_reuse_slots,
        banned_keys=banned_keys,
    )
    _remove_selected_recipe_duplicates_from_alternatives(slot_recommendations)
    fallback_pool: list[ScoredRecipe] = []
    seen_fallback_keys: set[tuple[str, str | int]] = set()
    for recipe in sorted(
        [r for slot in slot_recommendations for r in slot.recommendations] + new_recipes + favorites,
        key=lambda r: r.score,
        reverse=True,
    ):
        alias_keys = _recipe_alias_keys(recipe)
        if not alias_keys:
            continue
        if alias_keys & banned_keys:
            continue
        if alias_keys & seen_fallback_keys:
            continue
        seen_fallback_keys.update(alias_keys)
        fallback_pool.append(recipe)
    _top_up_slot_recommendations(
        slot_recommendations,
        fallback_pool,
        banned_keys=banned_keys,
        target_count=RECOMMENDATIONS_PER_SLOT,
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

    if multi_day_preferences:
        for group in multi_day_preferences:
            primary_weekday = group.get("primary_weekday")
            primary_slot = group.get("primary_slot")
            reuse_slots = [
                (r.get("weekday"), r.get("slot"))
                for r in group.get("reuse_slots", [])
                if r.get("weekday") and r.get("slot")
            ]
            if primary_weekday and primary_slot and reuse_slots:
                result.set_multi_day(primary_weekday, primary_slot, reuse_slots)

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

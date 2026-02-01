"""Recipe scoring system based on user preferences and availability.

This module calculates a score for recipes based on multiple factors:
- Ingredient affinity (40%): How well the recipe matches user's favorite ingredients
- Time compatibility (25%): How well the prep time fits the user's pattern for that slot
- Bioland availability (20%): How many ingredients are available at Bioland
- Seasonality (15%): How many ingredients are currently in season

Example usage:
    >>> from src.scoring.recipe_scorer import calculate_score, ScoringContext
    >>> context = ScoringContext(
    ...     weekday="Montag",
    ...     meal_slot="Abendessen",
    ...     profile=load_profile(),
    ...     available_ingredients=get_available_base_ingredients()
    ... )
    >>> score = calculate_score(recipe, context)
    >>> print(f"{recipe.title}: {score.total_score:.1f} - {score.reasoning}")
"""

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from src.core.config import LOCAL_DIR
from src.models.recipe import Recipe
from src.scoring.seasonality import is_in_season

# Scoring weights
WEIGHT_INGREDIENT_AFFINITY = 0.40
WEIGHT_TIME_COMPATIBILITY = 0.25
WEIGHT_BIOLAND_AVAILABILITY = 0.20
WEIGHT_SEASONALITY = 0.15

# Rating multipliers for user ratings (1-5 stars)
RATING_MULTIPLIERS = {
    1: 0.0,   # Blacklist (Score = 0, filtered in is_recipe_viable)
    2: 0.85,  # -15%
    3: 1.00,  # Neutral
    4: 1.10,  # +10%
    5: 1.20,  # +20%
}

# Availability filter threshold
# Recipes with less than this percentage of obtainable ingredients are excluded
MIN_OBTAINABLE_RATIO = 0.5  # 50% of ingredients must be obtainable

# Profile file path
PROFILE_FILE = LOCAL_DIR / "preference_profile.json"


@dataclass
class ScoringContext:
    """Context for scoring a recipe.

    Attributes:
        weekday: German weekday name (e.g., "Montag", "Dienstag")
        meal_slot: Meal slot ("Mittagessen" or "Abendessen")
        profile: User preference profile (from preference_profile.json)
        available_ingredients: Set of base ingredients available at Bioland
        month: Month for seasonality check (1-12), defaults to current month
        recipe_ratings: Dict mapping recipe_id to rating (1-5)
        blacklisted_ids: Set of recipe IDs that are blacklisted (rating = 1)
    """

    weekday: str
    meal_slot: str
    profile: dict
    available_ingredients: set[str] = field(default_factory=set)
    month: int | None = None
    recipe_ratings: dict[int, int] = field(default_factory=dict)
    blacklisted_ids: set[int] = field(default_factory=set)

    def __post_init__(self):
        if self.month is None:
            self.month = date.today().month


@dataclass
class ScoreBreakdown:
    """Detailed breakdown of a recipe's score.

    All component scores are normalized to 0-100 scale.
    """

    total_score: float  # 0-100
    ingredient_affinity: float  # 0-100
    time_compatibility: float  # 0-100
    bioland_availability: float  # 0-100
    seasonality: float  # 0-100
    reasoning: str = ""

    # Additional details for transparency
    matched_favorite_ingredients: list[str] = field(default_factory=list)
    available_at_bioland: list[str] = field(default_factory=list)
    out_of_season: list[str] = field(default_factory=list)

    # User rating info
    rating_multiplier: float = 1.0
    user_rating: int | None = None


def load_profile(profile_path: Path | None = None) -> dict:
    """Load the user preference profile from disk.

    Args:
        profile_path: Optional path to profile file. Defaults to standard location.

    Returns:
        Profile dict or empty dict if not found.
    """
    path = profile_path or PROFILE_FILE
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _get_recipe_base_ingredients(recipe: Recipe, profile: dict) -> list[str]:
    """Extract base ingredients from a recipe.

    Uses the profile's ingredient_preferences to map raw ingredients to base form.
    Falls back to simple lowercase normalization.

    Args:
        recipe: Recipe to extract ingredients from
        profile: User profile containing ingredient mappings

    Returns:
        List of normalized base ingredient names
    """
    # Build a lookup of known base ingredients from profile
    known_ingredients = {
        pref["base_ingredient"].lower()
        for pref in profile.get("ingredient_preferences", [])
    }

    base_ingredients = []
    for ing in recipe.ingredients:
        # Simple normalization: lowercase and strip
        ing_lower = ing.lower().strip()

        # Try to find a matching base ingredient
        matched = False
        for known in known_ingredients:
            if known in ing_lower or ing_lower in known:
                base_ingredients.append(known)
                matched = True
                break

        if not matched:
            # Use the raw ingredient (simplified)
            # Remove common prefixes/suffixes
            simplified = ing_lower.split(",")[0].strip()
            words = simplified.split()
            if words:
                # Take last word as likely ingredient name
                base_ingredients.append(words[-1])

    return base_ingredients


def _calculate_ingredient_affinity(
    recipe_ingredients: list[str],
    profile: dict,
) -> tuple[float, list[str]]:
    """Calculate how well the recipe matches user's ingredient preferences.

    Args:
        recipe_ingredients: List of base ingredient names in the recipe
        profile: User preference profile

    Returns:
        Tuple of (score 0-100, list of matched favorite ingredients)
    """
    if not recipe_ingredients:
        return 50.0, []  # Neutral score for no ingredients

    # Get favorite ingredients from profile (top 30)
    preferences = profile.get("ingredient_preferences", [])
    if not preferences:
        return 50.0, []  # No profile = neutral score

    # Build a dict of ingredient -> rank (lower rank = more preferred)
    favorite_ranks = {
        pref["base_ingredient"].lower(): i
        for i, pref in enumerate(preferences[:30])
    }

    # Calculate affinity score
    matched = []
    total_score = 0.0

    for ing in recipe_ingredients:
        ing_lower = ing.lower()
        if ing_lower in favorite_ranks:
            rank = favorite_ranks[ing_lower]
            # Higher score for higher-ranked ingredients
            # Rank 0 (top) = 100 points, Rank 29 = ~3 points
            score = 100 * (1 - rank / 30)
            total_score += score
            matched.append(ing_lower)

    if not matched:
        # No favorite ingredients found - give partial credit
        return 30.0, []

    # Normalize to 0-100 (average score of matches, with bonus for multiple matches)
    avg_score = total_score / len(matched)
    # Bonus for having multiple favorite ingredients (up to 20% boost)
    match_bonus = min(20, len(matched) * 5)
    final_score = min(100, avg_score + match_bonus)

    return final_score, matched


def _calculate_time_compatibility(
    recipe_prep_time: int | None,
    context: ScoringContext,
) -> float:
    """Calculate how well the recipe's prep time fits the slot's pattern.

    Args:
        recipe_prep_time: Recipe preparation time in minutes
        context: Scoring context with weekday and slot info

    Returns:
        Score 0-100 (100 = perfect fit, 0 = way too long/short)
    """
    if recipe_prep_time is None:
        return 50.0  # Unknown time = neutral score

    # Get expected prep time for this slot
    weekday_patterns = context.profile.get("weekday_patterns", {})
    slot_data = weekday_patterns.get(context.weekday, {}).get(context.meal_slot, {})
    expected_time = slot_data.get("avg_prep_time_min")

    if expected_time is None:
        # No pattern data - use general average
        overall = context.profile.get("overall_nutrition", {})
        expected_time = overall.get("avg_prep_time_min", 45)

    if expected_time == 0:
        expected_time = 45  # Fallback

    # Calculate deviation
    deviation = abs(recipe_prep_time - expected_time) / expected_time

    # Score: 100 for perfect match, decreasing with deviation
    # At 50% deviation: score ~50, at 100% deviation: score ~0
    if deviation <= 0.2:
        return 100.0  # Within 20% is perfect
    elif deviation <= 0.5:
        return 100 - (deviation - 0.2) * 166  # Linear decrease to ~50
    elif deviation <= 1.0:
        return 50 - (deviation - 0.5) * 80  # Slower decrease to ~10
    else:
        return max(0, 10 - (deviation - 1.0) * 10)


def _calculate_bioland_availability(
    recipe_ingredients: list[str],
    available_ingredients: set[str],
) -> tuple[float, list[str]]:
    """Calculate what percentage of ingredients is available at Bioland.

    Args:
        recipe_ingredients: List of base ingredient names
        available_ingredients: Set of ingredients available at Bioland

    Returns:
        Tuple of (score 0-100, list of available ingredients)
    """
    if not recipe_ingredients:
        return 50.0, []  # No ingredients = neutral

    available_lower = {i.lower() for i in available_ingredients}
    available_in_recipe = []

    for ing in recipe_ingredients:
        ing_lower = ing.lower()
        # Check direct match or if Bioland ingredient contains recipe ingredient
        if ing_lower in available_lower:
            available_in_recipe.append(ing_lower)
        elif any(ing_lower in avail or avail in ing_lower for avail in available_lower):
            available_in_recipe.append(ing_lower)

    # Score based on percentage available
    if len(recipe_ingredients) == 0:
        return 50.0, []

    percentage = len(available_in_recipe) / len(recipe_ingredients)
    score = percentage * 100

    return score, available_in_recipe


def _calculate_seasonality(
    recipe_ingredients: list[str],
    month: int,
) -> tuple[float, list[str]]:
    """Calculate how seasonal the recipe's ingredients are.

    Args:
        recipe_ingredients: List of base ingredient names
        month: Current month (1-12)

    Returns:
        Tuple of (score 0-100, list of out-of-season ingredients)
    """
    if not recipe_ingredients:
        return 100.0, []  # No ingredients = assume seasonal

    out_of_season = []
    in_season_count = 0
    checked_count = 0

    for ing in recipe_ingredients:
        result = is_in_season(ing.lower(), month)
        if result is None:
            # Unknown ingredient - assume available
            in_season_count += 1
            checked_count += 1
        elif result:
            in_season_count += 1
            checked_count += 1
        else:
            out_of_season.append(ing.lower())
            checked_count += 1

    if checked_count == 0:
        return 100.0, []

    score = (in_season_count / checked_count) * 100
    return score, out_of_season


def is_ingredient_obtainable(
    ingredient: str,
    available_ingredients: set[str],
    month: int,
) -> bool:
    """Check if an ingredient can be obtained (Bioland OR seasonal).

    An ingredient is obtainable if:
    - It's available at Bioland, OR
    - It's currently in season, OR
    - It's not in the seasonal calendar (assumed year-round, e.g., pasta, rice)

    Args:
        ingredient: Base ingredient name
        available_ingredients: Set of ingredients available at Bioland
        month: Current month (1-12)

    Returns:
        True if the ingredient can be obtained
    """
    ing_lower = ingredient.lower()
    available_lower = {i.lower() for i in available_ingredients}

    # Check Bioland availability
    if ing_lower in available_lower:
        return True
    # Fuzzy match for Bioland
    if any(ing_lower in avail or avail in ing_lower for avail in available_lower):
        return True

    # Check seasonality
    season_result = is_in_season(ing_lower, month)
    if season_result is None:
        # Not in calendar = assumed year-round (pasta, rice, spices, etc.)
        return True
    if season_result:
        # In season
        return True

    return False


def get_unobtainable_ingredients(
    recipe_ingredients: list[str],
    available_ingredients: set[str],
    month: int,
) -> list[str]:
    """Get list of ingredients that cannot be obtained.

    Args:
        recipe_ingredients: List of base ingredient names
        available_ingredients: Set of ingredients available at Bioland
        month: Current month (1-12)

    Returns:
        List of ingredients that are neither at Bioland nor in season
    """
    unobtainable = []
    for ing in recipe_ingredients:
        if not is_ingredient_obtainable(ing, available_ingredients, month):
            unobtainable.append(ing.lower())
    return unobtainable


def _is_key_ingredient(ingredient: str, recipe_title: str) -> bool:
    """Check if an ingredient is a key/main ingredient based on recipe title.

    Args:
        ingredient: Ingredient name to check
        recipe_title: Recipe title

    Returns:
        True if the ingredient appears in the recipe title
    """
    ing_lower = ingredient.lower()
    title_lower = recipe_title.lower()

    # Direct match
    if ing_lower in title_lower:
        return True

    # Common German variations
    variations = {
        "spargel": ["spargel"],
        "tomate": ["tomate", "tomaten"],
        "kartoffel": ["kartoffel", "kartoffeln"],
        "kürbis": ["kürbis", "hokkaido", "butternut"],
        "erdbeere": ["erdbeere", "erdbeer"],
        "pilz": ["pilz", "pilze", "champignon", "pfifferling"],
        "lachs": ["lachs"],
        "hähnchen": ["hähnchen", "huhn", "hühnchen", "chicken"],
        "rind": ["rind", "beef", "steak"],
        "schwein": ["schwein", "pork", "schnitzel"],
    }

    for base, vars in variations.items():
        if ing_lower == base or any(v in ing_lower for v in vars):
            if any(v in title_lower for v in vars):
                return True

    return False


def is_recipe_viable(
    recipe: Recipe,
    context: ScoringContext,
    min_obtainable_ratio: float = MIN_OBTAINABLE_RATIO,
) -> tuple[bool, list[str], float]:
    """Check if a recipe is viable (enough ingredients can be obtained).

    A recipe is viable if:
    1. Recipe is not blacklisted by user (1 star rating), AND
    2. All key ingredients (those in the title) can be obtained, AND
    3. At least `min_obtainable_ratio` of all ingredients can be obtained

    Args:
        recipe: Recipe to check
        context: Scoring context with availability data
        min_obtainable_ratio: Minimum ratio of obtainable ingredients (0.0-1.0)

    Returns:
        Tuple of (is_viable, unobtainable_ingredients, obtainable_ratio)
    """
    # Check blacklist first
    if recipe.id and recipe.id in context.blacklisted_ids:
        return (False, ["Vom User ausgeschlossen (1 Stern)"], 0.0)

    # Extract base ingredients
    recipe_ingredients = _get_recipe_base_ingredients(recipe, context.profile)

    if not recipe_ingredients:
        return True, [], 1.0  # No ingredients = viable

    # Check each ingredient
    unobtainable = get_unobtainable_ingredients(
        recipe_ingredients,
        context.available_ingredients,
        context.month,
    )

    obtainable_count = len(recipe_ingredients) - len(unobtainable)
    obtainable_ratio = obtainable_count / len(recipe_ingredients)

    # Check if any key ingredient is unobtainable
    key_ingredient_missing = False
    for ing in unobtainable:
        if _is_key_ingredient(ing, recipe.title):
            key_ingredient_missing = True
            break

    # Recipe is viable only if:
    # 1. No key ingredients are missing
    # 2. Enough total ingredients are obtainable
    is_viable = (
        not key_ingredient_missing and
        obtainable_ratio >= min_obtainable_ratio
    )

    return is_viable, unobtainable, obtainable_ratio


def generate_reasoning(score: ScoreBreakdown) -> str:
    """Generate a human-readable explanation of the score.

    Args:
        score: ScoreBreakdown with component scores

    Returns:
        German-language reasoning string
    """
    reasons = []

    # User rating info
    if score.user_rating is not None:
        if score.user_rating >= 4:
            reasons.append(f"Favorit ({score.user_rating} Sterne)")
        elif score.user_rating == 2:
            reasons.append("Weniger bevorzugt (2 Sterne)")

    # Ingredient affinity
    if score.ingredient_affinity >= 80:
        reasons.append(f"Enthält Lieblingszutaten ({', '.join(score.matched_favorite_ingredients[:3])})")
    elif score.ingredient_affinity >= 50:
        if score.matched_favorite_ingredients:
            reasons.append("Enthält einige bevorzugte Zutaten")
    else:
        reasons.append("Wenige Lieblingszutaten")

    # Time compatibility
    if score.time_compatibility >= 80:
        reasons.append("Zubereitungszeit passt perfekt zum Slot")
    elif score.time_compatibility >= 50:
        reasons.append("Zubereitungszeit ist akzeptabel")
    elif score.time_compatibility < 30:
        reasons.append("Zubereitungszeit passt nicht gut zum Slot")

    # Bioland availability
    if score.bioland_availability >= 80:
        reasons.append("Viele Zutaten bei Bioland verfügbar")
    elif score.bioland_availability >= 50:
        reasons.append("Einige Zutaten bei Bioland verfügbar")
    elif score.bioland_availability < 30:
        reasons.append("Wenige Zutaten bei Bioland verfügbar")

    # Seasonality
    if score.seasonality >= 90:
        reasons.append("Alle Zutaten saisonal")
    elif score.seasonality >= 70:
        reasons.append("Überwiegend saisonal")
    elif score.out_of_season:
        reasons.append(f"Nicht saisonal: {', '.join(score.out_of_season[:2])}")

    return ". ".join(reasons) + "." if reasons else "Keine besonderen Merkmale."


def calculate_score(
    recipe: Recipe,
    context: ScoringContext,
) -> ScoreBreakdown:
    """Calculate the overall score for a recipe in the given context.

    Args:
        recipe: Recipe to score
        context: Scoring context with user profile and availability data

    Returns:
        ScoreBreakdown with total score and component scores
    """
    # Extract base ingredients from recipe
    recipe_ingredients = _get_recipe_base_ingredients(recipe, context.profile)

    # Calculate component scores
    ingredient_affinity, matched_favorites = _calculate_ingredient_affinity(
        recipe_ingredients, context.profile
    )

    time_compatibility = _calculate_time_compatibility(
        recipe.prep_time_minutes, context
    )

    bioland_availability, available_at_bioland = _calculate_bioland_availability(
        recipe_ingredients, context.available_ingredients
    )

    seasonality, out_of_season = _calculate_seasonality(
        recipe_ingredients, context.month
    )

    # Calculate weighted total
    total_score = (
        ingredient_affinity * WEIGHT_INGREDIENT_AFFINITY +
        time_compatibility * WEIGHT_TIME_COMPATIBILITY +
        bioland_availability * WEIGHT_BIOLAND_AVAILABILITY +
        seasonality * WEIGHT_SEASONALITY
    )

    # Apply user rating multiplier
    user_rating = None
    rating_multiplier = 1.0
    if recipe.id:
        user_rating = context.recipe_ratings.get(recipe.id)
        if user_rating is not None:
            rating_multiplier = RATING_MULTIPLIERS[user_rating]
            total_score *= rating_multiplier

    # Create score breakdown
    score = ScoreBreakdown(
        total_score=round(total_score, 1),
        ingredient_affinity=round(ingredient_affinity, 1),
        time_compatibility=round(time_compatibility, 1),
        bioland_availability=round(bioland_availability, 1),
        seasonality=round(seasonality, 1),
        matched_favorite_ingredients=matched_favorites,
        available_at_bioland=available_at_bioland,
        out_of_season=out_of_season,
        rating_multiplier=rating_multiplier,
        user_rating=user_rating,
    )

    # Generate reasoning
    score.reasoning = generate_reasoning(score)

    return score


def score_recipes(
    recipes: list[Recipe],
    context: ScoringContext,
    top_n: int | None = None,
    filter_unavailable: bool = True,
    min_obtainable_ratio: float = MIN_OBTAINABLE_RATIO,
) -> list[tuple[Recipe, ScoreBreakdown]]:
    """Score multiple recipes and return sorted by score.

    Args:
        recipes: List of recipes to score
        context: Scoring context
        top_n: If set, return only top N results
        filter_unavailable: If True, exclude recipes with too many unobtainable ingredients
        min_obtainable_ratio: Minimum ratio of obtainable ingredients (0.0-1.0)

    Returns:
        List of (recipe, score) tuples, sorted by total_score descending
    """
    scored = []
    filtered_count = 0

    for recipe in recipes:
        # Check viability first if filtering is enabled
        if filter_unavailable:
            is_viable, unobtainable, ratio = is_recipe_viable(
                recipe, context, min_obtainable_ratio
            )
            if not is_viable:
                filtered_count += 1
                continue

        score = calculate_score(recipe, context)
        scored.append((recipe, score))

    if filtered_count > 0:
        print(f"  Filtered {filtered_count} recipes with unobtainable ingredients")

    scored.sort(key=lambda x: x[1].total_score, reverse=True)

    if top_n:
        return scored[:top_n]
    return scored


if __name__ == "__main__":
    from src.core.database import get_all_recipes, get_available_base_ingredients

    print("=" * 60)
    print("Recipe Scoring System Test")
    print("=" * 60)

    # Load profile
    profile = load_profile()
    if not profile:
        print("No preference profile found. Run preference_profile.py first.")
        exit(1)

    print(f"Profile loaded: {profile.get('summary', {}).get('total_meals', 0)} meals")

    # Get available ingredients
    available = get_available_base_ingredients("bioland_huesgen")
    print(f"Bioland ingredients: {len(available)}")

    # Create context
    context = ScoringContext(
        weekday="Montag",
        meal_slot="Abendessen",
        profile=profile,
        available_ingredients=available,
    )

    # Get recipes and score them
    recipes = get_all_recipes()
    if not recipes:
        print("No recipes in database.")
        exit(1)

    print(f"\nScoring {len(recipes)} recipes for {context.weekday} {context.meal_slot}...\n")

    # Get top 10
    top_recipes = score_recipes(recipes, context, top_n=10)

    print("Top 10 Recipes:")
    print("-" * 60)
    for i, (recipe, score) in enumerate(top_recipes, 1):
        print(f"{i:2}. {recipe.title[:40]:<40} Score: {score.total_score:5.1f}")
        print(f"    Zutaten: {score.ingredient_affinity:.0f} | Zeit: {score.time_compatibility:.0f} | "
              f"Bioland: {score.bioland_availability:.0f} | Saison: {score.seasonality:.0f}")
        print(f"    {score.reasoning}")
        print()

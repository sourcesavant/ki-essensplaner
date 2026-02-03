"""Generate a user preference profile from meal plan history.

This module analyzes the user's meal history to derive cooking preferences:
1. Ingredient preferences (filtered by distinctiveness)
2. Effort patterns per weekday and slot (lunch/dinner)
3. Nutrition patterns per weekday

The profile filters out universal ingredients (appearing in >70% of recipes)
since they don't differentiate preferences (e.g., salt, pepper).

Example usage:
    >>> from src.profile.preference_profile import generate_profile
    >>> profile = generate_profile()
    >>> print(profile["ingredient_preferences"][:5])
    >>> print(profile["weekday_patterns"]["Monday"])

Issue #6: Leite Vorlieben-Profil aus Daten ab
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.core.config import DATA_DIR
from src.core.database import get_connection, get_all_recipes
from src.profile.pseudo_recipes import get_all_pseudo_recipes

# Output path for the generated profile
PROFILE_PATH = DATA_DIR / "local" / "preference_profile.json"


# Threshold for filtering universal ingredients (appear in >70% of recipes)
UNIVERSAL_INGREDIENT_THRESHOLD = 0.70

# Profile update interval in days
PROFILE_UPDATE_INTERVAL_DAYS = 7

# Profile version for tracking schema changes
PROFILE_VERSION = "1.0"


@dataclass
class WeekdaySlotPattern:
    """Pattern data for a specific weekday and meal slot.

    Attributes:
        meal_count: Number of meals in this slot
        avg_prep_time: Average preparation time in minutes
        avg_calories: Average calories per meal
        avg_protein: Average protein in grams
        avg_carbs: Average carbohydrates in grams
        avg_fat: Average fat in grams
        top_ingredients: Most frequent ingredients for this slot
    """
    meal_count: int = 0
    avg_prep_time: float | None = None
    avg_calories: float | None = None
    avg_protein: float | None = None
    avg_carbs: float | None = None
    avg_fat: float | None = None
    top_ingredients: list[str] = field(default_factory=list)


def get_total_recipe_count() -> int:
    """Get total number of recipes (excluding test data)."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM recipes WHERE source != 'test'"
        ).fetchone()[0]


def get_universal_ingredients(threshold: float = UNIVERSAL_INGREDIENT_THRESHOLD) -> set[str]:
    """Get ingredients that appear in more than threshold% of recipes.

    These are filtered out as they don't indicate preferences.

    Args:
        threshold: Fraction of recipes (0.0-1.0) above which an ingredient
                   is considered universal

    Returns:
        Set of base_ingredient names to filter out
    """
    total_recipes = get_total_recipe_count()
    min_count = int(total_recipes * threshold)

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT base_ingredient, COUNT(DISTINCT recipe_id) as recipe_count
            FROM parsed_ingredients
            WHERE base_ingredient IS NOT NULL AND base_ingredient != ''
            GROUP BY base_ingredient
            HAVING recipe_count > ?
        """, (min_count,)).fetchall()

    return {row["base_ingredient"] for row in rows}


def get_distinctive_ingredient_frequencies() -> list[dict]:
    """Get ingredient frequencies excluding universal ingredients.

    Returns:
        List of {base_ingredient, recipe_count, total_count} sorted by frequency
    """
    universal = get_universal_ingredients()

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT
                base_ingredient,
                COUNT(*) as total_count,
                COUNT(DISTINCT recipe_id) as recipe_count
            FROM parsed_ingredients
            WHERE base_ingredient IS NOT NULL
              AND base_ingredient != ''
            GROUP BY base_ingredient
            ORDER BY recipe_count DESC, total_count DESC
        """).fetchall()

    return [
        {
            "base_ingredient": row["base_ingredient"],
            "total_count": row["total_count"],
            "recipe_count": row["recipe_count"],
        }
        for row in rows
        if row["base_ingredient"] not in universal
    ]


def get_weekday_slot_data(include_pseudo: bool = True) -> dict[str, dict[str, list[dict]]]:
    """Get meal data grouped by weekday and slot.

    Args:
        include_pseudo: Include pseudo-recipes (simple meal names without URLs)

    Returns:
        Nested dict: weekday -> slot -> list of meal data
        Each meal has: prep_time, calories, protein, carbs, fat, ingredients, is_pseudo
    """
    # Map day_of_week integer (0=Monday) to German weekday names
    day_mapping = {
        0: "Montag",
        1: "Dienstag",
        2: "Mittwoch",
        3: "Donnerstag",
        4: "Freitag",
        5: "Samstag",
        6: "Sonntag",
    }

    # Map slot enum values to German names
    slot_mapping = {
        "lunch": "Mittagessen",
        "dinner": "Abendessen",
    }

    weekdays = list(day_mapping.values())
    result = {day: {"Mittagessen": [], "Abendessen": []} for day in weekdays}

    with get_connection() as conn:
        # Get meals with recipe data (from scraped recipes)
        rows = conn.execute("""
            SELECT
                m.day_of_week,
                m.slot,
                r.prep_time_minutes,
                r.calories,
                r.protein_g,
                r.carbs_g,
                r.fat_g,
                r.id as recipe_id
            FROM meals m
            JOIN recipes r ON m.recipe_id = r.id
            WHERE r.source != 'test'
              AND m.day_of_week IS NOT NULL
              AND m.slot IS NOT NULL
        """).fetchall()

        for row in rows:
            weekday = day_mapping.get(row["day_of_week"])
            slot = slot_mapping.get(row["slot"])

            if weekday and slot and weekday in result and slot in result[weekday]:
                # Get ingredients for this recipe
                ing_rows = conn.execute("""
                    SELECT base_ingredient
                    FROM parsed_ingredients
                    WHERE recipe_id = ?
                      AND base_ingredient IS NOT NULL
                      AND base_ingredient != ''
                """, (row["recipe_id"],)).fetchall()

                ingredients = [r["base_ingredient"] for r in ing_rows]

                result[weekday][slot].append({
                    "prep_time": row["prep_time_minutes"],
                    "calories": row["calories"],
                    "protein": row["protein_g"],
                    "carbs": row["carbs_g"],
                    "fat": row["fat_g"],
                    "ingredients": ingredients,
                    "is_pseudo": False,
                })

    # Add pseudo-recipes (simple meal names)
    if include_pseudo:
        pseudo_meals = get_all_pseudo_recipes()

        for meal in pseudo_meals:
            weekday = day_mapping.get(meal["day_of_week"])
            slot = slot_mapping.get(meal["slot"])

            if weekday and slot and weekday in result and slot in result[weekday]:
                # Pseudo-recipes have no nutrition data, only ingredients
                if meal["ingredients"]:  # Only include if we have mapped ingredients
                    result[weekday][slot].append({
                        "prep_time": None,  # Quick meals, no formal prep time
                        "calories": None,
                        "protein": None,
                        "carbs": None,
                        "fat": None,
                        "ingredients": meal["ingredients"],
                        "is_pseudo": True,
                    })

    return result


def calculate_slot_pattern(meals: list[dict], universal: set[str]) -> WeekdaySlotPattern:
    """Calculate pattern statistics for a list of meals.

    Args:
        meals: List of meal dicts with nutrition and ingredient data
        universal: Set of universal ingredients to filter out

    Returns:
        WeekdaySlotPattern with aggregated statistics
    """
    if not meals:
        return WeekdaySlotPattern()

    pattern = WeekdaySlotPattern(meal_count=len(meals))

    # Calculate averages for numeric fields
    prep_times = [m["prep_time"] for m in meals if m["prep_time"] is not None]
    if prep_times:
        pattern.avg_prep_time = round(sum(prep_times) / len(prep_times), 1)

    calories = [m["calories"] for m in meals if m["calories"] is not None]
    if calories:
        pattern.avg_calories = round(sum(calories) / len(calories), 0)

    proteins = [m["protein"] for m in meals if m["protein"] is not None]
    if proteins:
        pattern.avg_protein = round(sum(proteins) / len(proteins), 1)

    carbs = [m["carbs"] for m in meals if m["carbs"] is not None]
    if carbs:
        pattern.avg_carbs = round(sum(carbs) / len(carbs), 1)

    fats = [m["fat"] for m in meals if m["fat"] is not None]
    if fats:
        pattern.avg_fat = round(sum(fats) / len(fats), 1)

    # Count ingredient frequencies (excluding universal)
    ing_counts: dict[str, int] = defaultdict(int)
    for meal in meals:
        for ing in meal["ingredients"]:
            if ing not in universal:
                ing_counts[ing] += 1

    # Top 10 ingredients for this slot
    sorted_ings = sorted(ing_counts.items(), key=lambda x: x[1], reverse=True)
    pattern.top_ingredients = [ing for ing, _ in sorted_ings[:10]]

    return pattern


def generate_profile(include_pseudo: bool = True) -> dict[str, Any]:
    """Generate a complete preference profile from meal history.

    Args:
        include_pseudo: Include pseudo-recipes in analysis

    Returns:
        Dict with:
        - universal_ingredients: Ingredients filtered out (>70% frequency)
        - ingredient_preferences: Top distinctive ingredients
        - weekday_patterns: Per-weekday, per-slot patterns
        - overall_nutrition: Average nutrition across all meals
        - summary: Human-readable summary statistics
    """
    # Get universal ingredients to filter
    universal = get_universal_ingredients()

    # Get distinctive ingredient preferences
    ingredient_prefs = get_distinctive_ingredient_frequencies()

    # Get weekday/slot data (now includes pseudo-recipes)
    weekday_data = get_weekday_slot_data(include_pseudo=include_pseudo)

    # Calculate patterns for each weekday and slot
    weekday_patterns = {}
    all_meals = []
    total_pseudo = 0
    total_with_recipe = 0

    for weekday, slots in weekday_data.items():
        weekday_patterns[weekday] = {}
        for slot, meals in slots.items():
            pattern = calculate_slot_pattern(meals, universal)

            # Count pseudo vs regular
            pseudo_count = sum(1 for m in meals if m.get("is_pseudo", False))
            recipe_count = len(meals) - pseudo_count
            total_pseudo += pseudo_count
            total_with_recipe += recipe_count

            weekday_patterns[weekday][slot] = {
                "meal_count": pattern.meal_count,
                "recipe_meals": recipe_count,
                "pseudo_meals": pseudo_count,
                "avg_prep_time_min": pattern.avg_prep_time,
                "avg_calories": pattern.avg_calories,
                "avg_protein_g": pattern.avg_protein,
                "avg_carbs_g": pattern.avg_carbs,
                "avg_fat_g": pattern.avg_fat,
                "top_ingredients": pattern.top_ingredients,
            }
            all_meals.extend(meals)

    # Calculate overall nutrition (only from meals with nutrition data)
    meals_with_nutrition = [m for m in all_meals if not m.get("is_pseudo", False)]
    overall_pattern = calculate_slot_pattern(meals_with_nutrition, universal)

    # Build summary
    total_meals = total_with_recipe + total_pseudo

    return {
        "metadata": {
            "last_profile_update": datetime.now().isoformat(),
            "version": PROFILE_VERSION,
            "meals_analyzed": total_meals,
        },
        "universal_ingredients": sorted(universal),
        "ingredient_preferences": ingredient_prefs[:50],  # Top 50
        "weekday_patterns": weekday_patterns,
        "overall_nutrition": {
            "meals_with_nutrition": total_with_recipe,
            "avg_calories": overall_pattern.avg_calories,
            "avg_protein_g": overall_pattern.avg_protein,
            "avg_carbs_g": overall_pattern.avg_carbs,
            "avg_fat_g": overall_pattern.avg_fat,
            "avg_prep_time_min": overall_pattern.avg_prep_time,
        },
        "summary": {
            "total_meals": total_meals,
            "meals_with_recipes": total_with_recipe,
            "pseudo_meals": total_pseudo,
            "unique_ingredients": len(ingredient_prefs),
            "filtered_universal": len(universal),
        },
    }


def save_profile(profile: dict) -> Path:
    """Save the preference profile to a JSON file.

    Args:
        profile: The generated profile dict

    Returns:
        Path to the saved file
    """
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    return PROFILE_PATH


def load_profile() -> dict | None:
    """Load a previously saved preference profile.

    Returns:
        Profile dict or None if not found
    """
    if PROFILE_PATH.exists():
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def get_profile_age() -> timedelta | None:
    """Get the age of the current profile.

    Returns:
        timedelta since last profile update, or None if no profile exists
        or no metadata available
    """
    profile = load_profile()
    if not profile:
        return None

    metadata = profile.get("metadata", {})
    last_update = metadata.get("last_profile_update")

    if not last_update:
        # Profile exists but has no metadata - treat as very old
        return timedelta(days=365)

    try:
        last_update_dt = datetime.fromisoformat(last_update)
        return datetime.now() - last_update_dt
    except (ValueError, TypeError):
        return timedelta(days=365)


def is_profile_outdated(max_age_days: int = PROFILE_UPDATE_INTERVAL_DAYS) -> bool:
    """Check if the profile needs updating.

    Args:
        max_age_days: Maximum age in days before profile is considered outdated

    Returns:
        True if profile is outdated or doesn't exist, False otherwise
    """
    age = get_profile_age()

    if age is None:
        # No profile exists
        return True

    return age > timedelta(days=max_age_days)


def ensure_profile_current(
    force: bool = False,
    max_age_days: int = PROFILE_UPDATE_INTERVAL_DAYS,
) -> tuple[dict, bool]:
    """Ensure the preference profile is current, regenerating if needed.

    This is the main entry point for agents that need the profile.
    It checks if the profile exists and is recent enough, regenerating
    it if necessary.

    Args:
        force: Force regeneration even if profile is current
        max_age_days: Maximum age in days before triggering update

    Returns:
        Tuple of (profile_dict, was_updated)
        - profile_dict: The current preference profile
        - was_updated: True if the profile was regenerated
    """
    if force:
        print(f"Forcing profile regeneration...")
        profile = generate_profile()
        save_profile(profile)
        return profile, True

    if is_profile_outdated(max_age_days):
        age = get_profile_age()
        if age is None:
            print("No profile found. Generating new profile...")
        else:
            print(f"Profile is {age.days} days old. Regenerating...")

        profile = generate_profile()
        save_profile(profile)
        return profile, True

    # Profile is current
    profile = load_profile()
    if profile is None:
        # Should not happen given is_profile_outdated check, but be safe
        profile = generate_profile()
        save_profile(profile)
        return profile, True

    return profile, False


def print_profile_summary(profile: dict) -> None:
    """Print a human-readable summary of the preference profile."""
    print("=" * 60)
    print("VORLIEBEN-PROFIL")
    print("=" * 60)

    # Summary stats
    summary = profile["summary"]
    print(f"\nAnalysierte Mahlzeiten: {summary['total_meals']}")
    print(f"  - Mit Rezept-Link:    {summary['meals_with_recipes']}")
    print(f"  - Pseudo-Rezepte:     {summary['pseudo_meals']}")
    print(f"Unterscheidende Zutaten: {summary['unique_ingredients']}")
    print(f"Gefilterte universelle Zutaten: {summary['filtered_universal']}")

    # Universal ingredients
    print(f"\nUniverselle Zutaten (>70%): {', '.join(profile['universal_ingredients'])}")

    # Overall nutrition
    nutr = profile["overall_nutrition"]
    print(f"\nDurchschnittliche Naehrwerte (basierend auf {nutr['meals_with_nutrition']} Rezepten):")
    print(f"  Kalorien: {nutr['avg_calories']:.0f} kcal")
    print(f"  Protein:  {nutr['avg_protein_g']:.1f} g")
    print(f"  Kohlenhydrate: {nutr['avg_carbs_g']:.1f} g")
    print(f"  Fett: {nutr['avg_fat_g']:.1f} g")
    print(f"  Zubereitungszeit: {nutr['avg_prep_time_min']:.0f} min")

    # Top ingredients
    print("\nTop 15 Zutaten-Vorlieben:")
    for i, ing in enumerate(profile["ingredient_preferences"][:15], 1):
        print(f"  {i:2}. {ing['base_ingredient']:25} ({ing['recipe_count']} Rezepte)")

    # Weekday patterns
    print("\nMuster nach Wochentag:")
    print("-" * 60)

    weekday_order = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                     "Freitag", "Samstag", "Sonntag"]

    for weekday in weekday_order:
        patterns = profile["weekday_patterns"].get(weekday, {})
        lunch = patterns.get("Mittagessen", {})
        dinner = patterns.get("Abendessen", {})

        print(f"\n{weekday}:")

        if lunch.get("meal_count", 0) > 0:
            pseudo_info = f", {lunch.get('pseudo_meals', 0)} Pseudo" if lunch.get('pseudo_meals') else ""
            print(f"  Mittagessen ({lunch['meal_count']} Mahlzeiten{pseudo_info}):")
            if lunch.get("avg_prep_time_min"):
                print(f"    Zeit: {lunch['avg_prep_time_min']:.0f} min")
            if lunch.get("avg_calories"):
                print(f"    Kalorien: {lunch['avg_calories']:.0f} kcal")
            if lunch.get("top_ingredients"):
                print(f"    Top Zutaten: {', '.join(lunch['top_ingredients'][:5])}")

        if dinner.get("meal_count", 0) > 0:
            pseudo_info = f", {dinner.get('pseudo_meals', 0)} Pseudo" if dinner.get('pseudo_meals') else ""
            print(f"  Abendessen ({dinner['meal_count']} Mahlzeiten{pseudo_info}):")
            if dinner.get("avg_prep_time_min"):
                print(f"    Zeit: {dinner['avg_prep_time_min']:.0f} min")
            if dinner.get("avg_calories"):
                print(f"    Kalorien: {dinner['avg_calories']:.0f} kcal")
            if dinner.get("top_ingredients"):
                print(f"    Top Zutaten: {', '.join(dinner['top_ingredients'][:5])}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate or update preference profile")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration even if profile is current",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check profile age, don't regenerate",
    )
    args = parser.parse_args()

    if args.check:
        age = get_profile_age()
        if age is None:
            print("Kein Profil vorhanden.")
        else:
            print(f"Profil-Alter: {age.days} Tage, {age.seconds // 3600} Stunden")
            if is_profile_outdated():
                print(f"Status: VERALTET (>{PROFILE_UPDATE_INTERVAL_DAYS} Tage)")
            else:
                print(f"Status: AKTUELL (<={PROFILE_UPDATE_INTERVAL_DAYS} Tage)")
    else:
        profile, was_updated = ensure_profile_current(force=args.force)
        print_profile_summary(profile)

        if was_updated:
            print(f"\nProfil neu generiert und gespeichert: {PROFILE_PATH}")
        else:
            print(f"\nProfil ist aktuell (< {PROFILE_UPDATE_INTERVAL_DAYS} Tage alt): {PROFILE_PATH}")

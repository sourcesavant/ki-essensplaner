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
from pathlib import Path
from typing import Any

from src.core.config import DATA_DIR
from src.core.database import get_connection, get_all_recipes

# Output path for the generated profile
PROFILE_PATH = DATA_DIR / "local" / "preference_profile.json"


# Threshold for filtering universal ingredients (appear in >70% of recipes)
UNIVERSAL_INGREDIENT_THRESHOLD = 0.70


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


def get_weekday_slot_data() -> dict[str, dict[str, list[dict]]]:
    """Get meal data grouped by weekday and slot.

    Returns:
        Nested dict: weekday -> slot -> list of meal data
        Each meal has: prep_time, calories, protein, carbs, fat, ingredients
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
        # Get meals with recipe data
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


def generate_profile() -> dict[str, Any]:
    """Generate a complete preference profile from meal history.

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

    # Get weekday/slot data
    weekday_data = get_weekday_slot_data()

    # Calculate patterns for each weekday and slot
    weekday_patterns = {}
    all_meals = []

    for weekday, slots in weekday_data.items():
        weekday_patterns[weekday] = {}
        for slot, meals in slots.items():
            pattern = calculate_slot_pattern(meals, universal)
            weekday_patterns[weekday][slot] = {
                "meal_count": pattern.meal_count,
                "avg_prep_time_min": pattern.avg_prep_time,
                "avg_calories": pattern.avg_calories,
                "avg_protein_g": pattern.avg_protein,
                "avg_carbs_g": pattern.avg_carbs,
                "avg_fat_g": pattern.avg_fat,
                "top_ingredients": pattern.top_ingredients,
            }
            all_meals.extend(meals)

    # Calculate overall nutrition
    overall_pattern = calculate_slot_pattern(all_meals, universal)

    # Build summary
    total_meals = sum(
        weekday_patterns[d][s]["meal_count"]
        for d in weekday_patterns
        for s in weekday_patterns[d]
    )

    return {
        "universal_ingredients": sorted(universal),
        "ingredient_preferences": ingredient_prefs[:50],  # Top 50
        "weekday_patterns": weekday_patterns,
        "overall_nutrition": {
            "total_meals_analyzed": total_meals,
            "avg_calories": overall_pattern.avg_calories,
            "avg_protein_g": overall_pattern.avg_protein,
            "avg_carbs_g": overall_pattern.avg_carbs,
            "avg_fat_g": overall_pattern.avg_fat,
            "avg_prep_time_min": overall_pattern.avg_prep_time,
        },
        "summary": {
            "total_meals": total_meals,
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


def print_profile_summary(profile: dict) -> None:
    """Print a human-readable summary of the preference profile."""
    print("=" * 60)
    print("VORLIEBEN-PROFIL")
    print("=" * 60)

    # Summary stats
    print(f"\nAnalysierte Mahlzeiten: {profile['summary']['total_meals']}")
    print(f"Unterscheidende Zutaten: {profile['summary']['unique_ingredients']}")
    print(f"Gefilterte universelle Zutaten: {profile['summary']['filtered_universal']}")

    # Universal ingredients
    print(f"\nUniverselle Zutaten (>70%): {', '.join(profile['universal_ingredients'])}")

    # Overall nutrition
    nutr = profile["overall_nutrition"]
    print(f"\nDurchschnittliche Naehrwerte:")
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
            print(f"  Mittagessen ({lunch['meal_count']} Mahlzeiten):")
            if lunch.get("avg_prep_time_min"):
                print(f"    Zeit: {lunch['avg_prep_time_min']:.0f} min")
            if lunch.get("avg_calories"):
                print(f"    Kalorien: {lunch['avg_calories']:.0f} kcal")
            if lunch.get("top_ingredients"):
                print(f"    Top Zutaten: {', '.join(lunch['top_ingredients'][:5])}")

        if dinner.get("meal_count", 0) > 0:
            print(f"  Abendessen ({dinner['meal_count']} Mahlzeiten):")
            if dinner.get("avg_prep_time_min"):
                print(f"    Zeit: {dinner['avg_prep_time_min']:.0f} min")
            if dinner.get("avg_calories"):
                print(f"    Kalorien: {dinner['avg_calories']:.0f} kcal")
            if dinner.get("top_ingredients"):
                print(f"    Top Zutaten: {', '.join(dinner['top_ingredients'][:5])}")


if __name__ == "__main__":
    profile = generate_profile()
    print_profile_summary(profile)

    # Save profile for later use
    path = save_profile(profile)
    print(f"\nProfil gespeichert: {path}")

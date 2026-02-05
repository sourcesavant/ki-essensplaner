"""Map pseudo-recipes to typical ingredients.

Pseudo-recipes are simple meal names in the OneNote meal plans that don't
have formal recipe URLs (e.g., "Falafel", "Wraps", "Spaghetti Bolognese").
These represent quick, everyday meals that follow familiar patterns.

This module maps these names to their typical ingredient components,
enabling inclusion in preference profile analysis.

Example usage:
    >>> from src.profile.pseudo_recipes import get_pseudo_recipe_ingredients
    >>> ingredients = get_pseudo_recipe_ingredients("Wrap mit Falafel")
    >>> print(ingredients)
    ['tortilla', 'falafel', 'gemüse', 'hummus']
"""

import html
import re
from src.core.database import get_connection


# Mapping of pseudo-recipe keywords to typical ingredients
# Format: keyword -> list of base_ingredients (matching the categorization)
INGREDIENT_MAPPING = {
    # Falafel variations
    "falafel": ["falafel", "gemüse", "brot", "hummus", "salat"],
    "falaffel": ["falafel", "gemüse", "brot", "hummus", "salat"],

    # Wrap variations
    "wrap": ["tortilla", "gemüse", "käse"],
    "wraps": ["tortilla", "gemüse", "käse"],

    # Pasta dishes
    "spaghetti bolognese": ["nudel", "hackfleisch", "tomate", "zwiebel"],
    "bolognese": ["nudel", "hackfleisch", "tomate", "zwiebel"],
    "nudeln mit pesto": ["nudel", "pesto", "parmesan"],
    "spaghetti mit pesto": ["nudel", "pesto", "parmesan"],
    "pesto": ["nudel", "pesto", "parmesan"],
    "nudeln mit spinat": ["nudel", "spinat", "parmesan"],
    "spaghetti mit spinat": ["nudel", "spinat", "parmesan"],
    "tortellini": ["tortellini", "sahne", "speck"],
    "carbonara": ["nudel", "speck", "ei", "parmesan"],

    # Egg dishes
    "omelette": ["ei", "gemüse", "käse"],
    "omelett": ["ei", "gemüse", "käse"],
    "rührei": ["ei", "butter"],
    "spiegelei": ["ei", "butter"],

    # Potato dishes
    "kartoffeln mit quark": ["kartoffel", "quark", "kräuter"],
    "pellkartoffeln": ["kartoffel", "quark", "kräuter"],
    "ofenkartoffeln": ["kartoffel", "käse", "sauerrahm"],
    "bratkartoffeln": ["kartoffel", "zwiebel", "speck"],
    "kartoffelpüree": ["kartoffel", "butter", "milch"],
    "kräuterquark": ["quark", "kräuter"],

    # Quick meals
    "brot": ["brot", "aufschnitt"],
    "sandwich": ["brot", "käse", "aufschnitt", "gemüse"],
    "sandwiches": ["brot", "käse", "aufschnitt", "gemüse"],
    "toast": ["brot", "käse"],

    # Fish
    "lachs": ["lachs", "gemüse"],
    "fischstäbchen": ["fisch", "kartoffel"],

    # Meat
    "hähnchen": ["hähnchen", "gemüse"],
    "schnitzel": ["schnitzel", "kartoffel"],
    "würstchen": ["wurst", "brot"],

    # Vegetarian
    "halloumi": ["halloumi", "gemüse"],
    "kichererbsen": ["kichererbse", "gemüse"],

    # Other
    "reste": [],  # Leftovers - no specific ingredients
    "tiefkühlessen": [],  # Frozen food - no specific ingredients
    "nix": [],  # Not eating
    "bäcker": ["brot"],  # Bakery
    "pizza": ["pizzateig", "tomate", "käse"],
    "flammkuchen": ["flammkuchenteig", "speck", "zwiebel", "sauerrahm"],
    "salat": ["salat", "gemüse", "dressing"],
    "suppe": ["gemüsebrühe", "gemüse"],
    "eintopf": ["gemüsebrühe", "gemüse", "kartoffel"],
    "curry": ["reis", "kokosmilch", "gemüse", "currypaste"],
    "burger": ["hackfleisch", "brötchen", "salat", "tomate"],
    "kaiserschmarrn": ["ei", "mehl", "zucker", "milch"],
    "müsli": ["haferflocken", "milch", "obst"],
    "porridge": ["haferflocken", "milch"],
    "brokkoli": ["brokkoli"],

    # Additions (detected in compound names)
    "avocado": ["avocado"],
    "gurke": ["gurke"],
    "tomate": ["tomate"],
    "spinat": ["spinat"],
    "gemüse": ["gemüse"],
}


def normalize_pseudo_title(title: str) -> str:
    """Normalize a pseudo-recipe title for matching.

    - Decode HTML entities
    - Lowercase
    - Remove punctuation
    """
    if not title:
        return ""

    # Decode HTML entities (&#228; -> ä)
    title = html.unescape(title)

    # Lowercase
    title = title.lower()

    # Normalize whitespace
    title = re.sub(r'\s+', ' ', title).strip()

    return title


def get_pseudo_recipe_ingredients(title: str) -> list[str]:
    """Extract typical ingredients from a pseudo-recipe title.

    Args:
        title: The recipe_title from meals table

    Returns:
        List of base_ingredient names
    """
    normalized = normalize_pseudo_title(title)

    if not normalized:
        return []

    ingredients = set()

    # Check for exact matches first (longer phrases)
    for phrase in sorted(INGREDIENT_MAPPING.keys(), key=len, reverse=True):
        if phrase in normalized:
            ingredients.update(INGREDIENT_MAPPING[phrase])

    # If no matches found, try word-by-word
    if not ingredients:
        words = normalized.split()
        for word in words:
            # Clean word
            word = re.sub(r'[,;+]', '', word)
            if word in INGREDIENT_MAPPING:
                ingredients.update(INGREDIENT_MAPPING[word])

    return sorted(ingredients)


def get_all_pseudo_recipes() -> list[dict]:
    """Get all pseudo-recipe meals with their mapped ingredients.

    Returns:
        List of dicts with: meal_id, day_of_week, slot, title, ingredients
    """
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, day_of_week, slot, recipe_title
            FROM meals
            WHERE recipe_id IS NULL
              AND recipe_title NOT LIKE 'http%'
              AND recipe_title IS NOT NULL
              AND recipe_title != ''
        """).fetchall()

    results = []
    for row in rows:
        title = row["recipe_title"]
        ingredients = get_pseudo_recipe_ingredients(title)

        results.append({
            "meal_id": row["id"],
            "day_of_week": row["day_of_week"],
            "slot": row["slot"],
            "title": html.unescape(title),
            "ingredients": ingredients,
        })

    return results


def get_pseudo_recipe_stats() -> dict:
    """Get statistics about pseudo-recipe mapping coverage.

    Returns:
        Dict with total, mapped, unmapped counts and examples
    """
    pseudo_meals = get_all_pseudo_recipes()

    mapped = [m for m in pseudo_meals if m["ingredients"]]
    unmapped = [m for m in pseudo_meals if not m["ingredients"]]

    # Group unmapped by title
    unmapped_titles = {}
    for m in unmapped:
        title = m["title"]
        unmapped_titles[title] = unmapped_titles.get(title, 0) + 1

    return {
        "total": len(pseudo_meals),
        "mapped": len(mapped),
        "unmapped": len(unmapped),
        "coverage_pct": 100 * len(mapped) / len(pseudo_meals) if pseudo_meals else 0,
        "unmapped_titles": sorted(unmapped_titles.items(), key=lambda x: -x[1])[:20],
    }


if __name__ == "__main__":
    # Test mapping
    test_cases = [
        "Falafel",
        "Falafel, Reste",
        "Wrap mit Falafel",
        "Wrap mit Lachs",
        "Spaghetti Bolognese",
        "Nudeln mit Pesto",
        "Omelette, Brot oder Nudeln",
        "Kartoffeln mit Kr&#228;uterquark",
        "Wrap mit Kichererbsen, Halloumi, + Gemüsereste",
        "Reste",
    ]

    print("Mapping-Tests:")
    print("=" * 60)
    for title in test_cases:
        ingredients = get_pseudo_recipe_ingredients(title)
        print(f"{title}")
        print(f"  -> {ingredients}")
        print()

    # Show stats
    print("\nStatistiken:")
    print("=" * 60)
    stats = get_pseudo_recipe_stats()
    print(f"Gesamt Pseudo-Rezepte: {stats['total']}")
    print(f"Mit Zutaten gemappt:   {stats['mapped']} ({stats['coverage_pct']:.0f}%)")
    print(f"Ohne Mapping:          {stats['unmapped']}")

    if stats["unmapped_titles"]:
        print("\nNicht gemappte Titel:")
        for title, count in stats["unmapped_titles"][:10]:
            print(f"  {count:3}x  {title}")
